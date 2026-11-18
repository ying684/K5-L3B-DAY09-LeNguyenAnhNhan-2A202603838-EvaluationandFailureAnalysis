"""SQLite world + ledger. One store per trial unless the test is a retry."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  status TEXT NOT NULL,
  delay_days INTEGER NOT NULL,
  shipping_fee_vnd INTEGER NOT NULL,
  paid_vnd INTEGER NOT NULL,
  damage_verified INTEGER NOT NULL,
  carrier TEXT NOT NULL,
  phone TEXT NOT NULL,
  address TEXT NOT NULL,
  internal_note TEXT NOT NULL,
  item_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policies (
  policy_id TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  is_current INTEGER NOT NULL,
  effective_date TEXT NOT NULL,
  superseded_by TEXT,
  clauses_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  order_id TEXT,
  ticket TEXT NOT NULL,
  parent_secret TEXT NOT NULL,
  raw_headers_json TEXT NOT NULL,
  approval_id TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL,
  approved_vnd INTEGER NOT NULL,
  status TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refund_ledger (
  claim_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL,
  amount_vnd INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status = 'committed')
);
CREATE TABLE IF NOT EXISTS audit_events (
  audit_key TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
  claim_id TEXT NOT NULL,
  step TEXT NOT NULL,
  result_json TEXT NOT NULL,
  PRIMARY KEY (claim_id, step)
);
"""


def connect(store_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(store_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_store(
    store_path: str | Path,
    world: dict[str, Any],
    claims: list[dict[str, Any]],
) -> sqlite3.Connection:
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        ("as_of", str(world.get("as_of", ""))),
    )
    for order in world["orders"]:
        conn.execute(
            """
            INSERT INTO orders (
              order_id, principal_id, status, delay_days, shipping_fee_vnd,
              paid_vnd, damage_verified, carrier, phone, address, internal_note, item_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["order_id"],
                order["principal_id"],
                order["status"],
                int(order["delay_days"]),
                int(order["shipping_fee_vnd"]),
                int(order["paid_vnd"]),
                1 if order["damage_verified"] else 0,
                order["carrier"],
                order["phone"],
                order["address"],
                order["internal_note"],
                order["item_name"],
            ),
        )
    for policy in world["policies"]:
        conn.execute(
            """
            INSERT INTO policies (
              policy_id, version, is_current, effective_date, superseded_by, clauses_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                policy["policy_id"],
                policy["version"],
                1 if policy["is_current"] else 0,
                policy["effective_date"],
                policy.get("superseded_by"),
                json.dumps(policy["clauses"], ensure_ascii=False),
            ),
        )
    for claim in claims:
        conn.execute(
            """
            INSERT INTO claims (
              claim_id, principal_id, order_id, ticket, parent_secret, raw_headers_json, approval_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim["claim_id"],
                claim["principal_id"],
                claim.get("order_id"),
                claim["ticket"],
                claim["parent_secret"],
                json.dumps(claim.get("raw_headers") or {}, ensure_ascii=False),
                claim.get("approval_id"),
            ),
        )
    for approval in world["approvals"]:
        conn.execute(
            """
            INSERT INTO approvals (approval_id, claim_id, approved_vnd, status, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                approval["approval_id"],
                approval["claim_id"],
                int(approval["approved_vnd"]),
                approval["status"],
                approval["expires_at"],
            ),
        )
    # Refunds already paid before this run (earlier claims on the same order).
    # They let one fresh trial test the per-order cap without running two claims.
    prior = world.get("prior_refunds") or []
    for refund in prior:
        conn.execute(
            """
            INSERT INTO refund_ledger (claim_id, order_id, idempotency_key, amount_vnd, status)
            VALUES (?, ?, ?, ?, 'committed')
            """,
            (
                refund["claim_id"],
                refund["order_id"],
                f"refund:{refund['claim_id']}",
                int(refund["amount_vnd"]),
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_events (audit_key, claim_id, event_type, details_json)
            VALUES (?, ?, 'refund_committed', ?)
            """,
            (
                f"refund_committed:{refund['claim_id']}",
                refund["claim_id"],
                json.dumps({"amount_vnd": int(refund["amount_vnd"]), "prior": True}, ensure_ascii=False),
            ),
        )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        ("prior_refund_rows", str(len(prior))),
    )
    conn.commit()
    return conn


def load_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
