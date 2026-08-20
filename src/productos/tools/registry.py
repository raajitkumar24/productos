from productos.domain.atlassian import ConfluenceSearchIntent, JiraSearchIntent
from productos.domain.tools import (
    ToolDefinition,
    ToolRisk,
    ToolSensitivity,
)


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition] | None = None) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"Tool {definition.name} is already registered")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def list(self) -> list[ToolDefinition]:
        return sorted(self._definitions.values(), key=lambda item: item.name)


def _object_schema(
    properties: dict[str, object] | None = None, required: list[str] | None = None
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


_STRING = {"type": "string", "minLength": 1}
_JIRA_INTENT = JiraSearchIntent.model_json_schema()
_CONFLUENCE_INTENT = ConfluenceSearchIntent.model_json_schema()


def _read_tool(
    name: str,
    capability: str,
    description: str,
    input_schema: dict[str, object],
    timeout: float = 20,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        capability=capability,
        provider="atlassian",
        input_schema=input_schema,
        output_schema={"type": "object"},
        risk_level=ToolRisk.LOW,
        read_only=True,
        requires_confirmation=False,
        idempotent=True,
        timeout_seconds=timeout,
        sensitivity=ToolSensitivity.INTERNAL,
        required_permissions={"atlassian:read"},
    )


def atlassian_tool_registry() -> ToolRegistry:
    tools = [
        _read_tool(
            "atlassian.list_sites",
            "atlassian.site.resolve",
            "List accessible sites.",
            _object_schema(),
        ),
        _read_tool(
            "jira.search_issues",
            "jira.search",
            "Search Jira from structured intent.",
            _object_schema(
                {"cloud_id": _STRING, "intent": _JIRA_INTENT},
                ["cloud_id", "intent"],
            ),
        ),
        _read_tool(
            "jira.get_issue",
            "jira.issue.read",
            "Read one Jira issue.",
            _object_schema({"cloud_id": _STRING, "issue_id": _STRING}, ["cloud_id", "issue_id"]),
        ),
        _read_tool(
            "jira.get_issue_history",
            "jira.issue.history",
            "Read issue history.",
            _object_schema({"cloud_id": _STRING, "issue_id": _STRING}, ["cloud_id", "issue_id"]),
        ),
        _read_tool(
            "jira.get_comments",
            "jira.issue.comments",
            "Read issue comments.",
            _object_schema({"cloud_id": _STRING, "issue_id": _STRING}, ["cloud_id", "issue_id"]),
        ),
        _read_tool(
            "jira.get_linked_issues",
            "jira.issue.links",
            "Read linked issues.",
            _object_schema({"cloud_id": _STRING, "issue_id": _STRING}, ["cloud_id", "issue_id"]),
        ),
        _read_tool(
            "jira.get_project",
            "jira.project.read",
            "Read a Jira project.",
            _object_schema(
                {"cloud_id": _STRING, "project_key": _STRING},
                ["cloud_id", "project_key"],
            ),
        ),
        _read_tool(
            "jira.get_sprint",
            "jira.sprint.read",
            "Read a Jira sprint.",
            _object_schema({"cloud_id": _STRING, "sprint_id": _STRING}, ["cloud_id", "sprint_id"]),
        ),
        _read_tool(
            "confluence.search",
            "confluence.search",
            "Search Confluence safely.",
            _object_schema(
                {"cloud_id": _STRING, "intent": _CONFLUENCE_INTENT},
                ["cloud_id", "intent"],
            ),
        ),
        _read_tool(
            "confluence.get_page",
            "confluence.page.read",
            "Read a Confluence page.",
            _object_schema({"cloud_id": _STRING, "page_id": _STRING}, ["cloud_id", "page_id"]),
        ),
        _read_tool(
            "confluence.get_page_history",
            "confluence.page.history",
            "Read Confluence page history.",
            _object_schema({"cloud_id": _STRING, "page_id": _STRING}, ["cloud_id", "page_id"]),
        ),
        _read_tool(
            "confluence.get_space",
            "confluence.space.read",
            "Read a space.",
            _object_schema({"cloud_id": _STRING, "space_key": _STRING}, ["cloud_id", "space_key"]),
        ),
        _read_tool(
            "atlassian.search",
            "atlassian.search",
            "Search Jira and Confluence.",
            _object_schema(
                {
                    "cloud_id": _STRING,
                    "jira_intent": _JIRA_INTENT,
                    "confluence_intent": _CONFLUENCE_INTENT,
                },
                ["cloud_id"],
            ),
        ),
    ]
    return ToolRegistry(tools)
