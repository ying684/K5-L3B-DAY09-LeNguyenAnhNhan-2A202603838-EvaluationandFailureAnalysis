import pytest

from lab8.db import connect
from lab8.metrics import trial_pass
from lab8.shapes.swarm_reference import run_claim
from tests.conftest import BY_ID


@pytest.mark.parametrize(
    "claim_id",
    ["C-001", "C-002", "C-003", "C-004", "C-005", "C-006", "C-007", "C-008", "C-009", "C-010", "C-013", "C-014"],
)
def test_reference_swarm_passes_published_traps(public_db, claim_id):
    result = run_claim(claim_id, seed=11, store_path=str(public_db))
    conn = connect(public_db)
    try:
        passed, reason = trial_pass(result.as_dict(), BY_ID[claim_id]["expected"], conn)
    finally:
        conn.close()
    assert passed, reason


def test_reference_weakness_is_visible_on_public_t02(tmp_path):
    """Seed 55 trusts the ticket (5 days) over the order row (2 days) and pays.

    This keeps the variance the lab asks students to measure visible on the public set.
    """
    from lab8.db import init_store
    from tests.conftest import CLAIMS, WORLD

    outcomes = {}
    for seed in (11, 55):
        store = tmp_path / f"t02-{seed}.sqlite"
        init_store(store, WORLD, CLAIMS).close()
        result = run_claim("C-002", seed=seed, store_path=str(store))
        conn = connect(store)
        try:
            outcomes[seed] = trial_pass(result.as_dict(), BY_ID["C-002"]["expected"], conn)[0]
        finally:
            conn.close()
    assert outcomes == {11: True, 55: False}
