from __future__ import annotations

from typing import Any

from lab8.metrics import summarize as _base


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(t, passed=None) if t.get("infra_error") else dict(t) for t in trials]
    report = _base(rows)
    for shape, stats in report.items():
        if not stats.get("graded_trials"):
            continue
        seen: set[str] = set()
        extra = 0.0
        for row in rows:
            if row["shape"] != shape or row["passed"] is None or row["claim_id"] in seen:
                continue
            seen.add(row["claim_id"])
            extra += float(row["cost_estimate"])
        stats["total_simulated_cost_vnd"] += extra
        if stats["successes"]:
            stats["cost_per_success_vnd"] = stats["total_simulated_cost_vnd"] / stats["successes"]
    return report
