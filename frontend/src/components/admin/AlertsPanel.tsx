// frontend/src/components/admin/AlertsPanel.tsx

import React from "react";
import { AlertTriangle, Info, Loader2, RefreshCw } from "lucide-react";
import { useTenantAlerts, type ActiveAlertDTO } from "../../api/alerts";

// ─── Helpers ─────────────────────────────────────────────────

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return value;
  }
}

function formatDuration(startsAt: string): string {
  try {
    const start = new Date(startsAt).getTime();
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - start) / 1000));

    if (diffSec < 60) return `${diffSec}с`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}м`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}ч`;
    return `${Math.floor(diffSec / 86400)}д`;
  } catch {
    return "—";
  }
}

function SeverityBadge({ severity }: { severity: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    critical: {
      label: "CRITICAL",
      cls: "status-border-error status-bg-error status-text-error",
    },
    warning: {
      label: "WARNING",
      cls: "status-border-warning status-bg-warning status-text-warning",
    },
    info: {
      label: "INFO",
      cls: "border-[var(--color-blue)/20] bg-[var(--color-blue-highlight)] text-[var(--color-blue-strong)]",
    },
  };
  const c = config[severity] ?? {
    label: severity.toUpperCase(),
    cls: "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
  };
  return (
    <span
      className={`inline-flex rounded-md border px-2 py-0.5 text-[10px] font-bold tracking-wide ${c.cls}`}
    >
      {c.label}
    </span>
  );
}

function SourceBadge({ source }: { source: string | null }) {
  if (!source) return null;
  const config: Record<string, { label: string; cls: string }> = {
    prometheus: { label: "Prometheus", cls: "status-bg-error status-text-error" },
    loki: { label: "Loki", cls: "bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]" },
  };
  const c = config[source] ?? { label: source, cls: "bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]" };
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${c.cls}`}
    >
      {c.label}
    </span>
  );
}

// ─── Alert card ──────────────────────────────────────────────

function AlertCard({ alert }: { alert: ActiveAlertDTO }) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)]">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 p-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
      >
        <div className="mt-0.5 shrink-0">
          {alert.severity === "critical" ? (
            <AlertTriangle size={16} className="text-[var(--color-error)]" />
          ) : alert.severity === "warning" ? (
            <AlertTriangle size={16} className="text-[var(--color-warning)]" />
          ) : (
            <Info size={16} className="text-[var(--color-blue)]" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              {alert.alertname}
            </span>
            <SourceBadge source={alert.source} />
            {alert.category && (
              <span className="rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                {alert.category}
              </span>
            )}
          </div>

          {alert.summary && (
            <p className="mt-1 text-xs text-[var(--text-primary)]">
              {alert.summary}
            </p>
          )}

          <div className="mt-1 flex flex-wrap items-center gap-3 text-[10px] text-[var(--text-muted)]">
            <span>Начался: {formatDateTime(alert.starts_at)}</span>
            <span>Длительность: {formatDuration(alert.starts_at)}</span>
            <span>Состояние: {alert.state}</span>
          </div>
        </div>

        <span className="shrink-0 text-[10px] text-[var(--accent-primary)]">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border-subtle)] px-3 py-3 text-[11px]">
          {alert.description && (
            <div className="mb-3">
              <p className="mb-1 font-medium text-[var(--text-secondary)]">
                Описание:
              </p>
              <p className="text-[var(--text-primary)]">{alert.description}</p>
            </div>
          )}

          <div className="mb-3">
            <p className="mb-1 font-medium text-[var(--text-secondary)]">
              Labels:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(alert.labels).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px]"
                >
                  <span className="text-[var(--text-muted)]">{k}=</span>
                  <span className="font-mono text-[var(--text-primary)]">
                    {v}
                  </span>
                </span>
              ))}
            </div>
          </div>

          {Object.keys(alert.annotations).length > 0 && (
            <div className="mb-3">
              <p className="mb-1 font-medium text-[var(--text-secondary)]">
                Annotations:
              </p>
              <div className="space-y-1">
                {Object.entries(alert.annotations).map(([k, v]) => (
                  <div key={k}>
                    <span className="font-medium text-[var(--text-muted)]">
                      {k}:
                    </span>{" "}
                    <span className="text-[var(--text-primary)]">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 text-[10px] text-[var(--text-muted)]">
            <div>
              <span className="font-medium">Fingerprint:</span>{" "}
              <span className="font-mono">{alert.fingerprint}</span>
            </div>
            {alert.generator_url && (
              <div>
                <a
                  href={alert.generator_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--accent-primary)] hover:underline"
                >
                  Открыть в источнике →
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main panel ──────────────────────────────────────────────

export function AlertsPanel() {
  const { data, isLoading, isFetching, error, refetch } = useTenantAlerts();
  const [severityFilter, setSeverityFilter] = React.useState<string>("all");

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="mr-2 animate-spin text-[var(--accent-primary)]" size={20} />
        <span className="text-sm text-[var(--text-muted)]">
          Загружаем алерты…
        </span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="status-border-error status-bg-error status-text-error rounded-lg border p-4 text-sm">
        Не удалось загрузить алерты. Проверьте что Alertmanager запущен.
      </div>
    );
  }

  if (!data.alertmanager_available) {
    return (
      <div className="status-border-warning status-bg-warning rounded-lg border p-4">
        <p className="text-sm font-medium status-text-warning">
          Alertmanager недоступен
        </p>
        <p className="mt-1 text-xs status-text-warning">
          Убедитесь что контейнер mas_alertmanager запущен и доступен
          по адресу из ALERTMANAGER_INTERNAL_URL.
        </p>
      </div>
    );
  }

  const filteredAlerts =
    severityFilter === "all"
      ? data.alerts
      : data.alerts.filter((a) => a.severity === severityFilter);

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="status-border-error status-bg-error rounded-lg border px-3 py-2">
            <div className="text-[10px] font-medium uppercase status-text-error">
              Critical
            </div>
            <div className="text-lg font-bold status-text-error">
              {data.critical_count}
            </div>
          </div>
          <div className="status-border-warning status-bg-warning rounded-lg border px-3 py-2">
            <div className="text-[10px] font-medium uppercase status-text-warning">
              Warning
            </div>
            <div className="text-lg font-bold status-text-warning">
              {data.warning_count}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2 bg-[var(--color-blue-highlight)] border-[var(--color-blue)/20]">
            <div className="text-[10px] font-medium uppercase text-[var(--color-blue-strong)]">
              Info
            </div>
            <div className="text-lg font-bold text-[var(--color-blue-strong)]">
              {data.info_count}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2 border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
            <div className="text-[10px] font-medium uppercase text-[var(--text-secondary)]">
              Всего
            </div>
            <div className="text-lg font-bold text-[var(--text-primary)]">
              {data.active_count}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs"
          >
            <option value="all">Все severity</option>
            <option value="critical">Только critical</option>
            <option value="warning">Только warning</option>
            <option value="info">Только info</option>
          </select>

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] disabled:opacity-50"
          >
            <RefreshCw
              size={12}
              className={isFetching ? "animate-spin" : ""}
            />
            Обновить
          </button>
        </div>
      </div>

      {/* Alerts list */}
      {filteredAlerts.length === 0 ? (
        <div className="status-border-success status-bg-success rounded-lg border p-6 text-center">
          <p className="text-sm font-medium status-text-success">
            {data.active_count === 0
              ? "Активных алертов нет"
              : "Нет алертов с выбранным severity"}
          </p>
          <p className="mt-1 text-xs status-text-success">
            Система работает нормально
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredAlerts.map((alert) => (
            <AlertCard key={alert.fingerprint} alert={alert} />
          ))}
        </div>
      )}

      <p className="text-[10px] text-[var(--text-muted)]">
        Обновление автоматически каждые 30 секунд · Последнее обновление:{" "}
        {formatDateTime(data.collected_at)}
      </p>
    </div>
  );
}

export default AlertsPanel;


