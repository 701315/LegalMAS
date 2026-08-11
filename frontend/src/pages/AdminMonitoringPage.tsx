// frontend/src/pages/AdminMonitoringPage.tsx
//
// Superadmin monitoring page — backend-driven.
//
// Источник истины для ссылок: GET /api/v1/tenant/tools (useExternalTools).
// Frontend не строит localhost URL самостоятельно — это неправильно для
// multi-contour deployment (dev/demo имеют разные настройки в .env).
//
// Отображает:
// - секцию Grafana Dashboards (deep links из backend)
// - секцию Сервисов (Grafana, Prometheus, Loki, MinIO, ...)
// Скелетон рендера: Loading → Error → Not superadmin → Groups

import React from "react";
import {
  Activity,
  GitBranch,
  CheckCircle,
  Search,
  BarChart2,
  AlertTriangle,
  Layers,
  FileText,
  Box,
  BookOpen,
  Cpu,
  ExternalLink,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { useExternalTools } from "../api/alerts";
import Button from "../components/ui/Button";

// ─── Icon maps ────────────────────────────────────────────────────────────────

type IconComponent = React.ComponentType<React.SVGProps<SVGSVGElement>>;

/** Иконки для Grafana dashboard deep links. Ключ — uid из backend. */
const DASHBOARD_ICONS: Record<string, IconComponent> = {
  "operations-overview": Activity,
  "legalmas-pipeline": GitBranch,
  "slo-overview": CheckCircle,
  "logs-explorer": Search,
};

/** Иконки для сервисов. Ключ — service.key из backend. */
const SERVICE_ICONS: Record<string, IconComponent> = {
  grafana: BarChart2,
  prometheus: Activity,
  alertmanager: AlertTriangle,
  tempo: Layers,
  loki: FileText,
  minio: Box,
  api_docs: BookOpen,
  ollama: Cpu,
};

const FALLBACK_ICON: IconComponent = Activity;

// ─── Types ────────────────────────────────────────────────────────────────────

interface ToolItem {
  id: string;
  title: string;
  description: string;
  href: string;
  icon: IconComponent;
}

interface ToolGroup {
  id: string;
  title: string;
  description: string;
  tools: ToolItem[];
}

// ─── ToolCard ─────────────────────────────────────────────────────────────────

const ToolCard: React.FC<{ tool: ToolItem }> = ({ tool }) => (
  <a
    href={tool.href}
    target="_blank"
    rel="noopener noreferrer"
    className={[
      "group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm",
      "transition-all duration-200 hover:shadow-md",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35",
      "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]",
    ].join(" ")}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
        <tool.icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <ExternalLink
        className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100"
        aria-hidden="true"
      />
    </div>

    <div className="mt-3 min-w-0">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
        {tool.title}
      </h3>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
        {tool.description}
      </p>
    </div>
  </a>
);

// ─── ToolGroupSection ─────────────────────────────────────────────────────────

const ToolGroupSection: React.FC<{ group: ToolGroup }> = ({ group }) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
    <div className="mb-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {group.title}
      </p>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        {group.description}
      </p>
    </div>

    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {group.tools.map((tool) => (
        <ToolCard key={tool.id} tool={tool} />
      ))}
    </div>
  </section>
);

// ─── AdminMonitoringPage ──────────────────────────────────────────────────────

const AdminMonitoringPage: React.FC = () => {
  const toolsQ = useExternalTools();

  // Собираем ToolGroup[] из backend response.
  // Мемоизация: пересчёт только когда меняется data.
  const groups = React.useMemo<ToolGroup[]>(() => {
    const data = toolsQ.data;
    // Доступ к странице уже гарантирован guard'ом RequireSuperadmin
    // в App.tsx — здесь не проверяем роль повторно.
    if (!data) return [];

    const dashboardTools: ToolItem[] = data.dashboards.map((d) => ({
      id: d.uid,
      title: d.label,
      description: d.description,
      href: d.url,
      icon: DASHBOARD_ICONS[d.uid] ?? FALLBACK_ICON,
    }));

    const serviceTools: ToolItem[] = data.services.map((s) => ({
      id: s.key,
      title: s.label,
      description: s.description,
      href: s.url,
      icon: SERVICE_ICONS[s.key] ?? FALLBACK_ICON,
    }));

    const result: ToolGroup[] = [];

    if (dashboardTools.length > 0) {
      result.push({
        id: "dashboards",
        title: "Обзорные дашборды",
        description:
          "Deep links в Grafana. URL берутся из backend-конфигурации текущего контура.",
        tools: dashboardTools,
      });
    }

    if (serviceTools.length > 0) {
      result.push({
        id: "services",
        title: "Сервисы observability",
        description:
          "Прямые ссылки на Grafana, Prometheus, Alertmanager, Loki, Tempo, MinIO, API docs и Ollama.",
        tools: serviceTools,
      });
    }

    return result;
  }, [toolsQ.data]);

  // ── Loading state ───────────────────────────────────────────────────────
  if (toolsQ.isLoading && !toolsQ.data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-[var(--text-muted)]">
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm">Загружаем monitoring links…</span>
        </div>
      </div>
    );
  }

  // ── Error state ─────────────────────────────────────────────────────────
  if (toolsQ.error && !toolsQ.data) {
    return (
      <div className="flex h-full items-center justify-center px-4">
        <div className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-6 text-center shadow-sm">
          <XCircle
            size={24}
            className="mx-auto mb-3 text-[var(--color-error-text)]"
          />
          <p className="text-sm font-semibold text-[var(--color-error-text)]">
            Не удалось загрузить ссылки мониторинга
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-muted)]">
            Проверьте backend config и доступность admin API
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => toolsQ.refetch()}
            className="mt-4"
          >
            Попробовать снова
          </Button>
        </div>
      </div>
    );
  }

  if (!toolsQ.data) return null;

  // ── Main render ─────────────────────────────────────────────────────────
  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">
        {/* Header */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Мониторинг
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Инструменты наблюдаемости платформы. Ссылки берутся из
                backend-конфигурации контура и не зависят от browser localhost.
              </p>
            </div>

            <Button
              size="sm"
              variant="secondary"
              onClick={() => toolsQ.refetch()}
              isLoading={toolsQ.isFetching}
              leftIcon={<RefreshCw size={14} />}
            >
              Обновить ссылки
            </Button>
          </div>
        </header>

        {/* Groups */}
        {groups.length === 0 ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
            <p className="text-sm text-[var(--text-secondary)]">
              Backend не вернул доступных monitoring links для текущего контура.
            </p>
          </section>
        ) : (
          groups.map((group) => (
            <ToolGroupSection key={group.id} group={group} />
          ))
        )}
      </div>
    </div>
  );
};

export default AdminMonitoringPage;


