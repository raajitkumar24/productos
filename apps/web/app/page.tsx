"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type View = "Home" | "Chat" | "Work" | "Research" | "Initiatives" | "Team" | "Attention" | "Memory" | "Decisions" | "Evaluations" | "Settings";
type WorkflowKind = "deep_research" | "product_strategy" | "product_review" | "spec_execution" | "experiment_design" | "decision_memo" | "prepare_one_on_one" | "pm_review" | "weekly_management_review" | "portfolio_review";
type Message = { role: "user" | "assistant"; content: string };
type Run = { id: string; status: "idle" | "running" | "complete" | "error" };
type Memory = {
  id: string;
  memory_type: string;
  content: string;
  summary: string | null;
  confidence: number;
  importance: number;
  status: string;
  provenance_type: string;
  source_type: string;
  memory_key: string | null;
  created_at: string;
  updated_at: string;
};
type WorkSession = {
  id: string;
  title: string;
  objective: string;
  workflow_type: string;
  status: string;
  open_questions: string[];
  hypotheses: string[];
  artifact_ids: string[];
  updated_at: string;
};
type Decision = {
  id: string;
  title: string;
  problem: string;
  decision: string;
  rationale: string;
  status: string;
  review_trigger: string | null;
  updated_at: string;
};
type CompleteData = {
  run_id: string;
  conversation_id: string;
  memory_updates: { memory_id: string; outcome: string }[];
};
type EvidenceItem = {
  id: string;
  content: string;
  source_type: string;
  source_id: string;
  title: string;
  url: string | null;
  section_title: string | null;
  authority: number;
  relevance: number;
  freshness: number;
  confidence: number;
  source_updated_at: string | null;
};
type EvidencePacket = {
  availability: string;
  evidence: EvidenceItem[];
  contradictions: { evidence_ids: [string, string]; description: string; confidence: number; likely_current_evidence_id: string | null; inference_rationale: string | null }[];
  known_unknowns: string[];
  source_coverage: Record<string, number>;
};
type ToolSummary = { tool_name: string; status: string; error_code: string | null; result_count: number; latency_ms: number };
type ToolDefinition = { name: string; capability: string; provider: string; read_only: boolean; requires_confirmation: boolean; risk_level: string; required_permissions: string[] };
type AtlassianSite = { cloud_id: string; site_url: string; site_name: string; user_identity: string | null; accessible_projects: string[]; accessible_spaces: string[] };
type Artifact = {
  id: string;
  artifact_type: string;
  title: string;
  structured_data: Record<string, unknown>;
  rendered_content: string;
  workflow_name: WorkflowKind;
  workflow_version: string;
  status: string;
  source_ids: string[];
  created_at: string;
};
type HealthDimension = { dimension: string; state: string; confidence: string; explanation: string; evidence_ids: string[] };
type Initiative = { id: string; name: string; description: string; problem: string; owner_ids: string[]; status: string; health: HealthDimension[]; updated_at: string };
type ManagementSignal = { id: string; signal_type: string; subject_type: string; subject_id: string; epistemic_level: string; observation: string; interpretation: string | null; recommendation: string | null; evidence_ids: string[]; confidence: string; significance: string; limitations: string[]; status: string };
type PMProfile = { pm_id: string; responsibilities: string[]; observed_strengths: ManagementSignal[]; coaching_opportunities: ManagementSignal[]; risks: ManagementSignal[]; limitations: string[] };
type AttentionItem = { id: string; management_signal_id: string; subject_type: string; subject_id: string; level: string; why_surfaced: string; evidence_ids: string[]; confidence: string; limitations: string[]; recommended_next_step: string };
type ProactiveNotification = { id: string; title: string; body: string; level: string; confidence: string; evidence_ids: string[]; limitations: string[]; recommended_next_step: string; status: string; created_at: string };
type NotificationPreferences = { enabled: boolean; in_app_enabled: boolean; daily_brief_enabled: boolean; weekly_brief_enabled: boolean; decision_reminders_enabled: boolean; risk_alerts_enabled: boolean; minimum_level: string; maximum_per_day: number; timezone: string };
type ProactiveSchedule = { id: string; kind: string; frequency: string; enabled: boolean; timezone: string; local_time: string; next_run_at: string; last_run_at: string | null };
type DecisionDebt = { decision_id: string; title: string; debt_type: string; severity: string; next_review_action: string; limitation: string | null };
type HomeData = { things_needing_attention: ManagementSignal[]; recent_wins: ManagementSignal[]; upcoming_decisions: DecisionDebt[]; notifications: ProactiveNotification[]; latest_brief: Artifact | null; limitations: string[] };
type EvaluationData = { catalogs: { milestone: number; suite: string; case_count: number; primary_metric: string; catalog_status: string; execution_status: string }[]; total_cases: number; quality_results_available: boolean; limitation: string };
type EvaluationRun = { id: string; dataset_name: string; dataset_version: string; status: string; subject_model: string; judge_model: string; total_cases: number; passed_cases: number; failed_cases: number; error_cases: number; pass_rate: number | null; limitation: string; created_at: string };
type EvaluationRunDetail = { run: EvaluationRun; cases: { id: string; agent_run_id: string | null; external_id: string; category: string; input_text: string; expected_behaviors: string[]; forbidden_behaviors: string[]; actual_output: string; judgment: { score: number; criteria: Record<string, number>; critical_failure: boolean; reasoning_summary: string; missing_elements: string[] } | null; status: string; error_code: string | null }[] };
type OidcDiscovery = { issuer: string; authorization_endpoint: string; token_endpoint: string };

const implemented: View[] = ["Home", "Chat", "Work", "Research", "Initiatives", "Team", "Attention", "Memory", "Decisions", "Evaluations", "Settings"];
const laterItems: string[] = [];
const suggestions = ["What is the current state of our launch?", "Review a PRD", "Think through a decision"];
const navIcons: Record<View, string> = {
  Home: "⌂",
  Chat: "✦",
  Work: "▦",
  Research: "⌕",
  Initiatives: "◇",
  Team: "◎",
  Attention: "!",
  Memory: "◫",
  Decisions: "✓",
  Evaluations: "◈",
  Settings: "⚙",
};

function parseSseBlock(block: string): { event: string; data: Record<string, unknown> } | null {
  const lines = block.split("\n");
  const event = lines.find((line) => line.startsWith("event: "))?.slice(7);
  const rawData = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!event || !rawData) return null;
  return { event, data: JSON.parse(rawData) as Record<string, unknown> };
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function statusLabel(value: string) {
  return value.replaceAll("_", " ");
}

function randomUrlSafe(bytes = 32) {
  const value = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...value)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function pkceChallenge(verifier: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return btoa(String.fromCharCode(...new Uint8Array(digest))).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export default function ProductOS() {
  const [view, setView] = useState<View>("Home");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [run, setRun] = useState<Run>({ id: "", status: "idle" });
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [memoryNotice, setMemoryNotice] = useState("");
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryType, setMemoryType] = useState("all");
  const [memoryStatus, setMemoryStatus] = useState("all");
  const [work, setWork] = useState<WorkSession[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(false);
  const [workTitle, setWorkTitle] = useState("");
  const [workObjective, setWorkObjective] = useState("");
  const [evidence, setEvidence] = useState<EvidencePacket | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolSummary[]>([]);
  const [toolDefinitions, setToolDefinitions] = useState<ToolDefinition[]>([]);
  const [connectionStatus, setConnectionStatus] = useState("unknown");
  const [atlassianSites, setAtlassianSites] = useState<AtlassianSite[]>([]);
  const [selectedSite, setSelectedSite] = useState("");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [workflowKind, setWorkflowKind] = useState<WorkflowKind>("deep_research");
  const [workflowObjective, setWorkflowObjective] = useState("");
  const [workflowSource, setWorkflowSource] = useState("");
  const [workflowPageId, setWorkflowPageId] = useState("");
  const [workflowSessionId, setWorkflowSessionId] = useState("");
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [team, setTeam] = useState<PMProfile[]>([]);
  const [attention, setAttention] = useState<AttentionItem[]>([]);
  const [initiativeName, setInitiativeName] = useState("");
  const [initiativeProblem, setInitiativeProblem] = useState("");
  const [initiativeOwner, setInitiativeOwner] = useState("");
  const [home, setHome] = useState<HomeData | null>(null);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [schedules, setSchedules] = useState<ProactiveSchedule[]>([]);
  const [proactiveBusy, setProactiveBusy] = useState(false);
  const [evaluations, setEvaluations] = useState<EvaluationData | null>(null);
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRun[]>([]);
  const [selectedEvaluation, setSelectedEvaluation] = useState<EvaluationRunDetail | null>(null);
  const [evaluationTrace, setEvaluationTrace] = useState<Record<string, unknown> | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  const apiUrl = useMemo(() => process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000", []);
  const [userId, setUserId] = useState(process.env.NEXT_PUBLIC_PRODUCTOS_USER_ID ?? "00000000-0000-4000-8000-000000000001");
  const [tenantId, setTenantId] = useState(process.env.NEXT_PUBLIC_PRODUCTOS_TENANT_ID ?? "00000000-0000-4000-8000-000000000010");
  const authEnabled = process.env.NEXT_PUBLIC_PRODUCTOS_AUTH_ENABLED === "true";
  const oidcAuthority = process.env.NEXT_PUBLIC_OIDC_AUTHORITY ?? "";
  const oidcClientId = process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "";
  const oidcScope = process.env.NEXT_PUBLIC_OIDC_SCOPE ?? "openid profile productos:api";

  async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
    const headers = new Headers(init.headers);
    const token = accessToken ?? (typeof window !== "undefined" ? window.sessionStorage.getItem("productos.access_token") : null);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    try {
      const response = await fetch(input, { ...init, headers });
      if (authEnabled && response.status === 401) signOut();
      if (response.ok) setApiError("");
      else if (response.status >= 500) setApiError(`The ProductOS API returned ${response.status}. Check the backend logs and configuration.`);
      return response;
    } catch {
      setApiError(`ProductOS cannot connect to the API at ${apiUrl}. Start the backend and confirm NEXT_PUBLIC_API_URL and CORS settings.`);
      return new Response(null, { status: 503, statusText: "ProductOS API unavailable" });
    }
  }

  async function discovery(): Promise<OidcDiscovery> {
    const response = await fetch(`${oidcAuthority.replace(/\/$/, "")}/.well-known/openid-configuration`);
    if (!response.ok) throw new Error("Identity provider discovery failed");
    const payload = await response.json() as OidcDiscovery;
    if (payload.issuer.replace(/\/$/, "") !== oidcAuthority.replace(/\/$/, "")) throw new Error("Identity provider issuer mismatch");
    return payload;
  }

  async function beginLogin() {
    const metadata = await discovery();
    const verifier = randomUrlSafe(48);
    const state = randomUrlSafe();
    window.sessionStorage.setItem("productos.pkce_verifier", verifier);
    window.sessionStorage.setItem("productos.oidc_state", state);
    const redirectUri = `${window.location.origin}${window.location.pathname}`;
    const url = new URL(metadata.authorization_endpoint);
    url.search = new URLSearchParams({ response_type: "code", client_id: oidcClientId, redirect_uri: redirectUri, scope: oidcScope, state, code_challenge: await pkceChallenge(verifier), code_challenge_method: "S256" }).toString();
    window.location.assign(url);
  }

  function signOut() {
    window.sessionStorage.removeItem("productos.access_token");
    window.sessionStorage.removeItem("productos.access_token_expires_at");
    setAccessToken(null);
  }

  useEffect(() => {
    if (!authEnabled) { setAuthLoading(false); return; }
    void (async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        let token = window.sessionStorage.getItem("productos.access_token");
        const expiresAt = Number(window.sessionStorage.getItem("productos.access_token_expires_at") ?? 0);
        if (token && expiresAt && Date.now() >= expiresAt) { signOut(); token = null; }
        if (params.has("code")) {
          const expectedState = window.sessionStorage.getItem("productos.oidc_state");
          if (!expectedState || params.get("state") !== expectedState) throw new Error("OIDC state mismatch");
          const verifier = window.sessionStorage.getItem("productos.pkce_verifier");
          if (!verifier) throw new Error("PKCE verifier missing");
          const metadata = await discovery();
          const response = await fetch(metadata.token_endpoint, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ grant_type: "authorization_code", code: String(params.get("code")), redirect_uri: `${window.location.origin}${window.location.pathname}`, client_id: oidcClientId, code_verifier: verifier }) });
          if (!response.ok) throw new Error("OIDC token exchange failed");
          const payload = await response.json() as { access_token: string; expires_in?: number };
          token = payload.access_token;
          window.sessionStorage.setItem("productos.access_token", token);
          window.sessionStorage.setItem("productos.access_token_expires_at", String(Date.now() + (payload.expires_in ?? 300) * 1000));
          window.sessionStorage.removeItem("productos.pkce_verifier");
          window.sessionStorage.removeItem("productos.oidc_state");
          window.history.replaceState({}, "", window.location.pathname);
        }
        setAccessToken(token);
        if (token) {
          const identity = await fetch(`${apiUrl}/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
          if (!identity.ok) { signOut(); return; }
          const principal = await identity.json() as { user_id: string; tenant_id: string };
          setUserId(principal.user_id); setTenantId(principal.tenant_id);
        }
      } catch {
        window.sessionStorage.removeItem("productos.access_token");
        window.sessionStorage.removeItem("productos.access_token_expires_at");
        setAccessToken(null);
      } finally { setAuthLoading(false); }
    })();
  }, [apiUrl, authEnabled, oidcAuthority, oidcClientId]);

  useEffect(() => {
    if (authEnabled && !accessToken) return;
    if (view === "Home") void loadHome();
    const stored = window.localStorage.getItem("productos.conversation_id");
    if (!stored) return;
    setConversationId(stored);
    apiFetch(`${apiUrl}/v1/sessions/${stored}?user_id=${userId}`)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((detail: { messages: Message[] }) => setMessages(detail.messages))
      .catch(() => window.localStorage.removeItem("productos.conversation_id"));
  }, [apiUrl, userId, tenantId, accessToken, authEnabled, view]);

  useEffect(() => {
    if (authEnabled && !accessToken) return;
    setSelectedSite(window.localStorage.getItem("productos.atlassian_cloud_id") ?? "");
  }, []);

  useEffect(() => {
    if (view === "Memory") void loadMemories();
    if (view === "Work") { void loadWork(); void loadArtifacts(); }
    if (view === "Research") { void loadArtifacts(); void loadWork(); }
    if (view === "Decisions") { void loadDecisions(); void loadArtifacts("decision_memo"); }
    if (view === "Initiatives") void loadInitiatives();
    if (view === "Team") void loadTeam();
    if (view === "Attention") void loadAttention();
    if (view === "Evaluations") void loadEvaluations();
    if (view === "Settings") { void loadTools(); void loadProactiveSettings(); }
  }, [view, memoryType, memoryStatus, accessToken, authEnabled, userId, tenantId]);

  async function loadHome() {
    setLoading(true);
    try {
      const response = await apiFetch(`${apiUrl}/v1/home?user_id=${userId}&tenant_id=${tenantId}`);
      setHome(response.ok ? await response.json() : null);
    } finally { setLoading(false); }
  }

  async function loadProactiveSettings() {
    const scope = `user_id=${userId}&tenant_id=${tenantId}`;
    const [preferencesResponse, schedulesResponse] = await Promise.all([
      apiFetch(`${apiUrl}/v1/proactive/preferences?${scope}`),
      apiFetch(`${apiUrl}/v1/proactive/schedules?${scope}`),
    ]);
    if (preferencesResponse.ok) setPreferences(await preferencesResponse.json());
    if (schedulesResponse.ok) setSchedules(await schedulesResponse.json());
  }

  async function loadEvaluations() {
    setLoading(true);
    try {
      const [catalogResponse, runsResponse] = await Promise.all([
        apiFetch(`${apiUrl}/v1/evaluations/catalogs`),
        apiFetch(`${apiUrl}/v1/evaluations?user_id=${userId}&tenant_id=${tenantId}`),
      ]);
      setEvaluations(catalogResponse.ok ? await catalogResponse.json() : null);
      setEvaluationRuns(runsResponse.ok ? await runsResponse.json() : []);
    } finally { setLoading(false); }
  }

  async function openEvaluation(runId: string) {
    const response = await apiFetch(`${apiUrl}/v1/evaluations/${runId}?user_id=${userId}&tenant_id=${tenantId}`);
    if (response.ok) setSelectedEvaluation(await response.json());
  }

  async function inspectEvaluationTrace(runId: string) {
    const response = await apiFetch(`${apiUrl}/v1/runs/${runId}/traces?user_id=${userId}&tenant_id=${tenantId}`);
    if (response.ok) setEvaluationTrace(await response.json());
  }

  async function updatePreferences(patch: Partial<NotificationPreferences>) {
    const response = await apiFetch(`${apiUrl}/v1/proactive/preferences?user_id=${userId}&tenant_id=${tenantId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
    });
    if (response.ok) setPreferences(await response.json());
  }

  async function createDefaultSchedules() {
    const nextRun = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    const definitions = [
      { kind: "daily_product_brief", frequency: "daily", local_time: "08:30:00" },
      { kind: "weekly_leadership_brief", frequency: "weekly", local_time: "08:30:00", weekday: 0 },
      { kind: "decision_review_scan", frequency: "daily", local_time: "09:00:00" },
      { kind: "risk_scan", frequency: "daily", local_time: "09:15:00" },
    ];
    await Promise.all(definitions.map((definition) => apiFetch(`${apiUrl}/v1/proactive/schedules`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...definition, enabled: false, timezone: preferences?.timezone ?? "UTC", next_run_at: nextRun, user_id: userId, tenant_id: tenantId }),
    })));
    await loadProactiveSettings();
  }

  async function toggleSchedule(schedule: ProactiveSchedule) {
    await apiFetch(`${apiUrl}/v1/proactive/schedules/${schedule.id}?user_id=${userId}&tenant_id=${tenantId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !schedule.enabled }),
    });
    await loadProactiveSettings();
  }

  async function generateDailyBrief() {
    setProactiveBusy(true);
    try {
      const response = await apiFetch(`${apiUrl}/v1/proactive/daily-brief`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, tenant_id: tenantId }),
      });
      if (response.ok) {
        const result = await response.json() as { artifact: Artifact };
        setSelectedArtifact(result.artifact);
        await loadHome();
      }
    } finally { setProactiveBusy(false); }
  }

  async function markNotificationRead(id: string) {
    await apiFetch(`${apiUrl}/v1/proactive/notifications/${id}?user_id=${userId}&tenant_id=${tenantId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "read" }),
    });
    await loadHome();
  }

  async function loadMemories() {
    setLoading(true);
    const params = new URLSearchParams({ user_id: userId });
    if (memoryType !== "all") params.set("memory_type", memoryType);
    if (memoryStatus !== "all") params.set("status", memoryStatus);
    try {
      const response = await apiFetch(`${apiUrl}/v1/memories?${params}`);
      setMemories(response.ok ? await response.json() : []);
    } finally {
      setLoading(false);
    }
  }

  async function loadWork() {
    setLoading(true);
    try {
      const response = await apiFetch(`${apiUrl}/v1/work?user_id=${userId}`);
      setWork(response.ok ? await response.json() : []);
    } finally {
      setLoading(false);
    }
  }

  async function loadDecisions() {
    setLoading(true);
    try {
      const response = await apiFetch(`${apiUrl}/v1/decisions?user_id=${userId}`);
      setDecisions(response.ok ? await response.json() : []);
    } finally {
      setLoading(false);
    }
  }

  async function loadTools() {
    setLoading(true);
    try {
      const toolsResponse = await apiFetch(`${apiUrl}/v1/tools`);
      if (toolsResponse.ok) {
        const payload = await toolsResponse.json() as { connection_status: string; tools: ToolDefinition[] };
        setConnectionStatus(payload.connection_status);
        setToolDefinitions(payload.tools);
        if (payload.connection_status === "read_enabled") {
          const sitesResponse = await apiFetch(`${apiUrl}/v1/atlassian/sites?user_id=${userId}&tenant_id=${tenantId}`);
          setAtlassianSites(sitesResponse.ok ? await sitesResponse.json() : []);
        } else {
          setAtlassianSites([]);
        }
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadArtifacts(type?: string) {
    const params = new URLSearchParams({ user_id: userId, tenant_id: tenantId });
    if (type) params.set("artifact_type", type);
    const response = await apiFetch(`${apiUrl}/v1/artifacts?${params}`);
    setArtifacts(response.ok ? await response.json() : []);
  }

  async function loadInitiatives() {
    setLoading(true);
    try {
      const response = await apiFetch(`${apiUrl}/v1/initiatives?user_id=${userId}&tenant_id=${tenantId}`);
      setInitiatives(response.ok ? await response.json() : []);
    } finally { setLoading(false); }
  }

  async function loadTeam() {
    setLoading(true);
    try {
      const response = await apiFetch(`${apiUrl}/v1/team?user_id=${userId}&tenant_id=${tenantId}`);
      setTeam(response.ok ? await response.json() : []);
    } finally { setLoading(false); }
  }

  async function loadAttention() {
    setLoading(true);
    try {
      await apiFetch(`${apiUrl}/v1/management/refresh?user_id=${userId}&tenant_id=${tenantId}`, { method: "POST" });
      const response = await apiFetch(`${apiUrl}/v1/attention?user_id=${userId}&tenant_id=${tenantId}`);
      setAttention(response.ok ? await response.json() : []);
    } finally { setLoading(false); }
  }

  async function createInitiative(event: FormEvent) {
    event.preventDefault();
    if (!initiativeName.trim()) return;
    const response = await apiFetch(`${apiUrl}/v1/initiatives`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: initiativeName, problem: initiativeProblem, owner_ids: initiativeOwner.trim() ? [initiativeOwner.trim()] : [], user_id: userId, tenant_id: tenantId }),
    });
    if (response.ok) { setInitiativeName(""); setInitiativeProblem(""); setInitiativeOwner(""); await loadInitiatives(); }
  }

  async function prepareOneOnOne(pmId: string) {
    const response = await apiFetch(`${apiUrl}/v1/management/one-on-one`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pm_id: pmId, weeks: 4, user_id: userId, tenant_id: tenantId }),
    });
    if (response.ok) setSelectedArtifact((await response.json() as { artifact: Artifact }).artifact);
  }

  async function correctSignal(item: AttentionItem, action: "confirm" | "add_context" | "disagree" | "dismiss" | "mark_outdated") {
    let context: string | null = null;
    if (action === "add_context" || action === "disagree") context = window.prompt("Add manager context. The original signal and this correction remain inspectable.")?.trim() ?? null;
    if ((action === "add_context" || action === "disagree") && !context) return;
    const response = await apiFetch(`${apiUrl}/v1/management/signals/${item.management_signal_id}/corrections?user_id=${userId}&tenant_id=${tenantId}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, context }),
    });
    if (response.ok) await loadAttention();
  }

  function chooseSite(cloudId: string) {
    setSelectedSite(cloudId);
    if (cloudId) window.localStorage.setItem("productos.atlassian_cloud_id", cloudId);
    else window.localStorage.removeItem("productos.atlassian_cloud_id");
  }

  async function submitChat(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || run.status === "running") return;

    setInput("");
    setMemoryNotice("");
    setEvidence(null);
    setEvidenceOpen(false);
    setToolCalls([]);
    setMessages((current) => [...current, { role: "user", content: message }, { role: "assistant", content: "" }]);
    setRun({ id: "", status: "running" });

    try {
      const response = await apiFetch(`${apiUrl}/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, user_id: userId, tenant_id: tenantId, conversation_id: conversationId, workspace_id: selectedSite || null }),
      });
      if (!response.ok || !response.body) throw new Error("API request failed");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const parsed = parseSseBlock(block);
          if (!parsed) continue;
          if (parsed.event === "run") {
            setRun({ id: String(parsed.data.run_id), status: "running" });
            const nextConversation = String(parsed.data.conversation_id);
            setConversationId(nextConversation);
            window.localStorage.setItem("productos.conversation_id", nextConversation);
          } else if (parsed.event === "tool") {
            setToolCalls(parsed.data.calls as ToolSummary[]);
          } else if (parsed.event === "evidence") {
            setEvidence(parsed.data as unknown as EvidencePacket);
          } else if (parsed.event === "delta") {
            setMessages((current) => {
              const next = [...current];
              const last = next.at(-1);
              if (last?.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + String(parsed.data.text) };
              }
              return next;
            });
          } else if (parsed.event === "complete") {
            const complete = parsed.data as CompleteData;
            setRun({ id: complete.run_id, status: "complete" });
            if (complete.memory_updates.length > 0) {
              const outcomes = complete.memory_updates.map((item) => statusLabel(item.outcome)).join(", ");
              setMemoryNotice(`Memory reviewed: ${outcomes}.`);
            }
          } else if (parsed.event === "error") {
            setRun({ id: String(parsed.data.run_id ?? ""), status: "error" });
            setMessages((current) => {
              const next = [...current];
              next[next.length - 1] = { role: "assistant", content: String(parsed.data.message) };
              return next;
            });
          }
        }
        if (done) break;
      }
    } catch {
      setRun({ id: "", status: "error" });
      setMessages((current) => {
        const next = [...current];
        next[next.length - 1] = {
          role: "assistant",
          content: "ProductOS could not reach the API. Check that the backend is running.",
        };
        return next;
      });
    }
  }

  function newConversation() {
    setConversationId(null);
    setMessages([]);
    setMemoryNotice("");
    setEvidence(null);
    setEvidenceOpen(false);
    setToolCalls([]);
    setRun({ id: "", status: "idle" });
    window.localStorage.removeItem("productos.conversation_id");
  }

  async function archiveMemory(memory: Memory) {
    await apiFetch(`${apiUrl}/v1/memories/${memory.id}?user_id=${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "archived" }),
    });
    await loadMemories();
  }

  async function correctMemory(memory: Memory) {
    const correction = window.prompt("Correct this memory. The prior version will be preserved.", memory.content)?.trim();
    if (!correction || correction === memory.content) return;
    await apiFetch(`${apiUrl}/v1/memories/${memory.id}?user_id=${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: correction }),
    });
    await loadMemories();
  }

  async function createWork(event: FormEvent) {
    event.preventDefault();
    if (!workTitle.trim() || !workObjective.trim()) return;
    const response = await apiFetch(`${apiUrl}/v1/work`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, title: workTitle, objective: workObjective, workflow_type: "general" }),
    });
    if (response.ok) {
      setWorkTitle("");
      setWorkObjective("");
      await loadWork();
    }
  }

  async function executeWorkflow(event: FormEvent) {
    event.preventDefault();
    if (!workflowObjective.trim() || workflowBusy) return;
    setWorkflowBusy(true);
    try {
      const payload: Record<string, unknown> = {
        workflow: workflowKind,
        objective: workflowObjective,
        user_id: userId,
        tenant_id: tenantId,
        workspace_id: selectedSite || null,
        working_session_id: workflowSessionId || null,
      };
      if (workflowKind === "product_review") payload.source_text = workflowSource;
      if (workflowKind === "spec_execution") payload.page_id = workflowPageId;
      const response = await apiFetch(`${apiUrl}/v1/workflows/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        const result = await response.json() as { artifact: Artifact };
        setSelectedArtifact(result.artifact);
        await loadArtifacts();
      }
    } finally {
      setWorkflowBusy(false);
    }
  }

  if (authEnabled && (authLoading || !accessToken)) {
    return (
      <main className="shell"><section className="workspace"><section className="emptyState">
        <p className="eyebrow">Secure ProductOS workspace</p>
        <h1>{authLoading ? "Verifying your session…" : "Sign in to ProductOS"}</h1>
        <p>Authentication uses Authorization Code with PKCE. The API independently validates the signed access token and binds its user and tenant claims.</p>
        {!authLoading && <button onClick={beginLogin} disabled={!oidcAuthority || !oidcClientId}>Sign in with your identity provider</button>}
      </section></section></main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brandMark">P</span><span className="brandText"><strong>ProductOS</strong><small>Product intelligence</small></span></div>
        <nav aria-label="Primary navigation">
          <p className="navLabel">Workspace</p>
          {implemented.map((item) => (
            <button className={item === view ? "navItem active" : "navItem"} key={item} onClick={() => setView(item)}>
              <span className="navIcon" aria-hidden="true">{navIcons[item]}</span>{item}
            </button>
          ))}
          {laterItems.map((item) => (
            <button className="navItem" key={item} disabled><span className="navIcon" aria-hidden="true">·</span>{item}<small>Later</small></button>
          ))}
        </nav>
        <div className="principle"><span className="principleIcon">◆</span><div><span>Operating principle</span><p>Evidence before recommendation.</p></div></div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">Product intelligence / {view}</p><h1>{view}</h1></div>
          <div className="topActions">
            {view === "Chat" && messages.length > 0 && <button className="quietButton" onClick={newConversation}>New conversation</button>}
            {authEnabled && <button className="quietButton" onClick={signOut}>Sign out</button>}
            <div className={`runtime ${run.status}`}><span />{run.status === "running" ? "Reasoning" : "Runtime 0.8"}</div>
          </div>
        </header>

        {apiError && (
          <div className="apiError" role="alert">
            <div><strong>API connection unavailable</strong><p>{apiError}</p></div>
            <button onClick={() => window.location.reload()}>Retry</button>
          </div>
        )}

        {view === "Home" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Product leadership brief</h2><p>A calm, evidence-backed view of documented changes. Missing data remains unknown, never a negative conclusion.</p></div><button onClick={generateDailyBrief} disabled={proactiveBusy}>{proactiveBusy ? "Generating…" : "Generate daily brief"}</button></div>
            {loading ? <p className="emptyList">Loading documented product state…</p> : !home ? <p className="emptyList">Documented product state is unavailable. Check the API connection notice above, then retry.</p> : <>
              <div className="profileColumns">
                <article className="dataCard"><h3>Needs attention</h3>{home.things_needing_attention.length ? home.things_needing_attention.map((item) => <div key={item.id}><p><strong>{item.observation}</strong></p><small>{item.confidence} confidence · {item.significance} significance · {item.evidence_ids.length} evidence refs</small></div>) : <p>No active high-significance documented signal.</p>}</article>
                <article className="dataCard"><h3>Recent wins</h3>{home.recent_wins.length ? home.recent_wins.map((item) => <p key={item.id}>{item.observation}</p>) : <p>No new evidenced win is documented.</p>}</article>
                <article className="dataCard"><h3>Upcoming decisions</h3>{home.upcoming_decisions.length ? home.upcoming_decisions.map((item) => <div key={`${item.decision_id}-${item.debt_type}`}><p><strong>{item.title}</strong> · {statusLabel(item.debt_type)}</p><small>{item.next_review_action}</small></div>) : <p>No decision review debt is documented.</p>}</article>
              </div>
              <div className="pageIntro"><div><h2>In-app notifications</h2><p>Only novel, material, sufficiently confident, actionable changes can appear here.</p></div><span className="count">{home.notifications.length} unread</span></div>
              {home.notifications.length ? <div className="cardList">{home.notifications.map((item) => <article className="dataCard attentionCard" key={item.id}><div className="cardHeader"><span className={`statusTag ${item.level}`}>{item.level}</span><span className="typeTag">{item.confidence} confidence</span></div><h3>{item.title}</h3><p>{item.body}</p><p><strong>Next step:</strong> {item.recommended_next_step}</p><p><strong>Evidence:</strong> {item.evidence_ids.join(", ")}</p><div className="limitations">{item.limitations.map((limit) => <p key={limit}>{limit}</p>)}</div><button className="quietButton" onClick={() => markNotificationRead(item.id)}>Mark read</button></article>)}</div> : <p className="emptyList">No unread proactive notification. ProductOS does not notify for unchanged or weakly supported state.</p>}
              {home.latest_brief && <button className="artifactCard" onClick={() => setSelectedArtifact(home.latest_brief)}><div><span className="typeTag">Latest brief</span><span className="statusTag draft">Draft</span></div><h3>{home.latest_brief.title}</h3><small>{home.latest_brief.source_ids.length} evidence references · Open inspectable artifact →</small></button>}
              <div className="limitations">{home.limitations.map((item) => <p key={item}>{item}</p>)}</div>
            </>}
          </section>
        )}

        {view === "Chat" && (
          <div className="conversation">
            {messages.length === 0 ? (
              <section className="emptyState">
                <p className="eyebrow">Milestone 6 · Proactive leadership support</p>
                <h2>What decision are you working through?</h2>
                <p>Ask across indexed product knowledge. Answers expose their sources, confidence, contradictions, and known unknowns.</p>
                <div className="suggestions">
                  {suggestions.map((suggestion) => <button key={suggestion} onClick={() => setInput(suggestion)}>{suggestion}<span>→</span></button>)}
                </div>
              </section>
            ) : (
              <div className="messages">
                {messages.map((message, index) => (
                  <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                    <div className="avatar">{message.role === "user" ? "You" : "P"}</div>
                    <div><p className="speaker">{message.role === "user" ? "You" : "ProductOS"}</p><p>{message.content || "Thinking…"}</p></div>
                  </article>
                ))}
              </div>
            )}
            <div className="composerWrap">
              {memoryNotice && <div className="memoryNotice">{memoryNotice}<button onClick={() => setView("Memory")}>Inspect memory →</button></div>}
              {run.id && <div className="traceLine"><span>Run {run.id.slice(0, 8)}</span><div>{toolCalls.length > 0 && <span className="toolCount">Tools {toolCalls.filter((call) => call.status === "succeeded").length}/{toolCalls.length}</span>}{evidence && <button className="evidenceButton" onClick={() => setEvidenceOpen(true)}>Evidence {evidence.evidence.length}</button>}<a href={`${apiUrl}/v1/runs/${run.id}/traces`} target="_blank">Inspect trace ↗</a></div></div>}
              <form className="composer" onSubmit={submitChat}>
                <textarea aria-label="Message ProductOS" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
                }} placeholder="Ask a product question, review a decision, or say ‘I prefer…’" rows={3} />
                <div className="composerFooter"><span>Enter to send · Shift + Enter for a new line</span><button type="submit" disabled={!input.trim() || run.status === "running"}>Send <b>↑</b></button></div>
              </form>
            </div>
          </div>
        )}

        {evidenceOpen && evidence && (
          <aside className="evidenceDrawer" aria-label="Evidence packet">
            <div className="drawerHeader"><div><p className="eyebrow">Application-issued citations</p><h2>Evidence packet</h2></div><button onClick={() => setEvidenceOpen(false)} aria-label="Close evidence">×</button></div>
            <div className={`availability ${evidence.availability}`}>{statusLabel(evidence.availability)}</div>
            {evidence.contradictions.length > 0 && <section className="contradictions"><h3>Conflicts detected</h3>{evidence.contradictions.map((item) => <p key={item.evidence_ids.join("-")}><strong>{item.evidence_ids.join(" ↔ ")}</strong> {item.description}{item.likely_current_evidence_id && <> Likely current: <strong>{item.likely_current_evidence_id}</strong> ({item.inference_rationale})</>}</p>)}</section>}
            <div className="evidenceList">
              {evidence.evidence.map((item) => <article className="evidenceCard" key={item.id}><div className="evidenceTitle"><span>{item.id}</span><div><h3>{item.title}</h3><p>{statusLabel(item.source_type)} · {item.source_id}</p></div></div>{item.section_title && <p className="sectionPath">Section: {item.section_title}</p>}<blockquote>{item.content}</blockquote><dl><div><dt>Relevance</dt><dd>{Math.round(item.relevance * 100)}%</dd></div><div><dt>Authority</dt><dd>{Math.round(item.authority * 100)}%</dd></div><div><dt>Freshness</dt><dd>{Math.round(item.freshness * 100)}%</dd></div><div><dt>Confidence</dt><dd>{Math.round(item.confidence * 100)}%</dd></div></dl>{item.url && <a href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>}</article>)}
            </div>
            {evidence.known_unknowns.length > 0 && <section className="unknowns"><h3>Known unknowns</h3><ul>{evidence.known_unknowns.map((item) => <li key={item}>{item}</li>)}</ul></section>}
          </aside>
        )}

        {view === "Initiatives" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Initiative intelligence</h2><p>Eight categorical health dimensions, each with evidence, confidence, and an explanation. No aggregate score.</p></div><span className="count">{initiatives.length} initiatives</span></div>
            <form className="createPanel initiativeCreate" onSubmit={createInitiative}><input value={initiativeName} onChange={(event) => setInitiativeName(event.target.value)} placeholder="Initiative name" /><textarea value={initiativeProblem} onChange={(event) => setInitiativeProblem(event.target.value)} placeholder="Problem statement" rows={2} /><input value={initiativeOwner} onChange={(event) => setInitiativeOwner(event.target.value)} placeholder="Owner ID (optional)" /><button disabled={!initiativeName.trim()}>Create initiative</button></form>
            {loading ? <p className="emptyList">Loading initiatives…</p> : initiatives.length === 0 ? <p className="emptyList">No initiatives yet. Add one explicitly to begin an evidence-backed health view.</p> : <div className="cardList">{initiatives.map((initiative) => <article className="dataCard initiativeCard" key={initiative.id}><div className="cardHeader"><span className={`statusTag ${initiative.status}`}>{statusLabel(initiative.status)}</span><time>{formatDate(initiative.updated_at)}</time></div><h3>{initiative.name}</h3><p>{initiative.problem || initiative.description || "No problem statement documented."}</p><p className="ownerLine">Owners: {initiative.owner_ids.join(", ") || "Unassigned"}</p><div className="healthGrid">{initiative.health.map((health) => <div className={`healthCell ${health.state}`} key={health.dimension}><div><span>{statusLabel(health.dimension)}</span><b>{statusLabel(health.state)}</b></div><p>{health.explanation}</p><small>{health.confidence} confidence · {health.evidence_ids.length} evidence refs</small></div>)}</div></article>)}</div>}
          </section>
        )}

        {view === "Team" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Team evidence profiles</h2><p>Inspectable responsibilities, documented wins, risks, and coaching questions. Never a rank, personality judgment, or employee score.</p></div><span className="count">{team.length} profiles</span></div>
            {loading ? <p className="emptyList">Loading profiles…</p> : team.length === 0 ? <p className="emptyList">No owner-linked initiatives are available.</p> : <div className="cardList">{team.map((profile) => <article className="dataCard teamCard" key={profile.pm_id}><div className="cardHeader"><span className="typeTag">PM evidence profile</span><button className="quietButton" onClick={() => prepareOneOnOne(profile.pm_id)}>Prepare 1:1</button></div><h3>{profile.pm_id}</h3><p><strong>Responsibilities:</strong> {profile.responsibilities.join(", ") || "None documented"}</p><div className="profileColumns"><div><h4>Wins to recognize</h4>{profile.observed_strengths.length ? profile.observed_strengths.map((item) => <p key={item.id}>{item.observation}</p>) : <p>No evidenced wins found.</p>}</div><div><h4>Things to understand</h4>{profile.risks.length ? profile.risks.map((item) => <p key={item.id}>{item.observation}</p>) : <p>No active risks found.</p>}</div><div><h4>Coaching questions</h4>{profile.coaching_opportunities.length ? profile.coaching_opportunities.map((item) => <p key={item.id}>{item.interpretation ?? item.observation}</p>) : <p>No recurring pattern met the evidence threshold.</p>}</div></div><div className="limitations"><strong>Evidence limits</strong>{profile.limitations.map((item) => <p key={item}>{item}</p>)}</div></article>)}</div>}
          </section>
        )}

        {view === "Attention" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Attention inbox</h2><p>Only high-significance active signals appear here. Review evidence and limitations before acting.</p></div><span className="count">{attention.length} items</span></div>
            {loading ? <p className="emptyList">Refreshing management signals…</p> : attention.length === 0 ? <p className="emptyList">No active high-significance signals require attention.</p> : <div className="cardList">{attention.map((item) => <article className="dataCard attentionCard" key={item.id}><div className="cardHeader"><div><span className={`statusTag ${item.level}`}>{item.level}</span><span className="typeTag">{item.subject_type}</span></div><span className="typeTag">{item.confidence} confidence</span></div><h3>{item.why_surfaced}</h3><p><strong>Recommendation:</strong> {item.recommended_next_step}</p><p><strong>Evidence:</strong> {item.evidence_ids.join(", ") || "No evidence references"}</p><div className="limitations"><strong>Limitations</strong>{item.limitations.map((limit) => <p key={limit}>{limit}</p>)}</div><div className="cardActions"><button onClick={() => correctSignal(item, "confirm")}>Confirm</button><button onClick={() => correctSignal(item, "add_context")}>Add context</button><button onClick={() => correctSignal(item, "disagree")}>Disagree</button><button onClick={() => correctSignal(item, "dismiss")}>Dismiss</button><button onClick={() => correctSignal(item, "mark_outdated")}>Outdated</button></div></article>)}</div>}
          </section>
        )}

        {view === "Memory" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Inspectable memory</h2><p>Every record retains provenance, confidence, status, and history. Corrections preserve the prior version.</p></div><span className="count">{memories.length} records</span></div>
            <div className="filters">
              <label>Type<select value={memoryType} onChange={(event) => setMemoryType(event.target.value)}><option value="all">All types</option><option value="preference">Preferences</option><option value="decision">Decisions</option><option value="belief">Beliefs</option><option value="semantic">Semantic facts</option><option value="episodic">Episodic</option><option value="procedural">Procedural</option></select></label>
              <label>Status<select value={memoryStatus} onChange={(event) => setMemoryStatus(event.target.value)}><option value="all">All states</option><option value="active">Active</option><option value="candidate">Candidate</option><option value="superseded">Superseded</option><option value="archived">Archived</option></select></label>
            </div>
            {loading ? <p className="emptyList">Loading memory…</p> : memories.length === 0 ? <p className="emptyList">No memory matches these filters.</p> : (
              <div className="cardList">
                {memories.map((memory) => (
                  <article className={`dataCard ${memory.status}`} key={memory.id}>
                    <div className="cardHeader"><div><span className="typeTag">{statusLabel(memory.memory_type)}</span><span className={`statusTag ${memory.status}`}>{statusLabel(memory.status)}</span></div><time>{formatDate(memory.updated_at)}</time></div>
                    <h3>{memory.content}</h3>
                    {memory.summary && memory.summary !== memory.content && <p>{memory.summary}</p>}
                    <dl><div><dt>Provenance</dt><dd>{statusLabel(memory.provenance_type)}</dd></div><div><dt>Source</dt><dd>{statusLabel(memory.source_type)}</dd></div><div><dt>Confidence</dt><dd>{Math.round(memory.confidence * 100)}%</dd></div>{memory.memory_key && <div><dt>Conflict key</dt><dd>{statusLabel(memory.memory_key)}</dd></div>}</dl>
                    <div className="cardActions"><a href={`${apiUrl}/v1/memories/${memory.id}?user_id=${userId}`} target="_blank">Inspect history ↗</a>{memory.status === "active" && <><button onClick={() => correctMemory(memory)}>Correct</button><button onClick={() => archiveMemory(memory)}>Archive</button></>}</div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {view === "Work" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Working sessions</h2><p>Persistent product work across conversations, evidence, and versioned artifacts.</p></div><span className="count">{artifacts.length} artifacts</span></div>
            <form className="createPanel" onSubmit={createWork}><input value={workTitle} onChange={(event) => setWorkTitle(event.target.value)} placeholder="Working session title" /><textarea value={workObjective} onChange={(event) => setWorkObjective(event.target.value)} placeholder="Objective or decision to work through" rows={2} /><button disabled={!workTitle.trim() || !workObjective.trim()}>Create session</button></form>
            {loading ? <p className="emptyList">Loading work…</p> : work.length === 0 ? <p className="emptyList">No working sessions yet.</p> : <div className="workGrid">{work.map((session) => <article className="workCard" key={session.id}><div className="cardHeader"><span className={`statusTag ${session.status}`}>{session.status}</span><time>{formatDate(session.updated_at)}</time></div><h3>{session.title}</h3><p>{session.objective}</p><div className="workMeta"><span>{statusLabel(session.workflow_type)}</span><span>{session.open_questions.length} open questions</span><span>{session.artifact_ids.length} artifacts</span></div></article>)}</div>}
          </section>
        )}

        {view === "Research" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Product intelligence workflows</h2><p>Run bounded, evidence-first workflows. Outputs remain inspectable drafts until you review them.</p></div><span className="count">{artifacts.length} artifacts</span></div>
            <form className="workflowPanel" onSubmit={executeWorkflow}>
              <label>Workflow<select value={workflowKind} onChange={(event) => setWorkflowKind(event.target.value as WorkflowKind)}><option value="deep_research">Deep research</option><option value="product_strategy">Product strategy</option><option value="product_review">PRD review</option><option value="spec_execution">Spec vs execution</option><option value="experiment_design">Experiment design</option><option value="decision_memo">Decision memo</option></select></label>
              <label>Objective<textarea value={workflowObjective} onChange={(event) => setWorkflowObjective(event.target.value)} placeholder="Frame the product question or decision" rows={3} /></label>
              <label>Working session<select value={workflowSessionId} onChange={(event) => setWorkflowSessionId(event.target.value)}><option value="">No session link</option>{work.map((session) => <option value={session.id} key={session.id}>{session.title}</option>)}</select></label>
              {workflowKind === "product_review" && <label>Document<textarea value={workflowSource} onChange={(event) => setWorkflowSource(event.target.value)} placeholder="Paste the PRD or specification to review" rows={8} /></label>}
              {workflowKind === "spec_execution" && <label>Confluence page ID<input value={workflowPageId} onChange={(event) => setWorkflowPageId(event.target.value)} placeholder="Explicit page ID" /></label>}
              <div className="workflowActions"><p>Evidence gaps are reported as unknown—not negative conclusions.</p><button disabled={!workflowObjective.trim() || workflowBusy || (workflowKind === "product_review" && !workflowSource.trim()) || (workflowKind === "spec_execution" && !workflowPageId.trim())}>{workflowBusy ? "Running workflow…" : "Create draft artifact"}</button></div>
            </form>
            <div className="artifactGrid">{artifacts.map((artifact) => <button className="artifactCard" key={artifact.id} onClick={() => setSelectedArtifact(artifact)}><div><span className="typeTag">{statusLabel(artifact.artifact_type)}</span><span className={`statusTag ${artifact.status}`}>{artifact.status}</span></div><h3>{artifact.title}</h3><p>{statusLabel(artifact.workflow_name)} · v{artifact.workflow_version}</p><small>{artifact.source_ids.length} source references · {formatDate(artifact.created_at)}</small></button>)}</div>
          </section>
        )}

        {view === "Decisions" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Decisions</h2><p>Draft decision memos remain separate from accepted decision memory until explicitly authorized.</p></div><span className="count">{artifacts.length} drafts</span></div>
            {artifacts.length > 0 && <div className="artifactGrid compact">{artifacts.map((artifact) => <button className="artifactCard" key={artifact.id} onClick={() => setSelectedArtifact(artifact)}><div><span className="typeTag">Decision memo</span><span className={`statusTag ${artifact.status}`}>{artifact.status}</span></div><h3>{artifact.title}</h3><small>Open inspectable draft →</small></button>)}</div>}
            <h2 className="sectionHeading">Accepted decision memory</h2>
            {loading ? <p className="emptyList">Loading decisions…</p> : decisions.length === 0 ? <p className="emptyList">No decisions have been recorded.</p> : <div className="cardList">{decisions.map((decision) => <article className="dataCard" key={decision.id}><div className="cardHeader"><span className={`statusTag ${decision.status}`}>{statusLabel(decision.status)}</span><time>{formatDate(decision.updated_at)}</time></div><h3>{decision.title}</h3><p><strong>Decision:</strong> {decision.decision}</p><p><strong>Rationale:</strong> {decision.rationale}</p>{decision.review_trigger && <p><strong>Review trigger:</strong> {decision.review_trigger}</p>}</article>)}</div>}
          </section>
        )}

        {selectedArtifact && (
          <aside className="artifactDrawer" aria-label="Artifact detail">
            <div className="drawerHeader"><div><p className="eyebrow">Structured + rendered artifact</p><h2>{selectedArtifact.title}</h2></div><button onClick={() => setSelectedArtifact(null)} aria-label="Close artifact">×</button></div>
            <div className="artifactMeta"><span className="statusTag draft">Draft</span><span>{statusLabel(selectedArtifact.workflow_name)} v{selectedArtifact.workflow_version}</span><span>{selectedArtifact.source_ids.length} sources</span></div>
            <pre>{selectedArtifact.rendered_content}</pre>
          </aside>
        )}

        {view === "Evaluations" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Measured quality runs</h2><p>Pass rates appear only for persisted executions against operator-supplied, versioned datasets.</p></div><span className="count">{evaluationRuns.length} runs</span></div>
            {evaluationRuns.length ? <div className="artifactGrid">{evaluationRuns.map((item) => <button className="artifactCard" onClick={() => openEvaluation(item.id)} key={item.id}><div><span className="typeTag">{item.dataset_name} · {item.dataset_version}</span><span className={`statusTag ${item.status}`}>{item.status}</span></div><h3>{item.pass_rate === null ? "No measured pass rate" : `${Math.round(item.pass_rate * 100)}% pass rate`}</h3><p>{item.passed_cases} passed · {item.failed_cases} failed · {item.error_cases} errors</p><small>{item.subject_model} judged by {item.judge_model} · Inspect results →</small></button>)}</div> : <p className="emptyList">No representative-data quality run has been persisted. Configure subject and judge models, then submit an approved versioned dataset through the evaluation API.</p>}
            <div className="pageIntro"><div><h2>Evaluation coverage</h2><p>Inspectable synthetic regression definitions. Catalog validation is not a production quality result.</p></div><span className="count">{evaluations?.total_cases ?? 0} cases</span></div>
            {loading ? <p className="emptyList">Loading evaluation catalog metadata…</p> : !evaluations ? <p className="emptyList">Evaluation catalog metadata is unavailable. Check the API connection notice above, then retry.</p> : <>
              <div className="artifactGrid">{evaluations.catalogs.map((catalog) => <article className="artifactCard" key={catalog.milestone}><div><span className="typeTag">Milestone {catalog.milestone}</span><span className="statusTag active">{catalog.catalog_status}</span></div><h3>{catalog.suite}</h3><p>{catalog.case_count} cases · Primary metric: {catalog.primary_metric}</p><small>Quality execution: {catalog.execution_status}</small></article>)}</div>
              <div className="limitations"><strong>Result boundary</strong><p>{evaluations.limitation}</p></div>
            </>}
          </section>
        )}

        {selectedEvaluation && (
          <aside className="artifactDrawer" aria-label="Evaluation run detail">
            <div className="drawerHeader"><div><p className="eyebrow">Measured evaluation run</p><h2>{selectedEvaluation.run.dataset_name}</h2></div><button onClick={() => { setSelectedEvaluation(null); setEvaluationTrace(null); }} aria-label="Close evaluation">×</button></div>
            <div className="artifactMeta"><span>{selectedEvaluation.run.dataset_version}</span><span>{selectedEvaluation.run.subject_model}</span><span>Judge: {selectedEvaluation.run.judge_model}</span></div>
            <div className="limitations"><strong>Interpretation limit</strong><p>{selectedEvaluation.run.limitation}</p></div>
            {selectedEvaluation.cases.map((item) => <article className="dataCard" key={item.id}><div className="cardHeader"><span className={`statusTag ${item.status}`}>{item.status}</span><span className="typeTag">{item.external_id} · {item.category}</span></div><h3>Input</h3><p>{item.input_text}</p><h3>Actual output</h3><p>{item.actual_output || "No output was produced."}</p>{item.judgment && <><h3>Judge feedback</h3><p>{item.judgment.reasoning_summary}</p><small>Score {item.judgment.score}/5 · Critical failure: {item.judgment.critical_failure ? "yes" : "no"}</small></>}{item.error_code && <p>Error: {item.error_code}</p>}{item.agent_run_id && <button className="quietButton" onClick={() => inspectEvaluationTrace(item.agent_run_id!)}>Inspect agent trace</button>}</article>)}
            {evaluationTrace && <><h3>Selected trace</h3><pre>{JSON.stringify(evaluationTrace, null, 2)}</pre></>}
          </aside>
        )}

        {view === "Settings" && (
          <section className="panelPage">
            <div className="pageIntro"><div><h2>Proactive support</h2><p>Delivery is in-app only, defaults off, and requires material change, sufficient confidence, and a clear action.</p></div><span className={`connectionBadge ${preferences?.enabled ? "read_enabled" : "unknown"}`}>{preferences?.enabled ? "enabled" : "off by default"}</span></div>
            {preferences && <article className="connectionCard">
              <div className="connectionHeader"><div><span className="providerMark">P</span><div><h3>Notification preferences</h3><p>No external messages or writes are performed.</p></div></div><label><input type="checkbox" checked={preferences.enabled} onChange={(event) => updatePreferences({ enabled: event.target.checked })} /> Enable in-app notifications</label></div>
              <div className="filters">
                <label><input type="checkbox" checked={preferences.daily_brief_enabled} onChange={(event) => updatePreferences({ daily_brief_enabled: event.target.checked })} /> Daily brief</label>
                <label><input type="checkbox" checked={preferences.weekly_brief_enabled} onChange={(event) => updatePreferences({ weekly_brief_enabled: event.target.checked })} /> Weekly leadership brief</label>
                <label><input type="checkbox" checked={preferences.decision_reminders_enabled} onChange={(event) => updatePreferences({ decision_reminders_enabled: event.target.checked })} /> Decision reminders</label>
                <label><input type="checkbox" checked={preferences.risk_alerts_enabled} onChange={(event) => updatePreferences({ risk_alerts_enabled: event.target.checked })} /> Risk alerts</label>
                <label>Minimum severity<select value={preferences.minimum_level} onChange={(event) => updatePreferences({ minimum_level: event.target.value })}><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
                <label>Daily cap<input type="number" min="0" max="25" value={preferences.maximum_per_day} onChange={(event) => updatePreferences({ maximum_per_day: Number(event.target.value) })} /></label>
              </div>
              <div className="pageIntro"><div><h3>Schedules</h3><p>Deployment automation invokes the tenant-scoped scheduler. Each schedule remains off until you enable it.</p></div>{schedules.length === 0 && <button onClick={createDefaultSchedules}>Set up schedules</button>}</div>
              {schedules.length > 0 && <div className="toolGrid">{schedules.map((schedule) => <article className="toolCard" key={schedule.id}><div><h3>{statusLabel(schedule.kind)}</h3><span>{schedule.enabled ? "enabled" : "off"}</span></div><p>{schedule.frequency} at {schedule.local_time.slice(0, 5)} · {schedule.timezone}</p><small>Next evaluation: {formatDate(schedule.next_run_at)}</small><button className="quietButton" onClick={() => toggleSchedule(schedule)}>{schedule.enabled ? "Disable" : "Enable"}</button></article>)}</div>}
            </article>}
            <div className="pageIntro"><div><h2>Connected tools</h2><p>ProductOS exposes only application-approved, read-only Atlassian capabilities. External writes are not registered.</p></div><span className={`connectionBadge ${connectionStatus}`}>{statusLabel(connectionStatus)}</span></div>
            <article className="connectionCard">
              <div className="connectionHeader"><div><span className="providerMark">A</span><div><h3>Atlassian</h3><p>Jira + Confluence through the MCP boundary</p></div></div><span className={`statusTag ${connectionStatus === "read_enabled" ? "active" : "archived"}`}>{statusLabel(connectionStatus)}</span></div>
              <dl><div><dt>Permissions</dt><dd>Read only</dd></div><div><dt>Write access</dt><dd>Not registered</dd></div><div><dt>Data scope</dt><dd>User and tenant scoped</dd></div><div><dt>Tool contracts</dt><dd>{toolDefinitions.length}</dd></div></dl>
              <label className="siteSelector">Workspace<select value={selectedSite} onChange={(event) => chooseSite(event.target.value)}><option value="">Select explicitly</option>{atlassianSites.map((site) => <option value={site.cloud_id} key={site.cloud_id}>{site.site_name}</option>)}</select></label>
              {selectedSite && atlassianSites.filter((site) => site.cloud_id === selectedSite).map((site) => <div className="scopeSummary" key={site.cloud_id}><span>{site.site_url}</span><span>{site.accessible_projects.length} projects</span><span>{site.accessible_spaces.length} spaces</span></div>)}
            </article>
            <div className="toolGrid">{toolDefinitions.map((tool) => <article className="toolCard" key={tool.name}><div><h3>{tool.name}</h3><span>{tool.risk_level} risk</span></div><p>{tool.capability}</p><small>{tool.read_only ? "Read only" : "Write"} · {tool.provider}</small></article>)}</div>
          </section>
        )}
      </section>
    </main>
  );
}
