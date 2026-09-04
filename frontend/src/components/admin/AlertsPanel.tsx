// frontend/src/components/admin/AlertsPanel.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, Loader2, RefreshCw } from "lucide-react";
import { useTenantAlerts, type ActiveAlertDTO } from "../../api/alerts";

// ─── Helpers ─────────────────────────────────────────────────

function formatDateTime(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(locale, {
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

function formatDuration(startsAt: string, tFn: (key: string, options?: any) => string): string {
  try {
    const start = new Date(startsAt).getTime();
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - start) / 1000));

    if (diffSec < 60) return tFn("alertsPanel.duration.seconds", { count: diffSec });
    if (diffSec < 3600) return tFn("alertsPanel.duration.minutes", { count: Math.floor(diffSec / 60) });
    if (diffSec < 86400) return tFn("alertsPanel.duration.hours", { count: Math.floor(diffSec / 3600) });
    return tFn("alertsPanel.duration.days", { count: Math.floor(diffSec / 86400) });
  } catch {
    return "—";
  }
}

function SeverityBadge({ severity }: { severity: string }) {
  const { t } = useTranslation("tenantAdmin");

  const config: Record<string, { label: string; cls: string }> = {
    critical: {
      label: t("alertsPanel.severity.critical"),
      cls: "status-border-error status-bg-error status-text-error",
    },
    warning: {
      label: t("alertsPanel.severity.warning"),
      cls: "status-border-warning status-bg-warning status-text-warning",
    },
    info: {
      label: t("alertsPanel.severity.info"),
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
  const { t, i18n } = useTranslation("tenantAdmin");
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
            <span>{t("alertsPanel.cards.started", { time: formatDateTime(alert.starts_at, i18n.language) })}</span>
            <span>{t("alertsPanel.cards.duration", { duration: formatDuration(alert.starts_at, t) })}</span>
            <span>{t("alertsPanel.cards.state", { state: alert.state })}</span>
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
                {t("alertsPanel.cards.description")}
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
                  {t("alertsPanel.cards.openInSource")}
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
  const { t, i18n } = useTranslation("tenantAdmin");
  const { data, isLoading, isFetching, error, refetch } = useTenantAlerts();
  const [severityFilter, setSeverityFilter] = React.useState<string>("all");

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="mr-2 animate-spin text-[var(--accent-primary)]" size={20} />
        <span className="text-sm text-[var(--text-muted)]">
          {t("alertsPanel.loading")}
        </span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="status-border-error status-bg-error status-text-error rounded-lg border p-4 text-sm">
        {t("alertsPanel.loadError")}
      </div>
    );
  }

  if (!data.alertmanager_available) {
    return (
      <div className="status-border-warning status-bg-warning rounded-lg border p-4">
        <p className="text-sm font-medium status-text-warning">
          {t("alertsPanel.unavailable.title")}
        </p>
        <p className="mt-1 text-xs status-text-warning">
          {t("alertsPanel.unavailable.desc")}
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
              {t("alertsPanel.summary.critical")}
            </div>
            <div className="text-lg font-bold status-text-error">
              {data.critical_count}
            </div>
          </div>
          <div className="status-border-warning status-bg-warning rounded-lg border px-3 py-2">
            <div className="text-[10px] font-medium uppercase status-text-warning">
              {t("alertsPanel.summary.warning")}
            </div>
            <div className="text-lg font-bold status-text-warning">
              {data.warning_count}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2 bg-[var(--color-blue-highlight)] border-[var(--color-blue)/20]">
            <div className="text-[10px] font-medium uppercase text-[var(--color-blue-strong)]">
              {t("alertsPanel.summary.info")}
            </div>
            <div className="text-lg font-bold text-[var(--color-blue-strong)]">
              {data.info_count}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2 border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
            <div className="text-[10px] font-medium uppercase text-[var(--text-secondary)]">
              {t("alertsPanel.summary.total")}
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
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-xs text-[var(--text-primary)]"
          >
            <option value="all">{t("alertsPanel.severity.all")}</option>
            <option value="critical">{t("alertsPanel.severity.onlyCritical")}</option>
            <option value="warning">{t("alertsPanel.severity.onlyWarning")}</option>
            <option value="info">{t("alertsPanel.severity.onlyInfo")}</option>
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
            {t("actions.refresh", { ns: "common" })}
          </button>
        </div>
      </div>

      {/* Alerts list */}
      {filteredAlerts.length === 0 ? (
        <div className="status-border-success status-bg-success rounded-lg border p-6 text-center">
          <p className="text-sm font-medium status-text-success">
            {data.active_count === 0
              ? t("alertsPanel.empty.noActive")
              : t("alertsPanel.empty.noWithSeverity")}
          </p>
          <p className="mt-1 text-xs status-text-success">
            {t("alertsPanel.empty.workingFine")}
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
        {t("alertsPanel.footer", { time: formatDateTime(data.collected_at, i18n.language) })}
      </p>
    </div>
  );
}

export default AlertsPanel;



