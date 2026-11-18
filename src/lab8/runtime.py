"""Bounded ReAct loop and read-only investigator runner.

Students compose these. The loop enforces the step cap and refuses write tools
when the caller says the actor is a worker.
"""

from __future__ import annotations

from typing import Any, Callable

from lab8.handoff import READONLY_TOOLS, WRITE_TOOLS
from lab8.schemas import Budget
from lab8.tools import (
    compute_compensation,
    get_claim_view,
    get_clause,
    lookup_order,
    lookup_policy,
    lookup_refund_history,
    tool_cost,
)

Decide = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRejected(Exception):
    pass


def dispatch(
    conn,
    budget: Budget,
    name: str,
    args: dict[str, Any],
    *,
    worker: bool,
) -> dict[str, Any]:
    if worker and name not in READONLY_TOOLS:
        raise ToolRejected(f"worker cannot call {name}")
    if name in WRITE_TOOLS:
        raise ToolRejected("write tools are host-only; call lab8.durability from the shape, not the model")
    budget.add_tool(tool_cost())
    if name == "get_claim_view":
        return get_claim_view(conn, args["claim_id"])
    if name == "lookup_order":
        return lookup_order(conn, args.get("order_id"), args["principal_id"])
    if name == "lookup_policy":
        return lookup_policy(conn)
    if name == "lookup_refund_history":
        return lookup_refund_history(conn, args.get("order_id"), args["principal_id"])
    if name == "get_clause":
        return get_clause(conn, args["clause_id"])
    if name == "compute_compensation":
        return compute_compensation(conn, args["order"])
    raise ToolRejected(f"unknown tool {name}")


def run_react(
    conn,
    budget: Budget,
    *,
    observation: dict[str, Any],
    decide: Decide,
    max_steps: int = 8,
    worker: bool = False,
) -> dict[str, Any]:
    """Call decide until it returns {"final": {...}} or the step cap is hit."""
    seen = dict(observation)
    for _ in range(max_steps):
        action = decide(seen)
        if "final" in action:
            return {"stopped": "final", "final": action["final"], "observation": seen}
        name = action.get("tool")
        args = action.get("args") or {}
        result = dispatch(conn, budget, name, args, worker=worker)
        seen = {"last_tool": name, "last_result": result, "claim": observation.get("claim")}
    return {"stopped": "step_cap", "final": {"status": "failed", "error_reason": "step_cap"}, "observation": seen}


def run_readonly_investigators(conn, budget: Budget, handoff: dict[str, Any], principal_id: str) -> dict[str, Any]:
    """Investigators only see the handoff plus read tools named there."""
    results = {}
    claim = get_claim_view(conn, handoff["claim_id"])
    budget.add_tool(tool_cost())
    for name in handoff["allowed_tools"]:
        if name == "get_claim_view":
            results[name] = claim
            continue
        if name == "lookup_order":
            results[name] = dispatch(
                conn,
                budget,
                name,
                {"order_id": claim.get("order_id"), "principal_id": principal_id},
                worker=True,
            )
        elif name == "lookup_policy":
            results[name] = dispatch(conn, budget, name, {}, worker=True)
        elif name == "lookup_refund_history":
            results[name] = dispatch(
                conn,
                budget,
                name,
                {"order_id": claim.get("order_id"), "principal_id": principal_id},
                worker=True,
            )
        elif name == "compute_compensation":
            order_view = results.get("lookup_order") or {}
            order = (order_view.get("order") if isinstance(order_view, dict) else None) or {}
            if order:
                results[name] = dispatch(conn, budget, name, {"order": order}, worker=True)
        elif name == "get_clause":
            continue
        else:
            raise ToolRejected(name)
    return {"claim_view": {k: claim[k] for k in ("found", "claim_id", "order_id") if k in claim}, "tools": results}
