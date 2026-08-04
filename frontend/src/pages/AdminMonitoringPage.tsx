// src/pages/AdminMonitoringPage.tsx
// Страница мониторинга для superadmin.
// Плашки с ссылками на внешние инструменты наблюдаемости.
// Все ссылки открываются в новой вкладке.

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
} from "lucide-react";

// ─────────────────────────────────────────────────────────────
// Конфигурация URL
// ─────────────────────────────────────────────────────────────

const GRAFANA_BASE =
  import.meta.env.VITE_GRAFANA_URL ?? "http://localhost:3000";
const PROMETHEUS_URL =
  import.meta.env.VITE_PROMETHEUS_URL ?? "http://localhost:9090";
const ALERTMANAGER_URL =
  import.meta.env.VITE_ALERTMANAGER_URL ?? "http://localhost:9093";
const MINIO_URL =
  import.meta.env.VITE_MINIO_CONSOLE_URL ?? "http://localhost:9001";
const API_DOCS_URL =
  import.meta.env.VITE_API_DOCS_URL ?? "http://localhost:8000/docs";
const OLLAMA_URL =
  import.meta.env.VITE_OLLAMA_URL ?? "http://localhost:11434";

// ─────────────────────────────────────────────────────────────
// Типы
// ─────────────────────────────────────────────────────────────

interface ToolItem {
  id: string;
  title: string;
  description: string;
  href: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  badge?: string;
}

interface ToolGroup {
  id: string;
  title: string;
  description: string;
  tools: ToolItem[];
}

// ─────────────────────────────────────────────────────────────
// Данные
// ─────────────────────────────────────────────────────────────

const TOOL_GROUPS: ToolGroup[] = [
  {
    id: "dashboards",
    title: "Обзорные дашборды",
    description:
      "Готовые визуализации по ключевым областям системы: работа платформы, конвейер обработки документов, качество сервиса и быстрый поиск по логам.",
    tools: [
      {
        id: "operations",
        title: "Operations Overview",
        description: "HTTP, LLM, DLQ, active runs",
        href: `${GRAFANA_BASE}/d/operations-overview`,
        icon: Activity,
      },
      {
        id: "pipeline",
        title: "Pipeline Overview",
        description: "Стадии обработки документов",
        href: `${GRAFANA_BASE}/d/pipeline-overview`,
        icon: GitBranch,
      },
      {
        id: "slo",
        title: "SLO Overview",
        description: "Метрики качества и SLO",
        href: `${GRAFANA_BASE}/d/slo-overview`,
        icon: CheckCircle,
      },
      {
        id: "logs-explorer",
        title: "Log Explorer",
        description: "Поиск и анализ логов Loki",
        href: `${GRAFANA_BASE}/explore`,
        icon: Search,
      },
    ],
  },
  {
    id: "metrics",
    title: "Метрики и алерты",
    description:
      "Первичные источники метрик и управление уведомлениями. Используются для глубокой диагностики инцидентов и настройки правил алертинга.",
    tools: [
      {
        id: "grafana",
        title: "Grafana",
        description: "Dashboards, alerts, explore",
        href: GRAFANA_BASE,
        icon: BarChart2,
      },
      {
        id: "prometheus",
        title: "Prometheus",
        description: "Метрики, alert rules, targets",
        href: PROMETHEUS_URL,
        icon: Activity,
      },
      {
        id: "alertmanager",
        title: "Alertmanager",
        description: "Активные алерты, silences",
        href: ALERTMANAGER_URL,
        icon: AlertTriangle,
      },
    ],
  },
  {
    id: "traces-logs",
    title: "Логи и трейсы",
    description:
      "Детальный разбор инцидентов: структурированные логи через Loki и распределённые трейсы запросов через Tempo. Открываются в Grafana Explore.",
    tools: [
      {
        id: "loki",
        title: "Loki",
        description: "Structured logs через Grafana Explore",
        href: `${GRAFANA_BASE}/explore?orgId=1&left=%5B%22now-1h%22,%22now%22,%22Loki%22,%7B%7D%5D`,
        icon: FileText,
        badge: "через Grafana",
      },
      {
        id: "tempo",
        title: "Tempo",
        description: "Distributed traces через Grafana Explore",
        href: `${GRAFANA_BASE}/explore?orgId=1&left=%5B%22now-1h%22,%22now%22,%22Tempo%22,%7B%7D%5D`,
        icon: Layers,
        badge: "через Grafana",
      },
    ],
  },
  {
    id: "infrastructure",
    title: "Инфраструктура и API",
    description:
      "Внутренние сервисы платформы: object storage с артефактами, документация backend API и статус LLM inference.",
    tools: [
      {
        id: "minio",
        title: "MinIO Console",
        description: "Object storage: артефакты, экспорты",
        href: MINIO_URL,
        icon: Box,
      },
      {
        id: "api-docs",
        title: "API Docs",
        description: "OpenAPI Swagger для backend",
        href: API_DOCS_URL,
        icon: BookOpen,
      },
      {
        id: "ollama",
        title: "Ollama API",
        description: "LLM inference status и модели",
        href: `${OLLAMA_URL}/api/tags`,
        icon: Cpu,
      },
    ],
  },
];

// ─────────────────────────────────────────────────────────────
// ToolCard
// ─────────────────────────────────────────────────────────────

const ToolCard: React.FC<{ tool: ToolItem }> = ({ tool }) => (
  <a
    href={tool.href}
    target="_blank"
    rel="noopener noreferrer"
    className={[
      "group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm",
      "transition-all duration-200",
      "hover:border-[var(--border-strong)] hover:shadow-md",
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
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
          {tool.title}
        </h3>
        {tool.badge && (
          <span className="shrink-0 rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
            {tool.badge}
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
        {tool.description}
      </p>
    </div>
  </a>
);

// ─────────────────────────────────────────────────────────────
// ToolGroupSection
// ─────────────────────────────────────────────────────────────

const ToolGroupSection: React.FC<{ group: ToolGroup }> = ({ group }) => (
  <section
    id={group.id}
    className="scroll-mt-20 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm"
  >
    <div className="mb-4">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {group.title}
      </div>
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

// ─────────────────────────────────────────────────────────────
// AdminMonitoringPage
// ─────────────────────────────────────────────────────────────

const AdminMonitoringPage: React.FC = () => (
  <div className="h-full overflow-y-auto overscroll-contain">
    <div className="animate-fadein space-y-4 p-4 md:p-5">
      <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Мониторинг
          </h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Инструменты наблюдаемости платформы: дашборды, метрики, логи,
            трейсы и инфраструктура.
          </p>
        </div>
      </header>

      {TOOL_GROUPS.map((group) => (
        <ToolGroupSection key={group.id} group={group} />
      ))}
    </div>
  </div>
);

export default AdminMonitoringPage;


