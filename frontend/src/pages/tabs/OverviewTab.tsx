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

  // ────────────────────────────────────────────────────────────────────
  // Overlay width calculation
  //
  // LaunchWideOverlay позиционируется absolute относительно rail wrapper
  // и торчит влево на ширину main column через right: calc(100% + 16px).
  // Ширина overlay = ширина main column, которая вычисляется динамически.
  //
  // Retry mechanism через requestAnimationFrame обрабатывает case когда
  // wrapper hidden при initial mount (railRect.width === 0). ResizeObserver
  // покрывает последующие resize events (window resize, viewport transitions).
  //
  // Известное архитектурное ограничение: retry loop через rAF — workaround
  // для CSS spec quirks с overflow-x visible + overflow-y hidden.
  // Правильное решение через CSS Grid same-cell placement или React Portal —
  // запланировано для future refactoring, но требует изменений в
  // LaunchWideOverlay и proof-of-concept тестирования.
  // ────────────────────────────────────────────────────────────────────
  const overviewRef = React.useRef<HTMLDivElement | null>(null);
  const railRef = React.useRef<HTMLDivElement | null>(null);
  const mobileLaunchRef = React.useRef<HTMLDivElement | null>(null);
  const [overlayWidth, setOverlayWidth] = React.useState<number | null>(null);

  React.useLayoutEffect(() => {
    const overviewEl = overviewRef.current;
    const railEl = railRef.current;
    if (!overviewEl || !railEl) return;

    let rafId: number | null = null;
    let cancelled = false;

    const update = () => {
      if (cancelled) return;

      const overviewRect = overviewEl.getBoundingClientRect();
      const railRect = railEl.getBoundingClientRect();

      // Rail hidden (display: none на <xl viewport) → width = 0.
      // Ставим overlayWidth = null (overlay не рендерится) и retry
      // на следующем rAF — CSS уже должен примениться к этому моменту.
      if (railRect.width === 0) {
        setOverlayWidth(null);
        rafId = window.requestAnimationFrame(update);
        return;
      }

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
      cancelled = true;
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
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

  // Mobile/tablet (<xl): после открытия панели перезапуска скроллим к ней,
  // чтобы пользователь сразу видел форму (in-flow под Actions-блоком).
  // На xl+ ветка не рендерится → mobileLaunchRef === null → no-op.
  React.useEffect(() => {
    if (!isLaunchPanelOpen) return;
    const rafId = window.requestAnimationFrame(() => {
      mobileLaunchRef.current?.scrollIntoView({
        block: "start",
        behavior: "smooth",
      });
    });
    return () => window.cancelAnimationFrame(rafId);
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
      className={`relative ${
        isMobile
          ? "flex min-h-0 flex-col gap-4"
          : "grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(0,2.2fr)_minmax(320px,360px)] xl:grid-rows-[minmax(0,1fr)]"
      }`}
    >
      {/* Main content column — grid col 1 на xl+, full width на <xl.
          shrink-0: в mobile flex-контексте запрещает схлопывание колонки
          (min-h-0 отключает automatic minimum size, и дефолтный flex-shrink: 1
          сжимал колонку до остатка высоты контейнера → контент overflow-ился
          под следующий блок). В desktop grid-контексте flex-shrink игнорируется,
          min-h-0 продолжает работать для internal scroll. */}
      <div className="flex min-w-0 min-h-0 shrink-0 flex-col gap-4">
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
              deal={effectiveDeal}
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
              deal={effectiveDeal}
            />
          </div>
        </div>
      </div>

      {/* Rail wrapper (grid col 2) — desktop only (xl+).
          
          АРХИТЕКТУРНОЕ РЕШЕНИЕ: разделение rail и overlay containing block.
          
          Wrapper выполняет две роли:
          1. Grid item в overviewRef grid (получает 360px ширины и h-full)
          2. Positioning context (relative) для LaunchWideOverlay,
             который позиционируется через right: calc(100% + 16px)
          
          Почему НЕ делать это через сам aside:
          - aside должен иметь overflow-hidden для vertical clipping
            (action panel не должен вылезать за границы grid row)
          - Но CSS spec запрещает overflow-x: visible + overflow-y: hidden
            (visible принудительно computed как auto, что не работает
            для overlay элементов торчащих наружу)
          
          Решение: wrapper без overflow — containing block для overlay;
          aside внутри с overflow-hidden — clip только своё содержимое.
          
          Ref для useLayoutEffect (вычисление overlayWidth) на wrapper,
          потому что overlayWidth считается от позиции wrapper в grid. */}
      <div
        ref={railRef}
        className="relative hidden min-h-0 xl:block xl:h-full"
      >
        <aside
          className="flex h-full min-h-0 w-full flex-col gap-4 overflow-hidden px-1"
          aria-label="Действия проекта"
        >
          <div className="shrink-0">
            <AnalysisActionsPanel
              deal={effectiveDeal}
              hasCurrentRun={!!currentRun}
              canStartRun={canLaunchRun}
              onOpenRunPanel={handleOpenLaunchPanel}
              showReclassBanner={showReclassBanner}
            />
          </div>

          {/* ── Декоративная картинка ─────────────────────────────
              flex-1 min-h-0: занимает всё пространство между низом
              карточки «Действия» и низом rail (за вычетом pb-4 = 16px).
              gap-4 на aside даёт стандартные 16px от низа карточки.
              object-contain: картинка ВСЕГДА цельная — вписывается
              в бокс пропорционально на любом разрешении экрана. */}
          <div
            aria-hidden="true"
            className="pointer-events-none min-h-0 flex-1 select-none"
          >
            <img
              src="/overviewpicture.png"
              alt=""
              className="h-full w-full rounded-2xl border border-[var(--border)] object-cover shadow-sm"
            />
          </div>
        </aside>

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

      {/* Mobile/tablet fallback — Action panel как обычный блок ниже
          основного контента на viewport < xl (rail hidden).
          shrink-0: блок всегда в конце, контентной высоты.
          LaunchWideOverlay variant="inline": mobile render-path панели
          перезапуска — in-flow под кнопкой, без absolute positioning. */}
      <div className="flex shrink-0 flex-col gap-4 xl:hidden">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          hasCurrentRun={!!currentRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={handleOpenLaunchPanel}
          showReclassBanner={showReclassBanner}
        />
        {isLaunchPanelOpen && (
          <div ref={mobileLaunchRef}>
            <LaunchWideOverlay
              variant="inline"
              open={isLaunchPanelOpen}
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
          </div>
        )}
      </div>
    </div>
  );
};

export default OverviewTab;

