"""The grader must keep grading when one shape is broken, and must work without labels."""

import json

import pytest

from lab8.benchmark import _steps, render_table, run_benchmark
from lab8.shapes import SHAPES
from lab8.shapes.swarm_reference import run_claim as swarm
from tests.conftest import CLAIMS, WORLD


def _boom(claim_id, *, seed, store_path, crash_at=None):
    raise ValueError("bug in student code")


def _returns_dict(claim_id, *, seed, store_path, crash_at=None):
    return {"status": "resolved"}


def _wrong_claim(claim_id, *, seed, store_path, crash_at=None):
    return swarm("C-001", seed=seed, store_path=store_path)


@pytest.fixture
def extra_shapes():
    added = {"boom": _boom, "as_dict": _returns_dict, "wrong_claim": _wrong_claim}
    SHAPES.update(added)
    try:
        yield
    finally:
        for name in added:
            SHAPES.pop(name, None)


def test_a_broken_shape_does_not_stop_grading_the_others(extra_shapes):
    claims = [row for row in CLAIMS if row["claim_id"] in ("C-002", "C-003")]
    report = run_benchmark(world=WORLD, claims=claims, shapes=["boom", "as_dict", "wrong_claim", "swarm"], seeds=[11])
    reasons = {(t["shape"], t["claim_id"]): t["reason"] for t in report["trials"]}
    assert reasons[("boom", "C-002")].startswith("exception:ValueError")
    assert reasons[("as_dict", "C-002")].startswith("invalid_result:dict")
    assert reasons[("wrong_claim", "C-002")] == "wrong_claim_id:C-001"
    assert report["by_shape"]["boom"]["pass_rate"] == 0.0
    assert report["by_shape"]["swarm"]["pass_rate"] == 1.0
    assert "exception x2" in render_table(report)


def test_unlabeled_claims_run_in_self_check_mode():
    claims = [{k: v for k, v in row.items() if k != "expected"} for row in CLAIMS[:3]]
    report = run_benchmark(world=WORLD, claims=claims, shapes=["swarm"], seeds=[11])
    stats = report["by_shape"]["swarm"]
    assert stats["pass_rate"] is None
    assert stats["graded_trials"] == 0
    assert stats["leak_suspect_trials"] == 0
    assert sum(stats["status_counts"].values()) == 3
    assert all(t["passed"] is None and t["reason"] == "unlabeled" for t in report["trials"])
    assert "tự kiểm" in render_table(report)


def test_steps_count_events_even_without_a_steps_key(tmp_path):
    trace = tmp_path / "t.json"
    trace.write_text(json.dumps({"run_id": "R", "events": [{}, {}, {}]}), encoding="utf-8")
    assert _steps(str(trace)) == 3
    assert _steps(str(tmp_path / "missing.json")) == 0
    assert _steps(None) == 0


def test_unknown_shape_name_is_a_config_error():
    with pytest.raises(SystemExit):
        run_benchmark(world=WORLD, claims=CLAIMS[:1], shapes=["wokflow"], seeds=[11])
