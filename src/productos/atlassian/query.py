from productos.domain.atlassian import ConfluenceSearchIntent, JiraSearchIntent


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_jql(intent: JiraSearchIntent) -> str:
    clauses: list[str] = []
    if intent.projects:
        clauses.append("project IN (" + ", ".join(_quote(value) for value in intent.projects) + ")")
    if intent.text:
        clauses.append(" AND ".join(f"text ~ {_quote(value)}" for value in intent.text))
    if intent.statuses:
        clauses.append("status IN (" + ", ".join(_quote(value) for value in intent.statuses) + ")")
    if intent.issue_types:
        clauses.append(
            "issuetype IN (" + ", ".join(_quote(value) for value in intent.issue_types) + ")"
        )
    if intent.owners:
        clauses.append("assignee IN (" + ", ".join(_quote(value) for value in intent.owners) + ")")
    if intent.updated_after:
        clauses.append(f"updated >= {_quote(intent.updated_after.isoformat())}")
    return (" AND ".join(f"({clause})" for clause in clauses) or "order by updated DESC") + (
        " ORDER BY updated DESC" if clauses else ""
    )


def build_cql(intent: ConfluenceSearchIntent) -> str:
    clauses: list[str] = ['type = "page"']
    if intent.spaces:
        clauses.append("space IN (" + ", ".join(_quote(value) for value in intent.spaces) + ")")
    if intent.text:
        clauses.append(" AND ".join(f"text ~ {_quote(value)}" for value in intent.text))
    if intent.labels:
        clauses.append(" AND ".join(f"label = {_quote(value)}" for value in intent.labels))
    if intent.contributors:
        clauses.append(
            " AND ".join(f"contributor = {_quote(value)}" for value in intent.contributors)
        )
    if intent.updated_after:
        clauses.append(f"lastmodified >= {_quote(intent.updated_after.isoformat())}")
    return " AND ".join(f"({clause})" for clause in clauses) + " ORDER BY lastmodified DESC"
