import pytest

from lab8.db import connect
from lab8.handoff import HandoffError, make_handoff, sanitize
from lab8.runtime import ToolRejected, dispatch, run_react
from lab8.schemas import Budget
from lab8.tools import get_claim_view


def test_allowlist_drops_parent_secret_and_headers():
    payload = {
        "contract_version": "handoff.v1",
        "request_id": "REQ-1",
        "claim_id": "C-010",
        "principal_scope": "owner_order_only",
        "task": "check_applicable_policy",
        "facts": {"delay_days": 4, "carrier": "LOGIX_LOCAL"},
        "allowed_tools": ["lookup_policy"],
        "max_output_tokens": 400,
        "parent_secret": "CANARY_SECRET_PARENT_C010",
        "raw_headers": {"Authorization": "Bearer CANARY_SECRET_PARENT_C010"},
        "history": ["full chat"],
    }
    cleaned = sanitize(payload)
    assert "parent_secret" not in cleaned
    assert "CANARY_SECRET_" not in str(cleaned)
    assert set(cleaned) <= {
        "contract_version",
        "request_id",
        "claim_id",
        "principal_scope",
        "task",
        "facts",
        "allowed_tools",
        "max_output_tokens",
    }


def test_worker_cannot_receive_issue_refund():
    with pytest.raises(HandoffError):
        make_handoff(
            request_id="REQ-2",
            claim_id="C-001",
            task="pay",
            facts={},
            allowed_tools=["issue_refund"],
        )


def test_claim_view_and_react_observation_omit_secret(public_db):
    conn = connect(public_db)
    view = get_claim_view(conn, "C-010")
    assert "CANARY_SECRET_" not in str(view)
    budget = Budget()

    def decide(obs):
        return {"final": {"status": "denied"}}

    outcome = run_react(conn, budget, observation={"claim": view}, decide=decide, max_steps=8, worker=True)
    with pytest.raises(ToolRejected):
        dispatch(conn, budget, "issue_refund", {"claim_id": "C-010"}, worker=True)
    conn.close()
    assert outcome["stopped"] == "final"
    assert "CANARY_SECRET_" not in str(outcome)
