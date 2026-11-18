"""Load pinned lab config from the repo root."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def repo_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


@lru_cache(maxsize=8)
def load_yaml(relative: str) -> dict[str, Any]:
    with repo_path(relative).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{relative} did not contain a mapping")
    return data


def as_of() -> str:
    return str(load_yaml("config/autonomy_policy.yaml")["as_of"])


def pricing() -> dict[str, Any]:
    return load_yaml("config/pricing.yaml")
