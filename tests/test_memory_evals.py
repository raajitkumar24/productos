from pathlib import Path
from uuid import UUID

import pytest
import yaml

from productos.memory.extraction import ExplicitMemoryExtractor

EVAL_PATH = Path(__file__).parents[1] / "evals" / "memory" / "milestone_1.yaml"
EVAL_CASES = yaml.safe_load(EVAL_PATH.read_text())["cases"]
EVAL_USER = UUID("00000000-0000-4000-8000-000000000001")


@pytest.mark.parametrize("case", EVAL_CASES, ids=[case["id"] for case in EVAL_CASES])
def test_memory_extraction_eval(case: dict[str, object]) -> None:
    results = ExplicitMemoryExtractor().extract(EVAL_USER, str(case["input"]), case["id"])

    assert len(results) == case["expected_count"]
    if results:
        assert results[0].memory_type == case["expected_type"]
        assert results[0].memory_key == case["expected_key"]
