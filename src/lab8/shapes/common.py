"""Helpers shared by shapes. Keeps RunResult construction in one place."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from lab8.durability import committed_audit_count, get_refund
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.trace import Trace


def not_implemented(shape: str, claim_id: str, seed: int) -> RunResult:
    run_id = make_run_id(shape, claim_id, seed)
    trace = Trace(run_id)
    trace.add("shape", {"status": "not_implemented"})
    path = trace.write()
    return RunResult(
        run_id=run_id,
        claim_id=claim_id,
        shape=shape,
        seed=seed,
        status="failed",
        proposal_amount=0,
        refund_effects=[],
        committed_audit_count=0,
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_estimate=0.0,
        trace_path=path,
        error_reason="not_implemented",
    )


def finish(
    conn: sqlite3.Connection,
    *,
    shape: str,
    claim_id: str,
    seed: int,
    status: str,
    proposal_amount: int,
    budget: Budget,
    trace: Trace,
    error_reason: str | None = None,
) -> RunResult:
    effect = get_refund(conn, claim_id)
    effects = [effect] if effect else []
    path = trace.write()
    return RunResult(
        run_id=trace.run_id,
        claim_id=claim_id,
        shape=shape,
        seed=seed,
        status=status,
        proposal_amount=int(proposal_amount),
        refund_effects=effects,
        committed_audit_count=committed_audit_count(conn, claim_id),
        model_calls=budget.model_calls,
        tool_calls=budget.tool_calls,
        input_tokens=budget.input_tokens,
        output_tokens=budget.output_tokens,
        cost_estimate=round(budget.cost_estimate, 6),
        trace_path=path,
        error_reason=error_reason,
    )


def safe_dump(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy a payload for the trace. Caller must already have dropped secrets."""
    return json.loads(json.dumps(payload, ensure_ascii=False))
