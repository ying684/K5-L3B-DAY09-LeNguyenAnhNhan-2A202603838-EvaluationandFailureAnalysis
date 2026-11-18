"""Typed handoff. Allowlist in code. An LLM summary is not redaction."""

from __future__ import annotations

import json
from typing import Any

CONTRACT_VERSION = "handoff.v1"
ALLOWED_FIELDS = {
    "contract_version",
    "request_id",
    "claim_id",
    "principal_scope",
    "task",
    "facts",
    "allowed_tools",
    "max_output_tokens",
}
READONLY_TOOLS = {
    "get_claim_view",
    "lookup_order",
    "lookup_policy",
    "lookup_refund_history",
    "get_clause",
    "compute_compensation",
}
WRITE_TOOLS = {"issue_refund", "append_audit"}
FACT_KEYS = {
    "delay_days",
    "damage_verified",
    "carrier",
    "order_status",
    "shipping_fee_vnd",
    "paid_vnd",
}


class HandoffError(ValueError):
    pass


def make_handoff(
    *,
    request_id: str,
    claim_id: str,
    task: str,
    facts: dict[str, Any],
    allowed_tools: list[str],
    max_output_tokens: int = 400,
) -> dict[str, Any]:
    unknown = set(allowed_tools) - READONLY_TOOLS
    if unknown:
        raise HandoffError(f"worker tools must be read-only, rejected: {sorted(unknown)}")
    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "claim_id": claim_id,
        "principal_scope": "owner_order_only",
        "task": task,
        "facts": {key: facts[key] for key in FACT_KEYS if key in facts},
        "allowed_tools": list(allowed_tools),
        "max_output_tokens": int(max_output_tokens),
    }
    return sanitize(payload)


def sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop anything outside the allowlist, then refuse canaries that remain."""
    cleaned = {key: payload[key] for key in ALLOWED_FIELDS if key in payload}
    if set(payload) - ALLOWED_FIELDS:
        # Extra keys are removed. They are not forwarded.
        pass
    blob = json.dumps(cleaned, ensure_ascii=False)
    if "CANARY_SECRET_" in blob or "parent_secret" in blob or "raw_headers" in blob:
        raise HandoffError("handoff still contains a parent secret or header material")
    tools = cleaned.get("allowed_tools") or []
    if set(tools) & WRITE_TOOLS:
        raise HandoffError("handoff granted a write tool")
    return cleaned
