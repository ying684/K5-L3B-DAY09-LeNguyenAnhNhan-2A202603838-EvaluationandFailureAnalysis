from pathlib import Path

from lab8.crash_test import run_suite


def test_twenty_crash_points_are_safe(tmp_path: Path):
    report = run_suite(tmp_path)
    failed = [row for row in report["scenarios"] if not row["passed"]]
    assert report["count"] == 20
    assert failed == []
