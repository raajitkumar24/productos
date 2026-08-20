from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from productos.atlassian.query import build_cql, build_jql
from productos.domain.atlassian import ConfluenceSearchIntent, JiraSearchIntent

EVAL_PATH = Path(__file__).parents[1] / "evals" / "tools" / "milestone_3_atlassian.yaml"
EVAL_DATA = yaml.safe_load(EVAL_PATH.read_text())
EVAL_CASES = EVAL_DATA["cases"]


@pytest.mark.parametrize("case", EVAL_CASES, ids=[case["id"] for case in EVAL_CASES])
def test_structured_atlassian_query_eval(case: dict[str, object]) -> None:
    kind = str(case["kind"])
    values = {key: value for key, value in case.items() if key not in {"id", "kind", "expected"}}
    if kind == "jira_invalid":
        with pytest.raises(ValidationError):
            JiraSearchIntent.model_validate(values)
        return
    if kind == "confluence_invalid":
        with pytest.raises(ValidationError):
            ConfluenceSearchIntent.model_validate(values)
        return
    if kind == "jira":
        query = build_jql(JiraSearchIntent.model_validate(values))
    else:
        query = build_cql(ConfluenceSearchIntent.model_validate(values))
    assert str(case["expected"]) in query
    assert len(query) < 5_000


def test_atlassian_eval_catalog_covers_tool_metrics() -> None:
    assert len(EVAL_CASES) == 30
    assert set(EVAL_DATA["metrics"]) == {
        "argument_accuracy",
        "permission_compliance",
        "failure_transparency",
        "MCP_task_completion",
    }
