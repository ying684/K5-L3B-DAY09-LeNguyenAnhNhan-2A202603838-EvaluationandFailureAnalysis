from __future__ import annotations

from typing import Any

from lab8.metrics import summarize as _base


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(t, passed=None) if t.get("infra_error") else dict(t) for t in trials]
    return _base(rows)
