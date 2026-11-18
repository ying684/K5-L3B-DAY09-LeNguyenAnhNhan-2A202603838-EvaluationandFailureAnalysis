"""python -m lab8.smoke — day-0 check. Does not grade student shapes.

Runs the same way on Windows, macOS, and Linux. Prints a clear hint instead of a
traceback for the usual setup mistakes (old Python, missing deps, wrong folder).
"""

from __future__ import annotations

import platform
import sys
import tempfile
from pathlib import Path

from lab8.console import utf8_stdio

MIN_PYTHON = (3, 11)


def _preflight() -> None:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            f"Python {platform.python_version()} quá cũ. Cần Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ "
            "(xem mục 'Cài đặt theo hệ điều hành' trong src/README.md)."
        )
    try:
        import yaml  # noqa: F401
    except ModuleNotFoundError:
        raise SystemExit(
            "Thiếu PyYAML. Đứng trong thư mục src/, kích hoạt venv rồi chạy: python -m pip install -r requirements.txt"
        ) from None
    root = Path(__file__).resolve().parents[1]
    if not (root / "config" / "autonomy_policy.yaml").exists():
        raise SystemExit(f"Không thấy config/ trong {root}. Mọi lệnh chạy trong thư mục src/. Repo bị thiếu file?")


def main() -> int:
    utf8_stdio()
    _preflight()

    from lab8.app import prepare_store, run_shape
    from lab8.config_loader import load_yaml
    from lab8.db import connect
    from lab8.durability import get_refund
    from lab8.mock_llm import complete
    from lab8.schemas import Budget

    manifest = load_yaml("config/tools.manifest.v1.1.yaml")
    if manifest["manifest_version"] != "1.1":
        raise SystemExit("manifest is not 1.1")
    harness = load_yaml("harness_map.yaml")
    if "orchestration" not in harness["sections"]:
        raise SystemExit("harness_map missing orchestration")

    left = Budget()
    right = Budget()
    text_a = complete(left, seed=11, purpose="draft", prompt="ping")
    text_b = complete(Budget(), seed=11, purpose="draft", prompt="ping")
    text_c = complete(right, seed=22, purpose="draft", prompt="ping")
    if text_a != text_b:
        raise SystemExit("MockLLM is not seed-stable")
    if text_a == text_c:
        raise SystemExit("MockLLM ignored the seed")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = Path(tmp) / "smoke.sqlite"
        prepare_store(store)
        result = run_shape("swarm", "C-001", seed=11, store_path=str(store))
        if result.status != "resolved" or result.proposal_amount != 35000:
            raise SystemExit(f"swarm reference failed smoke: {result.status} {result.proposal_amount}")
        conn = connect(store)
        try:
            effect = get_refund(conn, "C-001")
        finally:
            conn.close()
        if effect is None or int(effect["amount_vnd"]) != 35000:
            raise SystemExit("smoke ledger missing the 35000 refund")
        blob = Path(result.trace_path).read_text(encoding="utf-8")
        if "CANARY_SECRET_" in blob or "0901000107" in blob:
            raise SystemExit("smoke trace leaked a secret or phone number")
    print("lab8.smoke pass")
    print(f"python {platform.python_version()} | {platform.system()} {platform.machine()}")
    print("manifest 1.1 | MockLLM seeded | swarm C-001 refund 35000 | trace clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
