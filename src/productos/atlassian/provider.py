from datetime import UTC, datetime
from typing import Any

from productos.application.ports import MCPClient
from productos.atlassian.query import build_cql, build_jql
from productos.domain.atlassian import (
    AtlassianRecord,
    AtlassianSite,
    ConfluencePage,
    ConfluenceSearchIntent,
    JiraIssue,
    JiraSearchIntent,
    SourceReference,
)
from productos.domain.tools import PermissionContext


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


class AtlassianReadProvider:
    def __init__(self, client: MCPClient, tool_map: dict[str, str] | None = None) -> None:
        self._client = client
        self._tool_map = tool_map or {}

    async def execute(
        self, tool_name: str, arguments: dict[str, object], context: PermissionContext
    ) -> object:
        payload = dict(arguments)
        if tool_name == "jira.search_issues":
            intent = JiraSearchIntent.model_validate(payload.pop("intent"))
            payload.update(jql=build_jql(intent), limit=intent.limit)
        elif tool_name == "confluence.search":
            intent = ConfluenceSearchIntent.model_validate(payload.pop("intent"))
            payload.update(cql=build_cql(intent), limit=intent.limit)
        remote_name = self._tool_map.get(tool_name, tool_name)
        raw = await self._client.call_tool("atlassian", remote_name, payload)
        return self._normalize(tool_name, raw, context)

    def _normalize(self, tool_name: str, raw: object, context: PermissionContext) -> object:
        data = raw if isinstance(raw, dict) else {}
        if tool_name == "atlassian.list_sites":
            return [AtlassianSite.model_validate(item) for item in data.get("sites", [])]
        if tool_name == "atlassian.search":
            return {
                "issues": [self._issue(item, context) for item in data.get("issues", [])],
                "pages": [self._page(item, context) for item in data.get("pages", [])],
            }
        if tool_name == "jira.search_issues":
            return [self._issue(item, context) for item in data.get("issues", [])]
        if tool_name == "jira.get_issue":
            item = data.get("issue", data)
            return (
                self._issue(item, context) if isinstance(item, dict) and item.get("key") else None
            )
        if tool_name.startswith("jira.get_"):
            return self._records(data, tool_name, context)
        if tool_name == "confluence.search":
            return [self._page(item, context) for item in data.get("pages", [])]
        if tool_name == "confluence.get_page":
            item = data.get("page", data)
            return (
                self._page(item, context)
                if isinstance(item, dict) and item.get("page_id")
                else None
            )
        if tool_name.startswith("confluence.get_"):
            return self._records(data, tool_name, context)
        return self._records(data, tool_name, context)

    def _records(
        self, data: dict[str, Any], record_type: str, context: PermissionContext
    ) -> list[AtlassianRecord]:
        raw_records = data.get("results", [])
        if not isinstance(raw_records, list):
            raw_records = [raw_records]
        records: list[AtlassianRecord] = []
        for index, item in enumerate(raw_records):
            if not isinstance(item, dict):
                continue
            record_id = str(item.get("id") or item.get("key") or index)
            records.append(
                AtlassianRecord(
                    record_type=record_type,
                    record_id=record_id,
                    title=str(item.get("title") or item.get("name") or record_id),
                    content=item.get("content") or item.get("body") or item.get("description"),
                    source=self._source(item, record_type, record_id, context),
                    metadata={
                        key: value
                        for key, value in item.items()
                        if key in {"status", "type", "created_at", "updated_at", "author"}
                    },
                )
            )
        return records

    @staticmethod
    def _source(
        item: dict[str, Any], source_type: str, source_id: str, context: PermissionContext
    ) -> SourceReference:
        return SourceReference(
            source_type=source_type,
            source_id=source_id,
            title=str(item.get("title") or source_id),
            url=item.get("url"),
            cloud_id=str(item.get("cloud_id") or context.workspace_id or "unknown"),
            retrieved_at=datetime.now(UTC),
            updated_at=_datetime(item.get("updated_at")),
            authority=float(item.get("authority", 0.8)),
            access_boundary=f"tenant:{context.tenant_id}:user:{context.user_id}",
        )

    def _issue(self, item: dict[str, Any], context: PermissionContext) -> JiraIssue:
        key = str(item["key"])
        return JiraIssue(
            key=key,
            title=str(item.get("title") or item.get("summary") or key),
            description=item.get("description"),
            issue_type=item.get("issue_type"),
            status=item.get("status"),
            priority=item.get("priority"),
            assignee=item.get("assignee"),
            reporter=item.get("reporter"),
            project=str(item.get("project") or key.split("-", 1)[0]),
            parent=item.get("parent"),
            epic=item.get("epic"),
            labels=list(item.get("labels", [])),
            created_at=_datetime(item.get("created_at")),
            updated_at=_datetime(item.get("updated_at")),
            resolution=item.get("resolution"),
            links=list(item.get("links", [])),
            source=self._source(item, "jira_issue", key, context),
            metadata=dict(item.get("metadata", {})),
        )

    def _page(self, item: dict[str, Any], context: PermissionContext) -> ConfluencePage:
        page_id = str(item["page_id"])
        return ConfluencePage(
            page_id=page_id,
            title=str(item.get("title") or page_id),
            content=str(item.get("content") or ""),
            space=str(item.get("space") or ""),
            author=item.get("author"),
            owner=item.get("owner"),
            created_at=_datetime(item.get("created_at")),
            updated_at=_datetime(item.get("updated_at")),
            parent_page_id=item.get("parent_page_id"),
            labels=list(item.get("labels", [])),
            version=item.get("version"),
            source=self._source(item, "confluence_page", page_id, context),
            metadata=dict(item.get("metadata", {})),
        )
