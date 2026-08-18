// =============================================================
// src/pages/tabs/OverviewTab.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../types";
import { useUpdateDeal } from "../../api/deals";
import Button from "../../components/ui/Button";
import { ProjectDomainsOverviewPanel } from "./overview/ProjectDomainsOverviewPanel";
import { ProjectDomainDetailsPanel } from "./overview/ProjectDomainDetailsPanel";
import { useIsMobile } from "../../hooks/useIsMobile";

export type ChecksMode =
  | "global_only"
  | "doc_type_only"
  | "global_and_doc_type";

interface OverviewTabProps {
  deal: Deal;
  currentRunId?: string | null;
}

// ---------------------------------------------------------------------------
// DealInfoCard (collapsible)
// ---------------------------------------------------------------------------

const DealInfoCard: React.FC<{
  deal: Deal;
  projectSummary: string;
  isSaving: boolean;
  isDirty: boolean;
  onChangeSummary: (value: string) => void;
  onSaveSummary: () => void;
}> = ({ deal, projectSummary, isSaving, isDirty, onChangeSummary, onSaveSummary }) => {
  const [isOpen, setIsOpen] = React.useState(false);

  const hasContent = (projectSummary ?? "").trim().length > 0;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex w-full items-center justify-between gap-4 px-5 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
      >
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            О проекте
          </h2>
          {!isOpen && hasContent && (
            <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
              {projectSummary.trim().slice(0, 120)}
              {projectSummary.trim().length > 120 ? "…" : ""}
            </p>
          )}
          {!isOpen && !hasContent && (
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
              Нажмите, чтобы добавить описание
            </p>
          )}
        </div>
        <span
          className={[
            "shrink-0 text-[var(--text-muted)] transition-transform duration-200",
            isOpen ? "rotate-180" : "",
          ].join(" ")}
        >
          ▾
        </span>
      </button>

      {isOpen && (
        <>
          <div className="mx-5 border-t border-[var(--border-subtle)]" />
          <div className="px-5 py-4">
            <textarea
              id={`deal-summary-${deal.id}`}
              value={projectSummary}
              onChange={(e) => onChangeSummary(e.target.value)}
              rows={5}
              placeholder="Например: продажа группы компаний, buy-side DD, корпоративный блок, ключевые договоры и IP..."
              className="w-full resize-none overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-4 py-3 text-sm leading-6 text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]"
              style={{ minHeight: "7rem", maxHeight: "14rem" }}
            />
            <div className="mt-2 flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={onSaveSummary}
                isLoading={isSaving}
                disabled={isSaving || !isDirty}
              >
                Сохранить
              </Button>
            </div>
          </div>
        </>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// OverviewTab
// ---------------------------------------------------------------------------

const OverviewTab: React.FC<OverviewTabProps> = ({ deal, currentRunId }) => {
  const isMobile = useIsMobile();

  const updateDeal = useUpdateDeal(deal.id);

  const [activeDomain, setActiveDomain] = React.useState<
    "documents" | "counterparties" | "real_estate"
  >("documents");

  const [projectSummary, setProjectSummary] = React.useState(
    deal.summary ?? "",
  );

  React.useEffect(() => {
    setProjectSummary(deal.summary ?? "");
  }, [deal.id, deal.summary]);

  const normalizedOriginalSummary = (deal.summary ?? "").trim();
  const normalizedDraftSummary = projectSummary.trim();
  const isSummaryDirty = normalizedDraftSummary !== normalizedOriginalSummary;

  const handleSaveSummary = React.useCallback(() => {
    if (!isSummaryDirty) return;
    updateDeal.mutate({
      summary:
        normalizedDraftSummary.length > 0 ? normalizedDraftSummary : null,
    });
  }, [isSummaryDirty, normalizedDraftSummary, updateDeal]);

  return (
    <div
      className={`relative ${
        isMobile
          ? "flex min-h-0 flex-col gap-4"
          : "flex h-full min-h-0 flex-col gap-4"
      }`}
    >
      <div className="flex min-w-0 min-h-0 shrink-0 flex-col gap-4">
        {/* Баннер про ручную переклассификацию */}
        {deal.has_pending_manual_reclassifications && currentRunId && (
          <div className="shrink-0 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3">
            <p className="text-xs font-semibold text-[var(--color-warning-text)]">
              Обновите результаты
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--color-warning-text)]">
              Вы изменили типы документов вручную. Рекомендуем перезапустить
              анализ, чтобы обновить результаты проекта.
            </p>
          </div>
        )}

        <div className="shrink-0">
          <DealInfoCard
            deal={deal}
            projectSummary={projectSummary}
            isSaving={updateDeal.isPending}
            isDirty={isSummaryDirty}
            onChangeSummary={setProjectSummary}
            onSaveSummary={handleSaveSummary}
          />
        </div>

        {/* Связка "Состояние направлений" + "Детали результатов анализа"
            — визуально единый блок. Убран gap между ними, чтобы активная
            карточка сверху "врастала" в панель деталей снизу на xl+.
            Общий gap с DealInfoCard остаётся 16px. */}
        <div
          className={`flex flex-col ${
            isMobile ? "" : "min-h-0 flex-1"
          }`}
        >
          <div className="shrink-0">
            <ProjectDomainsOverviewPanel
              runId={currentRunId ?? null}
              deal={deal}
              activeDomain={activeDomain}
              onDomainSelect={setActiveDomain}
            />
          </div>

          <div
            className={`${
              isMobile ? "" : "min-h-0 flex-1"
            }`}
          >
            <ProjectDomainDetailsPanel
              activeDomain={activeDomain}
              onDomainChange={setActiveDomain}
              runId={currentRunId ?? null}
              deal={deal}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default OverviewTab;

