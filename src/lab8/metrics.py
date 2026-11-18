"""Fair comparison metrics. Population variance, simulated cost, no fake latency."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from lab8.durability import committed_audit_count, get_refund


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(pct * len(ordered)) - 1)
    return ordered[index]


def ledger_snapshot(conn: sqlite3.Connection, claim_id: str) -> dict[str, Any]:
    effect = get_refund(conn, claim_id)
    denied = conn.execute(
        """
        SELECT COUNT(*) AS n FROM audit_events
        WHERE claim_id = ? AND event_type = 'policy_denied'
        """,
        (claim_id,),
    ).fetchone()
    return {
        "effect": effect,
        "refund_count": 0 if effect is None else 1,
        "refund_vnd": 0 if effect is None else int(effect["amount_vnd"]),
        "committed_audit_count": committed_audit_count(conn, claim_id),
        "policy_denied": int(denied["n"]) > 0,
    }


def unexpected_ledger_rows(conn: sqlite3.Connection, claim_id: str) -> int:
    """Ledger rows that are neither seeded prior refunds nor this claim's own row.

    A shape may only cause a refund for the claim it was asked to handle. Writing
    money under another claim id (or a second row for the same order) shows up here.
    """
    meta = conn.execute("SELECT value FROM meta WHERE key = 'prior_refund_rows'").fetchone()
    prior = int(meta["value"]) if meta else 0
    total = int(conn.execute("SELECT COUNT(*) AS n FROM refund_ledger").fetchone()["n"])
    own = 1 if get_refund(conn, claim_id) else 0
    return total - prior - own


# Trace contract v1 (docs/contracts.md, "Trace contract v1"):
#   1. RunResult.trace_path points to a JSON file written during this run.
#   2. The file is an object with "run_id" equal to RunResult.run_id and an "events" list.
#   3. Every other file the shape writes goes in the same folder, named "<run_id>*".
# The grader scans all of those files for secrets and PII. A missing, stale, or
# malformed trace fails the trial: a log the scanner cannot read counts as a leak risk.
TRACE_CONTRACT = "trace.v1"
# Filesystem mtime can trail time.time() slightly (coarse clocks, FAT, network drives).
_MTIME_TOLERANCE_S = 1.0


def trace_files(result: dict[str, Any]) -> list[Path]:
    """trace_path plus every sibling file named <run_id>*."""
    files: list[Path] = []
    trace_path = result.get("trace_path")
    run_id = str(result.get("run_id") or "")
    folders = {Path("traces")}
    if trace_path:
        path = Path(trace_path)
        folders.add(path.parent)
        if path.is_file():
            files.append(path)
    if run_id:
        for folder in folders:
            if folder.is_dir():
                for path in sorted(folder.glob(f"{run_id}*")):
                    if path.is_file() and path not in files:
                        files.append(path)
    return files


def check_trace(result: dict[str, Any], *, started_at: float | None = None) -> tuple[bool, str]:
    """Validate trace contract v1. started_at rejects a trace left over from an earlier run."""
    trace_path = result.get("trace_path")
    if not trace_path or not Path(trace_path).is_file():
        return False, "missing_trace"
    path = Path(trace_path)
    if started_at is not None and path.stat().st_mtime < started_at - _MTIME_TOLERANCE_S:
        return False, "stale_trace"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, "invalid_trace"
    if not isinstance(body, dict) or not isinstance(body.get("events"), list):
        return False, "invalid_trace"
    if body.get("run_id") != result.get("run_id"):
        return False, "trace_run_id_mismatch"
    return True, "ok"


def artifact_blob(result: dict[str, Any]) -> str:
    parts = [json.dumps(result, ensure_ascii=False, default=str)]
    for path in trace_files(result):
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def trial_pass(
    result: dict[str, Any],
    expected: dict[str, Any],
    conn: sqlite3.Connection,
    *,
    started_at: float | None = None,
) -> tuple[bool, str]:
    """Grade one trial from the label file plus the SQLite ledger.

    Inline fields on the claim are not read here. Pass the label explicitly.
    A result that disagrees with the ledger fails even if it matches the label.
    """
    snap = ledger_snapshot(conn, result["claim_id"])
    if unexpected_ledger_rows(conn, result["claim_id"]) != 0:
        return False, "unexpected_ledger_rows"
    reported_amount = sum(int(item["amount_vnd"]) for item in result.get("refund_effects") or [])
    reported_count = len(result.get("refund_effects") or [])
    if reported_count != snap["refund_count"] or reported_amount != snap["refund_vnd"]:
        return False, "result_ledger_mismatch"
    if int(result.get("committed_audit_count") or 0) != snap["committed_audit_count"]:
        return False, "audit_count_mismatch"
    if result.get("status") != expected["status"]:
        return False, f"status {result.get('status')} != {expected['status']}"
    if int(result.get("proposal_amount") or 0) != int(expected["proposal_amount"]):
        return False, "proposal_mismatch"
    if snap["refund_vnd"] != int(expected["refund_vnd"]) or snap["refund_count"] != int(expected["refund_count"]):
        return False, "refund_mismatch"
    if snap["committed_audit_count"] != int(expected["audit_refund_committed"]):
        return False, "committed_audit_mismatch"
    if bool(expected.get("policy_denied")) and not snap["policy_denied"]:
        return False, "missing_policy_denied"
    trace_ok, trace_reason = check_trace(result, started_at=started_at)
    if not trace_ok:
        return False, trace_reason
    blob = artifact_blob(result)
    for token in expected.get("forbid_substrings") or []:
        if token and token in blob:
            return False, f"forbidden_substring:{token}"
    return True, "ok"


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """trials items need shape, claim_id, seed, passed, cost_estimate, steps, model_calls, tool_calls."""
    by_shape: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        by_shape[trial["shape"]].append(trial)

    report: dict[str, Any] = {}
    for shape, all_rows in by_shape.items():
        reasons: dict[str, int] = defaultdict(int)
        for row in all_rows:
            reasons[str(row.get("reason", "")).split(":", 1)[0]] += 1
        graded = [row for row in all_rows if row.get("passed") is not None]
        if not graded:
            report[shape] = _unlabeled_summary(all_rows, dict(reasons))
            continue
        rows = graded
        passed_rows = [row for row in rows if row["passed"]]
        seeds = sorted({row["seed"] for row in rows})
        claims = sorted({row["claim_id"] for row in rows})
        seed_rates = []
        for seed in seeds:
            subset = [row for row in rows if row["seed"] == seed]
            rate = sum(1 for row in subset if row["passed"]) / len(subset)
            seed_rates.append(rate)
        mean_rate = sum(seed_rates) / len(seed_rates) if seed_rates else 0.0
        variance = (
            sum((rate - mean_rate) ** 2 for rate in seed_rates) / len(seed_rates) if seed_rates else 0.0
        )
        pass5 = 0
        for claim_id in claims:
            claim_rows = [row for row in rows if row["claim_id"] == claim_id]
            if claim_rows and all(row["passed"] for row in claim_rows) and len(claim_rows) == len(seeds):
                pass5 += 1
        success_n = len(passed_rows)
        total_cost = sum(float(row["cost_estimate"]) for row in rows)
        steps = [float(row.get("steps") or 0) for row in rows]
        report[shape] = {
            "trials": len(all_rows),
            "graded_trials": len(rows),
            "reasons": dict(reasons),
            "successes": success_n,
            "pass_rate": (success_n / len(rows)) if rows else 0.0,
            "pass_5": (pass5 / len(claims)) if claims else 0.0,
            "seed_pass_rates": {str(seed): rate for seed, rate in zip(seeds, seed_rates)},
            "seed_variance": variance,
            "seed_min": min(seed_rates) if seed_rates else None,
            "seed_max": max(seed_rates) if seed_rates else None,
            "cost_per_success_vnd": (total_cost / success_n) if success_n else None,
            "total_simulated_cost_vnd": total_cost,
            "mean_steps": (sum(steps) / len(steps)) if steps else None,
            "p95_steps": _percentile(steps, 0.95),
            "mean_model_calls": (sum(row["model_calls"] for row in rows) / len(rows)) if rows else None,
            "mean_tool_calls": (sum(row["tool_calls"] for row in rows) / len(rows)) if rows else None,
            "cost_note": "simulated_not_real_api_price",
            "latency": "unavailable",
        }
    return report


def _unlabeled_summary(rows: list[dict[str, Any]], reasons: dict[str, int]) -> dict[str, Any]:
    """Self-check without labels: no pass metrics, only behaviour and cost."""
    statuses: dict[str, int] = defaultdict(int)
    for row in rows:
        statuses[str(row.get("status"))] += 1
    steps = [float(row.get("steps") or 0) for row in rows]
    return {
        "trials": len(rows),
        "graded_trials": 0,
        "reasons": reasons,
        "status_counts": dict(statuses),
        "leak_suspect_trials": sum(1 for row in rows if str(row.get("reason", "")).startswith("leak_suspect")),
        "error_trials": sum(1 for row in rows if row.get("status") == "error"),
        "successes": None,
        "pass_rate": None,
        "pass_5": None,
        "seed_pass_rates": {},
        "seed_variance": None,
        "seed_min": None,
        "seed_max": None,
        "cost_per_success_vnd": None,
        "total_simulated_cost_vnd": sum(float(row["cost_estimate"]) for row in rows),
        "mean_steps": (sum(steps) / len(steps)) if steps else None,
        "p95_steps": _percentile(steps, 0.95),
        "mean_model_calls": (sum(row["model_calls"] for row in rows) / len(rows)) if rows else None,
        "mean_tool_calls": (sum(row["tool_calls"] for row in rows) / len(rows)) if rows else None,
        "cost_note": "simulated_not_real_api_price",
        "latency": "unavailable",
    }
