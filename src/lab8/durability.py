"""Ledger + checkpoint.

A checkpoint does not make a side effect exactly-once. The refund row and the
refund_committed audit share one SQLite transaction. Retry after a crash is a
no-op when the claim already has a committed effect. A different amount on
retry is a conflict: the committed amount stays.

Refunds are also capped per order: other claims on the same order are
subtracted (see lab8.policy). The order total is re-read inside the write
transaction, so two claims for one order cannot both pay in full.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from lab8.policy import authorize, order_refunded_vnd


class InjectedCrash(Exception):
    """Deterministic crash used by the fault lab. Not a random failure."""


def idempotency_key(claim_id: str) -> str:
    return f"refund:{claim_id}"


def audit_key_committed(claim_id: str) -> str:
    return f"refund_committed:{claim_id}"


def get_refund(conn: sqlite3.Connection, claim_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT claim_id, idempotency_key, amount_vnd, status FROM refund_ledger WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    return dict(row) if row else None


def committed_audit_count(conn: sqlite3.Connection, claim_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM audit_events
        WHERE claim_id = ? AND event_type = 'refund_committed'
        """,
        (claim_id,),
    ).fetchone()
    return int(row["n"])


def record_policy_denied(conn: sqlite3.Connection, claim_id: str, reason: str) -> None:
    key = f"policy_denied:{claim_id}:{reason}"
    details = {"reason": reason}
    conn.execute(
        """
        INSERT OR IGNORE INTO audit_events (audit_key, claim_id, event_type, details_json)
        VALUES (?, ?, 'policy_denied', ?)
        """,
        (key, claim_id, json.dumps(details, ensure_ascii=False)),
    )
    conn.commit()


def issue_refund(
    conn: sqlite3.Connection,
    claim_id: str,
    proposed_vnd: int,
    *,
    crash_at: str | None = None,
    _retry: bool = True,
) -> dict[str, Any]:
    """Commit at most one refund for this claim. Model input cannot skip the gate.

    proposed_vnd is the full entitlement quote for the order (compute_compensation).
    The host subtracts what other claims already received for that order.
    """
    claim = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if claim is None:
        return {"ok": False, "reason": "unknown_claim", "effect": None, "conflict": False}
    if not claim["order_id"]:
        record_policy_denied(conn, claim_id, "missing_order")
        return {"ok": False, "reason": "missing_order", "effect": None, "conflict": False}

    order = conn.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (claim["order_id"],),
    ).fetchone()
    if order is None or order["principal_id"] != claim["principal_id"]:
        record_policy_denied(conn, claim_id, "outside_principal_scope")
        return {"ok": False, "reason": "outside_principal_scope", "effect": None, "conflict": False}

    already = order_refunded_vnd(conn, claim["order_id"], exclude_claim_id=claim_id)
    decision = authorize(
        conn,
        claim_id,
        proposed_vnd,
        paid_vnd=int(order["paid_vnd"]),
        already_refunded_vnd=already,
    )
    if not decision.ok:
        record_policy_denied(conn, claim_id, decision.reason)
        return {"ok": False, "reason": decision.reason, "effect": None, "conflict": False}

    amount = decision.amount_vnd
    if crash_at == "before_effect":
        raise InjectedCrash("before_effect")

    existing = get_refund(conn, claim_id)
    if existing is not None:
        if int(existing["amount_vnd"]) != amount:
            _audit_conflict(conn, claim_id, int(existing["amount_vnd"]), amount)
            return {"ok": False, "reason": "amount_conflict", "effect": existing, "conflict": True}
        _checkpoint(conn, claim_id, existing)
        return {"ok": True, "reason": "idempotent_replay", "effect": existing, "conflict": False}

    key = idempotency_key(claim_id)
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Another claim on the same order may have committed since we read the total.
        if order_refunded_vnd(conn, claim["order_id"], exclude_claim_id=claim_id) != already:
            conn.rollback()
            if _retry:
                return issue_refund(conn, claim_id, proposed_vnd, crash_at=crash_at, _retry=False)
            record_policy_denied(conn, claim_id, "order_total_changed")
            return {"ok": False, "reason": "order_total_changed", "effect": None, "conflict": False}
        conn.execute(
            """
            INSERT INTO refund_ledger (claim_id, order_id, idempotency_key, amount_vnd, status)
            VALUES (?, ?, ?, ?, 'committed')
            """,
            (claim_id, claim["order_id"], key, amount),
        )
        conn.execute(
            """
            INSERT INTO audit_events (audit_key, claim_id, event_type, details_json)
            VALUES (?, ?, 'refund_committed', ?)
            """,
            (
                audit_key_committed(claim_id),
                claim_id,
                json.dumps({"amount_vnd": amount, "approval_id": decision.approval_id}, ensure_ascii=False),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = get_refund(conn, claim_id)
        if existing is None:
            raise
        if int(existing["amount_vnd"]) != amount:
            _audit_conflict(conn, claim_id, int(existing["amount_vnd"]), amount)
            return {"ok": False, "reason": "amount_conflict", "effect": existing, "conflict": True}
        _checkpoint(conn, claim_id, existing)
        return {"ok": True, "reason": "idempotent_replay", "effect": existing, "conflict": False}
    except Exception:
        conn.rollback()
        raise

    effect = get_refund(conn, claim_id)
    if crash_at == "after_effect_before_checkpoint":
        raise InjectedCrash("after_effect_before_checkpoint")
    _checkpoint(conn, claim_id, effect or {})
    if crash_at == "after_checkpoint":
        raise InjectedCrash("after_checkpoint")
    return {"ok": True, "reason": "committed", "effect": effect, "conflict": False}


def _checkpoint(conn: sqlite3.Connection, claim_id: str, effect: dict[str, Any]) -> None:
    payload = {
        "claim_id": claim_id,
        "idempotency_key": effect.get("idempotency_key"),
        "amount_vnd": effect.get("amount_vnd"),
        "status": effect.get("status"),
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO checkpoints (claim_id, step, result_json)
        VALUES (?, 'issue_refund', ?)
        """,
        (claim_id, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def _audit_conflict(conn: sqlite3.Connection, claim_id: str, committed: int, attempted: int) -> None:
    key = f"amount_conflict:{claim_id}"
    details = {"committed_vnd": committed, "attempted_vnd": attempted}
    conn.execute(
        """
        INSERT OR IGNORE INTO audit_events (audit_key, claim_id, event_type, details_json)
        VALUES (?, ?, 'amount_conflict', ?)
        """,
        (key, claim_id, json.dumps(details, ensure_ascii=False)),
    )
    conn.commit()
