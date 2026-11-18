"""Host rules that span claims: per-order cap and approval bound to its own claim."""

from lab8.db import connect
from lab8.durability import committed_audit_count, get_refund, issue_refund
from lab8.metrics import trial_pass, unexpected_ledger_rows
from lab8.policy import order_refunded_vnd
from lab8.runtime import dispatch
from lab8.schemas import Budget
from lab8.tools import lookup_refund_history


def _add_claim(conn, claim_id, order_id, approval_id, *, principal="P-100"):
    conn.execute(
        """
        INSERT INTO claims (claim_id, principal_id, order_id, ticket, parent_secret, raw_headers_json, approval_id)
        VALUES (?, ?, ?, 'test', 'CANARY_SECRET_PARENT_T', '{}', ?)
        """,
        (claim_id, principal, order_id, approval_id),
    )


def _add_approval(conn, approval_id, claim_id, amount, status="valid", expires="2027-12-31"):
    conn.execute(
        "INSERT INTO approvals (approval_id, claim_id, approved_vnd, status, expires_at) VALUES (?, ?, ?, ?, ?)",
        (approval_id, claim_id, amount, status, expires),
    )


def _denials(conn, claim_id):
    rows = conn.execute(
        "SELECT details_json FROM audit_events WHERE claim_id = ? AND event_type = 'policy_denied'",
        (claim_id,),
    ).fetchall()
    return [row["details_json"] for row in rows]


def test_second_claim_on_the_same_order_pays_nothing(public_db):
    conn = connect(public_db)
    first = issue_refund(conn, "C-001", 35000)  # O-107
    second = issue_refund(conn, "C-010", 35000)  # also O-107
    total = order_refunded_vnd(conn, "O-107")
    denials = _denials(conn, "C-010")
    conn.close()
    assert first["ok"] is True
    assert second == {"ok": False, "reason": "order_already_refunded", "effect": None, "conflict": False}
    assert total == 35000
    assert any("order_already_refunded" in row for row in denials)


def test_seeded_prior_refund_blocks_t13_and_tops_up_t14(public_db):
    conn = connect(public_db)
    t13 = issue_refund(conn, "C-013", 35000)
    t14 = issue_refund(conn, "C-014", 150000)
    t14_effect = get_refund(conn, "C-014")
    o515_total = order_refunded_vnd(conn, "O-515")
    conn.close()
    assert t13["reason"] == "order_already_refunded"
    assert t14["ok"] is True
    assert int(t14_effect["amount_vnd"]) == 120000
    assert o515_total == 150000  # never more than the larger entitlement


def test_retry_of_the_paying_claim_is_still_idempotent(public_db):
    conn = connect(public_db)
    issue_refund(conn, "C-014", 150000)
    replay = issue_refund(conn, "C-014", 150000)
    audits = committed_audit_count(conn, "C-014")
    conn.close()
    assert replay["reason"] == "idempotent_replay"
    assert audits == 1


def test_order_total_is_rechecked_inside_the_write_transaction(public_db, monkeypatch):
    """Simulate another claim committing on the same order between the read and the write."""
    import lab8.durability as durability

    conn = connect(public_db)
    real = durability.order_refunded_vnd
    calls = {"n": 0}

    def racing(conn_, order_id, *, exclude_claim_id=None):
        calls["n"] += 1
        if calls["n"] == 2:  # first check inside BEGIN IMMEDIATE
            conn_.execute(
                "INSERT INTO refund_ledger (claim_id, order_id, idempotency_key, amount_vnd, status) "
                "VALUES ('C-RACE', 'O-107', 'refund:C-RACE', 35000, 'committed')"
            )
        return real(conn_, order_id, exclude_claim_id=exclude_claim_id)

    monkeypatch.setattr(durability, "order_refunded_vnd", racing)
    outcome = issue_refund(conn, "C-001", 35000)
    total = real(conn, "O-107")
    conn.close()
    # The racing insert was rolled back with our transaction; the retry then pays once.
    assert outcome["ok"] is True
    assert total == 35000


def test_approval_issued_for_another_claim_is_rejected(public_db):
    conn = connect(public_db)
    _add_claim(conn, "C-BORROW", "O-808", "A-001")  # A-001 belongs to C-001
    conn.commit()
    outcome = issue_refund(conn, "C-BORROW", 35000)
    effect = get_refund(conn, "C-BORROW")
    denials = _denials(conn, "C-BORROW")
    conn.close()
    assert outcome["reason"] == "approval_claim_mismatch"
    assert effect is None
    assert any("approval_claim_mismatch" in row for row in denials)


def test_only_the_approval_the_claim_points_to_counts(public_db):
    """A second, valid approval row for the same claim does not rescue a revoked one."""
    conn = connect(public_db)
    _add_approval(conn, "A-REVOKED", "C-RV", 35000, status="revoked")
    _add_approval(conn, "A-SPARE", "C-RV", 35000, status="valid")
    _add_claim(conn, "C-RV", "O-909", "A-REVOKED")
    conn.commit()
    outcome = issue_refund(conn, "C-RV", 35000)
    conn.close()
    assert outcome["reason"] == "approval_revoked"


def test_refund_history_tool_is_scoped_and_read_only(public_db):
    conn = connect(public_db)
    own = lookup_refund_history(conn, "O-505", "P-100")
    other = lookup_refund_history(conn, "O-110", "P-200")
    via_dispatch = dispatch(
        conn, Budget(), "lookup_refund_history", {"order_id": "O-515", "principal_id": "P-100"}, worker=True
    )
    conn.close()
    assert own == {"visible": True, "reason": "ok", "order_id": "O-505", "refund_count": 1, "refunded_vnd": 35000}
    assert other == {"visible": False, "reason": "outside_principal_scope"}
    assert via_dispatch["refunded_vnd"] == 30000


def test_grader_fails_a_shape_that_pays_under_another_claim_id(public_db):
    from tests.conftest import BY_ID

    conn = connect(public_db)
    assert unexpected_ledger_rows(conn, "C-002") == 0
    conn.execute(
        "INSERT INTO refund_ledger (claim_id, order_id, idempotency_key, amount_vnd, status) "
        "VALUES ('C-SIDE', 'O-202', 'refund:C-SIDE', 20000, 'committed')"
    )
    conn.commit()
    result = {
        "claim_id": "C-002",
        "status": "denied",
        "proposal_amount": 0,
        "refund_effects": [],
        "committed_audit_count": 0,
        "trace_path": "",
    }
    passed, reason = trial_pass(result, BY_ID["C-002"]["expected"], conn)
    conn.close()
    assert (passed, reason) == (False, "unexpected_ledger_rows")
