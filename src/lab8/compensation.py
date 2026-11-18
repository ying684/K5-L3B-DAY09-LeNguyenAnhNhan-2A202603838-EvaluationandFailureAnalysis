"""Deterministic compensation. Code owns the money. The model does not.

Stacking rule: if several clauses qualify, pay the larger amount once.
Do not add shipping and damage together.
"""

from __future__ import annotations

from typing import Any

from lab8.schemas import Quote

ELIGIBLE_STATUSES = {"delivered", "delivered_late"}


def quote(order: dict[str, Any], policies: list[dict[str, Any]], *, as_of: str) -> Quote:
    """Quote from structured order fields and current policy only."""
    status = order.get("status")
    if status not in ELIGIBLE_STATUSES:
        return Quote(0, f"order_status_{status}")

    parts: dict[str, int] = {}
    clause_ids: list[str] = []
    for policy in policies:
        if not policy.get("is_current"):
            continue
        if str(policy.get("effective_date", "")) > as_of:
            continue
        for clause in policy.get("clauses", []):
            amount = _clause_amount(order, clause)
            if amount > 0:
                parts[clause["clause_id"]] = amount
                clause_ids.append(clause["clause_id"])

    if not parts:
        return Quote(0, "no_entitlement", clause_ids, parts)
    winner = max(parts, key=parts.get)
    return Quote(parts[winner], "entitled", clause_ids, parts)


def _clause_amount(order: dict[str, Any], clause: dict[str, Any]) -> int:
    if order.get("status") not in set(clause.get("eligible_statuses") or ELIGIBLE_STATUSES):
        return 0
    kind = clause["kind"]
    if kind == "late_delivery":
        if int(order["delay_days"]) < int(clause["min_delay_days"]):
            return 0
        basis = clause["refund_basis"]
        if basis == "shipping_fee":
            return max(0, int(order["shipping_fee_vnd"]))
        if basis == "full_paid":
            return max(0, int(order["paid_vnd"]))
        return 0
    if kind == "damage":
        if clause.get("requires_verified") and not order.get("damage_verified"):
            return 0
        capped = min(int(clause["max_refund_vnd"]), int(order["paid_vnd"]))
        return max(0, capped)
    return 0
