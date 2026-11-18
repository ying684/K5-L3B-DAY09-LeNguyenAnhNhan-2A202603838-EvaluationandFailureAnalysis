"""Runner shared by the CLI, benchmark, and smoke test."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from lab8.config_loader import repo_path
from lab8.db import init_store, load_json, load_jsonl
from lab8.schemas import RunResult
from lab8.shapes import SHAPES

PUBLIC_WORLD = repo_path("data", "public_world_state.json")
PUBLIC_CLAIMS = repo_path("data", "public_claims.jsonl")


def prepare_store(
    store_path: str | Path,
    world_path: str | Path = PUBLIC_WORLD,
    claims_path: str | Path = PUBLIC_CLAIMS,
    extra_claims: list[dict[str, Any]] | None = None,
) -> None:
    world = load_json(world_path)
    claims = load_jsonl(claims_path)
    if extra_claims:
        claims = claims + extra_claims
    init_store(store_path, world, claims).close()


def register_extra_shapes(specs: list[str]) -> list[str]:
    """Register bonus variants for this process only: ["name=package.module:function", ...].

    The four official shapes stay fixed in lab8.shapes.SHAPES. Extra names are added
    at runtime so a variant runs under the same claims, seeds, prices, and evaluator.
    """
    names = []
    for spec in specs:
        name, sep, target = spec.partition("=")
        module_name, colon, func_name = target.partition(":")
        if not (sep and colon and name and module_name and func_name):
            raise SystemExit(f"--extra-shape expects name=package.module:function, got {spec!r}")
        if name in SHAPES:
            raise SystemExit(f"--extra-shape name {name!r} already exists")
        SHAPES[name] = getattr(importlib.import_module(module_name), func_name)
        names.append(name)
    return names


def run_shape(
    shape: str,
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    if shape not in SHAPES:
        raise SystemExit(f"unknown shape {shape!r}; choose from {', '.join(SHAPES)}")
    return SHAPES[shape](claim_id, seed=seed, store_path=str(store_path), crash_at=crash_at)
