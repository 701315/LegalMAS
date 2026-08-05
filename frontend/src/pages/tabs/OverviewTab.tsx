// =============================================================
// src/pages/tabs/OverviewTab.tsx
// =============================================================

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Deal } from "../../types";
import {
  runKeys,
  useRun,
  useStartRun,
} from "../../api/runs";
import { useSetPrimaryLanguage, useUpdateDeal } from "../../api/deals";
import { useDocuments } from "../../api/documents";
import { useDealPermissions } from "../../hooks/usePermissions";
import Button from "../../components/ui/Button";
import AnalysisActionsPanel from "./overview/AnalysisActionsPanel";
import LaunchWideOverlay from "./overview/LaunchWideOverlay";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../utils/languageDiscovery";
import { ProjectDomainsOverviewPanel } from "./overview/ProjectDomainsOverviewPanel";
import { ProjectDomainDetailsPanel } from "./overview/ProjectDomainDetailsPanel";

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
  const qc = useQueryClient();

  const { data: currentRun } = useRun(currentRunId ?? null, false);
  const { data: documentsPage } = useDocuments(deal.id, 1);
  const documentsCount = documentsPage?.total ?? 0;
  const { canStartRun, canUploadDocuments } = useDealPermissions(deal.id);

  const startRun = useStartRun(deal.id);
  const updateDeal = useUpdateDeal(deal.id);
  const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);

  const [isLaunchPanelOpen, setIsLaunchPanelOpen] = React.useState(false);
  const [checksMode, setChecksMode] =
    React.useState<ChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [hasRestartedAfterReclass, setHasRestartedAfterReclass] =
    React.useState(false);

  const [activeDomain, setActiveDomain] = React.useState<
    "documents" | "counterparties" | "real_estate"
  >("documents");

  const [projectSummary, setProjectSummary] = React.useState(
    deal.summary ?? "",
  );
  const [dealPatch, setDealPatch] = React.useState<Partial<Deal>>({});

  const overviewRef = React.useRef<HTMLDivElement | null>(null);
  const railRef = React.useRef<HTMLDivElement | null>(null);
  const [overlayWidth, setOverlayWidth] = React.useState<number | null>(null);

  React.useLayoutEffect(() => {
    const overviewEl = overviewRef.current;
    const railEl = railRef.current;
    if (!overviewEl || !railEl) return;

    const update = () => {
      const overviewRect = overviewEl.getBoundingClientRect();
      const railRect = railEl.getBoundingClientRect();
      const styles = window.getComputedStyle(overviewEl);
      const gap = parseFloat(styles.columnGap || styles.gap || "0") || 0;
      const width = Math.max(0, overviewRect.width - railRect.width - gap);
      setOverlayWidth(width > 0 ? width : null);
    };

    update();

    const ro = new ResizeObserver(() => update());
    ro.observe(overviewEl);
    ro.observe(railEl);
    window.addEventListener("resize", update);

    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  const dealLanguagesKey = JSON.stringify(deal.languages ?? []);

  React.useEffect(() => {
    setProjectSummary(deal.summary ?? "");
    setDealPatch({});
  }, [
    deal.id,
    deal.summary,
    deal.playbook_version_id,
    deal.primary_language,
    deal.language_discovery_status,
    dealLanguagesKey,
  ]);

  React.useEffect(() => {
    if (!isLaunchPanelOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsLaunchPanelOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isLaunchPanelOpen]);

  const effectiveDeal: Deal = { ...deal, ...dealPatch };

  const normalizedOriginalSummary = (deal.summary ?? "").trim();
  const normalizedDraftSummary = projectSummary.trim();
  const isSummaryDirty = normalizedDraftSummary !== normalizedOriginalSummary;

  const showReclassBanner =
    effectiveDeal.has_pending_manual_reclassifications &&
    (!!currentRun || !hasRestartedAfterReclass);

  const hasDocuments = documentsCount > 0;

  const discoveryStatus = normalizeDiscoveryStatus(
    effectiveDeal.language_discovery_status,
  );

  const isLanguageDiscoveryBlocking =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const canLaunchRun =
    canStartRun &&
    hasDocuments &&
    !!effectiveDeal.playbook_version_id &&
    !!effectiveDeal.primary_language &&
    !isLanguageDiscoveryBlocking &&
    !startRun.isPending &&
    !updateDeal.isPending &&
    !setPrimaryLanguage.isPending;

  const isSubmitting =
    startRun.isPending || updateDeal.isPending || setPrimaryLanguage.isPending;

  const handleOpenLaunchPanel = React.useCallback(() => {
    setIsLaunchPanelOpen(true);
  }, []);

  const handleCloseLaunchPanel = React.useCallback(() => {
    setIsLaunchPanelOpen(false);
  }, []);

  const handlePrimaryLanguageChange = React.useCallback(
    (value: string) => {
      const normalizedValue = normalizeLang(value) || null;
      setDealPatch((prev) => ({ ...prev, primary_language: normalizedValue }));
      setPrimaryLanguage.mutate(
        { primary_language: normalizedValue },
        {
          onError: () => {
            setDealPatch((prev) => ({
              ...prev,
              primary_language: deal.primary_language ?? null,
            }));
          },
        },
      );
    },
    [deal.primary_language, setPrimaryLanguage],
  );

  const handleSaveSummary = React.useCallback(() => {
    if (!isSummaryDirty) return;
    updateDeal.mutate({
      summary:
        normalizedDraftSummary.length > 0 ? normalizedDraftSummary : null,
    });
  }, [isSummaryDirty, normalizedDraftSummary, updateDeal]);

  const handleStartRun = React.useCallback(() => {
    if (!canLaunchRun) return;
    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: async (run) => {
          setHasRestartedAfterReclass(true);
          setForceReclassify(false);
          setIsLaunchPanelOpen(false);
          await Promise.all([
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, true) }),
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, false) }),
            qc.invalidateQueries({
              queryKey: runKeys.classificationReport(run.id),
            }),
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, false) }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, true) }),
          ]);
        },
      },
    );
  }, [canLaunchRun, checksMode, deal.id, forceReclassify, qc, startRun]);

  const handleDealPatched = React.useCallback(
    async (patch?: Partial<Deal>) => {
      if (patch && Object.keys(patch).length > 0) {
        setDealPatch((prev) => ({ ...prev, ...patch }));
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
      ]);
    },
    [deal.id, qc],
  );

  return (
    <div
      ref={overviewRef}
      className="relative grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(0,2.2fr)_360px]"
    >
      <div className="flex min-w-0 min-h-0 flex-col gap-4">
        <div className="shrink-0">
          <DealInfoCard
            deal={effectiveDeal}
            projectSummary={projectSummary}
            isSaving={updateDeal.isPending}
            isDirty={isSummaryDirty}
            onChangeSummary={setProjectSummary}
            onSaveSummary={handleSaveSummary}
          />
        </div>

        <div className="shrink-0">
          <ProjectDomainsOverviewPanel
            runId={currentRunId ?? null}
            deal={effectiveDeal}
            activeDomain={activeDomain}
            onDomainSelect={setActiveDomain}
          />
        </div>

        <div className="min-h-0 flex-1">
          <ProjectDomainDetailsPanel
            activeDomain={activeDomain}
            onDomainChange={setActiveDomain}
            runId={currentRunId ?? null}
            deal={effectiveDeal}
          />
        </div>
      </div>

      <div ref={railRef} className="relative hidden xl:block px-1 pb-2">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          hasCurrentRun={!!currentRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={handleOpenLaunchPanel}
          showReclassBanner={showReclassBanner}
        />

        {/* Декоративная иллюстрация под панелью действий (только на xl+) */}
        <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
          <img
            src="/overviewpicture.png"
            alt=""
            aria-hidden="true"
            loading="lazy"
            decoding="async"
            className="pointer-events-none block w-full h-auto select-none opacity-90"
          />
        </div>

        {overlayWidth !== null && (
          <LaunchWideOverlay
            open={isLaunchPanelOpen}
            overlayWidth={overlayWidth}
            deal={effectiveDeal}
            hasCurrentRun={!!currentRun}
            documentsCount={documentsCount}
            checksMode={checksMode}
            onChecksModeChange={setChecksMode}
            forceReclassify={forceReclassify}
            onForceReclassifyChange={setForceReclassify}
            canStartRun={canLaunchRun}
            canUploadDocuments={canUploadDocuments}
            isSubmitting={isSubmitting}
            onPrimaryLanguageChange={handlePrimaryLanguageChange}
            onSubmit={handleStartRun}
            onClose={handleCloseLaunchPanel}
            onDealPatched={handleDealPatched}
          />
        )}
      </div>

      <div className="xl:hidden">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          hasCurrentRun={!!currentRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={handleOpenLaunchPanel}
          showReclassBanner={showReclassBanner}
        />
      </div>
    </div>
  );
};

export default OverviewTab;


