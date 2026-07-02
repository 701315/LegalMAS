// frontend/src/api/tenantAdmin.ts

import { useQuery } from "@tanstack/react-query";
import client from "./client";

// ─── Dashboard types ──────────────────────────────────────────────────────

export interface UserProjectDTO {
  deal_id: string;
  deal_name: string;
  role: string;
}

export interface TenantUserDTO {
  id: string;
  email: string;
  full_name: string | null;
  system_role: string;
  is_active: boolean;
  created_at: string;
  projects: UserProjectDTO[];
  projects_count: number;
}

export interface ProjectRunSummaryDTO {
  run_id: string;
  status: string;
  total_checks: number;
  completed_checks: number;
  has_errors: boolean;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProjectHealthDTO {
  deal_id: string;
  deal_name: string;
  created_at: string;
  total_documents: number;
  failed_documents: number;
  quarantine_documents: number;
  last_run: ProjectRunSummaryDTO | null;
}

export interface TenantStatsDTO {
  total_projects: number;
  total_users: number;
  active_users: number;
  total_documents: number;
  failed_documents: number;
  quarantine_documents: number;
  runs_last_7_days: number;
  dlq_size: number;
}

export interface TenantDashboardResponse {
  tenant_id: string;
  stats: TenantStatsDTO;
  projects: ProjectHealthDTO[];
  users: TenantUserDTO[];
}

// ─── Metrics types ────────────────────────────────────────────────────────

export interface PipelineMetrics {
  dlq_size: number;
  active_runs: number;
  stuck_executions: number;
  docs_processed_last_hour: number;
  docs_failed_last_hour: number;
}

export interface ApiEndpointMetric {
  handler: string;
  method: string;
  requests: number;
  errors: number;
  p95_ms: number | null;
}

export interface ApiMetrics {
  top_endpoints: ApiEndpointMetric[];
}

export interface CeleryTaskFailureMetric {
  task_name: string;
  failures_last_hour: number;
  failure_types: string[];
}

export interface CeleryMetrics {
  task_failures_last_hour: CeleryTaskFailureMetric[];
}

export interface LlmProviderMetric {
  provider: string;
  requests_last_hour: number;
  timeouts_last_hour: number;
}

export interface LlmMetrics {
  providers: LlmProviderMetric[];
}

export interface PlatformMetricsResponse {
  collected_at: string;
  prometheus_available: boolean;
  pipeline: PipelineMetrics;
  api: ApiMetrics;
  celery: CeleryMetrics;
  llm: LlmMetrics;
}

// ─── Logs types ───────────────────────────────────────────────────────────

export interface LogEntry {
  timestamp: string;
  level: string;
  event: string;
  logger: string;
  stage: string | null;
  queue: string | null;
  worker_hostname: string | null;
  deal_id: string | null;
  run_id: string | null;
  document_id: string | null;
  task_id: string | null;
  task_name: string | null;
  raw: Record<string, unknown>;
  count: number;
  first_seen: string | null;
  last_seen: string | null;
}

export interface LogsStats {
  fetched: number;
  returned: number;
  filtered_out_by_mode: number;
  grouped_into: number;
  mode: string;
}

export interface LogsResponse {
  collected_at: string;
  loki_available: boolean;
  entries: LogEntry[];
  stats: LogsStats;
}

export type LogsMode = "operational" | "debug";

export interface TenantLogsParams {
  tenant_id?: string;
  deal_id?: string;
  run_id?: string;
  document_id?: string;
  task_id?: string;
  level?: string;
  stage?: string;
  queue?: string;
  mode?: LogsMode;
  group_similar?: boolean;
  limit?: number;
  since_minutes?: number;
}

// ─── Project insights ─────────────────────────────────────────────────────

export interface ProjectDocumentStats {
  total: number;
  failed: number;
  quarantine: number;
  by_status: Record<string, number>;
  by_doc_type: Record<string, number>;
  reviewed_by_person: number;
  requires_review: number;
}

export interface ProjectRunStats {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  completed_with_errors_runs: number;
  running_runs: number;
  pending_runs: number;
  runs_last_7_days: number;
  avg_duration_seconds: number | null;
  last_run: ProjectRunSummaryDTO | null;
  recent_runs: ProjectRunSummaryDTO[];
}

export interface ProjectMemberDTO {
  user_id: string;
  email: string;
  full_name: string | null;
  system_role: string;
  is_active: boolean;
  project_role: string;
}

export interface ProjectErrorItem {
  kind: "document" | "run" | string;
  occurred_at: string | null;
  document_id: string | null;
  document_filename: string | null;
  document_status: string | null;
  run_id: string | null;
  run_status: string | null;
  stage: string | null;
  error_type: string | null;
  error_reason: string | null;
  error_message: string | null;
  error_details: Record<string, unknown> | null;
}

export interface ProjectErrorStats {
  failed_documents: number;
  quarantine_documents: number;
  failed_runs: number;
  completed_with_errors_runs: number;
  total_items: number;
  truncated: boolean;
  items: ProjectErrorItem[];
}

export interface ProjectInsightsResponse {
  deal_id: string;
  deal_name: string;
  created_at: string;
  tenant_id: string;
  documents: ProjectDocumentStats;
  runs: ProjectRunStats;
  members: ProjectMemberDTO[];
  members_count: number;
  last_activity_at: string | null;
  errors: ProjectErrorStats;
}

// ─── Options ──────────────────────────────────────────────────────────────

interface TenantAdminQueryOptions {
  enabled?: boolean;
}

// ─── API ─────────────────────────────────────────────────────────────────

export const tenantAdminApi = {
  getDashboard: (tenantId?: string) =>
    client
      .get<TenantDashboardResponse>("/api/v1/tenant/dashboard", {
        params: tenantId ? { tenant_id: tenantId } : undefined,
      })
      .then((r) => r.data),

  getMetrics: (tenantId?: string) =>
    client
      .get<PlatformMetricsResponse>("/api/v1/tenant/metrics", {
        params: tenantId ? { tenant_id: tenantId } : undefined,
      })
      .then((r) => r.data),

  getLogs: (params: TenantLogsParams = {}) => {
    const queryParams: Record<string, string | number | boolean> = {
      limit: params.limit ?? 50,
      since_minutes: params.since_minutes ?? 60,
      mode: params.mode ?? "operational",
      group_similar:
        params.group_similar === undefined ? true : params.group_similar,
    };

    if (params.tenant_id) queryParams.tenant_id = params.tenant_id;
    if (params.deal_id) queryParams.deal_id = params.deal_id;
    if (params.run_id) queryParams.run_id = params.run_id;
    if (params.document_id) queryParams.document_id = params.document_id;
    if (params.task_id) queryParams.task_id = params.task_id;
    if (params.level) queryParams.level = params.level;
    if (params.stage) queryParams.stage = params.stage;
    if (params.queue) queryParams.queue = params.queue;

    return client
      .get<LogsResponse>("/api/v1/tenant/logs", { params: queryParams })
      .then((r) => r.data);
  },

  getProjectInsights: (dealId: string, tenantId?: string) =>
    client
      .get<ProjectInsightsResponse>(
        `/api/v1/tenant/projects/${dealId}/insights`,
        {
          params: tenantId ? { tenant_id: tenantId } : undefined,
        },
      )
      .then((r) => r.data),
};

// ─── Hooks ────────────────────────────────────────────────────────────────

export function useTenantDashboard(
  tenantId?: string,
  options?: TenantAdminQueryOptions,
) {
  return useQuery({
    queryKey: ["tenant-dashboard", tenantId ?? "self"],
    queryFn: () => tenantAdminApi.getDashboard(tenantId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: options?.enabled ?? true,
  });
}

export function usePlatformMetrics(
  tenantId?: string,
  options?: TenantAdminQueryOptions,
) {
  return useQuery({
    queryKey: ["tenant-platform-metrics", tenantId ?? "self"],
    queryFn: () => tenantAdminApi.getMetrics(tenantId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: options?.enabled ?? true,
  });
}

export function useTenantLogs(
  params: TenantLogsParams = {},
  options?: TenantAdminQueryOptions,
) {
  return useQuery({
    queryKey: [
      "tenant-logs",
      params.tenant_id ?? "self",
      params.deal_id ?? "all",
      params.run_id ?? "all",
      params.document_id ?? "all",
      params.task_id ?? "all",
      params.level ?? "all",
      params.stage ?? "all",
      params.queue ?? "all",
      params.mode ?? "operational",
      params.group_similar === false ? "flat" : "grouped",
      params.limit ?? 50,
      params.since_minutes ?? 60,
    ],
    queryFn: () => tenantAdminApi.getLogs(params),
    staleTime: 15_000,
    refetchInterval: 30_000,
    enabled: options?.enabled ?? true,
  });
}

export function useProjectInsights(
  dealId: string | null | undefined,
  tenantId?: string,
  options?: TenantAdminQueryOptions,
) {
  return useQuery({
    queryKey: ["tenant-project-insights", dealId, tenantId ?? "self"],
    queryFn: () => tenantAdminApi.getProjectInsights(dealId as string, tenantId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: !!dealId && (options?.enabled ?? true),
  });
}

