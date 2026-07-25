// frontend/src/pages/TenantAdminPage.tsx

import React from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  ChevronDown,
  ChevronRight,
  Copy,
  Database,
  ExternalLink,
  Filter,
  Layers,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";

import {
  usePlatformMetrics,
  useProjectInsights,
  useTenantDashboard,
  useTenantLogs,
  type LogEntry,
  type LogsMode,
  type ProjectErrorItem,
  type ProjectHealthDTO,
  type ProjectInsightsResponse,
  type TenantUserDTO,
} from "../api/tenantAdmin";
import Button from "../components/ui/Button";
import { AlertsPanel } from "../components/admin/AlertsPanel";
import ProjectMembersPanel from "../components/settings/ProjectMembersPanel";
import { ExternalToolsBar } from "../components/admin/ExternalToolsBar";
import { useAuth } from "../hooks/useAuth";

// ─── Constants ───────────────────────────────────────────────────────────

type AdminTab = "projects" | "users" | "monitoring" | "logs" | "alerts";
type ProjectDrillTab = "overview" | "members" | "logs";
type ErrorFilter = "all" | "document" | "run";

const FILTER_CONTROL =
  "min-h-8 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-3 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]";

const SECTION_CARD =
  "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm";

const SECTION_HEADER_WRAP = "px-5";
const SECTION_HEADER_INNER = "py-3";
const SECTION_DIVIDER = "border-t border-[var(--border-subtle)]";

const LABEL_XS =
  "text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]";

const SINCE_OPTIONS: { value: string; label: string }[] = [
  { value: "15", label: "15 мин" },
  { value: "60", label: "1 час" },
  { value: "240", label: "4 часа" },
  { value: "1440", label: "24 часа" },
  { value: "2880", label: "48 часов" },
  { value: "10080", label: "7 дней" },
  { value: "43200", label: "30 дней" },
  { value: "0", label: "Всё время" },
];

const ROLE_LABELS: Record<string, string> = {
  superadmin: "Супер-администратор",
  tenant_admin: "Администратор",
  member: "Участник",
};

const PROJECT_ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  editor: "Редактор",
  viewer: "Наблюдатель",
};

const RUN_STATUS_CONFIG: Record<
  string,
  { label: string; tone: "ok" | "warn" | "error" | "neutral" }
> = {
  completed: { label: "Завершён", tone: "ok" },
  completed_with_errors: { label: "С ошибками", tone: "warn" },
  failed: { label: "Ошибка", tone: "error" },
  running: { label: "Выполняется", tone: "neutral" },
  pending: { label: "В очереди", tone: "neutral" },
};

// ─── Helpers ─────────────────────────────────────────────────────────────

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("ru-RU").format(value);
}

function fmtMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 1) return "< 1 мс";
  return `${new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: value < 10 ? 2 : 0,
  }).format(value)} мс`;
}

function fmtDurationSeconds(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return "—";
  if (sec < 60) return `${sec.toFixed(1)} с`;
  const mins = Math.floor(sec / 60);
  const rest = Math.round(sec - mins * 60);
  return `${mins} мин ${rest} с`;
}

function normLevel(level: string | null | undefined): string {
  if (!level) return "info";
  const n = level.toLowerCase();
  return n === "warn" ? "warning" : n;
}

function toneClass(tone: "ok" | "warn" | "error" | "default" | "neutral"): string {
  if (tone === "ok") return "text-[var(--color-success)]";
  if (tone === "warn") return "text-[var(--color-warning)]";
  if (tone === "error") return "text-[var(--color-error)]";
  return "text-[var(--text-primary)]";
}

function projectRoleLabel(role: string): string {
  return PROJECT_ROLE_LABELS[role.toLowerCase()] ?? role;
}

// ─── KpiCard ─────────────────────────────────────────────────────────────

const KpiCard: React.FC<{
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "ok" | "warn" | "error";
}> = ({ label, value, sub, tone = "default" }) => (
  <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 shadow-sm">
    <p className={LABEL_XS}>{label}</p>
    <p
      className={`truncate text-sm font-semibold tabular-nums leading-5 ${toneClass(tone)}`}
    >
      {value}
    </p>
    {sub && (
      <p className="truncate text-[10px] leading-4 text-[var(--text-muted)]">
        {sub}
      </p>
    )}
  </div>
);

// ─── LevelBadge ──────────────────────────────────────────────────────────

const LevelBadge: React.FC<{ level: string | null | undefined }> = ({
  level,
}) => {
  const n = normLevel(level);

  const cls =
    n === "error" || n === "critical"
      ? "border-red-200 bg-red-50 text-red-700"
      : n === "warning"
        ? "border-yellow-200 bg-yellow-50 text-yellow-700"
        : "border-blue-200 bg-blue-50 text-blue-700";

  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] ${cls}`}
    >
      {n}
    </span>
  );
};

// ─── ModeSwitch ──────────────────────────────────────────────────────────

const ModeSwitch: React.FC<{
  value: LogsMode;
  onChange: (v: LogsMode) => void;
}> = ({ value, onChange }) => (
  <div className="inline-flex overflow-hidden rounded-xl border border-[var(--border)] text-xs">
    <button
      type="button"
      onClick={() => onChange("operational")}
      className={`px-3 py-1.5 transition-colors ${
        value === "operational"
          ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
      }`}
    >
      События платформы
    </button>
    <button
      type="button"
      onClick={() => onChange("debug")}
      className={`border-l border-[var(--border)] px-3 py-1.5 transition-colors ${
        value === "debug"
          ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
      }`}
    >
      Debug (все логи)
    </button>
  </div>
);

// ─── MetaField ───────────────────────────────────────────────────────────

const MetaField: React.FC<{
  label: string;
  value: string | null | undefined;
  onClick?: () => void;
  actionLabel?: string;
}> = ({ label, value, onClick, actionLabel }) => (
  <div className="rounded-xl border border-[var(--border)] px-3 py-2">
    <div className="flex items-start justify-between gap-2">
      <p className={LABEL_XS}>{label}</p>
      {value && onClick && (
        <button
          type="button"
          onClick={onClick}
          className="text-[10px] font-medium text-[var(--accent-primary)] hover:underline"
        >
          {actionLabel ?? "Показать всё"}
        </button>
      )}
    </div>
    <p className="mt-0.5 break-all text-sm text-[var(--text-primary)]">
      {value || "—"}
    </p>
  </div>
);

// ─── TabButton ───────────────────────────────────────────────────────────

const TabButton: React.FC<{
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  badge?: number | string;
}> = ({ active, onClick, children, badge }) => (
  <button
    type="button"
    onClick={onClick}
    className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-xs font-medium transition-colors ${
      active
        ? "bg-[var(--accent-muted)] text-[var(--accent-primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
    }`}
  >
    {children}
    {badge != null && (
      <span className="rounded-full bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] tabular-nums">
        {badge}
      </span>
    )}
  </button>
);

// ─── ProjectRow ──────────────────────────────────────────────────────────

const ProjectRow: React.FC<{
  project: ProjectHealthDTO;
  onOpen: (id: string) => void;
}> = ({ project, onOpen }) => {
  const run = project.last_run;
  const cfg = run?.status ? RUN_STATUS_CONFIG[run.status] : null;

  const pct =
    run && run.total_checks > 0
      ? Math.round((run.completed_checks / run.total_checks) * 100)
      : null;

  const hasProblems =
    project.failed_documents > 0 ||
    project.quarantine_documents > 0 ||
    run?.has_errors === true;

  const barColor =
    run?.status === "failed"
      ? "bg-[var(--color-error)]"
      : run?.status === "completed"
        ? "bg-[var(--color-success)]"
        : run?.status === "completed_with_errors"
          ? "bg-[var(--color-warning)]"
          : "bg-[var(--accent-primary)]";

  return (
    <tr
      className="cursor-pointer border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--bg-elevated-soft)]"
      onClick={() => onOpen(project.deal_id)}
    >
      <td className="px-4 py-3">
        <div className="flex items-start gap-2">
          {hasProblems && (
            <AlertTriangle
              size={14}
              className="mt-0.5 shrink-0 text-[var(--color-warning)]"
            />
          )}
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
              {project.deal_name}
            </p>
            <p className="text-[10px] text-[var(--text-muted)]">
              Создан {formatDate(project.created_at)}
            </p>
          </div>
        </div>
      </td>

      <td className="px-4 py-3 text-center">
        <p className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
          {project.total_documents}
        </p>
        {(project.failed_documents > 0 ||
          project.quarantine_documents > 0) && (
          <p className="text-[10px]">
            {project.failed_documents > 0 && (
              <span className="text-[var(--color-error)]">
                ошибок: {project.failed_documents}
              </span>
            )}
            {project.failed_documents > 0 &&
              project.quarantine_documents > 0 &&
              " · "}
            {project.quarantine_documents > 0 && (
              <span className="text-[var(--color-warning)]">
                карантин: {project.quarantine_documents}
              </span>
            )}
          </p>
        )}
      </td>

      <td className="px-4 py-3">
        {cfg && run ? (
          <div className="space-y-0.5">
            <p className={`text-xs font-medium ${toneClass(cfg.tone)}`}>
              {cfg.label}
            </p>
            {run.completed_at && (
              <p className="text-[10px] text-[var(--text-muted)]">
                {formatDateTime(run.completed_at)}
              </p>
            )}
          </div>
        ) : (
          <span className="text-[10px] text-[var(--text-muted)]">
            Не запускался
          </span>
        )}
      </td>

      <td className="px-4 py-3">
        {pct !== null && run ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px] tabular-nums">
              <span className="text-[var(--text-muted)]">
                {run.completed_checks}/{run.total_checks}
              </span>
              <span className="font-semibold text-[var(--text-primary)]">
                {pct}%
              </span>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
              <div
                className={`h-1 rounded-full transition-all duration-500 ease-out ${barColor}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        ) : (
          <span className="text-[10px] text-[var(--text-muted)]">—</span>
        )}
      </td>

      <td className="px-4 py-3">
        <Button
          size="sm"
          variant="secondary"
          onClick={(e) => {
            e.stopPropagation();
            onOpen(project.deal_id);
          }}
        >
          Открыть
        </Button>
      </td>
    </tr>
  );
};

// ─── UserRow ─────────────────────────────────────────────────────────────

const UserRow: React.FC<{
  user: TenantUserDTO;
  expanded: boolean;
  onToggle: () => void;
  onOpenProject: (dealId: string) => void;
}> = ({ user, expanded, onToggle, onOpenProject }) => {
  const hasProjects = user.projects_count > 0;

  return (
    <>
      <tr
        className={`border-b border-[var(--border-subtle)] transition-colors ${
          hasProjects ? "cursor-pointer hover:bg-[var(--bg-elevated-soft)]" : ""
        }`}
        onClick={() => {
          if (hasProjects) onToggle();
        }}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {hasProjects ? (
              expanded ? (
                <ChevronDown
                  size={14}
                  className="shrink-0 text-[var(--text-muted)]"
                />
              ) : (
                <ChevronRight
                  size={14}
                  className="shrink-0 text-[var(--text-muted)]"
                />
              )
            ) : (
              <span className="inline-block w-3.5 shrink-0" />
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                {user.full_name || user.email}
              </p>
              {user.full_name && (
                <p className="truncate text-[10px] text-[var(--text-muted)]">
                  {user.email}
                </p>
              )}
            </div>
          </div>
        </td>
        <td className="px-4 py-3">
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
            {ROLE_LABELS[user.system_role] ?? user.system_role}
          </span>
        </td>
        <td className="px-4 py-3">
          {user.is_active ? (
            <span className="inline-flex items-center gap-1.5 text-[10px] text-[var(--color-success)]">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
              Активен
            </span>
          ) : (
            <span className="text-[10px] text-[var(--text-muted)]">
              Деактивирован
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          <span className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {user.projects_count}
          </span>
        </td>
        <td className="px-4 py-3 text-[10px] text-[var(--text-muted)]">
          {formatDate(user.created_at)}
        </td>
      </tr>

      {expanded && hasProjects && (
        <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
          <td colSpan={5} className="px-4 py-3">
            <div className="ml-6 flex flex-wrap gap-1.5">
              {user.projects.map((p) => (
                <button
                  key={p.deal_id}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenProject(p.deal_id);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-2.5 py-1 text-[11px] text-[var(--text-primary)] transition hover:border-[var(--accent-primary)] hover:bg-[var(--accent-muted)]"
                >
                  <span className="font-medium">{p.deal_name}</span>
                  <span className="text-[10px] text-[var(--text-muted)]">
                    · {projectRoleLabel(p.role)}
                  </span>
                </button>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

// ─── LogDetailsPane ──────────────────────────────────────────────────────

interface LogDetailsCorrelations {
  onFilterByRun?: (runId: string) => void;
  onFilterByDocument?: (documentId: string) => void;
  onFilterByTask?: (taskId: string) => void;
}

const LogDetailsPane: React.FC<{
  entry: LogEntry | null;
  copied: boolean;
  onCopy: () => void;
  onClear: () => void;
  correlations?: LogDetailsCorrelations;
}> = ({ entry, copied, onCopy, onClear, correlations }) => {
  if (!entry) {
    return (
      <div className="flex h-full items-center justify-center p-5">
        <div className="text-center">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Выберите запись лога
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-muted)]">
            Нажмите на строку в таблице, чтобы увидеть подробности
          </p>
        </div>
      </div>
    );
  }

  const isGrouped = (entry.count ?? 1) > 1;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={SECTION_HEADER_WRAP}>
        <div
          className={`flex items-start justify-between gap-3 ${SECTION_HEADER_INNER}`}
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Детали лога
            </p>
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
              {formatDateTime(entry.timestamp)}
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              onClick={onCopy}
              leftIcon={<Copy size={12} />}
            >
              {copied ? "Скопировано" : "JSON"}
            </Button>
            <Button size="sm" variant="ghost" onClick={onClear}>
              ✕
            </Button>
          </div>
        </div>
        <div className={SECTION_DIVIDER} />
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <LevelBadge level={entry.level} />
            {entry.stage && (
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                {entry.stage}
              </span>
            )}
            {entry.queue && (
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                {entry.queue}
              </span>
            )}
            {isGrouped && (
              <span
                className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                title="Группа повторяющихся событий"
              >
                <Layers size={10} />×{entry.count}
              </span>
            )}
          </div>

          <div className="rounded-xl border border-[var(--border)] px-3 py-2">
            <p className={LABEL_XS}>Event</p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-primary)]">
              {entry.event || "—"}
            </p>
            {isGrouped && entry.first_seen && entry.last_seen && (
              <p className="mt-2 text-[10px] text-[var(--text-muted)]">
                Первое: {formatDateTime(entry.first_seen)} · Последнее:{" "}
                {formatDateTime(entry.last_seen)}
              </p>
            )}
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <MetaField label="Logger" value={entry.logger} />
            <MetaField label="Worker" value={entry.worker_hostname} />
            <MetaField label="Deal ID" value={entry.deal_id} />
            <MetaField
              label="Run ID"
              value={entry.run_id}
              onClick={
                entry.run_id && correlations?.onFilterByRun
                  ? () => correlations.onFilterByRun?.(entry.run_id as string)
                  : undefined
              }
              actionLabel="Все логи run"
            />
            <MetaField
              label="Document ID"
              value={entry.document_id}
              onClick={
                entry.document_id && correlations?.onFilterByDocument
                  ? () =>
                      correlations.onFilterByDocument?.(
                        entry.document_id as string,
                      )
                  : undefined
              }
              actionLabel="Все логи документа"
            />
            <MetaField
              label="Task ID"
              value={entry.task_id}
              onClick={
                entry.task_id && correlations?.onFilterByTask
                  ? () => correlations.onFilterByTask?.(entry.task_id as string)
                  : undefined
              }
              actionLabel="Все логи task"
            />
            <MetaField label="Task name" value={entry.task_name} />
            <MetaField label="Timestamp" value={entry.timestamp} />
          </div>

          <div>
            <p className={LABEL_XS}>Raw JSON</p>
            <pre className="mt-1.5 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-4 py-3 text-[10px] leading-5 text-[var(--text-secondary)]">
              {JSON.stringify(entry.raw, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── LogsTable ───────────────────────────────────────────────────────────

const LogsTable: React.FC<{
  logs: LogEntry[];
  selectedIdx: number | null;
  onSelect: (idx: number) => void;
  compact?: boolean;
}> = ({ logs, selectedIdx, onSelect, compact = false }) => (
  <table className={`w-full ${compact ? "min-w-[720px]" : "min-w-[920px]"} border-collapse`}>
    <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
      <tr className="border-b border-[var(--border)]">
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Timestamp</th>
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Level</th>
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Event</th>
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Stage</th>
        {!compact && (
          <>
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Queue</th>
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Worker</th>
          </>
        )}
      </tr>
    </thead>
    <tbody>
      {logs.map((entry, idx) => {
        const sel = selectedIdx === idx;
        const grouped = (entry.count ?? 1) > 1;

        return (
          <tr
            key={idx}
            className={`cursor-pointer border-b border-[var(--border-subtle)] transition-colors ${
              sel
                ? "bg-[var(--accent-muted)]"
                : "hover:bg-[var(--bg-elevated-soft)]"
            }`}
            onClick={() => onSelect(idx)}
          >
            <td className="px-4 py-2.5 align-top text-[10px] text-[var(--text-secondary)]">
              {formatDateTime(entry.timestamp)}
            </td>
            <td className="px-4 py-2.5 align-top">
              <div className="flex flex-wrap items-center gap-1">
                <LevelBadge level={entry.level} />
                {grouped && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                    title="Группа повторяющихся событий"
                  >
                    <Layers size={9} />×{entry.count}
                  </span>
                )}
              </div>
            </td>
            <td className="px-4 py-2.5 align-top">
              <div className={compact ? "max-w-[340px]" : "max-w-[400px]"}>
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {entry.event || "—"}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                  {entry.logger || "—"}
                  {entry.run_id ? ` · run ${entry.run_id.slice(0, 8)}…` : ""}
                </p>
              </div>
            </td>
            <td className="px-4 py-2.5 align-top text-sm text-[var(--text-secondary)]">
              {entry.stage || "—"}
            </td>
            {!compact && (
              <>
                <td className="px-4 py-2.5 align-top text-sm text-[var(--text-secondary)]">
                  {entry.queue || "—"}
                </td>
                <td className="px-4 py-2.5 align-top text-sm text-[var(--text-secondary)]">
                  <span className="inline-block max-w-[180px] truncate">
                    {entry.worker_hostname || "—"}
                  </span>
                </td>
              </>
            )}
          </tr>
        );
      })}
    </tbody>
  </table>
);

// ─── ErrorRow ────────────────────────────────────────────────────────────

const ErrorRow: React.FC<{
  item: ProjectErrorItem;
  expanded: boolean;
  onToggle: () => void;
  onOpenLogs: () => void;
}> = ({ item, expanded, onToggle, onOpenLogs }) => {
  const isDoc = item.kind === "document";
  const title = isDoc
    ? item.document_filename || `Документ ${item.document_id?.slice(0, 8) ?? ""}…`
    : `Run ${item.run_id?.slice(0, 8) ?? ""}…`;

  const statusText = isDoc
    ? item.document_status ?? "—"
    : item.run_status ?? "—";

  const statusTone: "error" | "warn" | "neutral" =
    (isDoc && item.document_status === "failed") ||
    (!isDoc && item.run_status === "failed")
      ? "error"
      : (isDoc && item.document_status === "quarantine") ||
          (!isDoc && item.run_status === "completed_with_errors")
        ? "warn"
        : "neutral";

  return (
    <>
      <tr
        className="cursor-pointer border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--bg-elevated-soft)]"
        onClick={onToggle}
      >
        <td className="px-4 py-3 align-top">
          <div className="flex items-center gap-2">
            {expanded ? (
              <ChevronDown
                size={14}
                className="shrink-0 text-[var(--text-muted)]"
              />
            ) : (
              <ChevronRight
                size={14}
                className="shrink-0 text-[var(--text-muted)]"
              />
            )}
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
              {isDoc ? "Документ" : "Run"}
            </span>
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <p className="truncate text-sm font-medium text-[var(--text-primary)]">
            {title}
          </p>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            {formatDateTime(item.occurred_at)}
          </p>
        </td>
        <td className="px-4 py-3 align-top">
          <span
            className={`text-xs font-medium ${
              statusTone === "error"
                ? "text-[var(--color-error)]"
                : statusTone === "warn"
                  ? "text-[var(--color-warning)]"
                  : "text-[var(--text-secondary)]"
            }`}
          >
            {statusText}
          </span>
          {item.stage && (
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
              stage: {item.stage}
            </p>
          )}
        </td>
        <td className="px-4 py-3 align-top">
          <div className="max-w-[420px]">
            <p className="truncate text-sm text-[var(--text-primary)]">
              {item.error_message || item.error_type || item.error_reason || "—"}
            </p>
            {item.error_type && item.error_message && (
              <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                {item.error_type}
                {item.error_reason ? ` · ${item.error_reason}` : ""}
              </p>
            )}
          </div>
        </td>
        <td className="px-4 py-3 align-top text-right">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              onOpenLogs();
            }}
          >
            Логи
          </Button>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
          <td colSpan={5} className="px-4 py-3">
            <div className="ml-6 space-y-2">
              <div className="grid gap-2 sm:grid-cols-2">
                {isDoc && (
                  <>
                    <MetaField
                      label="Document ID"
                      value={item.document_id}
                    />
                    <MetaField label="Файл" value={item.document_filename} />
                  </>
                )}
                {!isDoc && (
                  <MetaField label="Run ID" value={item.run_id} />
                )}
                <MetaField label="Stage" value={item.stage} />
                <MetaField label="Тип ошибки" value={item.error_type} />
                <MetaField label="Причина" value={item.error_reason} />
                <MetaField label="Время" value={item.occurred_at} />
              </div>

              {item.error_details &&
                Object.keys(item.error_details).length > 0 && (
                  <div>
                    <p className={LABEL_XS}>Raw error_details</p>
                    <pre className="mt-1.5 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-[10px] leading-5 text-[var(--text-secondary)]">
                      {JSON.stringify(item.error_details, null, 2)}
                    </pre>
                  </div>
                )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

// ─── ProjectDrillDown ────────────────────────────────────────────────────

const ProjectDrillDown: React.FC<{
  dealId: string;
  onBack: () => void;
  onOpenProject: (dealId: string) => void;
}> = ({ dealId, onBack, onOpenProject }) => {
  const insightsQ = useProjectInsights(dealId);
  const [subTab, setSubTab] = React.useState<ProjectDrillTab>("overview");

  const [logsMode, setLogsMode] = React.useState<LogsMode>("operational");
  const [projectLogsSince, setProjectLogsSince] =
    React.useState<number>(1440);
  const [correlationRunId, setCorrelationRunId] = React.useState<string | null>(
    null,
  );
  const [correlationDocId, setCorrelationDocId] = React.useState<string | null>(
    null,
  );
  const [correlationTaskId, setCorrelationTaskId] = React.useState<
    string | null
  >(null);

  const [errorFilter, setErrorFilter] = React.useState<ErrorFilter>("all");
  const [expandedErrorKey, setExpandedErrorKey] = React.useState<string | null>(
    null,
  );

  const projectLogsQ = useTenantLogs(
    {
      deal_id: dealId,
      run_id: correlationRunId ?? undefined,
      document_id: correlationDocId ?? undefined,
      task_id: correlationTaskId ?? undefined,
      mode: logsMode,
      limit: 100,
      since_minutes: projectLogsSince,
      group_similar: true,
    },
    { enabled: subTab === "logs" },
  );

  const [selectedLogIdx, setSelectedLogIdx] = React.useState<number | null>(
    null,
  );
  const [copied, setCopied] = React.useState(false);
  const copyTimer = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    };
  }, []);

  React.useEffect(() => {
    setSelectedLogIdx(null);
  }, [
    dealId,
    subTab,
    logsMode,
    projectLogsSince,
    correlationRunId,
    correlationDocId,
    correlationTaskId,
  ]);

  React.useEffect(() => {
    setCopied(false);
  }, [selectedLogIdx]);

  const insights: ProjectInsightsResponse | undefined = insightsQ.data;
  const logs = projectLogsQ.data?.entries ?? [];
  const logsStats = projectLogsQ.data?.stats;
  const lokiUp = projectLogsQ.data?.loki_available ?? false;
  const selectedLog: LogEntry | null =
    selectedLogIdx != null ? (logs[selectedLogIdx] ?? null) : null;

  const runStats = insights?.runs;
  const docs = insights?.documents;
  const members = insights?.members ?? [];
  const membersCount = insights?.members_count ?? members.length;
  const dealName = insights?.deal_name ?? "Проект";
  const errors = insights?.errors;
  const allErrorItems = errors?.items ?? [];

  const filteredErrorItems = allErrorItems.filter((item) => {
    if (errorFilter === "all") return true;
    return item.kind === errorFilter;
  });

  const handleCopy = async () => {
    if (!selectedLog) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(selectedLog.raw, null, 2),
      );
      setCopied(true);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* noop */
    }
  };

  const hasCorrelation =
    correlationRunId || correlationDocId || correlationTaskId;

  const clearCorrelation = () => {
    setCorrelationRunId(null);
    setCorrelationDocId(null);
    setCorrelationTaskId(null);
  };

  const openLogsForError = (item: ProjectErrorItem) => {
    setSubTab("logs");
    setLogsMode("debug");
    setProjectLogsSince(0); // "всё время" — ошибка могла произойти давно
    setCorrelationRunId(item.run_id ?? null);
    setCorrelationDocId(item.document_id ?? null);
    setCorrelationTaskId(null);
  };

  const errorKey = (item: ProjectErrorItem, idx: number) =>
    `${item.kind}-${item.document_id ?? ""}-${item.run_id ?? ""}-${idx}`;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Sub-header */}
      <div className={SECTION_HEADER_WRAP}>
        <div
          className={`flex flex-wrap items-center justify-between gap-3 ${SECTION_HEADER_INNER}`}
        >
          <div className="flex min-w-0 items-center gap-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={onBack}
              leftIcon={<ArrowLeft size={14} />}
            >
              К списку
            </Button>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                {dealName}
              </p>
              {insights?.created_at && (
                <p className="text-[10px] text-[var(--text-muted)]">
                  Создан {formatDate(insights.created_at)}
                  {insights.last_activity_at
                    ? ` · Активность: ${formatDateTime(insights.last_activity_at)}`
                    : ""}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <TabButton
              active={subTab === "overview"}
              onClick={() => setSubTab("overview")}
            >
              Обзор
            </TabButton>
            <TabButton
              active={subTab === "members"}
              onClick={() => setSubTab("members")}
              badge={membersCount}
            >
              Участники
            </TabButton>
            <TabButton
              active={subTab === "logs"}
              onClick={() => setSubTab("logs")}
              badge={logs.length}
            >
              Логи
            </TabButton>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onOpenProject(dealId)}
              leftIcon={<ExternalLink size={14} />}
            >
              Открыть проект целиком
            </Button>
          </div>
        </div>
        <div className={SECTION_DIVIDER} />
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-auto">
        {insightsQ.isLoading && !insights ? (
          <div className="flex h-full items-center justify-center text-[var(--text-muted)]">
            <Loader2 size={20} className="animate-spin" />
            <span className="ml-3 text-sm">Загружаем сводку по проекту…</span>
          </div>
        ) : insightsQ.error && !insights ? (
          <div className="flex h-full items-center justify-center p-5 text-center">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Не удалось загрузить сводку по проекту
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => insightsQ.refetch()}
                className="mt-3"
              >
                Повторить
              </Button>
            </div>
          </div>
        ) : (
          <>
            {/* Overview */}
            {subTab === "overview" && (
              <div className="space-y-4 px-5 pb-5 pt-4">
                {/* Documents */}
                <div className={SECTION_CARD}>
                  <div className={SECTION_HEADER_WRAP}>
                    <div className={SECTION_HEADER_INNER}>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        Документы
                      </p>
                      <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                        Сводка по документам этого проекта
                      </p>
                    </div>
                    <div className={SECTION_DIVIDER} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">
                    <KpiCard label="Всего" value={fmt(docs?.total)} />
                    <KpiCard
                      label="Ошибки"
                      value={fmt(docs?.failed)}
                      tone={(docs?.failed ?? 0) > 0 ? "error" : "default"}
                    />
                    <KpiCard
                      label="Карантин"
                      value={fmt(docs?.quarantine)}
                      tone={
                        (docs?.quarantine ?? 0) > 0 ? "warn" : "default"
                      }
                    />
                    <KpiCard
                      label="Проверены человеком"
                      value={fmt(docs?.reviewed_by_person)}
                    />
                  </div>

                  {docs && Object.keys(docs.by_status).length > 0 && (
                    <div className="border-t border-[var(--border-subtle)] px-5 py-4">
                      <p className={LABEL_XS}>По статусам</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {Object.entries(docs.by_status).map(([st, cnt]) => (
                          <span
                            key={st}
                            className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
                          >
                            {st}: <span className="tabular-nums">{cnt}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {docs && Object.keys(docs.by_doc_type).length > 0 && (
                    <div className="border-t border-[var(--border-subtle)] px-5 py-4">
                      <p className={LABEL_XS}>По типам документов</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {Object.entries(docs.by_doc_type).map(([dt, cnt]) => (
                          <span
                            key={dt}
                            className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
                          >
                            {dt}: <span className="tabular-nums">{cnt}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Runs */}
                <div className={SECTION_CARD}>
                  <div className={SECTION_HEADER_WRAP}>
                    <div className={SECTION_HEADER_INNER}>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        Анализы (runs)
                      </p>
                      <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                        История запусков анализа по проекту
                      </p>
                    </div>
                    <div className={SECTION_DIVIDER} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">
                    <KpiCard label="Всего" value={fmt(runStats?.total_runs)} />
                    <KpiCard
                      label="Успешных"
                      value={fmt(runStats?.completed_runs)}
                      tone={
                        (runStats?.completed_runs ?? 0) > 0 ? "ok" : "default"
                      }
                    />
                    <KpiCard
                      label="Провальных"
                      value={fmt(runStats?.failed_runs)}
                      tone={
                        (runStats?.failed_runs ?? 0) > 0 ? "error" : "default"
                      }
                    />
                    <KpiCard
                      label="Средняя длительность"
                      value={fmtDurationSeconds(runStats?.avg_duration_seconds)}
                    />
                  </div>

                  {(runStats?.recent_runs.length ?? 0) > 0 && (
                    <div className="border-t border-[var(--border-subtle)] px-5 py-4">
                      <p className={LABEL_XS}>Последние запуски</p>
                      <div className="mt-2 overflow-auto">
                        <table className="w-full min-w-[560px] border-collapse">
                          <thead className="bg-[var(--bg-elevated-soft)]">
                            <tr className="border-b border-[var(--border)]">
                              <th
                                className={`px-3 py-2 text-left ${LABEL_XS}`}
                              >
                                Статус
                              </th>
                              <th
                                className={`px-3 py-2 text-left ${LABEL_XS}`}
                              >
                                Прогресс
                              </th>
                              <th
                                className={`px-3 py-2 text-left ${LABEL_XS}`}
                              >
                                Начат
                              </th>
                              <th
                                className={`px-3 py-2 text-left ${LABEL_XS}`}
                              >
                                Завершён
                              </th>
                              <th
                                className={`px-3 py-2 text-left ${LABEL_XS}`}
                              />
                            </tr>
                          </thead>
                          <tbody>
                            {runStats!.recent_runs.map((r) => {
                              const cfg = RUN_STATUS_CONFIG[r.status] ?? {
                                label: r.status,
                                tone: "neutral" as const,
                              };
                              return (
                                <tr
                                  key={r.run_id}
                                  className="border-b border-[var(--border-subtle)] last:border-b-0"
                                >
                                  <td className="px-3 py-2">
                                    <span
                                      className={`text-xs font-medium ${toneClass(cfg.tone)}`}
                                    >
                                      {cfg.label}
                                    </span>
                                  </td>
                                  <td className="px-3 py-2 text-sm tabular-nums text-[var(--text-secondary)]">
                                    {r.completed_checks}/{r.total_checks}
                                  </td>
                                  <td className="px-3 py-2 text-[11px] text-[var(--text-muted)]">
                                    {formatDateTime(r.started_at)}
                                  </td>
                                  <td className="px-3 py-2 text-[11px] text-[var(--text-muted)]">
                                    {formatDateTime(r.completed_at)}
                                  </td>
                                  <td className="px-3 py-2 text-right">
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => {
                                        setSubTab("logs");
                                        setCorrelationRunId(r.run_id);
                                        setCorrelationDocId(null);
                                        setCorrelationTaskId(null);
                                        setLogsMode("debug");
                                        setProjectLogsSince(0);
                                      }}
                                    >
                                      Логи
                                    </Button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>

                {/* Problems & Errors */}
                <div className={SECTION_CARD}>
                  <div className={SECTION_HEADER_WRAP}>
                    <div
                      className={`flex flex-wrap items-center justify-between gap-2 ${SECTION_HEADER_INNER}`}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          Проблемы и ошибки
                        </p>
                        <p className="mt-0.5 flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
                          <Database size={11} />
                          История из PostgreSQL — доступна всегда, независимо от
                          retention логов
                        </p>
                      </div>

                      <div className="inline-flex overflow-hidden rounded-xl border border-[var(--border)] text-[11px]">
                        {(
                          [
                            { v: "all", label: "Все" },
                            { v: "document", label: "Документы" },
                            { v: "run", label: "Runs" },
                          ] as { v: ErrorFilter; label: string }[]
                        ).map((opt) => (
                          <button
                            key={opt.v}
                            type="button"
                            onClick={() => setErrorFilter(opt.v)}
                            className={`px-2.5 py-1 transition-colors ${
                              errorFilter === opt.v
                                ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className={SECTION_DIVIDER} />
                  </div>

                  <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">
                    <KpiCard
                      label="Документов failed"
                      value={fmt(errors?.failed_documents)}
                      tone={(errors?.failed_documents ?? 0) > 0 ? "error" : "default"}
                    />
                    <KpiCard
                      label="Документов quarantine"
                      value={fmt(errors?.quarantine_documents)}
                      tone={
                        (errors?.quarantine_documents ?? 0) > 0
                          ? "warn"
                          : "default"
                      }
                    />
                    <KpiCard
                      label="Runs failed"
                      value={fmt(errors?.failed_runs)}
                      tone={(errors?.failed_runs ?? 0) > 0 ? "error" : "default"}
                    />
                    <KpiCard
                      label="Runs с ошибками"
                      value={fmt(errors?.completed_with_errors_runs)}
                      tone={
                        (errors?.completed_with_errors_runs ?? 0) > 0
                          ? "warn"
                          : "default"
                      }
                    />
                  </div>

                  <div className="border-t border-[var(--border-subtle)]">
                    {filteredErrorItems.length === 0 ? (
                      <div className="flex min-h-[120px] items-center justify-center px-5 py-6 text-sm text-[var(--text-muted)]">
                        {(errors?.total_items ?? 0) === 0
                          ? "В этом проекте нет зафиксированных ошибок 🎉"
                          : "Нет записей по выбранному фильтру"}
                      </div>
                    ) : (
                      <div className="overflow-auto">
                        <table className="w-full min-w-[860px] border-collapse">
                          <thead className="bg-[var(--bg-elevated-soft)]">
                            <tr className="border-b border-[var(--border)]">
                              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                                Тип
                              </th>
                              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                                Объект
                              </th>
                              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                                Статус / Stage
                              </th>
                              <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                                Ошибка
                              </th>
                              <th className={`px-4 py-2.5 ${LABEL_XS}`} />
                            </tr>
                          </thead>
                          <tbody>
                            {filteredErrorItems.map((item, idx) => {
                              const key = errorKey(item, idx);
                              return (
                                <ErrorRow
                                  key={key}
                                  item={item}
                                  expanded={expandedErrorKey === key}
                                  onToggle={() =>
                                    setExpandedErrorKey(
                                      expandedErrorKey === key ? null : key,
                                    )
                                  }
                                  onOpenLogs={() => openLogsForError(item)}
                                />
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {errors?.truncated && (
                      <p className="px-5 py-3 text-[10px] text-[var(--text-muted)]">
                        Показаны последние {filteredErrorItems.length} записей.
                        Всего ошибок больше — используйте фильтры или прямой
                        запрос к БД.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Members */}
            {subTab === "members" && (
              <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
                <ProjectMembersPanel dealId={dealId} />
              </div>
            )}

            {/* Logs */}
            {subTab === "logs" && (
              <div className="flex h-full min-h-0 flex-col px-5 pb-5 pt-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <ModeSwitch value={logsMode} onChange={setLogsMode} />

                    <label className="inline-flex items-center gap-1.5">
                      <span className={LABEL_XS}>Период:</span>
                      <select
                        value={String(projectLogsSince)}
                        onChange={(e) =>
                          setProjectLogsSince(
                            Number.parseInt(e.target.value, 10) || 0,
                          )
                        }
                        className="min-h-7 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] px-2 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
                      >
                        {SINCE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {hasCorrelation && (
                      <button
                        type="button"
                        onClick={clearCorrelation}
                        className="inline-flex items-center gap-1 rounded-full border border-[var(--accent-primary)] bg-[var(--accent-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)] hover:brightness-95"
                      >
                        <Filter size={11} />
                        {correlationRunId && (
                          <span>run: {correlationRunId.slice(0, 8)}…</span>
                        )}
                        {correlationDocId && (
                          <span>doc: {correlationDocId.slice(0, 8)}…</span>
                        )}
                        {correlationTaskId && (
                          <span>task: {correlationTaskId.slice(0, 8)}…</span>
                        )}
                        <span className="ml-1 text-[10px] opacity-70">
                          ✕ сбросить
                        </span>
                      </button>
                    )}

                    {logsStats && (
                      <p className="text-[10px] text-[var(--text-muted)]">
                        Показано {logsStats.returned}
                        {logsStats.filtered_out_by_mode > 0
                          ? ` · скрыто info: ${logsStats.filtered_out_by_mode}`
                          : ""}
                      </p>
                    )}
                  </div>
                </div>

                {!lokiUp && projectLogsQ.data && (
                  <div className="mb-3 shrink-0 rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-xs text-yellow-800">
                    Loki временно недоступен.
                  </div>
                )}

                <div
                  className={`${SECTION_CARD} flex min-h-[420px] flex-1 overflow-hidden`}
                >
                  {projectLogsQ.isLoading && !projectLogsQ.data ? (
                    <div className="flex h-full w-full items-center justify-center text-[var(--text-muted)]">
                      <Loader2 size={20} className="animate-spin" />
                      <span className="ml-3 text-sm">Загружаем логи…</span>
                    </div>
                  ) : projectLogsQ.error ? (
                    <div className="flex h-full w-full items-center justify-center p-5 text-center">
                      <div>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          Не удалось загрузить логи
                        </p>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => projectLogsQ.refetch()}
                          className="mt-3"
                        >
                          Повторить
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="grid h-full w-full grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px]">
                      <div className="flex min-h-0 min-w-0 flex-col overflow-hidden xl:border-r xl:border-[var(--border-subtle)]">
                        {logs.length === 0 ? (
                          <div className="flex h-full items-center justify-center p-6 text-center text-sm text-[var(--text-muted)]">
                            {logsMode === "operational"
                              ? "Проблемных событий не найдено. Переключитесь на «Debug» или используйте раздел «Проблемы и ошибки» в Обзоре — данные из БД доступны всегда."
                              : "Логи в Loki не найдены. Возможно, они уже удалены по retention — см. «Проблемы и ошибки» в Обзоре."}
                          </div>
                        ) : (
                          <div className="min-h-0 flex-1 overflow-auto">
                            <LogsTable
                              logs={logs}
                              selectedIdx={selectedLogIdx}
                              onSelect={setSelectedLogIdx}
                              compact
                            />
                          </div>
                        )}
                      </div>

                      <aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">
                        <LogDetailsPane
                          entry={selectedLog}
                          copied={copied}
                          onCopy={handleCopy}
                          onClear={() => setSelectedLogIdx(null)}
                          correlations={{
                            onFilterByRun: (id) => {
                              setCorrelationRunId(id);
                              setCorrelationDocId(null);
                              setCorrelationTaskId(null);
                              setLogsMode("debug");
                            },
                            onFilterByDocument: (id) => {
                              setCorrelationDocId(id);
                              setCorrelationRunId(null);
                              setCorrelationTaskId(null);
                              setLogsMode("debug");
                            },
                            onFilterByTask: (id) => {
                              setCorrelationTaskId(id);
                              setCorrelationRunId(null);
                              setCorrelationDocId(null);
                              setLogsMode("debug");
                            },
                          }}
                        />
                      </aside>
                    </div>
                  )}
                </div>

                {selectedLog && (
                  <div
                    className={`${SECTION_CARD} mt-3 shrink-0 overflow-hidden xl:hidden`}
                  >
                    <LogDetailsPane
                      entry={selectedLog}
                      copied={copied}
                      onCopy={handleCopy}
                      onClear={() => setSelectedLogIdx(null)}
                    />
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

// ─── Main Page ───────────────────────────────────────────────────────────

const TenantAdminPage: React.FC = () => {
  const navigate = useNavigate();
  const { globalRole } = useAuth();

  const [activeTab, setActiveTab] = React.useState<AdminTab>("projects");
  const [selectedProjectId, setSelectedProjectId] = React.useState<string | null>(
    null,
  );
  const [expandedUserIds, setExpandedUserIds] = React.useState<Set<string>>(
    new Set(),
  );

  const dashQ = useTenantDashboard();

  const metricsQ = usePlatformMetrics(undefined, {
    enabled: activeTab === "monitoring",
  });

  const [logsMode, setLogsMode] = React.useState<LogsMode>("operational");
  const [correlationRunId, setCorrelationRunId] = React.useState<string | null>(
    null,
  );
  const [correlationDocId, setCorrelationDocId] = React.useState<string | null>(
    null,
  );
  const [correlationTaskId, setCorrelationTaskId] = React.useState<
    string | null
  >(null);

  const [draftDealId, setDraftDealId] = React.useState("");
  const [draftLevel, setDraftLevel] = React.useState("");
  const [draftStage, setDraftStage] = React.useState("");
  const [draftQueue, setDraftQueue] = React.useState("");
  const [draftSince, setDraftSince] = React.useState("60");
  const [draftLimit, setDraftLimit] = React.useState("50");

  const [applied, setApplied] = React.useState({
    deal_id: "",
    level: "",
    stage: "",
    queue: "",
    since_minutes: 60,
    limit: 50,
  });

  const logsQ = useTenantLogs(
    {
      deal_id: applied.deal_id || undefined,
      run_id: correlationRunId ?? undefined,
      document_id: correlationDocId ?? undefined,
      task_id: correlationTaskId ?? undefined,
      level: applied.level || undefined,
      stage: applied.stage || undefined,
      queue: applied.queue || undefined,
      mode: logsMode,
      since_minutes: applied.since_minutes,
      limit: applied.limit,
      group_similar: true,
    },
    { enabled: activeTab === "logs" },
  );

  const [selectedLogIdx, setSelectedLogIdx] = React.useState<number | null>(
    null,
  );
  const [copied, setCopied] = React.useState(false);
  const copyTimer = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    };
  }, []);

  React.useEffect(() => {
    setCopied(false);
  }, [selectedLogIdx]);

  React.useEffect(() => {
    setSelectedLogIdx(null);
  }, [
    applied,
    logsMode,
    correlationRunId,
    correlationDocId,
    correlationTaskId,
  ]);

  const projects = dashQ.data?.projects ?? [];
  const users = dashQ.data?.users ?? [];
  const md = metricsQ.data;
  const ld = logsQ.data;
  const logs = ld?.entries ?? [];
  const logsStats = ld?.stats;
  const promUp = md?.prometheus_available ?? false;
  const lokiUp = ld?.loki_available ?? false;
  const selectedLog: LogEntry | null =
    selectedLogIdx != null ? (logs[selectedLogIdx] ?? null) : null;

  const problemProjects = projects.filter(
    (p) =>
      p.failed_documents > 0 ||
      p.quarantine_documents > 0 ||
      p.last_run?.status === "failed",
  );

  const stageSet = new Set<string>();
  if (draftStage) stageSet.add(draftStage);
  if (applied.stage) stageSet.add(applied.stage);
  logs.forEach((e) => {
    if (e.stage) stageSet.add(e.stage);
  });
  const stageOpts = Array.from(stageSet).sort((a, b) =>
    a.localeCompare(b, "ru"),
  );

  const queueSet = new Set<string>();
  if (draftQueue) queueSet.add(draftQueue);
  if (applied.queue) queueSet.add(applied.queue);
  logs.forEach((e) => {
    if (e.queue) queueSet.add(e.queue);
  });
  const queueOpts = Array.from(queueSet).sort((a, b) =>
    a.localeCompare(b, "ru"),
  );

  const handleCopy = async () => {
    if (!selectedLog) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(selectedLog.raw, null, 2),
      );
      setCopied(true);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* noop */
    }
  };

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    const s = Number.parseInt(draftSince, 10);
    const l = Number.parseInt(draftLimit, 10);
    setApplied({
      deal_id: draftDealId,
      level: draftLevel,
      stage: draftStage,
      queue: draftQueue,
      since_minutes: Number.isFinite(s) && s >= 0 ? s : 60,
      limit: Number.isFinite(l) && l > 0 ? l : 50,
    });
  };

  const handleRefresh = () => {
    dashQ.refetch();
    if (activeTab === "monitoring") metricsQ.refetch();
    if (activeTab === "logs") logsQ.refetch();
  };

  const isRefreshing =
    dashQ.isFetching ||
    (activeTab === "monitoring" && metricsQ.isFetching) ||
    (activeTab === "logs" && logsQ.isFetching);

  const metricVal = (v: number | null | undefined) =>
    promUp ? fmt(v ?? 0) : "—";

  const openProjectDrillDown = (dealId: string) => {
    setActiveTab("projects");
    setSelectedProjectId(dealId);
  };

  const toggleUserExpanded = (userId: string) => {
    setExpandedUserIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };

  const clearCorrelation = () => {
    setCorrelationRunId(null);
    setCorrelationDocId(null);
    setCorrelationTaskId(null);
  };

  const hasCorrelation =
    correlationRunId || correlationDocId || correlationTaskId;

  if (dashQ.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-[var(--text-muted)]">
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm">Загружаем панель администратора…</span>
        </div>
      </div>
    );
  }

  if (dashQ.error) {
    return (
      <div className="flex h-full items-center justify-center px-4">
        <div className={`${SECTION_CARD} w-full max-w-sm px-6 py-6 text-center`}>
          <XCircle size={24} className="mx-auto mb-3 text-[var(--color-error)]" />
          <p className="text-sm font-semibold text-[var(--color-error)]">
            Не удалось загрузить панель
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-muted)]">
            Проверьте права доступа или обратитесь в поддержку
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => dashQ.refetch()}
            className="mt-4"
          >
            Попробовать снова
          </Button>
        </div>
      </div>
    );
  }

  if (!dashQ.data) return null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">
      <header className="flex shrink-0 items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Панель администратора
          </h1>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            Проекты · Пользователи · Мониторинг · Логи · Алерты
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ExternalToolsBar />
          <Button
            size="sm"
            variant="secondary"
            onClick={handleRefresh}
            isLoading={isRefreshing}
            leftIcon={<RefreshCw size={14} />}
          >
            Обновить
          </Button>
        </div>
      </header>

      {problemProjects.length > 0 && !selectedProjectId && (
        <div
          className={`${SECTION_CARD} shrink-0 border-yellow-200 bg-yellow-50 px-5 py-4`}
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              size={16}
              className="mt-0.5 shrink-0 text-[var(--color-warning)]"
            />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-yellow-800">
                {problemProjects.length === 1
                  ? "1 проект требует внимания"
                  : `${problemProjects.length} проекта требуют внимания`}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {problemProjects.map((p) => (
                  <button
                    key={p.deal_id}
                    type="button"
                    onClick={() => openProjectDrillDown(p.deal_id)}
                    className="rounded-lg border border-yellow-300 bg-white px-2.5 py-1 text-[10px] font-medium text-yellow-800 transition hover:bg-yellow-50"
                  >
                    {p.deal_name}
                    {p.failed_documents > 0 && (
                      <span className="ml-1.5 text-[var(--color-error)]">
                        · {p.failed_documents} ошибок
                      </span>
                    )}
                    {p.quarantine_documents > 0 && (
                      <span className="ml-1.5 text-[var(--color-warning)]">
                        · {p.quarantine_documents} карантин
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <section
        className={`${SECTION_CARD} flex min-h-0 flex-1 flex-col overflow-hidden`}
      >
        {!selectedProjectId && (
          <div className={`${SECTION_HEADER_WRAP} shrink-0`}>
            <div className={`flex flex-wrap gap-1.5 ${SECTION_HEADER_INNER}`}>
              <TabButton
                active={activeTab === "projects"}
                onClick={() => setActiveTab("projects")}
                badge={projects.length}
              >
                Проекты
              </TabButton>
              <TabButton
                active={activeTab === "users"}
                onClick={() => setActiveTab("users")}
                badge={users.length}
              >
                Пользователи
              </TabButton>
              <TabButton
                active={activeTab === "monitoring"}
                onClick={() => setActiveTab("monitoring")}
              >
                Мониторинг
              </TabButton>
              <TabButton
                active={activeTab === "logs"}
                onClick={() => setActiveTab("logs")}
              >
                Логи
              </TabButton>
              <TabButton
                active={activeTab === "alerts"}
                onClick={() => setActiveTab("alerts")}
              >
                Алерты
              </TabButton>
            </div>
            <div className={SECTION_DIVIDER} />
          </div>
        )}

        {/* Projects */}
        {activeTab === "projects" && (
          <>
            {selectedProjectId ? (
              <ProjectDrillDown
                dealId={selectedProjectId}
                onBack={() => setSelectedProjectId(null)}
                onOpenProject={(id) => navigate(`/projects/${id}`)}
              />
            ) : (
              <div className="min-h-0 flex-1 overflow-auto">
                {projects.length === 0 ? (
                  <div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">
                    Нет проектов
                  </div>
                ) : (
                  <table className="w-full min-w-[920px] border-collapse">
                    <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
                      <tr className="border-b border-[var(--border)]">
                        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                          Проект
                        </th>
                        <th className={`px-4 py-2.5 text-center ${LABEL_XS}`}>
                          Документы
                        </th>
                        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                          Последний анализ
                        </th>
                        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                          Прогресс
                        </th>
                        <th className="w-24 px-4 py-2.5" />
                      </tr>
                    </thead>
                    <tbody>
                      {projects.map((p) => (
                        <ProjectRow
                          key={p.deal_id}
                          project={p}
                          onOpen={openProjectDrillDown}
                        />
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </>
        )}

        {/* Users */}
        {activeTab === "users" && (
          <div className="min-h-0 flex-1 overflow-auto">
            {users.length === 0 ? (
              <div className="flex h-full min-h-[240px] items-center justify-center text-sm text-[var(--text-muted)]">
                Нет пользователей
              </div>
            ) : (
              <table className="w-full min-w-[820px] border-collapse">
                <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
                  <tr className="border-b border-[var(--border)]">
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      Пользователь
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      Роль
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      Статус
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      Проекты
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      Добавлен
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <UserRow
                      key={u.id}
                      user={u}
                      expanded={expandedUserIds.has(u.id)}
                      onToggle={() => toggleUserExpanded(u.id)}
                      onOpenProject={openProjectDrillDown}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Monitoring */}
        {activeTab === "monitoring" && (
          <div className="min-h-0 flex-1 overflow-auto">
            {metricsQ.isLoading && !md ? (
              <div className="flex h-full min-h-[240px] items-center justify-center text-[var(--text-muted)]">
                <Loader2 size={20} className="animate-spin" />
                <span className="ml-3 text-sm">Загружаем метрики…</span>
              </div>
            ) : metricsQ.error && !md ? (
              <div className="flex h-full min-h-[240px] items-center justify-center p-5">
                <div className="text-center">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Не удалось загрузить метрики
                  </p>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => metricsQ.refetch()}
                    className="mt-3"
                  >
                    Повторить
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4 px-5 pb-5 pt-4">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <KpiCard
                    label="Prometheus"
                    value={promUp ? "Доступен" : "Недоступен"}
                    tone={promUp ? "ok" : "warn"}
                    sub={`Обновлено: ${formatDateTime(md?.collected_at)}`}
                  />
                  <KpiCard
                    label="DLQ size"
                    value={metricVal(md?.pipeline.dlq_size)}
                    tone={
                      promUp && (md?.pipeline.dlq_size ?? 0) > 0
                        ? "warn"
                        : "default"
                    }
                  />
                  <KpiCard
                    label="Active runs"
                    value={metricVal(md?.pipeline.active_runs)}
                  />
                  <KpiCard
                    label="Stuck executions"
                    value={metricVal(md?.pipeline.stuck_executions)}
                    tone={
                      promUp && (md?.pipeline.stuck_executions ?? 0) > 0
                        ? "error"
                        : "default"
                    }
                  />
                </div>

                {globalRole === "tenant_admin" && (
                  <p className="text-[10px] text-[var(--text-muted)]">
                    Метрики Prometheus — инфраструктурные и глобальные. Для
                    метрик по проекту откройте проект во вкладке «Проекты».
                  </p>
                )}

                {!promUp && (
                  <div className="rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-xs text-yellow-800">
                    Метрики временно недоступны — деградированный режим.
                  </div>
                )}

                <div className={SECTION_CARD}>
                  <div className={SECTION_HEADER_WRAP}>
                    <div className={SECTION_HEADER_INNER}>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        Pipeline
                      </p>
                      <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                        Документы за последний час
                      </p>
                    </div>
                    <div className={SECTION_DIVIDER} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 px-5 py-4">
                    <KpiCard
                      label="Processed / 1h"
                      value={metricVal(md?.pipeline.docs_processed_last_hour)}
                      tone={
                        promUp &&
                        (md?.pipeline.docs_processed_last_hour ?? 0) > 0
                          ? "ok"
                          : "default"
                      }
                    />
                    <KpiCard
                      label="Failed / 1h"
                      value={metricVal(md?.pipeline.docs_failed_last_hour)}
                      tone={
                        promUp && (md?.pipeline.docs_failed_last_hour ?? 0) > 0
                          ? "error"
                          : "default"
                      }
                    />
                  </div>
                </div>

                <div className={SECTION_CARD}>
                  <div className={SECTION_HEADER_WRAP}>
                    <div className={SECTION_HEADER_INNER}>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        API
                      </p>
                      <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                        Топ-5 endpoint&apos;ов по запросам за час
                      </p>
                    </div>
                    <div className={SECTION_DIVIDER} />
                  </div>
                  <div className="px-5 py-4">
                    {!promUp || (md?.api.top_endpoints ?? []).length === 0 ? (
                      <p className="text-[10px] text-[var(--text-muted)]">
                        {promUp
                          ? "Нет данных — метрики появятся после накопления трафика."
                          : "Prometheus недоступен."}
                      </p>
                    ) : (
                      <div className="overflow-auto">
                        <table className="w-full min-w-[680px] border-collapse">
                          <thead className="bg-[var(--bg-elevated-soft)]">
                            <tr className="border-b border-[var(--border)]">
                              <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                                Endpoint
                              </th>
                              <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                                Requests
                              </th>
                              <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                                Errors
                              </th>
                              <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                                P95
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {(md?.api.top_endpoints ?? []).map((ep) => (
                              <tr
                                key={`${ep.method}-${ep.handler}`}
                                className="border-b border-[var(--border-subtle)] last:border-b-0"
                              >
                                <td className="px-3 py-2">
                                  <p className="font-mono text-[10px] text-[var(--text-muted)]">
                                    {ep.method}
                                  </p>
                                  <p className="truncate text-sm text-[var(--text-primary)]">
                                    {ep.handler}
                                  </p>
                                </td>
                                <td className="px-3 py-2 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                                  {fmt(ep.requests)}
                                </td>
                                <td className="px-3 py-2 text-sm tabular-nums">
                                  <span
                                    className={
                                      ep.errors > 0
                                        ? "font-semibold text-[var(--color-error)]"
                                        : "text-[var(--text-secondary)]"
                                    }
                                  >
                                    {fmt(ep.errors)}
                                  </span>
                                </td>
                                <td className="px-3 py-2 text-sm text-[var(--text-secondary)]">
                                  {fmtMs(ep.p95_ms)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <div className={SECTION_CARD}>
                    <div className={SECTION_HEADER_WRAP}>
                      <div className={SECTION_HEADER_INNER}>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          LLM
                        </p>
                        <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                          Запросы и таймауты за час
                        </p>
                      </div>
                      <div className={SECTION_DIVIDER} />
                    </div>
                    <div className="px-5 py-4">
                      {!promUp || (md?.llm.providers ?? []).length === 0 ? (
                        <p className="text-[10px] text-[var(--text-muted)]">
                          {promUp
                            ? "Нет LLM-метрик — появятся после прогона pipeline."
                            : "Prometheus недоступен."}
                        </p>
                      ) : (
                        <div className="grid gap-2">
                          {(md?.llm.providers ?? []).map((prov) => (
                            <div
                              key={prov.provider}
                              className="rounded-xl border border-[var(--border)] px-3 py-2"
                            >
                              <div className="flex items-center justify-between">
                                <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                                  {prov.provider}
                                </p>
                                <Bot
                                  size={14}
                                  className="text-[var(--text-muted)]"
                                />
                              </div>
                              <div className="mt-2 grid grid-cols-2 gap-2">
                                <div>
                                  <p className={LABEL_XS}>Requests</p>
                                  <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                                    {fmt(prov.requests_last_hour)}
                                  </p>
                                </div>
                                <div>
                                  <p className={LABEL_XS}>Timeouts</p>
                                  <p
                                    className={`mt-0.5 text-sm font-semibold tabular-nums ${
                                      prov.timeouts_last_hour > 0
                                        ? "text-[var(--color-error)]"
                                        : "text-[var(--text-primary)]"
                                    }`}
                                  >
                                    {fmt(prov.timeouts_last_hour)}
                                  </p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={SECTION_CARD}>
                    <div className={SECTION_HEADER_WRAP}>
                      <div className={SECTION_HEADER_INNER}>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          Celery
                        </p>
                        <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                          Ошибки задач за час
                        </p>
                      </div>
                      <div className={SECTION_DIVIDER} />
                    </div>
                    <div className="px-5 py-4">
                      {!promUp ||
                      (md?.celery.task_failures_last_hour ?? []).length ===
                        0 ? (
                        <p className="text-[10px] text-[var(--text-muted)]">
                          {promUp
                            ? "Нет ошибок Celery за последний час."
                            : "Prometheus недоступен."}
                        </p>
                      ) : (
                        <div className="overflow-auto">
                          <table className="w-full min-w-[480px] border-collapse">
                            <thead className="bg-[var(--bg-elevated-soft)]">
                              <tr className="border-b border-[var(--border)]">
                                <th
                                  className={`px-3 py-2 text-left ${LABEL_XS}`}
                                >
                                  Task
                                </th>
                                <th
                                  className={`px-3 py-2 text-left ${LABEL_XS}`}
                                >
                                  Failures
                                </th>
                                <th
                                  className={`px-3 py-2 text-left ${LABEL_XS}`}
                                >
                                  Types
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {(md?.celery.task_failures_last_hour ?? []).map(
                                (t) => (
                                  <tr
                                    key={t.task_name}
                                    className="border-b border-[var(--border-subtle)] last:border-b-0"
                                  >
                                    <td className="px-3 py-2 font-mono text-[10px] text-[var(--text-primary)]">
                                      {t.task_name}
                                    </td>
                                    <td className="px-3 py-2 text-sm font-semibold tabular-nums text-[var(--color-error)]">
                                      {fmt(t.failures_last_hour)}
                                    </td>
                                    <td className="px-3 py-2 text-sm text-[var(--text-secondary)]">
                                      {t.failure_types.length > 0
                                        ? t.failure_types.join(", ")
                                        : "—"}
                                    </td>
                                  </tr>
                                ),
                              )}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Logs */}
        {activeTab === "logs" && (
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden px-5 pb-5 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <ModeSwitch value={logsMode} onChange={setLogsMode} />

              {hasCorrelation && (
                <button
                  type="button"
                  onClick={clearCorrelation}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--accent-primary)] bg-[var(--accent-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)] hover:brightness-95"
                >
                  <Filter size={11} />
                  {correlationRunId && (
                    <span>run: {correlationRunId.slice(0, 8)}…</span>
                  )}
                  {correlationDocId && (
                    <span>doc: {correlationDocId.slice(0, 8)}…</span>
                  )}
                  {correlationTaskId && (
                    <span>task: {correlationTaskId.slice(0, 8)}…</span>
                  )}
                  <span className="ml-1 text-[10px] opacity-70">
                    ✕ сбросить
                  </span>
                </button>
              )}
            </div>

            <form
              onSubmit={handleApplyFilters}
              className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-7"
            >
              <label className="xl:col-span-2">
                <span className={`mb-1 block ${LABEL_XS}`}>Проект</span>
                <select
                  value={draftDealId}
                  onChange={(e) => setDraftDealId(e.target.value)}
                  className={FILTER_CONTROL}
                >
                  <option value="">Все проекты</option>
                  {projects.map((p) => (
                    <option key={p.deal_id} value={p.deal_id}>
                      {p.deal_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className={`mb-1 block ${LABEL_XS}`}>Level</span>
                <select
                  value={draftLevel}
                  onChange={(e) => setDraftLevel(e.target.value)}
                  className={FILTER_CONTROL}
                >
                  <option value="">Все</option>
                  <option value="error">error</option>
                  <option value="warning">warning</option>
                  <option value="info">info</option>
                </select>
              </label>
              <label>
                <span className={`mb-1 block ${LABEL_XS}`}>Stage</span>
                <select
                  value={draftStage}
                  onChange={(e) => setDraftStage(e.target.value)}
                  className={FILTER_CONTROL}
                >
                  <option value="">Все</option>
                  {stageOpts.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className={`mb-1 block ${LABEL_XS}`}>Queue</span>
                <select
                  value={draftQueue}
                  onChange={(e) => setDraftQueue(e.target.value)}
                  className={FILTER_CONTROL}
                >
                  <option value="">Все</option>
                  {queueOpts.map((q) => (
                    <option key={q} value={q}>
                      {q}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className={`mb-1 block ${LABEL_XS}`}>Период</span>
                <select
                  value={draftSince}
                  onChange={(e) => setDraftSince(e.target.value)}
                  className={FILTER_CONTROL}
                >
                  {SINCE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-end gap-2">
                <label className="flex-1">
                  <span className={`mb-1 block ${LABEL_XS}`}>Лимит</span>
                  <select
                    value={draftLimit}
                    onChange={(e) => setDraftLimit(e.target.value)}
                    className={FILTER_CONTROL}
                  >
                    <option value="25">25</option>
                    <option value="50">50</option>
                    <option value="100">100</option>
                    <option value="200">200</option>
                    <option value="500">500</option>
                  </select>
                </label>
                <Button type="submit" size="sm" variant="secondary">
                  ОК
                </Button>
              </div>
            </form>

            <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4">
              <KpiCard
                label="Loki"
                value={lokiUp ? "Доступен" : "Недоступен"}
                tone={lokiUp ? "ok" : "warn"}
              />
              <KpiCard label="Показано" value={fmt(logs.length)} />
              <KpiCard
                label="Скрыто info"
                value={fmt(logsStats?.filtered_out_by_mode ?? 0)}
                tone={
                  (logsStats?.filtered_out_by_mode ?? 0) > 0
                    ? "warn"
                    : "default"
                }
              />
              <KpiCard
                label="Режим"
                value={logsMode === "operational" ? "События" : "Debug"}
                tone={logsMode === "operational" ? "ok" : "default"}
              />
            </div>

            {!lokiUp && ld && (
              <div className="shrink-0 rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-xs text-yellow-800">
                Loki временно недоступен.
              </div>
            )}

            <div
              className={`${SECTION_CARD} flex min-h-0 flex-1 overflow-hidden`}
            >
              {logsQ.isLoading && !ld ? (
                <div className="flex h-full w-full items-center justify-center text-[var(--text-muted)]">
                  <Loader2 size={20} className="animate-spin" />
                  <span className="ml-3 text-sm">Загружаем логи…</span>
                </div>
              ) : logsQ.error && !ld ? (
                <div className="flex h-full w-full items-center justify-center p-5 text-center">
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      Не удалось загрузить логи
                    </p>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => logsQ.refetch()}
                      className="mt-3"
                    >
                      Повторить
                    </Button>
                  </div>
                </div>
              ) : !lokiUp ? (
                <div className="flex h-full w-full items-center justify-center text-sm text-[var(--text-muted)]">
                  Loki недоступен
                </div>
              ) : (
                <div className="grid h-full w-full grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px]">
                  <div className="flex min-h-0 min-w-0 flex-col overflow-hidden xl:border-r xl:border-[var(--border-subtle)]">
                    {logs.length === 0 ? (
                      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-[var(--text-muted)]">
                        {logsMode === "operational"
                          ? "Проблемных событий не найдено. Для долговременной истории откройте проект → «Проблемы и ошибки»."
                          : "Логи не найдены — измените фильтры или период. Для долговременной истории откройте проект → «Проблемы и ошибки»."}
                      </div>
                    ) : (
                      <div className="min-h-0 flex-1 overflow-auto">
                        <LogsTable
                          logs={logs}
                          selectedIdx={selectedLogIdx}
                          onSelect={setSelectedLogIdx}
                        />
                      </div>
                    )}
                  </div>

                  <aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">
                    <LogDetailsPane
                      entry={selectedLog}
                      copied={copied}
                      onCopy={handleCopy}
                      onClear={() => setSelectedLogIdx(null)}
                      correlations={{
                        onFilterByRun: (id) => {
                          setCorrelationRunId(id);
                          setCorrelationDocId(null);
                          setCorrelationTaskId(null);
                          setLogsMode("debug");
                        },
                        onFilterByDocument: (id) => {
                          setCorrelationDocId(id);
                          setCorrelationRunId(null);
                          setCorrelationTaskId(null);
                          setLogsMode("debug");
                        },
                        onFilterByTask: (id) => {
                          setCorrelationTaskId(id);
                          setCorrelationRunId(null);
                          setCorrelationDocId(null);
                          setLogsMode("debug");
                        },
                      }}
                    />
                  </aside>
                </div>
              )}
            </div>

            {selectedLog && (
              <div
                className={`${SECTION_CARD} shrink-0 overflow-hidden xl:hidden`}
              >
                <LogDetailsPane
                  entry={selectedLog}
                  copied={copied}
                  onCopy={handleCopy}
                  onClear={() => setSelectedLogIdx(null)}
                />
              </div>
            )}
          </div>
        )}

        {/* Alerts */}
        {activeTab === "alerts" && (
          <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
            <AlertsPanel />
          </div>
        )}
      </section>
    </div>
  );
};

export default TenantAdminPage;


