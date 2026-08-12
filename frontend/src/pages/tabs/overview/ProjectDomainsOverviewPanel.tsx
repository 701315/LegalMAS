// =============================================================
// src/pages/tabs/overview/ProjectDomainsOverviewPanel.tsx
// Три равные карточки: Документы · Контрагенты · Имущество
//
// Активная карточка визуально "врастает" в панель "Детали
// результатов анализа" снизу:
//   - Плоский нижний бордер (bottom-border убран)
//   - rounded-b убран (углы снизу — прямые)
//   - bg === bg панели ниже (var(--bg-card))
//   - Left accent border вместо full-border accent
//
// На mobile connected эффект не применяется — карточки стакаются,
// активная может быть не последней в ряду, и "connect" ломается.
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import { useRunProgress } from "../../../api/runs";
import { DEMO_AGGREGATES } from "../counterparties/constants";
import { DEMO_OBJECTS } from "../real-estate/constants";

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
// DomainCard (компактный + connected для активной на xl+)
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
      "relative flex min-h-[4.5rem] w-full flex-col px-3 py-2 text-left shadow-sm transition",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
      // Базовые скругления — на mobile всегда полные
      "rounded-2xl",
      // На xl+ у активной карточки убираем нижние скругления —
      // она визуально сливается с панелью деталей ниже.
      isActive ? "xl:rounded-b-none" : "",
      isActive
        ? [
            // Активная карточка на всех размерах:
            // - border вокруг (base border, не accent)
            // - но на xl+ убираем bottom-border (сливается с панелью)
            "border border-[var(--border)]",
            "xl:border-b-0",
            // Bg === bg панели ниже — ключевой connect-эффект
            "bg-[var(--bg-card)]",
            "shadow-md",
          ].join(" ")
        : [
            // Неактивная — стандартная карточка
            "border border-[var(--border)]",
            "bg-[var(--bg-card)]",
            "hover:bg-[var(--bg-elevated-soft)]",
          ].join(" "),
    ].join(" ")}
  >
    {/* Left accent border для активной карточки — визуальный маркер выбора */}
    {isActive && (
      <div
        className="pointer-events-none absolute inset-y-0 left-0 w-[3px] rounded-l-2xl bg-[var(--accent-primary)] xl:rounded-bl-none"
        aria-hidden
      />
    )}

    <div className="mb-0.5 flex items-center gap-1.5">
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

    {lines.length > 0 && (
      <div className="mt-0.5 space-y-0">
        {lines.slice(0, 2).map((line, i) => (
          <p
            key={i}
            className="truncate text-[10px] leading-4 text-[var(--text-muted)]"
          >
            {line}
          </p>
        ))}
      </div>
    )}
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
  if (progress?.last_activity_at && docRunning && docLines.length < 2) {
    docLines.push(`обновлено ${formatRelativeTime(progress.last_activity_at)}`);
  }
  if (progress?.documents_total && docLines.length === 0) {
    docLines.push(`Документов: ${progress.documents_total}`);
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
    <section
      className={[
        // Убираем нижние скругления секции на xl+ — секция плавно
        // переходит в панель деталей ниже.
        "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",
        "xl:rounded-b-none xl:border-b-0 xl:shadow-none",
      ].join(" ")}
    >
      <div className="px-5 py-2">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          Состояние направлений проекта
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-2 px-5 pb-3 sm:grid-cols-3">
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


