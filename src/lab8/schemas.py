"""Shared contracts. Every shape returns the same RunResult."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


STATUSES = ("resolved", "needs_info", "escalated", "denied", "failed")


@dataclass
class RunResult:
    run_id: str
    claim_id: str
    shape: str
    seed: int
    status: str
    proposal_amount: int
    refund_effects: list[dict[str, Any]]
    committed_audit_count: int
    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float
    trace_path: str
    error_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Budget:
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float = 0.0
    steps: int = 0

    def add_llm(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        self.model_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_estimate += cost
        self.steps += 1

    def add_tool(self, cost: float) -> None:
        self.tool_calls += 1
        self.cost_estimate += cost
        self.steps += 1


@dataclass
class Quote:
    amount_vnd: int
    reason: str
    clause_ids: list[str] = field(default_factory=list)
    parts: dict[str, int] = field(default_factory=dict)


def make_run_id(shape: str, claim_id: str, seed: int) -> str:
    return f"R-{shape}-{claim_id}-s{seed}"
