from lab8.metrics import summarize


def test_pass5_and_population_variance_and_cost():
    trials = []
    for seed in (11, 22):
        for claim_id, passed in (("A", True), ("B", seed == 11)):
            trials.append(
                {
                    "shape": "workflow",
                    "claim_id": claim_id,
                    "seed": seed,
                    "passed": passed,
                    "cost_estimate": 10.0,
                    "steps": 2,
                    "model_calls": 1,
                    "tool_calls": 3,
                }
            )
    stats = summarize(trials)["workflow"]
    assert stats["pass_rate"] == 0.75
    assert stats["pass_5"] == 0.5
    assert stats["seed_min"] == 0.5
    assert stats["seed_max"] == 1.0
    # seed rates 1.0 and 0.5, mean 0.75 -> population variance 0.0625 (sample variance would be 0.125)
    assert stats["seed_variance"] == 0.0625
    assert stats["cost_per_success_vnd"] == 40 / 3
    assert stats["latency"] == "unavailable"
    assert stats["cost_note"] == "simulated_not_real_api_price"
