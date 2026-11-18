"""python -m lab8.run --shape workflow --claim-id C-001 --seed 11 --db data/run.sqlite"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.app import prepare_store, run_shape
from lab8.console import utf8_stdio
from lab8.durability import InjectedCrash


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Run one LogiX-VN claim through one shape")
    parser.add_argument("--shape", required=True, choices=["workflow", "single", "orchestrator", "swarm"])
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--world", default=None)
    parser.add_argument("--cases", default=None)
    parser.add_argument("--crash-at", default=None, choices=[
        "before_effect",
        "after_effect_before_checkpoint",
        "after_checkpoint",
    ])
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        kwargs = {}
        if args.world:
            kwargs["world_path"] = args.world
        if args.cases:
            kwargs["claims_path"] = args.cases
        prepare_store(db_path, **kwargs)
    try:
        result = run_shape(
            args.shape,
            args.claim_id,
            seed=args.seed,
            store_path=str(db_path),
            crash_at=args.crash_at,
        )
    except InjectedCrash as exc:
        print(json.dumps({"crashed": True, "at": str(exc), "claim_id": args.claim_id}, ensure_ascii=False))
        return 2
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
