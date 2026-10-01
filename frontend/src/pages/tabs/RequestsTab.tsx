// =============================================================
// src/pages/tabs/RequestsTab.tsx
// =============================================================

import React, { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, AlertTriangle } from "lucide-react";
import type { OpenViewerAtFn } from "../../types";
import {
  dealReviewApi,
  useDealReviewDdRequests,
} from "../../api/dealReview";
import type { DDRequestDTO } from "../../types/dealReview";
import { ReviewRequestsTable } from "../../components/requests/ReviewRequestsTable";
import { ReviewRequestSidePanel } from "../../components/requests/ReviewRequestSidePanel";
import Button from "../../components/ui/Button";
import { toRequestTableRowFromReview } from "../../viewAdapters/requestPresentation";
import { ResultsLocaleSelector } from "../../components/shared/ResultsLocaleSelector";
import ExportMenu from "../../components/shared/ExportMenu";
import { ResultPresentationStatus } from "./dd-grid-v1/ResultPresentationStatus";
import { useDDGridV1UIStore } from "./dd-grid-v1/ddGridV1.collapseStore";

interface Props {
  dealId: string;
  runId: string | null;
  onOpenViewerAt?: OpenViewerAtFn;
}

type InlineMessageTone = "error" | "warning" | "info";

interface InlineMessageState {
  tone: InlineMessageTone;
  title: string;
  description: string;
}

const MIN_PANEL_HEIGHT = 320;
const VIEWPORT_GUTTER = 12;
const PANEL_GUTTER = 16;
const PANEL_CENTER_THRESHOLD = 80;

// -------------------------------------------------------------
// InlineBanner
// -------------------------------------------------------------

const InlineBanner: React.FC<{
  tone: InlineMessageTone;
  title: string;
  description: string;
  onDismiss?: () => void;
}> = ({ tone, title, description, onDismiss }) => {
  const { t } = useTranslation("requests");
  const toneClassName =
    tone === "error"
      ? "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]"
      : tone === "warning"
        ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]"
        : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";

  return (
    <div
      className={`rounded-2xl border px-4 py-3 ${toneClassName}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="text-sm font-semibold">{title}</p>
          </div>
          <p className="mt-1 text-sm leading-6">{description}</p>
        </div>
        {onDismiss && (
          <Button variant="ghost" size="sm" onClick={onDismiss}>
            {t("actions.close", { ns: "common", defaultValue: "Close" })}
          </Button>
        )}
      </div>
    </div>
  );
};

// -------------------------------------------------------------
// LoadingState
// -------------------------------------------------------------

const LoadingState: React.FC = () => {
  const { t } = useTranslation("requests");

  return (
    <section
      className="flex h-full flex-col items-center justify-center px-6 py-10 text-center"
      aria-labelledby="requests-loading-title"
    >
      <div
        className="inline-flex items-center gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-4 text-[var(--text-secondary)]"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <Loader2
          className="h-5 w-5 animate-spin text-[var(--accent-primary)]"
          aria-hidden="true"
        />
        <div className="text-left">
          <p
            id="requests-loading-title"
            className="text-sm font-medium text-[var(--text-primary)]"
          >
            {t("tab.loading.title")}
          </p>
          <p className="text-[12px] text-[var(--text-muted)]">
            {t("tab.loading.description")}
          </p>
        </div>
      </div>
    </section>
  );
};

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max);

const computePanelPlacement = ({
  rowElement,
  layoutElement,
  panelElement,
}: {
  rowElement: HTMLElement | null;
  layoutElement: HTMLDivElement | null;
  panelElement: HTMLDivElement | null;
}) => {
  if (!layoutElement) {
    return { offsetTop: 0, maxHeight: MIN_PANEL_HEIGHT };
  }

  const layoutRect = layoutElement.getBoundingClientRect();
  const rowRect = rowElement?.getBoundingClientRect() ?? null;

  const viewportTop = VIEWPORT_GUTTER;
  const viewportBottom = window.innerHeight - VIEWPORT_GUTTER;

  const visibleTop = Math.max(layoutRect.top, viewportTop);
  const visibleBottom = Math.min(layoutRect.bottom, viewportBottom);

  const safeTop = visibleTop + PANEL_GUTTER;
  const safeBottom = visibleBottom - PANEL_GUTTER;

  const availableHeight = Math.max(MIN_PANEL_HEIGHT, safeBottom - safeTop);

  const panelNaturalHeight = panelElement?.offsetHeight ?? MIN_PANEL_HEIGHT;
  const fittedPanelHeight = Math.min(panelNaturalHeight, availableHeight);

  const visibleCenter = safeTop + (safeBottom - safeTop) / 2;
  const rowCenter = rowRect
    ? rowRect.top + rowRect.height / 2
    : visibleCenter;

  const targetCenter =
    rowCenter < visibleCenter - PANEL_CENTER_THRESHOLD ||
    rowCenter > visibleCenter + PANEL_CENTER_THRESHOLD
      ? visibleCenter
      : rowCenter;

  const desiredTop = targetCenter - fittedPanelHeight / 2;
  const minTop = safeTop;
  const maxTop = Math.max(safeTop, safeBottom - fittedPanelHeight);

  const adjustedTop = clamp(desiredTop, minTop, maxTop);
  const offsetTop = Math.max(0, adjustedTop - layoutRect.top);

  return {
    offsetTop,
    maxHeight: Math.max(MIN_PANEL_HEIGHT, safeBottom - adjustedTop),
  };
};

// -------------------------------------------------------------
// RequestsTab
// -------------------------------------------------------------

export const RequestsTab: React.FC<Props> = ({
  dealId,
  runId,
  onOpenViewerAt,
}) => {
  const { t } = useTranslation("requests");

  // Local UI state for the shared ExportMenu (open/closed).
  // Export itself is a single-shot call via dealReviewApi — no
  // React Query mutation, the file downloads immediately.
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);

  // Results output locale — shared with DD Grid / Documents via the
  // same persistent store (useDDGridV1UIStore.outputLocale is backed
  // by localStorage `steloom_output_locale`).
  const outputLocale = useDDGridV1UIStore((state) => state.outputLocale);
  const setOutputLocale = useDDGridV1UIStore(
    (state) => state.setOutputLocale,
  );

  // ── Selection state (persisted after panel close) ──────────
  const [selectedReviewReqKey, setSelectedReviewReqKey] = useState<string | null>(null);

  // ── Panel visibility state (independent from selection) ────
  const [isReviewPanelOpen, setIsReviewPanelOpen] = useState(false);

  // ── Inline message state ───────────────────────────────────
  const [inlineMessage, setInlineMessage] = useState<InlineMessageState | null>(null);

  // ── Panel placement (desktop computed positioning) ─────────
  const [reviewPanelOffsetTop, setReviewPanelOffsetTop] = useState(0);
  const [reviewPanelMaxHeight, setReviewPanelMaxHeight] = useState(MIN_PANEL_HEIGHT);

  const reviewLayoutRef = useRef<HTMLDivElement | null>(null);
  const reviewPanelRef = useRef<HTMLDivElement | null>(null);

  const { data: reviewRequests, isLoading: isLoadingReview } =
    useDealReviewDdRequests(dealId, runId ?? null, outputLocale, {
      enabled: !!runId,
    });

  // Review UI is shown whenever a run is present, regardless of data
  // arrival state. Data-loading is handled separately via isLoadingReview.
  //
  // History: previously `isReviewMode` also required `!isLoadingReview`,
  // so the first frame after mount rendered the legacy manual header
  // (Word / Excel / New request) and then switched to the review header
  // once data arrived — a visible "flash" of unrelated UI. The legacy
  // manual mode operated on the dd_requests table, which is empty and
  // unused, so it has been removed entirely.
  const isReviewMode = !!runId;

  const visibleCount = reviewRequests?.length ?? 0;

  const selectedReviewReq: DDRequestDTO | null = useMemo(() => {
    if (!selectedReviewReqKey || !Array.isArray(reviewRequests)) return null;
    const found = reviewRequests.find((req) => {
      const view = toRequestTableRowFromReview(req);
      return view.id === selectedReviewReqKey;
    });
    return found ?? null;
  }, [selectedReviewReqKey, reviewRequests]);

  const clearInlineMessage = useCallback(() => {
    setInlineMessage(null);
  }, []);

  const updateReviewPanelPlacement = useCallback(
    (rowElement: HTMLElement | null) => {
      const placement = computePanelPlacement({
        rowElement,
        layoutElement: reviewLayoutRef.current,
        panelElement: reviewPanelRef.current,
      });
      setReviewPanelOffsetTop(placement.offsetTop);
      setReviewPanelMaxHeight(placement.maxHeight);
    },
    [],
  );

  // ── Derived visibility (panel is open only if both selection and visibility are set) ──
  const hasReviewPanel =
    isReviewPanelOpen && !!selectedReviewReqKey && !!selectedReviewReq;

  // ── Body overflow lock for mobile fullscreen panel ─────────
  React.useEffect(() => {
    if (!hasReviewPanel) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [hasReviewPanel]);

  // ── Escape key closes the review panel ─────────────────────
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && hasReviewPanel) {
        setIsReviewPanelOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasReviewPanel]);

  const downloadBlob = useCallback((blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }, []);

  const handleSelectReviewRequest = useCallback(
    (req: DDRequestDTO, rowElement: HTMLElement | null) => {
      const view = toRequestTableRowFromReview(req);
      setSelectedReviewReqKey(view.id);
      setIsReviewPanelOpen(true);
      requestAnimationFrame(() => updateReviewPanelPlacement(rowElement));
    },
    [updateReviewPanelPlacement],
  );

  const handleCloseReviewPanel = useCallback(() => {
    setIsReviewPanelOpen(false);
    // Do NOT clear selectedReviewReqKey — the row stays highlighted
    // so the user can see which request they had opened.
  }, []);

  // Review-mode export uses the /dd-requests/export endpoint, which
  // produces byte-for-byte the same content as the Requests section
  // of the multi-sheet Summary (XLSX) and the DD Report Appendix A
  // (DOCX) for the same output_locale.
  const handleReviewExport = useCallback(
    async (format: "xlsx" | "docx") => {
      if (!runId) return;
      try {
        setInlineMessage(null);
        setIsExportMenuOpen(false);
        const blob = await dealReviewApi.exportDdRequestsForRun(
          dealId,
          runId,
          outputLocale,
          format,
        );
        const ext = format === "xlsx" ? "xlsx" : "docx";
        downloadBlob(blob, `dd_requests_${runId.slice(0, 8)}.${ext}`);
      } catch (e) {
        console.error(e);
        setInlineMessage({
          tone: "error",
          title:
            format === "docx"
              ? t("tab.errors.exportWordFailed.title")
              : t("tab.errors.exportExcelFailed.title"),
          description: t("tab.errors.exportFailedDescription"),
        });
      }
    },
    [runId, dealId, outputLocale, downloadBlob, t],
  );

  // No run → no review data available at all. Show a placeholder
  // instead of an empty table.
  if (!isReviewMode) {
    return (
      <section
        className="flex h-full min-h-0 flex-col"
        aria-labelledby="requests-tab-title"
      >
        <header className="flex min-h-0 flex-1 flex-col items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center shadow-sm">
          <p className="text-sm text-[var(--text-muted)]">
            {t("tab.noRun.title")}
          </p>
        </header>
      </section>
    );
  }

  // Subtitle depends only on review state: loading / has data / empty.
  const resolvedSubtitle = isLoadingReview
    ? t("tab.subtitles.loading")
    : visibleCount > 0
      ? t("tab.subtitles.reviewWithCount", { count: visibleCount })
      : t("tab.subtitles.reviewEmpty");

  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-labelledby="requests-tab-title"
    >
      <header className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="flex min-h-0 flex-1 flex-col px-5">

          {/* ── Header row ──────────────────────────────────── */}
          <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] py-3">
            <div className="min-w-0 flex-1">
              <h2
                id="requests-tab-title"
                className="text-sm font-semibold text-[var(--text-primary)]"
              >
                {t("tab.title")}
              </h2>
              <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                {resolvedSubtitle}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {runId && (
                <>
                  <ResultPresentationStatus
                    dealId={dealId}
                    runId={runId}
                    presentationLocale={outputLocale}
                    canRequest={false}
                  />
                  <ExportMenu
                    isOpen={isExportMenuOpen}
                    onToggle={() =>
                      setIsExportMenuOpen((prev) => !prev)
                    }
                    onClose={() => setIsExportMenuOpen(false)}
                    onExportExcel={() => handleReviewExport("xlsx")}
                    onExportWord={() => handleReviewExport("docx")}
                    disabled={isLoadingReview}
                    /* onExportPDF — omitted: PDF is not produced by the backend */
                  />
                </>
              )}
              <ResultsLocaleSelector
                value={outputLocale}
                onChange={setOutputLocale}
              />
            </div>
          </div>

          {inlineMessage && (
            <div className="border-b border-[var(--border-subtle)] py-3">
              <div aria-live="polite" aria-atomic="true">
                <InlineBanner
                  tone={inlineMessage.tone}
                  title={inlineMessage.title}
                  description={inlineMessage.description}
                  onDismiss={clearInlineMessage}
                />
              </div>
            </div>
          )}

          <div className="flex min-h-0 flex-1 flex-col py-4">
            <div
              ref={reviewLayoutRef}
              className={
                hasReviewPanel
                  ? "grid min-h-0 min-w-0 flex-1 items-stretch gap-4 overflow-hidden lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"
                  : "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
              }
            >
              <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
                {isLoadingReview ? (
                  <LoadingState />
                ) : (
                  <ReviewRequestsTable
                    requests={reviewRequests ?? []}
                    selectedRequestId={selectedReviewReqKey}
                    onRowClick={handleSelectReviewRequest}
                  />
                )}
              </div>

              {/* ── Review Panel ──────────────────────────── */}
              {hasReviewPanel && selectedReviewReq && (
                <>
                  {/* Mobile backdrop */}
                  <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden" />

                  {/* Mobile fullscreen panel */}
                  <div className="fixed inset-0 z-50 flex min-h-0 flex-col bg-[var(--bg-card)] lg:hidden">
                    <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4">
                      <span className="text-sm font-semibold text-[var(--text-primary)]">
                        {t("tab.detailsPanel.title")}
                      </span>
                      <button
                        type="button"
                        onClick={handleCloseReviewPanel}
                        className="shrink-0 rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
                        aria-label={t("panel.closeAria")}
                      >
                        {t("tab.detailsPanel.back")}
                      </button>
                    </div>
                    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[var(--bg-elevated-soft)]">
                      <ReviewRequestSidePanel
                        request={selectedReviewReq}
                        onClose={handleCloseReviewPanel}
                        onOpenAtLocation={onOpenViewerAt}
                      />
                    </div>
                  </div>

                  {/* Desktop inline panel */}
                  <div
                    className="hidden min-w-0 self-start overflow-y-auto overscroll-contain rounded-2xl bg-[var(--bg-elevated-soft)] lg:block"
                    style={{
                      marginTop: reviewPanelOffsetTop,
                      maxHeight: reviewPanelMaxHeight,
                    }}
                  >
                    <div ref={reviewPanelRef}>
                      <ReviewRequestSidePanel
                        request={selectedReviewReq}
                        onClose={handleCloseReviewPanel}
                        onOpenAtLocation={onOpenViewerAt}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </header>
    </section>
  );
};

export default RequestsTab;


