"""Seeded stand-in for an LLM. Same seed + same prompt => same usage and text.

Token cost is simulated from config/pricing.yaml. Do not report it as an API bill.
Latency is not measured here.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from lab8.config_loader import pricing
from lab8.schemas import Budget


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def parse_delay_days(ticket: str) -> int | None:
    """Number the ticket *claims*. This can disagree with the order row."""
    match = re.search(r"tre\s+(\d+)\s+ngay", _fold(ticket))
    if not match:
        return None
    return int(match.group(1))


def complete(budget: Budget, *, seed: int, purpose: str, prompt: str) -> str:
    digest = hashlib.sha256(f"{seed}|{purpose}|{prompt}".encode()).hexdigest()[:12]
    if purpose == "draft":
        text = f"LogiX da ghi nhan yeu cau. ref={digest}."
    elif purpose == "peer":
        text = f"peer-ack seed={seed} ref={digest}"
    elif purpose == "parse":
        parsed = parse_delay_days(prompt)
        text = f"parsed_delay={parsed if parsed is not None else 'none'}"
    else:
        text = f"{purpose}:{digest}"
    prices = pricing()
    input_tokens = max(1, len(prompt) // 4)
    output_tokens = max(1, len(text) // 4)
    cost = (
        input_tokens / 1000 * float(prices["input_per_1k_tokens_vnd"])
        + output_tokens / 1000 * float(prices["output_per_1k_tokens_vnd"])
    )
    budget.add_llm(input_tokens, output_tokens, cost)
    return text
