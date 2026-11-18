import importlib
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "grader_audit" / "fixtures"


@pytest.mark.parametrize("name", ["grader_a", "grader_b", "grader_c"])
def test_variant_imports_and_returns_dict(name):
    module = importlib.import_module(f"grader_audit.{name}")
    fixture = json.loads((FIXTURES / "metamorphic_duplicate.json").read_text(encoding="utf-8"))
    report = module.summarize(fixture["a"])
    assert isinstance(report, dict)
    assert report
    assert all(isinstance(stats, dict) for stats in report.values())
