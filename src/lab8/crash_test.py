"""20 deterministic crash points. A safe point leaves one refund and one committed audit.

python -m lab8.crash_test --count 20 --out reports/crash.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lab8.app import prepare_store
from lab8.console import utf8_stdio
from lab8.db import connect
from lab8.durability import InjectedCrash, committed_audit_count, get_refund, issue_refund

POINTS = (
    ["before_effect"] * 5
    + ["after_effect_before_checkpoint"] * 7
    + ["after_checkpoint"] * 5
)


def _fresh(tmp: Path, name: str) -> str:
    store = tmp / name
    prepare_store(store)
    return str(store)


def _assert_single(conn, claim_id: str, amount: int) -> None:
    effect = get_refund(conn, claim_id)
    if effect is None or int(effect["amount_vnd"]) != amount:
        raise AssertionError(f"ledger {effect} != {amount}")
    if committed_audit_count(conn, claim_id) != 1:
        raise AssertionError("expected one refund_committed audit")


def run_suite(tmp: Path) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for index, point in enumerate(POINTS, start=1):
        store = _fresh(tmp, f"crash-{index}.sqlite")
        conn = connect(store)
        crashed = False
        try:
            issue_refund(conn, "C-001", 35000, crash_at=point)
        except InjectedCrash:
            crashed = True
        if not crashed:
            conn.close()
            scenarios.append(_fail(index, point, "crash did not fire"))
            continue
        if point == "before_effect" and get_refund(conn, "C-001") is not None:
            conn.close()
            scenarios.append(_fail(index, point, "effect written before crash point"))
            continue
        try:
            issue_refund(conn, "C-001", 35000, crash_at=None)
            _assert_single(conn, "C-001", 35000)
            checkpoint = conn.execute(
                "SELECT 1 FROM checkpoints WHERE claim_id = ? AND step = 'issue_refund'",
                ("C-001",),
            ).fetchone()
            ok = checkpoint is not None
            reason = "ok" if ok else "checkpoint missing after resume"
        except Exception as exc:  # noqa: BLE001 — scenario report, not a crash of the suite
            ok = False
            reason = str(exc)
        conn.close()
        scenarios.append(_row(index, point, ok, reason))

    scenarios.append(_conflict(tmp))
    scenarios.append(_missing_approval(tmp))
    scenarios.append(_swarm_crash(tmp))
    passed = sum(1 for row in scenarios if row["passed"])
    return {
        "count": len(scenarios),
        "passed": passed,
        "crash_safety": f"{passed}/{len(scenarios)}",
        "scenarios": scenarios,
    }


def _conflict(tmp: Path) -> dict[str, Any]:
    store = _fresh(tmp, "conflict.sqlite")
    conn = connect(store)
    first = issue_refund(conn, "C-001", 35000)
    second = issue_refund(conn, "C-001", 10000)
    effect = get_refund(conn, "C-001")
    ok = (
        first["ok"]
        and second["conflict"]
        and effect is not None
        and int(effect["amount_vnd"]) == 35000
        and committed_audit_count(conn, "C-001") == 1
    )
    conn.close()
    return _row(18, "amount_conflict_on_retry", ok, "ok" if ok else "conflict handling failed")


def _missing_approval(tmp: Path) -> dict[str, Any]:
    store = _fresh(tmp, "no-approval.sqlite")
    conn = connect(store)
    conn.execute(
        """
        INSERT INTO claims (claim_id, principal_id, order_id, ticket, parent_secret, raw_headers_json, approval_id)
        VALUES ('C-NOAPPROVAL', 'P-100', 'O-107', 'retry me', 'CANARY_SECRET_PARENT_NOAPPROVAL', '{}', NULL)
        """
    )
    conn.commit()
    first = issue_refund(conn, "C-NOAPPROVAL", 35000)
    second = issue_refund(conn, "C-NOAPPROVAL", 35000)
    ok = (
        not first["ok"]
        and not second["ok"]
        and get_refund(conn, "C-NOAPPROVAL") is None
        and committed_audit_count(conn, "C-NOAPPROVAL") == 0
    )
    conn.close()
    return _row(19, "retry_without_approval", ok, "ok" if ok else "approval bypass on retry")


def _swarm_crash(tmp: Path) -> dict[str, Any]:
    from lab8.shapes.swarm_reference import run_claim

    store = _fresh(tmp, "swarm-crash.sqlite")
    try:
        run_claim("C-001", seed=11, store_path=store, crash_at="after_effect_before_checkpoint")
        return _row(20, "swarm_after_effect_before_checkpoint", False, "crash did not fire")
    except InjectedCrash:
        pass
    result = run_claim("C-001", seed=11, store_path=store, crash_at=None)
    conn = connect(store)
    try:
        effect = get_refund(conn, "C-001")
        ok = (
            result.status == "resolved"
            and effect is not None
            and int(effect["amount_vnd"]) == 35000
            and committed_audit_count(conn, "C-001") == 1
        )
    finally:
        conn.close()
    return _row(20, "swarm_after_effect_before_checkpoint", ok, "ok" if ok else "swarm resume duplicated")


def _row(index: int, point: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"id": f"CR-{index:02d}", "point": point, "passed": passed, "reason": reason}


def _fail(index: int, point: str, reason: str) -> dict[str, Any]:
    return _row(index, point, False, reason)


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Run the 20-point crash lab")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.count != 20:
        raise SystemExit("this lab defines exactly 20 crash points")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="lab8-crash-", ignore_cleanup_errors=True) as tmp:
        report = run_suite(Path(tmp))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"crash_safety {report['crash_safety']}")
    return 0 if report["passed"] == 20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
