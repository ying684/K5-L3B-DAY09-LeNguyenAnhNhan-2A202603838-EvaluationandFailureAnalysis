from lab8.db import connect
from lab8.durability import InjectedCrash, committed_audit_count, get_refund, issue_refund


def test_retry_same_amount_is_one_row(public_db):
    conn = connect(public_db)
    first = issue_refund(conn, "C-001", 35000)
    second = issue_refund(conn, "C-001", 35000)
    effect = get_refund(conn, "C-001")
    audits = committed_audit_count(conn, "C-001")
    conn.close()
    assert first["reason"] == "committed"
    assert second["reason"] == "idempotent_replay"
    assert int(effect["amount_vnd"]) == 35000
    assert effect["idempotency_key"] == "refund:C-001"
    assert audits == 1


def test_retry_different_amount_conflicts_and_keeps_committed(public_db):
    conn = connect(public_db)
    issue_refund(conn, "C-001", 35000)
    second = issue_refund(conn, "C-001", 10000)
    effect = get_refund(conn, "C-001")
    conn.close()
    assert second["conflict"] is True
    assert int(effect["amount_vnd"]) == 35000


def test_crash_after_effect_before_checkpoint_resumes_once(public_db):
    conn = connect(public_db)
    try:
        issue_refund(conn, "C-011", 35000, crash_at="after_effect_before_checkpoint")
        raised = False
    except InjectedCrash:
        raised = True
    assert raised
    assert get_refund(conn, "C-011") is not None
    missing_checkpoint = conn.execute(
        "SELECT 1 FROM checkpoints WHERE claim_id = 'C-011'"
    ).fetchone()
    assert missing_checkpoint is None
    replay = issue_refund(conn, "C-011", 35000)
    count = conn.execute("SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-011'").fetchone()["n"]
    conn.close()
    assert replay["reason"] == "idempotent_replay"
    assert count == 1
    assert committed_audit_count_safe(public_db) == 1


def committed_audit_count_safe(store) -> int:
    conn = connect(store)
    try:
        return committed_audit_count(conn, "C-011")
    finally:
        conn.close()
