// frontend/src/api/alerts.ts

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
 * Один внешний сервис (Grafana / Prometheus / MinIO / ...).
 * Показывается как пункт в dropdown "Внешние инструменты".
 */
export interface ExternalServiceDTO {
  key: string;
  label: string;
  url: string;
  description: string;
}

/**
 * Один Grafana dashboard с deep link.
 */
export interface ExternalDashboardDTO {
  uid: string;
  label: string;
  description: string;
  url: string;
}

/**
 * Ответ endpoint /api/v1/tenant/tools.
 *
 * Старые поля (grafana_url / prometheus_url / alertmanager_url) сохранены
 * для обратной совместимости — используются в AlertsPanel.
 *
 * Новые поля (services, dashboards) заполнены только для superadmin —
 * для обычного tenant_admin возвращаются пустые массивы.
 */
export interface ExternalToolsDTO {
  // Legacy — для обратной совместимости с AlertsPanel
  grafana_url: string;
  prometheus_url: string;
  alertmanager_url: string;
  is_superadmin: boolean;

  // Расширенные данные для dropdown "Внешние инструменты"
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
  // Auth-scoped cache key: при смене пользователя / роли автоматически
  // будет выполнен новый запрос. Это защищает от stale-cache между
  // сессиями разных пользователей в одном браузере.
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


