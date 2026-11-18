from lab8.compensation import quote
from lab8.config_loader import as_of
from lab8.db import connect, init_store
from lab8.tools import get_clause, lookup_policy
from tests.conftest import CLAIMS, WORLD


def _policies():
    return lookup_policy_from_fixture()


def lookup_policy_from_fixture():
    current = [row for row in WORLD["policies"] if row["is_current"]]
    return current


def _order(**kwargs):
    base = {
        "status": "delivered",
        "delay_days": 0,
        "shipping_fee_vnd": 35000,
        "paid_vnd": 250000,
        "damage_verified": False,
    }
    base.update(kwargs)
    return base


def test_late_boundary_and_stacking_and_cancelled():
    policies = _policies()
    today = as_of()
    late = quote(_order(delay_days=4), policies, as_of=today)
    assert late.amount_vnd == 35000
    early = quote(_order(delay_days=2), policies, as_of=today)
    assert early.amount_vnd == 0
    edge = quote(_order(delay_days=3, shipping_fee_vnd=22000), policies, as_of=today)
    assert edge.amount_vnd == 22000
    damage = quote(_order(damage_verified=True, paid_vnd=40000), policies, as_of=today)
    assert damage.amount_vnd == 40000
    both = quote(
        _order(delay_days=4, shipping_fee_vnd=20000, damage_verified=True, paid_vnd=300000),
        policies,
        as_of=today,
    )
    assert both.amount_vnd == 150000
    assert both.parts["SHIP-LATE-03"] == 20000
    cancelled = quote(_order(status="cancelled", delay_days=9), policies, as_of=today)
    assert cancelled.amount_vnd == 0
    transit = quote(_order(status="in_transit", delay_days=6), policies, as_of=today)
    assert transit.amount_vnd == 0


def test_quote_ignores_superseded_policy_even_if_passed_in():
    today = as_of()
    result = quote(_order(delay_days=2, paid_vnd=300000), WORLD["policies"], as_of=today)
    assert result.amount_vnd == 0
    assert "SHIP-LATE-OLD" not in result.parts


def test_get_clause_still_returns_old_clause(tmp_path):
    store = tmp_path / "c.sqlite"
    init_store(store, WORLD, CLAIMS).close()
    conn = connect(store)
    old = get_clause(conn, "SHIP-LATE-OLD")
    current = lookup_policy(conn)
    conn.close()
    assert old["found"] is True
    assert old["is_current"] is False
    assert [row["policy_id"] for row in current["policies"]] == ["POL-2026-11"]
