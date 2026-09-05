// =============================================================
// src/api/alerts.ts
// Tenant-level Alertmanager alerts and external tools integration API.
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import { useAuth } from "../hooks/useAuth";

// ─── Types ───────────────────────────────────────────────────

export interface ActiveAlertDTO {
  fingerprint: string;
  alertname: string;
  severity: string;
  state: string;
  starts_at: string;
  ends_at: string | null;
  updated_at: string | null;
  summary: string | null;
  description: string | null;
  source: string | null;
  category: string | null;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  generator_url: string | null;
}

export interface AlertsResponse {
  collected_at: string;
  alertmanager_available: boolean;
  active_count: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  alerts: ActiveAlertDTO[];
}

/**
 * An external service (Grafana / Prometheus / MinIO / etc.).
 * Displayed as an item in the "External Tools" dropdown menu.
 */
export interface ExternalServiceDTO {
  key: string;
  label: string;
  url: string;
  description: string;
}

/**
 * A single Grafana dashboard with a deep link.
 */
export interface ExternalDashboardDTO {
  uid: string;
  label: string;
  description: string;
  url: string;
}

/**
 * Response payload from /api/v1/tenant/tools endpoint.
 *
 * Legacy fields (grafana_url / prometheus_url / alertmanager_url) are retained
 * for backwards compatibility and used inside AlertsPanel.
 *
 * Extended fields (services, dashboards) are populated only for superadmins.
 * For a standard tenant_admin, empty arrays are returned.
 */
export interface ExternalToolsDTO {
  // Legacy fields for backwards compatibility with AlertsPanel
  grafana_url: string;
  prometheus_url: string;
  alertmanager_url: string;
  is_superadmin: boolean;

  // Extended fields for the "External Tools" dropdown menu
  services: ExternalServiceDTO[];
  dashboards: ExternalDashboardDTO[];
}

// ─── API ─────────────────────────────────────────────────────

export const alertsApi = {
  getAlerts: () =>
    client.get<AlertsResponse>("/api/v1/tenant/alerts").then((r) => r.data),

  getTools: () =>
    client.get<ExternalToolsDTO>("/api/v1/tenant/tools").then((r) => r.data),
};

// ─── Hooks ───────────────────────────────────────────────────

export function useTenantAlerts() {
  return useQuery({
    queryKey: ["tenant-alerts"],
    queryFn: () => alertsApi.getAlerts(),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useExternalTools() {
  // Auth-scoped cache key: changing the user / role automatically triggers
  // a fresh request. This protects against stale cache issues when switching
  // sessions of different users in the same browser.
  const { userId, globalRole } = useAuth();

  return useQuery({
    queryKey: ["external-tools", userId ?? "anon", globalRole ?? "none"],
    queryFn: () => alertsApi.getTools(),
    enabled: !!userId,
    staleTime: 5 * 60_000,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
  });
}


