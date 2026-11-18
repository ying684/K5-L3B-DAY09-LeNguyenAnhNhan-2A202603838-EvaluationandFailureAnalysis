"""Same claims, same seeds, same prices, separate database per trial.

python -m lab8.benchmark --shapes workflow,single,orchestrator,swarm \
    --cases data/public_claims.jsonl --seeds 11,22,33,44,55 --out reports/benchmark.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from lab8.app import register_extra_shapes, run_shape
from lab8.config_loader import as_of, pricing, repo_path
from lab8.console import utf8_stdio
from lab8.db import connect, load_json, load_jsonl
from lab8.metrics import artifact_blob, check_trace, summarize, trial_pass
from lab8.schemas import RunResult, make_run_id

# Markers a self-check can look for without labels (student_drop has no labels).
LEAK_MARKERS = ("CANARY_SECRET_", "CANARY_INTERNAL_")


def _steps(trace_path: str | None) -> int:
    """Steps = number of events in the trace (trace contract v1)."""
    if not trace_path:
        return 0
    path = Path(trace_path)
    if not path.is_file():
        return 0
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 0
    events = body.get("events") if isinstance(body, dict) else None
    return len(events) if isinstance(events, list) else 0


def run_trial(shape: str, claim_id: str, seed: int, store: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Run one trial. A bug in one shape must not stop grading the others.

    Returns (payload, None) on success, or (None, reason) when the shape raised or
    returned something that is not a RunResult for the requested claim.
    """
    try:
        result = run_shape(shape, claim_id, seed=seed, store_path=str(store))
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — record and keep grading
        return None, f"exception:{type(exc).__name__}:{str(exc)[:120]}"
    if not isinstance(result, RunResult):
        return None, f"invalid_result:{type(result).__name__} (return a lab8.schemas.RunResult)"
    payload = result.as_dict()
    if payload["claim_id"] != claim_id:
        return None, f"wrong_claim_id:{payload['claim_id']}"
    return payload, None


def run_benchmark(
    *,
    world: dict[str, Any],
    claims: list[dict[str, Any]],
    shapes: list[str],
    seeds: list[int],
    labels: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score shapes. When `labels` is set, claim['expected'] is ignored.

    Claims without a label (for example the student_drop of the hidden pack) run in
    self-check mode: passed is None, and the row still reports status, trace contract,
    and whether a CANARY marker leaked.
    """
    from lab8.shapes import SHAPES

    unknown = [shape for shape in shapes if shape not in SHAPES]
    if unknown:
        raise SystemExit(f"unknown shape(s) {unknown}; choose from {', '.join(SHAPES)}")
    trials: list[dict[str, Any]] = []
    # ignore_cleanup_errors: on Windows a connection a shape forgot to close locks its
    # .sqlite file; the report must still be written.
    with tempfile.TemporaryDirectory(prefix="lab8-bench-", ignore_cleanup_errors=True) as tmp:
        for shape in shapes:
            for claim in claims:
                claim_id = claim["claim_id"]
                if labels is not None:
                    if claim_id not in labels:
                        raise KeyError(f"missing label for {claim_id}")
                    expected = labels[claim_id]
                else:
                    expected = claim.get("expected")
                for seed in seeds:
                    store = Path(tmp) / f"{shape}-{claim_id}-{seed}.sqlite"
                    prepare_from_memory(store, world, claims)
                    started_at = time.time()
                    payload, error = run_trial(shape, claim_id, seed, store)
                    row: dict[str, Any] = {"shape": shape, "claim_id": claim_id, "seed": seed}
                    if error is not None:
                        row.update(
                            passed=False if expected is not None else None,
                            reason=error,
                            cost_estimate=0.0,
                            steps=0,
                            model_calls=0,
                            tool_calls=0,
                            run_id=make_run_id(shape, claim_id, seed),
                            status="error",
                        )
                        trials.append(row)
                        continue
                    if expected is not None:
                        conn = connect(store)
                        try:
                            passed, reason = trial_pass(payload, expected, conn, started_at=started_at)
                        except Exception as exc:  # noqa: BLE001 — malformed result fields
                            passed, reason = False, f"invalid_result:{type(exc).__name__}:{str(exc)[:120]}"
                        finally:
                            conn.close()
                    else:
                        trace_ok, trace_reason = check_trace(payload, started_at=started_at)
                        blob = artifact_blob(payload)
                        leaked = [marker for marker in LEAK_MARKERS if marker in blob]
                        passed = None
                        reason = "unlabeled" if trace_ok else trace_reason
                        if leaked:
                            reason = f"leak_suspect:{','.join(leaked)}"
                    row.update(
                        passed=passed,
                        reason=reason,
                        cost_estimate=payload["cost_estimate"],
                        steps=_steps(payload["trace_path"]),
                        model_calls=payload["model_calls"],
                        tool_calls=payload["tool_calls"],
                        run_id=payload["run_id"],
                        status=payload["status"],
                    )
                    trials.append(row)
    prices = pricing()
    return {
        "controlled_variables": {
            "as_of": as_of(),
            "seeds": seeds,
            "claim_ids": [claim["claim_id"] for claim in claims],
            "pricing": {
                "simulated": True,
                "currency": prices["currency"],
                "input_per_1k_tokens_vnd": prices["input_per_1k_tokens_vnd"],
                "output_per_1k_tokens_vnd": prices["output_per_1k_tokens_vnd"],
                "tool_call_vnd": prices["tool_call_vnd"],
            },
            "model_backend": "MockLLM",
            "latency": "unavailable",
            "isolation": "fresh_sqlite_per_trial",
        },
        "by_shape": summarize(trials),
        "trials": trials,
    }


def prepare_from_memory(store: Path, world: dict[str, Any], claims: list[dict[str, Any]]) -> None:
    from lab8.db import init_store

    init_store(store, world, claims).close()


def render_table(report: dict[str, Any]) -> str:
    lines = [
        f"{'shape':<14} {'pass':>8} {'pass^5':>8} {'var':>10} {'min':>6} {'max':>6} {'cost/success':>14} {'steps':>8}",
        "-" * 82,
    ]
    def num(value: float | None, fmt: str, width: int) -> str:
        return f"{'-':>{width}}" if value is None else f"{value:>{width}{fmt}}"

    unlabeled = False
    for shape, stats in report["by_shape"].items():
        unlabeled = unlabeled or stats["graded_trials"] < stats["trials"]
        lines.append(
            f"{shape:<14} {num(stats['pass_rate'], '.3f', 8)} {num(stats['pass_5'], '.3f', 8)} "
            f"{num(stats['seed_variance'], '.6f', 10)} {num(stats['seed_min'], '.3f', 6)} "
            f"{num(stats['seed_max'], '.3f', 6)} {num(stats['cost_per_success_vnd'], '.2f', 14)} "
            f"{num(stats['mean_steps'], '.2f', 8)}"
        )
        problems = {k: v for k, v in stats["reasons"].items() if k not in ("ok", "unlabeled")}
        if problems:
            top = ", ".join(f"{k} x{v}" for k, v in sorted(problems.items(), key=lambda kv: -kv[1])[:4])
            lines.append(f"{'':<14} lỗi hay gặp: {top}")
    if unlabeled:
        lines.append("claim không nhãn (tự kiểm): không tính pass được; xem status, trace và leak_suspect trong file JSON")
    lines.append("cost is simulated VND, not an API bill. latency: unavailable")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Benchmark shapes on the same claims and seeds")
    parser.add_argument("--shapes", required=True, help="comma-separated: workflow,single,orchestrator,swarm")
    parser.add_argument("--cases", default=str(repo_path("data", "public_claims.jsonl")))
    parser.add_argument("--world", default=str(repo_path("data", "public_world_state.json")))
    parser.add_argument("--seeds", default="11,22,33,44,55")
    parser.add_argument("--out", required=True)
    parser.add_argument("--labels", default=None, help="JSON map claim_id -> expected. Ignores inline expected.")
    parser.add_argument(
        "--extra-shape",
        action="append",
        default=[],
        metavar="NAME=MODULE:FUNC",
        help="bonus variant to benchmark next to the four shapes, e.g. swarm_verified=bonus.swarm_verified:run_claim",
    )
    args = parser.parse_args(argv)
    register_extra_shapes(args.extra_shape)
    shapes = [part.strip() for part in args.shapes.split(",") if part.strip()]
    seeds = [int(part) for part in args.seeds.split(",") if part.strip()]
    world = load_json(args.world)
    claims = load_jsonl(args.cases)
    labels = load_json(args.labels) if args.labels else None
    report = run_benchmark(world=world, claims=claims, shapes=shapes, seeds=seeds, labels=labels)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render_table(report))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
