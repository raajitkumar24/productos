from typing import TypedDict


class EvaluationCatalog(TypedDict):
    milestone: int
    suite: str
    case_count: int
    primary_metric: str
    catalog_status: str
    execution_status: str


CATALOGS: list[EvaluationCatalog] = [
    {
        "milestone": 0,
        "suite": "runtime foundation",
        "case_count": 2,
        "primary_metric": "runtime contract",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
    {
        "milestone": 1,
        "suite": "persistent memory",
        "case_count": 15,
        "primary_metric": "memory safety",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
    {
        "milestone": 2,
        "suite": "evidence retrieval",
        "case_count": 20,
        "primary_metric": "citation accuracy",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
    {
        "milestone": 3,
        "suite": "Atlassian tool use",
        "case_count": 30,
        "primary_metric": "tool selection accuracy",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
    {
        "milestone": 4,
        "suite": "product intelligence",
        "case_count": 50,
        "primary_metric": "grounded output rate",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
    {
        "milestone": 5,
        "suite": "management intelligence",
        "case_count": 60,
        "primary_metric": "false management signal rate",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
    {
        "milestone": 6,
        "suite": "proactive leadership",
        "case_count": 30,
        "primary_metric": "proactive noise rate",
        "catalog_status": "validated",
        "execution_status": "not persisted",
    },
]


def evaluation_catalogs() -> dict[str, object]:
    return {
        "catalogs": CATALOGS,
        "total_cases": sum(item["case_count"] for item in CATALOGS),
        "quality_results_available": False,
        "limitation": (
            "Catalog structure is validated by automated tests. Quality pass rates and "
            "LLM-as-Judge results are not persisted, so ProductOS does not report them."
        ),
    }
