import re
from dataclasses import dataclass
from uuid import UUID

from productos.domain.atlassian import (
    AtlassianSite,
    ConfluencePage,
    ConfluenceSearchIntent,
    CoverageStatus,
    CurrentState,
    JiraIssue,
    JiraSearchIntent,
    RequirementCoverage,
    RetrievalStrategy,
    SpecExecutionComparison,
)
from productos.domain.knowledge import (
    Citation,
    EvidenceAvailability,
    EvidenceItem,
    EvidencePacket,
    KnowledgeSearchRequest,
)
from productos.domain.tools import PermissionContext, ToolCallStatus, ToolErrorCode
from productos.retrieval.service import HybridRetrievalService
from productos.tools.engine import ToolExecutor


class SiteSelectionError(Exception):
    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class AtlassianSiteResolver:
    def __init__(self, tools: ToolExecutor) -> None:
        self._tools = tools

    async def resolve(
        self, run_id: UUID, context: PermissionContext, cloud_id: str | None = None
    ) -> AtlassianSite:
        result = await self._tools.execute(run_id, "atlassian.list_sites", {}, context)
        if result.status != ToolCallStatus.SUCCEEDED:
            raise SiteSelectionError(
                result.error_code or ToolErrorCode.TOOL_UNAVAILABLE,
                result.message or "Atlassian sites could not be resolved.",
            )
        sites = result.data if isinstance(result.data, list) else []
        if cloud_id:
            matches = [site for site in sites if site.cloud_id == cloud_id]
            if len(matches) == 1:
                return matches[0]
            raise SiteSelectionError(
                ToolErrorCode.AUTHORIZATION_FAILED,
                "The requested Atlassian site is not accessible.",
            )
        if len(sites) == 1:
            return sites[0]
        if not sites:
            raise SiteSelectionError(
                ToolErrorCode.NO_RESULTS, "No accessible Atlassian sites were returned."
            )
        raise SiteSelectionError(
            ToolErrorCode.SITE_SELECTION_REQUIRED,
            "Multiple Atlassian sites are accessible; select a site explicitly.",
        )


class FreshnessPlanner:
    def choose(self, query: str) -> RetrievalStrategy:
        terms = set(re.findall(r"[a-z0-9]+", query.casefold()))
        if terms & {"current", "currently", "blocked", "blocker", "status", "sprint", "now"}:
            return RetrievalStrategy.INDEX_PLUS_LIVE
        if terms & {"decided", "remember", "preference"}:
            return RetrievalStrategy.MEMORY_ONLY
        return RetrievalStrategy.INDEX_PLUS_LIVE


@dataclass
class OrganizationResult:
    current_state: CurrentState
    evidence: EvidencePacket
    tool_calls: list[dict[str, object]]


class OrganizationService:
    def __init__(
        self,
        tools: ToolExecutor,
        sites: AtlassianSiteResolver,
        indexed: HybridRetrievalService | None = None,
        freshness: FreshnessPlanner | None = None,
    ) -> None:
        self._tools = tools
        self._sites = sites
        self._indexed = indexed
        self._freshness = freshness or FreshnessPlanner()

    async def search(
        self,
        run_id: UUID,
        query: str,
        context: PermissionContext,
        cloud_id: str | None = None,
    ) -> EvidencePacket:
        """Return normalized cross-system evidence through the same bounded workflow."""
        result = await self.current_state(run_id, query, context, cloud_id)
        return result.evidence

    async def current_state(
        self,
        run_id: UUID,
        topic: str,
        context: PermissionContext,
        cloud_id: str | None = None,
    ) -> OrganizationResult:
        strategy = self._freshness.choose(topic)
        unknowns: list[str] = []
        issues: list[JiraIssue] = []
        pages: list[ConfluencePage] = []
        calls: list[dict[str, object]] = []
        indexed_packet = EvidencePacket(
            question=topic,
            availability=EvidenceAvailability.NO_EVIDENCE_FOUND,
            known_unknowns=["The indexed knowledge search was not configured."],
        )
        if self._indexed and strategy in {
            RetrievalStrategy.INDEX_ONLY,
            RetrievalStrategy.INDEX_PLUS_LIVE,
        }:
            indexed_packet = await self._indexed.search(
                KnowledgeSearchRequest(query=topic), context.tenant_id, context.user_id
            )
        try:
            site = await self._sites.resolve(run_id, context, cloud_id)
            live_context = context.model_copy(update={"workspace_id": site.cloud_id})
            jira = await self._tools.execute(
                run_id,
                "jira.search_issues",
                {
                    "cloud_id": site.cloud_id,
                    "intent": JiraSearchIntent(text=[topic], limit=50).model_dump(mode="json"),
                },
                live_context,
            )
            calls.append(self._call_summary(jira))
            if jira.status == ToolCallStatus.SUCCEEDED and isinstance(jira.data, list):
                issues = jira.data
            else:
                unknowns.append(jira.message or "Live Jira evidence could not be retrieved.")
            confluence = await self._tools.execute(
                run_id,
                "confluence.search",
                {
                    "cloud_id": site.cloud_id,
                    "intent": ConfluenceSearchIntent(text=[topic], limit=25).model_dump(
                        mode="json"
                    ),
                },
                live_context,
            )
            calls.append(self._call_summary(confluence))
            if confluence.status == ToolCallStatus.SUCCEEDED and isinstance(confluence.data, list):
                pages = confluence.data
            else:
                unknowns.append(
                    confluence.message or "Live Confluence evidence could not be retrieved."
                )
        except SiteSelectionError as exc:
            unknowns.append(exc.safe_message)

        evidence = self._merge_evidence(topic, indexed_packet, pages, issues, unknowns)
        statuses = sorted({issue.status for issue in issues if issue.status})
        owners = sorted({issue.assignee for issue in issues if issue.assignee})
        blockers = [
            f"{issue.key}: {issue.title}"
            for issue in issues
            if (issue.status or "").casefold() in {"blocked", "impeded"}
            or "blocked" in issue.labels
        ]
        open_work = [
            f"{issue.key}: {issue.title} ({issue.status or 'status unknown'})"
            for issue in issues
            if (issue.status or "").casefold() not in {"done", "closed", "resolved"}
        ]
        recent = [
            f"{issue.key} updated {issue.updated_at.isoformat()}"
            for issue in issues
            if issue.updated_at
        ]
        state = CurrentState(
            topic=topic,
            definition=pages[0].content[:1_000] if pages else None,
            product_status=pages[0].title if pages else None,
            implementation_status=", ".join(statuses) if statuses else None,
            owners=owners,
            open_work=open_work,
            blockers=blockers,
            recent_changes=recent[:10],
            unknowns=unknowns + evidence.known_unknowns,
            sources=[*([page.source for page in pages]), *([issue.source for issue in issues])],
            strategy=strategy,
        )
        return OrganizationResult(current_state=state, evidence=evidence, tool_calls=calls)

    async def compare_spec_execution(
        self,
        run_id: UUID,
        page_id: str,
        context: PermissionContext,
        cloud_id: str | None = None,
        projects: list[str] | None = None,
    ) -> SpecExecutionComparison:
        site = await self._sites.resolve(run_id, context, cloud_id)
        live_context = context.model_copy(update={"workspace_id": site.cloud_id})
        page_result = await self._tools.execute(
            run_id,
            "confluence.get_page",
            {"cloud_id": site.cloud_id, "page_id": page_id},
            live_context,
        )
        if page_result.status != ToolCallStatus.SUCCEEDED or not isinstance(
            page_result.data, ConfluencePage
        ):
            raise SiteSelectionError(
                page_result.error_code or ToolErrorCode.NO_RESULTS,
                page_result.message or "The specification page could not be retrieved.",
            )
        page = page_result.data
        requirements = self._requirements(page.content)
        issue_result = await self._tools.execute(
            run_id,
            "jira.search_issues",
            {
                "cloud_id": site.cloud_id,
                "intent": JiraSearchIntent(
                    projects=projects or [], text=requirements[:20], limit=100
                ).model_dump(mode="json"),
            },
            live_context,
        )
        issues = issue_result.data if issue_result.status == ToolCallStatus.SUCCEEDED else []
        issues = issues if isinstance(issues, list) else []
        coverage = [self._coverage(requirement, issues) for requirement in requirements]
        unknowns: list[str] = []
        if not requirements:
            unknowns.append("No explicit requirements were extracted from the specification.")
        if issue_result.status != ToolCallStatus.SUCCEEDED:
            unknowns.append(issue_result.message or "Jira execution evidence was unavailable.")
        return SpecExecutionComparison(
            spec_page_id=page.page_id,
            spec_title=page.title,
            requirements=coverage,
            unknowns=unknowns,
            sources=[page.source, *[issue.source for issue in issues]],
        )

    @staticmethod
    def _requirements(content: str) -> list[str]:
        requirements = []
        for line in content.splitlines():
            match = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", line)
            if match:
                value = match.group(1).strip()
                if value and value not in requirements:
                    requirements.append(value)
        return requirements[:50]

    @staticmethod
    def _coverage(requirement: str, issues: list[JiraIssue]) -> RequirementCoverage:
        terms = set(re.findall(r"[a-z0-9]+", requirement.casefold()))
        matches = []
        for issue in issues:
            issue_terms = set(
                re.findall(r"[a-z0-9]+", f"{issue.title} {issue.description or ''}".casefold())
            )
            if len(terms & issue_terms) / max(1, len(terms)) >= 0.35:
                matches.append(issue)
        if not matches:
            return RequirementCoverage(
                requirement=requirement,
                status=CoverageStatus.NO_EVIDENCE,
                explanation=(
                    "No matching Jira execution evidence was found; implementation is unknown."
                ),
            )
        states = {(issue.status or "").casefold() for issue in matches}
        mapped = set()
        for state in states:
            if state in {"done", "closed", "resolved"}:
                mapped.add(CoverageStatus.IMPLEMENTED)
            elif state in {"in progress", "blocked", "impeded"}:
                mapped.add(CoverageStatus.IN_PROGRESS)
            else:
                mapped.add(CoverageStatus.PLANNED)
        status = mapped.pop() if len(mapped) == 1 else CoverageStatus.AMBIGUOUS
        return RequirementCoverage(
            requirement=requirement,
            status=status,
            issue_keys=[issue.key for issue in matches],
            evidence=[issue.source for issue in matches],
            explanation=(
                "Coverage is classified from matching Jira evidence and its current status."
            ),
        )

    @staticmethod
    def _call_summary(result: object) -> dict[str, object]:
        return {
            "tool_name": getattr(result, "tool_name", "unknown"),
            "status": getattr(result, "status", "unknown"),
            "error_code": getattr(result, "error_code", None),
            "result_count": getattr(result, "result_count", 0),
            "latency_ms": getattr(result, "latency_ms", 0),
        }

    @staticmethod
    def _merge_evidence(
        topic: str,
        indexed: EvidencePacket,
        pages: list[ConfluencePage],
        issues: list[JiraIssue],
        unknowns: list[str],
    ) -> EvidencePacket:
        evidence = [item.model_copy(deep=True) for item in indexed.evidence]
        citations = [item.model_copy(deep=True) for item in indexed.citations]
        for source, content in [
            *[(page.source, page.content) for page in pages],
            *[
                (
                    issue.source,
                    f"{issue.key}: {issue.title}. Status: {issue.status or 'unknown'}. "
                    f"{issue.description or ''}".strip(),
                )
                for issue in issues
            ],
        ]:
            evidence_id = f"E{len(evidence) + 1}"
            evidence.append(
                EvidenceItem(
                    id=evidence_id,
                    topic=topic,
                    content=content,
                    source_type=source.source_type,
                    source_id=source.source_id,
                    title=source.title,
                    url=source.url,
                    authority=source.authority,
                    relevance=0.85,
                    freshness=1.0,
                    confidence=0.8,
                    source_updated_at=source.updated_at,
                )
            )
            citations.append(
                Citation(
                    citation_id=evidence_id,
                    source_type=source.source_type,
                    source_id=source.source_id,
                    title=source.title,
                    url=source.url,
                    excerpt=content[:500],
                    source_updated_at=source.updated_at,
                )
            )
        known_unknowns = [
            item
            for item in [*unknowns, *indexed.known_unknowns]
            if "not configured" not in item or not evidence
        ]
        coverage: dict[str, int] = {}
        for item in evidence:
            coverage[item.source_type] = coverage.get(item.source_type, 0) + 1
        return EvidencePacket(
            question=topic,
            availability=(
                EvidenceAvailability.EVIDENCE_FOUND
                if evidence
                else EvidenceAvailability.NO_EVIDENCE_FOUND
            ),
            evidence=evidence,
            contradictions=indexed.contradictions,
            known_unknowns=known_unknowns,
            source_coverage=coverage,
            citations=citations,
        )
