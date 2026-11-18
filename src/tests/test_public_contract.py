import json

from lab8.config_loader import load_yaml, repo_path
from lab8.schemas import RunResult, make_run_id
from lab8.shapes import SHAPES


def test_manifest_and_harness_pin_orchestration():
    manifest = load_yaml("config/tools.manifest.v1.1.yaml")
    harness = load_yaml("harness_map.yaml")
    assert manifest["manifest_version"] == "1.1"
    names = {tool["name"] for tool in manifest["tools"]}
    assert "issue_refund" in names
    assert "compute_compensation" in names
    section = harness["sections"]["orchestration"]
    assert section["idempotency"] == "lab8.durability.issue_refund"
    assert "after_effect_before_checkpoint" in section["crash_injection"]


def test_run_result_fields_match_the_lab_contract():
    result = RunResult(
        run_id=make_run_id("workflow", "C-001", 11),
        claim_id="C-001",
        shape="workflow",
        seed=11,
        status="failed",
        proposal_amount=0,
        refund_effects=[],
        committed_audit_count=0,
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_estimate=0.0,
        trace_path="traces/unused.json",
        error_reason="not_implemented",
    )
    assert set(result.as_dict()) == {
        "run_id",
        "claim_id",
        "shape",
        "seed",
        "status",
        "proposal_amount",
        "refund_effects",
        "committed_audit_count",
        "model_calls",
        "tool_calls",
        "input_tokens",
        "output_tokens",
        "cost_estimate",
        "trace_path",
        "error_reason",
    }


def test_four_shapes_share_one_signature():
    assert set(SHAPES) == {"workflow", "single", "orchestrator", "swarm"}


def test_public_matrix_has_fourteen_labeled_cases():
    rows = (repo_path("data", "public_claims.jsonl")).read_text(encoding="utf-8").strip().splitlines()
    ids = [json.loads(line)["matrix_id"] for line in rows]
    assert ids == [f"T{i:02d}" for i in range(1, 15)]


def test_extra_shape_registers_for_one_process_only():
    import pytest

    from lab8.app import register_extra_shapes

    try:
        assert register_extra_shapes(["swarm_copy=lab8.shapes.swarm_reference:run_claim"]) == ["swarm_copy"]
        assert SHAPES["swarm_copy"] is SHAPES["swarm"]
        with pytest.raises(SystemExit):
            register_extra_shapes(["swarm=lab8.shapes.swarm_reference:run_claim"])
        with pytest.raises(SystemExit):
            register_extra_shapes(["no_colon=lab8.shapes.swarm_reference"])
    finally:
        SHAPES.pop("swarm_copy", None)
    assert set(SHAPES) == {"workflow", "single", "orchestrator", "swarm"}
