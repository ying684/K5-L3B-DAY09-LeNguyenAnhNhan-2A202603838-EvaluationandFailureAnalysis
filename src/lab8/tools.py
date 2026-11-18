"""Tool adapters. Read tools return an allowlist of fields. Writes stay in the host."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from lab8.compensation import quote
from lab8.config_loader import as_of, pricing

ORDER_FIELDS = (
    "order_id",
    "status",
    "delay_days",
    "shipping_fee_vnd",
    "paid_vnd",
    "damage_verified",
    "carrier",
)


def tool_cost() -> float:
    return float(pricing()["tool_call_vnd"])


def get_claim_view(conn: sqlite3.Connection, claim_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT claim_id, principal_id, order_id, ticket FROM claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return {"found": False, "claim_id": claim_id}
    return {"found": True, **dict(row)}


def lookup_order(
    conn: sqlite3.Connection,
    order_id: str | None,
    principal_id: str,
) -> dict[str, Any]:
    if not order_id:
        return {"visible": False, "reason": "missing_order_id"}
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        return {"visible": False, "reason": "not_found", "order_id": order_id}
    if row["principal_id"] != principal_id:
        return {"visible": False, "reason": "outside_principal_scope", "order_id": order_id}
    order = {key: row[key] for key in ORDER_FIELDS}
    order["damage_verified"] = bool(order["damage_verified"])
    return {"visible": True, "reason": "ok", "order": order}


def lookup_refund_history(
    conn: sqlite3.Connection,
    order_id: str | None,
    principal_id: str,
) -> dict[str, Any]:
    """How much this order has already been refunded, by any claim. Same scope rules as lookup_order."""
    scope = lookup_order(conn, order_id, principal_id)
    if not scope["visible"]:
        return {"visible": False, "reason": scope["reason"]}
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(amount_vnd), 0) AS total FROM refund_ledger WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    return {
        "visible": True,
        "reason": "ok",
        "order_id": order_id,
        "refund_count": int(row["n"]),
        "refunded_vnd": int(row["total"]),
    }


def lookup_policy(conn: sqlite3.Connection) -> dict[str, Any]:
    today = as_of()
    rows = conn.execute(
        """
        SELECT * FROM policies
        WHERE is_current = 1 AND effective_date <= ?
        ORDER BY effective_date DESC
        """,
        (today,),
    ).fetchall()
    policies = [_policy_dict(row) for row in rows]
    return {"as_of": today, "policies": policies}


def get_clause(conn: sqlite3.Connection, clause_id: str) -> dict[str, Any]:
    """Historical clauses are returned on purpose. Check is_current before paying."""
    for row in conn.execute("SELECT * FROM policies"):
        policy = _policy_dict(row)
        for clause in policy["clauses"]:
            if clause["clause_id"] == clause_id:
                return {
                    "found": True,
                    "clause": clause,
                    "policy_id": policy["policy_id"],
                    "is_current": policy["is_current"],
                    "effective_date": policy["effective_date"],
                }
    return {"found": False, "clause_id": clause_id}


def compute_compensation(conn: sqlite3.Connection, order: dict[str, Any]) -> dict[str, Any]:
    policies = lookup_policy(conn)["policies"]
    result = quote(order, policies, as_of=as_of())
    return {
        "amount_vnd": result.amount_vnd,
        "reason": result.reason,
        "clause_ids": result.clause_ids,
        "parts": result.parts,
    }


def _policy_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "policy_id": row["policy_id"],
        "version": row["version"],
        "is_current": bool(row["is_current"]),
        "effective_date": row["effective_date"],
        "superseded_by": row["superseded_by"],
        "clauses": json.loads(row["clauses_json"]),
    }
