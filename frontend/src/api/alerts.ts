// frontend/src/api/alerts.ts

import { useQuery } from "@tanstack/react-query";
import client from "./client";

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

export interface ExternalToolsDTO {
  grafana_url: string;
  prometheus_url: string;
  alertmanager_url: string;
  is_superadmin: boolean;
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
  return useQuery({
    queryKey: ["external-tools"],
    queryFn: () => alertsApi.getTools(),
    staleTime: 60 * 60_000,
  });
}


