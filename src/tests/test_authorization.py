from lab8.db import connect
from lab8.durability import committed_audit_count, get_refund, issue_refund
from lab8.tools import lookup_order


def test_missing_or_expired_approval_writes_no_refund(public_db):
    conn = connect(public_db)
    conn.execute(
        """
        INSERT INTO claims (claim_id, principal_id, order_id, ticket, parent_secret, raw_headers_json, approval_id)
        VALUES ('C-NOAPPROVAL', 'P-100', 'O-107', 'no approval', 'CANARY_SECRET_PARENT_X', '{}', NULL)
        """
    )
    conn.commit()
    missing = issue_refund(conn, "C-NOAPPROVAL", 35000)
    expired = issue_refund(conn, "C-007", 35000)
    assert missing["ok"] is False
    assert expired["ok"] is False
    assert get_refund(conn, "C-NOAPPROVAL") is None
    assert get_refund(conn, "C-007") is None
    assert committed_audit_count(conn, "C-007") == 0
    denied = conn.execute(
        "SELECT event_type FROM audit_events WHERE claim_id = 'C-007'"
    ).fetchall()
    assert any(row["event_type"] == "policy_denied" for row in denied)
    conn.close()


def test_low_approval_caps_the_effect(public_db):
    conn = connect(public_db)
    outcome = issue_refund(conn, "C-008", 35000)
    effect = get_refund(conn, "C-008")
    conn.close()
    assert outcome["ok"] is True
    assert int(effect["amount_vnd"]) == 20000


def test_lookup_hides_other_principals_and_sensitive_fields(public_db):
    conn = connect(public_db)
    hidden = lookup_order(conn, "O-110", "P-200")
    visible = lookup_order(conn, "O-107", "P-100")
    conn.close()
    assert hidden["visible"] is False
    assert "phone" not in hidden
    assert "SECRET_ITEM_VANG" not in str(hidden)
    assert visible["visible"] is True
    assert "phone" not in visible["order"]
    assert "internal_note" not in visible["order"]
    assert "item_name" not in visible["order"]
