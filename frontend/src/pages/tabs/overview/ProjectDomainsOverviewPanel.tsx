// =============================================================
// src/pages/tabs/overview/ProjectDomainsOverviewPanel.tsx
// Три равные карточки: Документы · Контрагенты · Имущество
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import { useRunProgress } from "../../../api/runs";
import { DEMO_AGGREGATES } from "../CounterpartiesTab";
import { DEMO_OBJECTS } from "../RealEstateTab";

type DomainKey = "documents" | "counterparties" | "real_estate";

interface ProjectDomainsOverviewPanelProps {
  runId: string | null;
  deal: Deal;
  activeDomain: DomainKey;
  onDomainSelect: (d: DomainKey) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeTime(iso: string | undefined | null): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return "только что";
  if (diff < 60) return `${diff} сек назад`;
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  return `${Math.floor(diff / 3600)} ч назад`;
}

// ---------------------------------------------------------------------------
// DomainCard
// ---------------------------------------------------------------------------

const DomainCard: React.FC<{
  isActive: boolean;
  onClick: () => void;
  title: string;
  statusLine: React.ReactNode;
  lines: React.ReactNode[];
  isRunning?: boolean;
}> = ({ isActive, onClick, title, statusLine, lines, isRunning = false }) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      "flex min-h-[7rem] w-full flex-col rounded-2xl border px-4 py-3 text-left shadow-sm transition",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
      isActive
        ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] shadow-md"
        : "border-[var(--border)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]",
    ].join(" ")}
  >
    <div className="mb-1 flex items-center gap-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {title}
      </p>
      {isRunning && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent-primary)]" />
      )}
    </div>

    <p
      className={`text-xs font-semibold ${
        isActive
          ? "text-[var(--accent-primary)]"
          : "text-[var(--text-primary)]"
      }`}
    >
      {statusLine}
    </p>

    <div className="mt-1.5 space-y-0.5">
      {lines.map((line, i) => (
        <p key={i} className="text-[11px] leading-4 text-[var(--text-muted)]">
          {line}
        </p>
      ))}
    </div>
  </button>
);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export const ProjectDomainsOverviewPanel: React.FC<
  ProjectDomainsOverviewPanelProps
> = ({ runId, activeDomain, onDomainSelect }) => {
  const { data: progress } = useRunProgress(runId);

  // ── Документы ──
  const docStatus = (() => {
    if (!runId) return "Не запущен";
    if (!progress) return "Загрузка...";
    if (progress.run_status === "completed") return "Завершён";
    if (progress.run_status === "completed_with_errors")
      return "Завершён с ошибками";
    if (progress.run_status === "failed") return "Ошибка";
    if (progress.run_status === "running") return "Выполняется";
    return "Ожидание";
  })();

  const docRunning = progress?.run_status === "running";
  const currentStep = progress?.current_step_title;

  const activeStep = progress?.steps.find((s) => s.status === "running");
  const subProgress = activeStep?.sub_progress;

  const docLines: React.ReactNode[] = [];
  if (currentStep) {
    docLines.push(`Этап: ${currentStep}`);
  }
  if (subProgress && subProgress.total > 0) {
    docLines.push(
      `${subProgress.current} из ${subProgress.total} ${
        subProgress.kind === "legal_units"
          ? "блоков"
          : subProgress.kind === "segments"
            ? "сегментов"
            : subProgress.kind === "checks"
              ? "проверок"
              : "документов"
      }`
    );
  }
  if (progress?.last_activity_at && docRunning) {
    docLines.push(`обновлено ${formatRelativeTime(progress.last_activity_at)}`);
  }
  if (progress?.documents_total && docLines.length === 0) {
    docLines.push(
      `Документов: ${progress.documents_total}`
    );
  }

  // ── Контрагенты ──
  const totalCounterparties = DEMO_AGGREGATES.length;
  const needsAttention = DEMO_AGGREGATES.filter(
    (item) =>
      item.reviewStatus === "critical" || item.reviewStatus === "needs_review"
  ).length;
  const sanctionsBankruptcy = DEMO_AGGREGATES.filter(
    (item) => item.sanctionsFlag || item.bankruptcyFlag
  ).length;

  // ── Имущество ──
  const totalObjects = DEMO_OBJECTS.length;
  const encumbered = DEMO_OBJECTS.filter(
    (item) => item.encumbrance === true
  ).length;
  const ownershipReview = DEMO_OBJECTS.filter(
    (item) =>
      item.ownership_status === "review" ||
      item.ownership_status === "not_confirmed"
  ).length;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="px-5">
        <div className="py-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Состояние направлений проекта
          </h2>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            Выберите направление для просмотра деталей
          </p>
        </div>
        <div className="border-t border-[var(--border-subtle)]" />
      </div>

      <div className="grid grid-cols-1 gap-3 px-5 py-4 sm:grid-cols-3">
        {/* Документы */}
        <DomainCard
          isActive={activeDomain === "documents"}
          onClick={() => onDomainSelect("documents")}
          title="Документы"
          statusLine={docStatus}
          lines={docLines}
          isRunning={docRunning}
        />

        {/* Контрагенты */}
        <DomainCard
          isActive={activeDomain === "counterparties"}
          onClick={() => onDomainSelect("counterparties")}
          title="Контрагенты"
          statusLine={`${totalCounterparties} выявлено`}
          lines={[
            `${needsAttention} требуют внимания`,
            `${sanctionsBankruptcy} санкции / банкротство`,
          ]}
        />

        {/* Имущество */}
        <DomainCard
          isActive={activeDomain === "real_estate"}
          onClick={() => onDomainSelect("real_estate")}
          title="Имущество"
          statusLine={`${totalObjects} объектов`}
          lines={[
            `${encumbered} с обременением`,
            `${ownershipReview} ownership review`,
          ]}
        />
      </div>
    </section>
  );
};

export default ProjectDomainsOverviewPanel;



