from pathlib import Path

import yaml

CATALOG = Path("evals/management/milestone_5.yaml")


def test_management_eval_catalog_has_sixty_distinct_cases() -> None:
    suite = yaml.safe_load(CATALOG.read_text())
    cases = suite["cases"]

    assert suite["critical_metric"] == "false_management_signal_rate"
    assert suite["minimum_cases"] == 60
    assert len(cases) == 60
    assert len({case["id"] for case in cases}) == 60
    assert {case["category"] for case in cases} >= {
        "activity_bias",
        "attribution",
        "patterns",
        "corrections",
        "one_on_one",
        "pm_review",
        "weekly_review",
        "portfolio",
        "fairness",
    }


def test_management_eval_catalog_enforces_constitutional_failure_modes() -> None:
    suite = yaml.safe_load(CATALOG.read_text())
    expected = {case["expected"] for case in suite["cases"]}

    assert "no_score_or_rank_field" in expected
    assert "no_temporal_causality" in expected
    assert "no_performance_equivalence" in expected
    assert "require_independent_observations" in expected
    assert "challenge_requested_conclusion" in expected
    assert "positive_signal_with_limit" in expected
