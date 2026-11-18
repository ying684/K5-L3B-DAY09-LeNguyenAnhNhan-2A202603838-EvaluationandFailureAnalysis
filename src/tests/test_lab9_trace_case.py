import pytest

pytestmark = pytest.mark.student


@pytest.mark.parametrize(("shape", "expected_pass", "expected_refund"), [
    ("seeded_regression", False, 20000),
    ("fixed", True, 0),
])
def test_ticket_cannot_override_order_delay(shape, expected_pass, expected_refund):
    from lab9.trace_case import investigate

    trial = investigate(shape, "C-002", 11)["trial"]
    assert trial["lab8_pass"] is expected_pass
    assert trial["snapshot"]["refund_vnd"] == expected_refund
    assert any(e["kind"] == "model_override" for e in trial["events"]) is (not expected_pass)
