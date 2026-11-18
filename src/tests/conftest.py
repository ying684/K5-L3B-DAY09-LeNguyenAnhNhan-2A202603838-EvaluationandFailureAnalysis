from __future__ import annotations

from pathlib import Path

import pytest

from lab8.config_loader import repo_path
from lab8.db import init_store, load_json, load_jsonl

WORLD = load_json(repo_path("data", "public_world_state.json"))
CLAIMS = load_jsonl(repo_path("data", "public_claims.jsonl"))
BY_ID = {row["claim_id"]: row for row in CLAIMS}


@pytest.fixture
def public_db(tmp_path: Path) -> Path:
    store = tmp_path / "public.sqlite"
    init_store(store, WORLD, CLAIMS).close()
    return store
