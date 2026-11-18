"""Unsafe refund used only as a classroom demo.

The official ledger keys one row per claim. This demo table does not, so a
crash between the side effect and the checkpoint pays twice. Do not copy it
into a shape.
"""

from __future__ import annotations

import sqlite3

from lab8.console import utf8_stdio


def demo_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE demo_unsafe_refunds (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          claim_id TEXT NOT NULL,
          amount_vnd INTEGER NOT NULL,
          checkpointed INTEGER NOT NULL
        )
        """
    )
    return conn


def buggy_pay(conn: sqlite3.Connection, claim_id: str, amount: int) -> None:
    conn.execute(
        "INSERT INTO demo_unsafe_refunds (claim_id, amount_vnd, checkpointed) VALUES (?, ?, 0)",
        (claim_id, amount),
    )
    conn.commit()
    # Crash window: effect is durable, checkpoint flag is still 0.
    # A resume that only looks at checkpointed=1 inserts again.
    already = conn.execute(
        "SELECT COUNT(*) FROM demo_unsafe_refunds WHERE claim_id = ? AND checkpointed = 1",
        (claim_id,),
    ).fetchone()[0]
    if already:
        return
    conn.execute(
        "INSERT INTO demo_unsafe_refunds (claim_id, amount_vnd, checkpointed) VALUES (?, ?, 0)",
        (claim_id, amount),
    )
    conn.execute(
        "UPDATE demo_unsafe_refunds SET checkpointed = 1 WHERE claim_id = ?",
        (claim_id,),
    )
    conn.commit()


def main() -> int:
    utf8_stdio()
    conn = demo_connection()
    buggy_pay(conn, "C-001", 35000)
    count = conn.execute("SELECT COUNT(*) FROM demo_unsafe_refunds").fetchone()[0]
    conn.close()
    print(f"unsafe refund rows: {count} (the host ledger must stay at 1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
