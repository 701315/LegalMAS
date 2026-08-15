// =============================================================
// src/pages/tabs/CounterpartiesTab.tsx
// Вкладка «Анализ выявленных контрагентов».
//
// Preview flow:
// 1) Intro screen — короткое описание раздела
// 2) Demo screen  — overview + shared split-view workspace
//
// Архитектура после Wave 1 refactoring:
// - types    → ./counterparties/types.ts
// - constants + demo data → ./counterparties/constants.ts
// - pure utils / sort helpers → ./counterparties/utils.ts
//
// TODO при подключении API:
// - подключить useCounterparties(dealId, currentRunId)
// - заменить demo-данные на backend DTO
// - привязать summary / table / detail panel к реальному enrichment
// - заменить alert() на реальный export flow
// =============================================================

import React from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  ChevronsUpDown,
  Link2,
  Search,
  ShieldCheck,
} from "lucide-react";

import Button from "../../components/ui/Button";
import PageSection from "../../components/ui/PageSection";

import {
  COVERAGE_ROWS,
  DEMO_AGGREGATES,
  DEMO_DETAILS,
} from "./counterparties/constants";
import type {
  CounterpartiesTabProps,
  CounterpartyAggregate,
  CounterpartyDetail,
  DrilldownKind,
  ExportFormat,
  ExportMenuKind,
  PreviewMode,
  SortKey,
  SortState,
} from "./counterparties/types";
import {
  buildCountryStructure,
  buildCounterpartiesTotals,
  buildCriticalCounterparties,
  buildRiskMeta,
  buildTopByContracts,
  buildTopByValue,
  getAriaSort,
  getNextSortState,
  reviewLabel,
  reviewTone,
  riskBadgeLabel,
  riskBadgeTone,
  sortCounterparties,
} from "./counterparties/utils";

// ---------------------------------------------------------------------------
// Shared UI primitives
// ---------------------------------------------------------------------------

const FeatureCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
}> = ({ icon, title, description }) => (
  <div className="flex h-full flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
    <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--accent-primary)]">
      {icon}
    </div>
    <div>
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
    </div>
  </div>
);

/**
 * Badge — семантические тоны:
 *   neutral — нейтральный тэг (страна, тип контракта)
 *   success — accent-статус (Preview badge), терракотовый
 *   high    — критичный / negative signal (красный)
 *   medium  — warning / требует внимания (жёлтый)
 *   low     — позитивный статус (зелёный, semantic success)
 *
 * NB: tone="success" (accent) и tone="low" (semantic success) —
 * это разные визуальные категории с разной семантикой.
 */
const Badge: React.FC<{
  children: React.ReactNode;
  tone?: "neutral" | "success" | "high" | "medium" | "low";
}> = ({ children, tone = "neutral" }) => {
  const toneClass = {
    neutral:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
    success:
      "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]",
    high: "status-border-error status-bg-error status-text-error",
    medium: "status-border-warning status-bg-warning status-text-warning",
    low: "status-border-success status-bg-success status-text-success",
  }[tone];

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
        toneClass,
      ].join(" ")}
    >
      {children}
    </span>
  );
};

const KpiCard: React.FC<{
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
  onClick?: () => void;
}> = ({ label, value, hint, accent = false, onClick }) => {
  const isInteractive = typeof onClick === "function";

  const content = (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {label}
      </p>
      <p
        className={[
          "mt-1 text-2xl font-semibold tabular-nums",
          accent ? "text-[var(--color-error-text)]" : "text-[var(--text-primary)]",
          isInteractive
            ? "underline decoration-transparent transition group-hover:decoration-current"
            : "",
        ].join(" ")}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">{hint}</p>
      ) : null}
    </>
  );

  if (!isInteractive) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left shadow-sm transition hover:bg-[var(--bg-elevated-soft)]"
    >
      {content}
    </button>
  );
};

const RankedListCard: React.FC<{
  title: string;
  items: Array<{
    name: string;
    country: string;
    value: string;
  }>;
}> = ({ title, items }) => (
  <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="border-b border-[var(--border-subtle)] px-4 py-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
    </div>
    <div className="divide-y divide-[var(--border-subtle)]">
      {items.map((item, index) => (
        <div key={`${item.name}-${index}`} className="flex items-center gap-3 px-4 py-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)] text-[12px] font-semibold text-[var(--text-primary)]">
            {index + 1}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[var(--text-primary)]">{item.name}</p>
            <p className="text-[12px] text-[var(--text-muted)]">{item.country}</p>
          </div>
          <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {item.value}
          </div>
        </div>
      ))}
    </div>
  </div>
);

const CountryStructureCard: React.FC<{
  items: Array<{
    country: string;
    count: number;
  }>;
}> = ({ items }) => {
  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="space-y-3 px-4 py-4">
        {items.map((item) => {
          const share = total > 0 ? Math.round((item.count / total) * 100) : 0;
          return (
            <div key={item.country}>
              <div className="mb-1 flex items-center justify-between gap-3">
                <p className="text-sm text-[var(--text-primary)]">{item.country}</p>
                <p className="text-[12px] font-medium tabular-nums text-[var(--text-muted)]">
                  {item.count} · {share}%
                </p>
              </div>
              <div className="h-2 rounded-full bg-[var(--bg-elevated-soft)]">
                <div
                  className="h-2 rounded-full bg-[var(--accent-primary)]"
                  style={{ width: `${share}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const CriticalCounterpartiesTable: React.FC<{
  items: Array<{
    name: string;
    country: string;
    reasons: string[];
  }>;
}> = ({ items }) => (
  <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-[var(--bg-elevated-soft)]">
          <tr>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Контрагент</th>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Страна</th>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
              Основания критичности
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.name} className="border-t border-[var(--border-subtle)] align-top">
              <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{item.name}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{item.country}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">
                <ul className="space-y-1">
                  {item.reasons.map((reason) => (
                    <li key={reason} className="flex gap-2">
                      <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-error)]" />
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

const DrilldownModal: React.FC<{
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ title, open, onClose, children }) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6">
      <div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Демонстрационный drilldown по выбранному показателю
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Закрыть
          </Button>
        </div>
        <div className="max-h-[calc(85vh-84px)] overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
};

const ExportMenuButton: React.FC<{
  label: string;
  open: boolean;
  onToggle: () => void;
  onSelect: (format: ExportFormat) => void;
}> = ({ label, open, onToggle, onSelect }) => (
  <div className="relative">
    <Button
      variant="secondary"
      size="sm"
      onClick={onToggle}
      rightIcon={
        <ChevronDown
          className={`h-4 w-4 transition-transform duration-200 ${
            open ? "rotate-180" : "rotate-0"
          }`}
          aria-hidden
        />
      }
      aria-expanded={open}
      aria-haspopup="menu"
    >
      {label}
    </Button>

    {open ? (
      <div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">
        <div className="border-b border-[var(--border-subtle)] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Формат сохранения
          </p>
        </div>
        <div className="p-2">
          {[
            { key: "excel", label: "Excel" },
            { key: "docx", label: "Docx" },
            { key: "pdf", label: "Pdf" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => onSelect(item.key as ExportFormat)}
              className="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:bg-[var(--bg-elevated-soft)]"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    ) : null}
  </div>
);

// ---------------------------------------------------------------------------
// Intro screen
// ---------------------------------------------------------------------------

const IntroScreen: React.FC<{
  onOpenDemo: () => void;
}> = ({ onOpenDemo }) => (
  <div className="flex flex-col lg:h-full lg:min-h-0 lg:overflow-hidden">
    <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto pr-1">
      <div className="space-y-4">
        <PageSection
          title="Демонстрационный сценарий работы раздела"
          subtitle="Как будет выглядеть анализ выявленных контрагентов"
          rightSlot={<Badge tone="success">Preview</Badge>}
        >
          <p className="max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">
            Этот раздел будет автоматически выявлять контрагентов в документах сделки,
            сопоставлять их с внешними и внутренними источниками данных и формировать
            рабочий интерфейс для юридического и due diligence анализа.
          </p>
        </PageSection>

        <PageSection
          title="Как это будет работать"
          subtitle="Основной сценарий обработки контрагентов"
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <FeatureCard
              icon={<Search className="h-5 w-5" aria-hidden />}
              title="Выявление в документах"
              description="Система находит контрагентов в тексте, таблицах, приложениях и иных материалах сделки."
            />
            <FeatureCard
              icon={<Link2 className="h-5 w-5" aria-hidden />}
              title="Сопоставление и enrichment"
              description="Найденные сущности связываются с глобальными, локальными и внутренними источниками данных."
            />
            <FeatureCard
              icon={<ShieldCheck className="h-5 w-5" aria-hidden />}
              title="Рабочий интерфейс анализа"
              description="Пользователь получает сводную картину, список контрагентов и detail panel по выбранной сущности."
            />
          </div>
        </PageSection>

        <PageSection
          title="Источники данных"
          subtitle="Глобальные, локальные и внутренние провайдеры"
        >
          <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-[var(--bg-elevated-soft)]">
                  <tr>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Регион</th>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      Глобальные
                    </th>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      Локальные
                    </th>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      Внутренние
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {COVERAGE_ROWS.map((row) => (
                    <tr
                      key={row.region}
                      className="border-t border-[var(--border-subtle)] align-top"
                    >
                      <td className="px-4 py-3 text-[var(--text-primary)]">{row.region}</td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {row.globalProviders}
                      </td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {row.localSources}
                      </td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {row.internalSources}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </PageSection>
      </div>
    </div>

    <div className="mt-4 shrink-0 border-t border-[var(--border-subtle)] pb-2 pt-4">
      <Button
        variant="primary"
        size="md"
        onClick={onOpenDemo}
        className="w-full sm:w-auto"
      >
        Перейти на демостраницу работы блока
      </Button>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Table header
// ---------------------------------------------------------------------------

const SortableHeader: React.FC<{
  label: string;
  sortKey: SortKey;
  currentSort: SortState;
  onSort: (key: SortKey) => void;
  className?: string;
}> = ({ label, sortKey, currentSort, onSort, className = "" }) => {
  const isActive = currentSort.key === sortKey;
  const isAscending = isActive && currentSort.direction === "asc";
  const isDescending = isActive && currentSort.direction === "desc";

  // Иконка отражает текущее состояние сортировки.
  // Screen reader получает state через aria-sort на <th>.
  const SortIcon = isAscending ? ChevronUp : isDescending ? ChevronDown : ChevronsUpDown;

  return (
    <th
      scope="col"
      className={["px-4 py-3 font-semibold text-[var(--text-primary)]", className].join(" ")}
      aria-sort={getAriaSort(currentSort, sortKey)}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-2 text-left transition hover:text-[var(--accent-primary)]"
        title={`Сортировать по колонке ${label}`}
      >
        <span>{label}</span>
        <SortIcon
          className={`h-3 w-3 ${
            isActive ? "text-[var(--accent-primary)]" : "text-[var(--text-muted)]"
          }`}
          aria-hidden
        />
      </button>
    </th>
  );
};

// ---------------------------------------------------------------------------
// Counterparties table
// ---------------------------------------------------------------------------

const CounterpartiesTable: React.FC<{
  items: CounterpartyAggregate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  sort: SortState;
  onSort: (key: SortKey) => void;
}> = ({ items, selectedId, onSelect, sort, onSort }) => (
  /*
    Dual-mode scroll contract:
    Mobile (<lg):  overflow-x-auto для горизонтального свайпа таблицы.
                   Вертикальный скролл страничный, sticky-header НЕ применяется
                   (wrapper не создаёт vertical scroll context → sticky
                   привязался бы к внешнему ancestor и визуально плавал бы
                   по viewport).
    Desktop (lg+): h-full + overflow-auto → internal scroll context.
                   Sticky-header корректно привязывается к wrapper.
  */
  <div className="overflow-x-auto rounded-2xl border border-[var(--border)] lg:h-full lg:min-h-0 lg:overflow-auto">
    <table className="min-w-full text-left text-sm">
      <thead className="bg-[var(--bg-elevated-soft)] lg:sticky lg:top-0 lg:z-10">
        <tr>
          <SortableHeader
            label="№"
            sortKey="index"
            currentSort={sort}
            onSort={onSort}
            className="w-14"
          />
          <SortableHeader
            label="Название"
            sortKey="name"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Страна"
            sortKey="country"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Кол-во контрактов"
            sortKey="contractCount"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Сумма контрактов"
            sortKey="contractValueUsdM"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Оценка риска"
            sortKey="risk"
            currentSort={sort}
            onSort={onSort}
          />
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => {
          const isSelected = item.id === selectedId;
          const risk = buildRiskMeta(item);

          return (
            <tr
              key={item.id}
              className={[
                "border-t border-[var(--border-subtle)] transition",
                isSelected
                  ? "bg-[color:color-mix(in_srgb,var(--accent-primary)_7%,var(--bg-card))]"
                  : "hover:bg-[var(--bg-elevated-soft)]",
              ].join(" ")}
            >
              <td className="px-4 py-3 tabular-nums text-[var(--text-muted)]">{index + 1}</td>
              <td className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => onSelect(item.id)}
                  className="text-left text-sm font-medium text-[var(--accent-primary)] underline decoration-transparent transition hover:decoration-current"
                >
                  {item.name}
                </button>
              </td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{item.country}</td>
              <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                {item.contractCount}
              </td>
              <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                ${item.contractValueUsdM}m
              </td>
              <td className="px-4 py-3">
                <Badge tone={risk.tone}>{risk.label}</Badge>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

const DetailPanel: React.FC<{
  aggregate: CounterpartyAggregate;
  detail: CounterpartyDetail;
}> = ({ aggregate, detail }) => (
  <div className="space-y-4">
    <PageSection
      title="Карточка контрагента"
      subtitle="Детальная информация"
      rightSlot={
        <Badge tone={reviewTone(aggregate.reviewStatus)}>
          {reviewLabel(aggregate.reviewStatus)}
        </Badge>
      }
    >
      <div className="space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-[var(--text-primary)]">
              {aggregate.name}
            </p>
            <Badge>{aggregate.country}</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.shortDescription}
          </p>
        </div>
      </div>
    </PageSection>

    <PageSection
      title="Упоминания в контрактах"
      subtitle="Список документов и контрактов, в которых найден контрагент"
    >
      <div className="space-y-3">
        {detail.contracts.map((contract) => (
          <div
            key={contract.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {contract.title}
              </p>
              <Badge>{contract.contractType}</Badge>
              <Badge>{contract.section}</Badge>
            </div>
            <div className="mt-2 flex flex-wrap gap-4 text-sm text-[var(--text-secondary)]">
              <span>
                <span className="font-medium text-[var(--text-primary)]">Role:</span>{" "}
                {contract.mentionRole}
              </span>
              <span>
                <span className="font-medium text-[var(--text-primary)]">Value:</span>{" "}
                {contract.contractValueUsdM != null ? `$${contract.contractValueUsdM}m` : "—"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </PageSection>

    <PageSection
      title="Финансовая выжимка"
      subtitle="Ключевые финансовые показатели по контрагенту"
    >
      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          label="Revenue"
          value={detail.financials.revenue}
          hint={`${detail.financials.fiscalYear} · ${detail.financials.currency}`}
        />
        <KpiCard label="EBITDA" value={detail.financials.ebitda} />
        <KpiCard label="Assets" value={detail.financials.totalAssets} />
        <KpiCard label="Employees" value={`${detail.financials.employees}`} />
      </div>
    </PageSection>

    <PageSection title="Риски" subtitle="Состояние банкротства, санкции и суды">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {(
          [
            { label: "Банкротство", key: "bankruptcy" },
            { label: "Санкции", key: "sanctions" },
            { label: "Суды", key: "litigation" },
          ] as const
        ).map(({ label, key }) => (
          <div key={key} className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {label}
            </p>
            <div className="mt-2">
              <Badge tone={riskBadgeTone(detail.risks[key])}>
                {riskBadgeLabel(detail.risks[key])}
              </Badge>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        <p className="text-sm font-semibold text-[var(--text-primary)]">Risk notes</p>
        <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
          {detail.risks.notes.map((note) => (
            <li key={note} className="flex gap-2">
              <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
      </div>
    </PageSection>

    <PageSection
      title="Собственник / UBO"
      subtitle="Ownership context и санкционная проверка UBO"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Owner
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {detail.ownership.ownerName}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.ownership.ownerType} · {detail.ownership.ownerJurisdiction}
            {detail.ownership.ownerShare ? ` · ${detail.ownership.ownerShare}` : ""}
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            UBO
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {detail.ownership.uboName}
          </p>
          <div className="mt-2">
            <Badge
              tone={
                detail.ownership.uboSanctionsStatus === "match"
                  ? "high"
                  : detail.ownership.uboSanctionsStatus === "review"
                    ? "medium"
                    : "low"
              }
            >
              {detail.ownership.uboSanctionsStatus === "match"
                ? "Sanctions match"
                : detail.ownership.uboSanctionsStatus === "review"
                  ? "Sanctions review"
                  : "No sanctions match"}
            </Badge>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        <p className="text-sm font-semibold text-[var(--text-primary)]">Ownership note</p>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          {detail.ownership.ownershipNote}
        </p>
      </div>
    </PageSection>
  </div>
);

// ---------------------------------------------------------------------------
// Mobile fullscreen drawer
// ---------------------------------------------------------------------------

/**
 * Fullscreen drawer для DetailPanel на mobile viewport.
 *
 * Паттерн повторяет DocumentsTab / RealEstateTab: fixed inset-0 z-50
 * + затемнение фона + body scroll lock + Escape close. Отображается
 * только на <lg (компонент помечен lg:hidden).
 *
 * Body scroll lock — критично для мобильного UX: без него страница
 * под drawer'ом продолжит скроллиться при инерционном touch scroll.
 */
const MobileDetailDrawer: React.FC<{
  aggregate: CounterpartyAggregate;
  detail: CounterpartyDetail;
  onClose: () => void;
}> = ({ aggregate, detail, onClose }) => {
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  React.useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  return (
    <div className="lg:hidden">
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      <aside
        className="fixed inset-0 z-50 flex flex-col bg-[var(--bg-card)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cp-mobile-drawer-title"
      >
        <div className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4">
          <Button
            variant="secondary"
            size="sm"
            onClick={onClose}
            leftIcon={<ChevronLeft className="h-4 w-4" aria-hidden />}
          >
            Назад к списку
          </Button>

          <div
            id="cp-mobile-drawer-title"
            className="truncate text-sm font-semibold text-[var(--text-primary)]"
          >
            {aggregate.name}
          </div>

          <div className="w-[80px] shrink-0" aria-hidden />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[var(--bg-base)] p-4">
          <DetailPanel aggregate={aggregate} detail={detail} />
        </div>
      </aside>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Demo screen
// ---------------------------------------------------------------------------

const DemoScreen: React.FC<{
  onBack: () => void;
}> = ({ onBack }) => {
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [drilldown, setDrilldown] = React.useState<DrilldownKind>(null);
  const [openExportMenu, setOpenExportMenu] = React.useState<ExportMenuKind>(null);
  const [sort, setSort] = React.useState<SortState>({
    key: "index",
    direction: "asc",
  });

  // Все derive-вычисления мемоизированы. DEMO_AGGREGATES статичен → пересчёт
  // не нужен; sorted пересчитывается только при изменении sort state.
  const { totalCounterparties, totalContracts, totalContractValue } = React.useMemo(
    () => buildCounterpartiesTotals(DEMO_AGGREGATES),
    []
  );

  const topByContracts = React.useMemo(() => buildTopByContracts(DEMO_AGGREGATES), []);
  const topByValue = React.useMemo(() => buildTopByValue(DEMO_AGGREGATES), []);
  const countryStructure = React.useMemo(() => buildCountryStructure(DEMO_AGGREGATES), []);
  const criticalCounterparties = React.useMemo(
    () => buildCriticalCounterparties(DEMO_AGGREGATES),
    []
  );

  const sortedAggregates = React.useMemo(
    () => sortCounterparties(DEMO_AGGREGATES, sort),
    [sort]
  );

  const selectedAggregate = selectedId
    ? DEMO_AGGREGATES.find((item) => item.id === selectedId) ?? null
    : null;

  const selectedDetail = selectedAggregate ? DEMO_DETAILS[selectedAggregate.id] ?? null : null;

  const handleExport = (format: ExportFormat) => {
    setOpenExportMenu(null);
    window.alert(`Сохранить список контрагентов: ${format.toUpperCase()}`);
  };

  const handleSort = (key: SortKey) => {
    setSort((prev) => getNextSortState(prev, key));
  };

  const drilldownTitle =
    drilldown === "geography"
      ? "География выявленных контрагентов"
      : drilldown === "contracts_top"
        ? "Топ-5 контрагентов по количеству контрактов"
        : drilldown === "value_top"
          ? "Топ-5 контрагентов по сумме контрактов"
          : "Критические контрагенты";

  return (
    <div className="flex min-h-0 flex-col lg:h-full lg:overflow-hidden">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            Выявленные контрагенты
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Агрегированное представление по результатам анализа контрактов и связанных источников
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={onBack}>
          Назад к описанию
        </Button>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard
          label="Выявлено контрагентов"
          value={`${totalCounterparties}`}
          hint="Нажмите, чтобы открыть географию"
          onClick={() => setDrilldown("geography")}
        />
        <KpiCard
          label="Контрактов с контрагентами"
          value={`${totalContracts}`}
          hint="Нажмите, чтобы открыть топ-5"
          onClick={() => setDrilldown("contracts_top")}
        />
        <KpiCard
          label="Сумма контрактов"
          value={`$${totalContractValue}m`}
          hint="Нажмите, чтобы открыть топ-5"
          onClick={() => setDrilldown("value_top")}
        />
        <KpiCard
          label="Критические контрагенты"
          value={`${criticalCounterparties.length}`}
          hint="Нажмите, чтобы открыть список"
          accent
          onClick={() => setDrilldown("critical")}
        />
      </div>

      <div className="min-h-0 flex-1">
        {/*
          ═══════════════════════════════════════════════════════════════
          Desktop render-path (lg+): split-view при выбранном контрагенте,
          обычная таблица без выбранного.

          Mobile render-path (< lg): всегда обычная таблица; DetailPanel
          рендерится отдельно как fullscreen drawer ниже.
          ═══════════════════════════════════════════════════════════════
        */}

        {/* Desktop: split-view при selectedAggregate */}
        {selectedAggregate && selectedDetail ? (
          <div className="hidden lg:block lg:h-full">
            <PageSection
              title="Рабочая область анализа"
              subtitle="Список контрагентов и карточка выбранной компании"
              rightSlot={
                <div className="flex items-center gap-2">
                  <ExportMenuButton
                    label="Сохранить список контрагентов"
                    open={openExportMenu === "list"}
                    onToggle={() =>
                      setOpenExportMenu((prev) => (prev === "list" ? null : "list"))
                    }
                    onSelect={handleExport}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelectedId(null)}
                  >
                    Закрыть карточку
                  </Button>
                </div>
              }
              className="h-full"
              contentClassName="p-0"
              bodyClassName="h-full min-h-0"
            >
              <div className="grid min-h-0 grid-cols-1 lg:h-full xl:grid-cols-[minmax(0,1.1fr)_minmax(420px,560px)]">
                <div className="min-h-0 lg:overflow-hidden border-b border-[var(--border-subtle)] xl:border-b-0 xl:border-r">
                  <div className="flex h-full min-h-0 flex-col p-5">
                    <div className="mb-4 shrink-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        Список контрагентов
                      </p>
                      <p className="mt-1 text-sm text-[var(--text-muted)]">
                        Выберите компанию в таблице, чтобы просмотреть детальную карточку справа
                      </p>
                    </div>

                    <div className="min-h-0 flex-1">
                      <CounterpartiesTable
                        items={sortedAggregates}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        sort={sort}
                        onSort={handleSort}
                      />
                    </div>
                  </div>
                </div>

                <div className="min-h-0 lg:overflow-y-auto">
                  <div className="p-5">
                    <DetailPanel
                      aggregate={selectedAggregate}
                      detail={selectedDetail}
                    />
                  </div>
                </div>
              </div>
            </PageSection>
          </div>
        ) : null}

        {/* Desktop: fallback — plain table без выбранного контрагента */}
        {(!selectedAggregate || !selectedDetail) && (
          <div className="hidden lg:block lg:h-full">
            <PageSection
              title="Список контрагентов"
              subtitle="Табличный перечень контрагентов, выявленных в документах сделки"
              rightSlot={
                <ExportMenuButton
                  label="Сохранить список контрагентов"
                  open={openExportMenu === "list"}
                  onToggle={() =>
                    setOpenExportMenu((prev) => (prev === "list" ? null : "list"))
                  }
                  onSelect={handleExport}
                />
              }
              className="h-full"
              bodyClassName="flex h-full min-h-0 flex-col"
            >
              <div className="mb-3 shrink-0">
                <p className="text-sm text-[var(--text-secondary)]">
                  В демонстрационном списке добавлено больше компаний, чтобы таблица имела
                  собственную внутреннюю прокрутку.
                </p>
              </div>
              <div className="min-h-0 flex-1 lg:overflow-hidden">
                <CounterpartiesTable
                  items={sortedAggregates}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  sort={sort}
                  onSort={handleSort}
                />
              </div>
            </PageSection>
          </div>
        )}

        {/* Mobile: всегда plain table (independent от selectedAggregate) */}
        <div className="lg:hidden">
          <PageSection
            title="Список контрагентов"
            subtitle="Табличный перечень контрагентов, выявленных в документах сделки"
            rightSlot={
              <ExportMenuButton
                label="Сохранить список контрагентов"
                open={openExportMenu === "list"}
                onToggle={() =>
                  setOpenExportMenu((prev) => (prev === "list" ? null : "list"))
                }
                onSelect={handleExport}
              />
            }
          >
            <div className="mb-3">
              <p className="text-sm text-[var(--text-secondary)]">
                В демонстрационном списке добавлено больше компаний. Нажмите на имя контрагента,
                чтобы открыть детальную карточку.
              </p>
            </div>
            <CounterpartiesTable
              items={sortedAggregates}
              selectedId={selectedId}
              onSelect={setSelectedId}
              sort={sort}
              onSort={handleSort}
            />
          </PageSection>
        </div>
      </div>

      {/*
        Mobile fullscreen drawer с DetailPanel. Активируется только на <lg
        при selectedAggregate. На lg+ этот блок не рендерится (lg:hidden
        в MobileDetailDrawer), т.к. там используется split-view выше.
      */}
      {selectedAggregate && selectedDetail ? (
        <MobileDetailDrawer
          aggregate={selectedAggregate}
          detail={selectedDetail}
          onClose={() => setSelectedId(null)}
        />
      ) : null}

      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={drilldownTitle}
      >
        {drilldown === "geography" ? (
          <CountryStructureCard items={countryStructure} />
        ) : drilldown === "contracts_top" ? (
          <RankedListCard title="Топ-5 по количеству контрактов" items={topByContracts} />
        ) : drilldown === "value_top" ? (
          <RankedListCard title="Топ-5 по сумме контрактов" items={topByValue} />
        ) : (
          <CriticalCounterpartiesTable items={criticalCounterparties} />
        )}
      </DrilldownModal>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

const CounterpartiesTab: React.FC<CounterpartiesTabProps> = ({
  dealId: _dealId,
  currentRunId: _currentRunId,
}) => {
  const [mode, setMode] = React.useState<PreviewMode>("intro");

  return (
    <div className="flex flex-col lg:h-full lg:min-h-0 lg:overflow-hidden">
      {mode === "intro" ? (
        <IntroScreen onOpenDemo={() => setMode("demo")} />
      ) : (
        <DemoScreen onBack={() => setMode("intro")} />
      )}
    </div>
  );
};

export default CounterpartiesTab;


