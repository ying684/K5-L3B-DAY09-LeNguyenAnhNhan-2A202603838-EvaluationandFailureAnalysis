"""Trace files are part of the security boundary. Do not write raw parent context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, run_id: str, directory: str | Path = "traces") -> None:
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []
        self.directory = Path(directory)
        self.path = self.directory / f"{run_id}.json"

    def add(self, kind: str, payload: dict[str, Any]) -> None:
        self.events.append({"kind": kind, "payload": payload})

    def dump(self) -> str:
        return json.dumps({"run_id": self.run_id, "events": self.events}, ensure_ascii=False)

    def write(self) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        body = {
            "run_id": self.run_id,
            "steps": len(self.events),
            "events": self.events,
        }
        self.path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(self.path)
