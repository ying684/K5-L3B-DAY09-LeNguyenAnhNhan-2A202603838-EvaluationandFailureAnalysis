"""Approval gate. Reads autonomy_policy.yaml. Does not mint approvals.

Two host rules that model output cannot skip:

1. The approval is the one the claim points to (`claims.approval_id`), and that
   approval must belong to this claim. An approval issued for another claim does
   not count, even if the amount looks right.
2. Refunds are capped per order, not only per claim. Earlier refunds on the same
   order are subtracted from the entitlement, so a second ticket for an order that
   was already refunded pays nothing, and a later, larger entitlement (damage after
   a shipping refund) only pays the difference. This is the stacking rule
   (max of eligible, never the sum) applied across claims.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from lab8.config_loader import as_of, load_yaml


@dataclass
class AuthDecision:
    ok: bool
    reason: str
    amount_vnd: int
    approved_vnd: int
    approval_id: str | None


def order_refunded_vnd(conn: sqlite3.Connection, order_id: str, *, exclude_claim_id: str | None = None) -> int:
    """Total already committed for this order by other claims."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount_vnd), 0) AS total FROM refund_ledger
        WHERE order_id = ? AND claim_id != COALESCE(?, '')
        """,
        (order_id, exclude_claim_id),
    ).fetchone()
    return int(row["total"])


def authorize(
    conn: sqlite3.Connection,
    claim_id: str,
    proposed_vnd: int,
    *,
    paid_vnd: int,
    already_refunded_vnd: int = 0,
) -> AuthDecision:
    """Decide the amount the host may write.

    proposed_vnd is the full entitlement quote for the order. already_refunded_vnd is
    what other claims on the same order have already received.
    """
    policy = load_yaml("config/autonomy_policy.yaml")
    refund = policy["refund"]
    today = as_of()
    if not refund["require_approval_event"]:
        raise RuntimeError("lab policy requires an approval event")

    claim = conn.execute("SELECT approval_id FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    approval_id = claim["approval_id"] if claim is not None else None
    if not approval_id:
        return AuthDecision(False, "missing_approval", 0, 0, None)
    row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        return AuthDecision(False, "missing_approval", 0, 0, approval_id)
    approved = int(row["approved_vnd"])
    if refund["approval_must_match_claim_id"] and row["claim_id"] != claim_id:
        return AuthDecision(False, "approval_claim_mismatch", 0, approved, approval_id)
    if refund["reject_non_valid_status"] and row["status"] != "valid":
        return AuthDecision(False, f"approval_{row['status']}", 0, approved, approval_id)
    if refund["reject_expired"] and str(row["expires_at"]) < today:
        return AuthDecision(False, "approval_expired", 0, approved, approval_id)
    if approved <= 0 or int(proposed_vnd) <= 0:
        return AuthDecision(False, "non_positive_amount", 0, approved, approval_id)

    already = max(0, int(already_refunded_vnd))
    amount = int(proposed_vnd)
    if refund.get("cap_per_order", True):
        amount -= already
        if amount <= 0:
            return AuthDecision(False, "order_already_refunded", 0, approved, approval_id)
    if refund["cap_at_approved_amount"]:
        amount = min(amount, approved)
    if refund["cap_at_paid_amount"]:
        amount = min(amount, int(paid_vnd) - already)
    if amount <= 0:
        return AuthDecision(False, "capped_to_zero", 0, approved, approval_id)
    return AuthDecision(True, "ok", amount, approved, approval_id)
