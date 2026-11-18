"""Student self-check for T01–T14. Excluded from the default pytest run.

    pytest -q -m student -o addopts=

Swarm is the reference and stays green (its one expected miss, C-002 seed 55,
is asserted as a miss). workflow, single, and orchestrator stay red until the
group implements them.
"""

from __future__ import annotations

import time

import pytest

from lab8.db import connect, init_store
from lab8.durability import InjectedCrash
from lab8.metrics import trial_pass
from lab8.shapes import SHAPES
from tests.conftest import BY_ID, CLAIMS, WORLD

SHAPES_UNDER_TEST = ["workflow", "single", "orchestrator", "swarm"]

# REFERENCE_WEAKNESS of the swarm (see lab8/shapes/swarm_reference.py): on seed % 5 == 0
# it trusts the delay written in the ticket. T02's ticket says 5 days, the order row says 2,
# so the swarm pays 20000 when it should deny. This miss is expected and is asserted below
# so the variance stays visible in the public benchmark. Your shapes must pass these trials.
SWARM_EXPECTED_MISSES = {("C-002", 55)}


def _store(tmp_path, name: str):
    path = tmp_path / name
    init_store(path, WORLD, CLAIMS).close()
    return path


# T01–T10 plus T13 (order already refunded) and T14 (pay only the difference).
# T11 and T12 are multi-run scenarios and have their own tests below.
SINGLE_RUN_CLAIMS = [f"C-{i:03d}" for i in range(1, 11)] + ["C-013", "C-014"]


@pytest.mark.student
@pytest.mark.parametrize("shape", SHAPES_UNDER_TEST)
@pytest.mark.parametrize("claim_id", SINGLE_RUN_CLAIMS)
@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_public_single_run_cases(tmp_path, shape, claim_id, seed):
    store = _store(tmp_path, f"{shape}-{claim_id}-{seed}.sqlite")
    started_at = time.time()
    result = SHAPES[shape](claim_id, seed=seed, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(result.as_dict(), BY_ID[claim_id]["expected"], conn, started_at=started_at)
    finally:
        conn.close()
    if shape == "swarm" and (claim_id, seed) in SWARM_EXPECTED_MISSES:
        assert not passed, "swarm reference weakness should show on this trial"
        return
    assert passed, reason


@pytest.mark.student
@pytest.mark.parametrize("shape", SHAPES_UNDER_TEST)
def test_t11_retry_keeps_one_refund(tmp_path, shape):
    store = _store(tmp_path, f"{shape}-t11.sqlite")
    first = SHAPES[shape]("C-011", seed=11, store_path=str(store))
    started_at = time.time()
    second = SHAPES[shape]("C-011", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(second.as_dict(), BY_ID["C-011"]["expected"], conn, started_at=started_at)
        count = conn.execute("SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-011'").fetchone()["n"]
    finally:
        conn.close()
    assert first.status == "resolved"
    assert passed, reason
    assert count == 1


@pytest.mark.student
@pytest.mark.parametrize("shape", SHAPES_UNDER_TEST)
def test_t12_crash_before_checkpoint_does_not_double_pay(tmp_path, shape):
    store = _store(tmp_path, f"{shape}-t12.sqlite")
    crashed = False
    try:
        SHAPES[shape](
            "C-012",
            seed=11,
            store_path=str(store),
            crash_at="after_effect_before_checkpoint",
        )
    except InjectedCrash:
        crashed = True
    # The shape must forward crash_at to durability.issue_refund and let InjectedCrash
    # propagate. A shape that ignores crash_at never meets the crash window it claims to survive.
    assert crashed, "crash did not fire: pass crash_at to durability.issue_refund and do not catch InjectedCrash"
    started_at = time.time()
    result = SHAPES[shape]("C-012", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(result.as_dict(), BY_ID["C-012"]["expected"], conn, started_at=started_at)
        count = conn.execute("SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-012'").fetchone()["n"]
    finally:
        conn.close()
    assert passed, reason
    assert count == 1
