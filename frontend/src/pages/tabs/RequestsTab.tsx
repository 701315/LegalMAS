// =============================================================
// src/pages/tabs/RequestsTab.tsx
// =============================================================

import React, { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Loader2,
  FileSpreadsheet,
  FileText,
  FolderPlus,
  AlertTriangle,
} from "lucide-react";
import type { DDRequest, OpenViewerAtFn } from "../../types";
import {
  useRequests,
  useUpdateRequest,
  useDeleteRequest,
  useExportRequests,
} from "../../api/requests";
import { RequestsTable } from "../../components/requests/RequestsTable";
import { RequestSidePanel } from "../../components/requests/RequestSidePanel";
import { useDealPermissions } from "../../hooks/usePermissions";
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
      className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm"
      aria-labelledby="requests-loading-title"
    >
      <div className="flex min-h-[320px] flex-col items-center justify-center px-6 py-10 text-center">
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
  const { data: requests, isLoading } = useRequests(dealId);

  const updateMutation = useUpdateRequest(dealId);
  const deleteMutation = useDeleteRequest(dealId);
  const exportRequestsMutation = useExportRequests();

  // Pending-флаг для review-mode экспорта (xlsx/docx) через новый
  // /dd-requests/export endpoint. Использует dealReviewApi напрямую:
  // single-shot запрос без React Query — файл скачивается сразу.
  const [reviewExportFormat, setReviewExportFormat] = useState<
    "xlsx" | "docx" | null
  >(null);

  const { canManageRequests } = useDealPermissions(dealId);

  // Results output locale — shared with DD Grid / Documents via the
  // same persistent store (useDDGridV1UIStore.outputLocale is backed
  // by localStorage `steloom_output_locale`).
  const outputLocale = useDDGridV1UIStore((state) => state.outputLocale);
  const setOutputLocale = useDDGridV1UIStore(
    (state) => state.setOutputLocale,
  );

  // ── Selection state (persisted after panel close) ──────────
  const [selectedReq, setSelectedReq] = useState<DDRequest | null>(null);
  const [selectedReviewReqKey, setSelectedReviewReqKey] = useState<string | null>(null);

  // ── Panel visibility state (independent from selection) ────
  const [isLegacyPanelOpen, setIsLegacyPanelOpen] = useState(false);
  const [isReviewPanelOpen, setIsReviewPanelOpen] = useState(false);

  // ── Inline message state ───────────────────────────────────
  const [inlineMessage, setInlineMessage] = useState<InlineMessageState | null>(null);

  // ── Panel placement (desktop computed positioning) ─────────
  const [legacyPanelOffsetTop, setLegacyPanelOffsetTop] = useState(0);
  const [reviewPanelOffsetTop, setReviewPanelOffsetTop] = useState(0);
  const [legacyPanelMaxHeight, setLegacyPanelMaxHeight] = useState(MIN_PANEL_HEIGHT);
  const [reviewPanelMaxHeight, setReviewPanelMaxHeight] = useState(MIN_PANEL_HEIGHT);

  const legacyLayoutRef = useRef<HTMLDivElement | null>(null);
  const reviewLayoutRef = useRef<HTMLDivElement | null>(null);
  const legacyPanelRef = useRef<HTMLDivElement | null>(null);
  const reviewPanelRef = useRef<HTMLDivElement | null>(null);

  const { data: reviewRequests, isLoading: isLoadingReview } =
    useDealReviewDdRequests(dealId, runId ?? null, outputLocale, {
      enabled: !!runId,
    });

  const isReviewMode =
    !!runId && !isLoadingReview && Array.isArray(reviewRequests);

  const visibleCount = isReviewMode
    ? (reviewRequests?.length ?? 0)
    : (requests?.length ?? 0);

  const selectedReviewReq: DDRequestDTO | null = useMemo(() => {
    if (!selectedReviewReqKey || !Array.isArray(reviewRequests)) return null;
    const found = reviewRequests.find((req) => {
      const view = toRequestTableRowFromReview(req);
      return view.id === selectedReviewReqKey;
    });
    return found ?? null;
  }, [selectedReviewReqKey, reviewRequests]);

  const clearInlineMessage = useCallback(() => { setInlineMessage(null); }, []);

  const updateLegacyPanelPlacement = useCallback(
    (rowElement: HTMLElement | null) => {
      const placement = computePanelPlacement({
        rowElement,
        layoutElement: legacyLayoutRef.current,
        panelElement: legacyPanelRef.current,
      });
      setLegacyPanelOffsetTop(placement.offsetTop);
      setLegacyPanelMaxHeight(placement.maxHeight);
    },
    [],
  );

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
  const hasLegacyPanel = isLegacyPanelOpen && !!selectedReq;
  const hasReviewPanel = isReviewPanelOpen && !!selectedReviewReqKey && !!selectedReviewReq;

  // ── Body overflow lock for mobile fullscreen panel ─────────
  React.useEffect(() => {
    const isAnyPanelOpen = hasLegacyPanel || hasReviewPanel;
    if (!isAnyPanelOpen) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [hasLegacyPanel, hasReviewPanel]);

  // ── Escape key to close panels ─────────────────────────────
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (hasLegacyPanel) {
          setIsLegacyPanelOpen(false);
          return;
        }
        if (hasReviewPanel) {
          setIsReviewPanelOpen(false);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasLegacyPanel, hasReviewPanel]);

  const handleSave = useCallback(
    async (reqId: string, data: Partial<DDRequest>) => {
      if (!canManageRequests) {
        setInlineMessage({
          tone: "warning",
          title: t("tab.errors.noPermissions.title"),
          description: t("tab.errors.noPermissions.editDescription"),
        });
        return;
      }
      setInlineMessage(null);
      await updateMutation.mutateAsync({ reqId, data });
    },
    [updateMutation, canManageRequests, t],
  );

  const handleDelete = useCallback(
    async (reqId: string) => {
      if (!canManageRequests) {
        setInlineMessage({
          tone: "warning",
          title: t("tab.errors.noPermissions.title"),
          description: t("tab.errors.noPermissions.deleteDescription"),
        });
        return;
      }
      setInlineMessage(null);
      await deleteMutation.mutateAsync(reqId);
      setSelectedReq((current) => (current?.id === reqId ? null : current));
    },
    [deleteMutation, canManageRequests, t],
  );

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

  const handleExportWord = useCallback(async () => {
    try {
      setInlineMessage(null);
      const blob = await exportRequestsMutation.mutateAsync({ dealId, format: "word" });
      downloadBlob(blob, `dd_requests_${dealId}.docx`);
    } catch (e) {
      console.error(e);
      setInlineMessage({
        tone: "error",
        title: t("tab.errors.exportWordFailed.title"),
        description: t("tab.errors.exportFailedDescription"),
      });
    }
  }, [dealId, exportRequestsMutation, downloadBlob, t]);

  const handleExportExcel = useCallback(async () => {
    try {
      setInlineMessage(null);
      const blob = await exportRequestsMutation.mutateAsync({ dealId, format: "excel" });
      downloadBlob(blob, `dd_requests_${dealId}.xlsx`);
    } catch (e) {
      console.error(e);
      setInlineMessage({
        tone: "error",
        title: t("tab.errors.exportExcelFailed.title"),
        description: t("tab.errors.exportFailedDescription"),
      });
    }
  }, [dealId, exportRequestsMutation, downloadBlob, t]);

  const handleCreate = useCallback(() => {
    if (!canManageRequests) {
      setInlineMessage({
        tone: "warning",
        title: t("tab.errors.createUnavailable.title"),
        description: t("tab.errors.createUnavailable.description"),
      });
      return;
    }
    setInlineMessage({
      tone: "info",
      title: t("tab.info.createRequest.title"),
      description: t("tab.info.createRequest.description"),
    });
  }, [canManageRequests, t]);

  // ── Selection handlers (set selection AND open panel) ──────
  const handleSelectLegacyRequest = useCallback(
    (req: DDRequest, rowElement: HTMLElement | null) => {
      setSelectedReq(req);
      setIsLegacyPanelOpen(true);
      requestAnimationFrame(() => updateLegacyPanelPlacement(rowElement));
    },
    [updateLegacyPanelPlacement],
  );

  const handleSelectReviewRequest = useCallback(
    (req: DDRequestDTO, rowElement: HTMLElement | null) => {
      const view = toRequestTableRowFromReview(req);
      setSelectedReviewReqKey(view.id);
      setIsReviewPanelOpen(true);
      requestAnimationFrame(() => updateReviewPanelPlacement(rowElement));
    },
    [updateReviewPanelPlacement],
  );

  // ── Panel close handlers (close panel, keep selection) ─────
  const handleCloseLegacyPanel = useCallback(() => {
    setIsLegacyPanelOpen(false);
    // НЕ сбрасываем selectedReq — строка остаётся активной
  }, []);

  const handleCloseReviewPanel = useCallback(() => {
    setIsReviewPanelOpen(false);
    // НЕ сбрасываем selectedReviewReqKey — строка остаётся активной
  }, []);

  const isBusy =
    exportRequestsMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending;

  // Review-mode экспорт: тот же /dd-requests/export endpoint,
  // что обеспечивает byte-for-byte consistency с DD Report Appendix A
  // и с Excel Summary — Request List sheet.
  const handleReviewExport = useCallback(
    async (format: "xlsx" | "docx") => {
      if (!runId) return;
      try {
        setInlineMessage(null);
        setReviewExportFormat(format);
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
      } finally {
        setReviewExportFormat(null);
      }
    },
    [
      runId,
      dealId,
      outputLocale,
      downloadBlob,
      t,
    ],
  );

  if (isLoading && !isReviewMode) {
    return (
      <div className="space-y-4">
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {t("tab.loading.title")}
        </div>
        <LoadingState />
      </div>
    );
  }

  // Вычисляем заголовок и подзаголовок в зависимости от режима и числа элементов
  const resolvedSubtitle = isReviewMode
    ? visibleCount > 0
      ? t("tab.subtitles.reviewWithCount", { count: visibleCount })
      : t("tab.subtitles.reviewEmpty")
    : visibleCount > 0
      ? t("tab.subtitles.manualWithCount", { count: visibleCount })
      : t("tab.subtitles.manualEmpty");

  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-labelledby="requests-tab-title"
    >
      <header className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="flex min-h-0 flex-1 flex-col px-5">

          {/* ── Заголовок — выровнен с PageSection ─────────── */}
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
              {isReviewMode && runId && (
                <>
                  <ResultPresentationStatus
                    dealId={dealId}
                    runId={runId}
                    presentationLocale={outputLocale}
                    canRequest={false}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleReviewExport("docx")}
                    isLoading={reviewExportFormat === "docx"}
                    disabled={reviewExportFormat !== null}
                    leftIcon={<FileText />}
                  >
                    Word
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleReviewExport("xlsx")}
                    isLoading={reviewExportFormat === "xlsx"}
                    disabled={reviewExportFormat !== null}
                    leftIcon={<FileSpreadsheet />}
                  >
                    Excel
                  </Button>
                </>
              )}
              <ResultsLocaleSelector
                value={outputLocale}
                onChange={setOutputLocale}
              />
            </div>
          </div>

          {!isReviewMode && (
            <div className="flex flex-wrap items-center justify-end gap-2 border-b border-[var(--border-subtle)] py-3">
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportWord}
                isLoading={exportRequestsMutation.isPending}
                disabled={isBusy}
                leftIcon={<FileText />}
              >
                Word
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportExcel}
                isLoading={exportRequestsMutation.isPending}
                disabled={isBusy}
                leftIcon={<FileSpreadsheet />}
              >
                Excel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCreate}
                disabled={isBusy}
                leftIcon={<FolderPlus />}
              >
                {t("tab.buttons.newRequest")}
              </Button>
            </div>
          )}

          {!isReviewMode && !canManageRequests && (
            <div className="border-b border-[var(--border-subtle)] py-3">
              <div className="rounded-2xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3 text-[var(--color-warning-text)]">
                <p className="text-sm font-medium">{t("tab.viewOnly.title")}</p>
                <p className="mt-1 text-sm leading-6">
                  {t("tab.viewOnly.description")}
                </p>
              </div>
            </div>
          )}

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
            {isReviewMode ? (
              <div
                ref={reviewLayoutRef}
                className={
                  hasReviewPanel
                    ? "grid min-h-0 min-w-0 flex-1 items-start gap-4 overflow-hidden lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"
                    : "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
                }
              >
                <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
                  <ReviewRequestsTable
                    requests={reviewRequests ?? []}
                    selectedRequestId={selectedReviewReqKey}
                    onRowClick={handleSelectReviewRequest}
                  />
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
            ) : (
              <div
                ref={legacyLayoutRef}
                className={
                  hasLegacyPanel
                    ? "grid min-h-0 min-w-0 flex-1 items-start gap-4 overflow-hidden lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"
                    : "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
                }
              >
                <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
                  <RequestsTable
                    requests={requests ?? []}
                    selectedRequestId={selectedReq?.id ?? null}
                    onRowClick={handleSelectLegacyRequest}
                    onCreateClick={handleCreate}
                    onExportWord={handleExportWord}
                    onExportExcel={handleExportExcel}
                    canManageRequests={canManageRequests}
                  />
                </div>

                {/* ── Legacy (Manual) Panel ─────────────────── */}
                {hasLegacyPanel && (
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
                          onClick={handleCloseLegacyPanel}
                          className="shrink-0 rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
                          aria-label={t("panel.closeAria")}
                        >
                          {t("tab.detailsPanel.back")}
                        </button>
                      </div>
                      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[var(--bg-elevated-soft)]">
                        <RequestSidePanel
                          request={selectedReq}
                          onClose={handleCloseLegacyPanel}
                          onSave={handleSave}
                          onDelete={handleDelete}
                          isSaving={updateMutation.isPending}
                          canManageRequests={canManageRequests}
                        />
                      </div>
                    </div>

                    {/* Desktop inline panel */}
                    <div
                      className="hidden min-w-0 self-start overflow-y-auto overscroll-contain rounded-2xl bg-[var(--bg-elevated-soft)] lg:block"
                      style={{
                        marginTop: legacyPanelOffsetTop,
                        maxHeight: legacyPanelMaxHeight,
                      }}
                    >
                      <div ref={legacyPanelRef}>
                        <RequestSidePanel
                          request={selectedReq}
                          onClose={handleCloseLegacyPanel}
                          onSave={handleSave}
                          onDelete={handleDelete}
                          isSaving={updateMutation.isPending}
                          canManageRequests={canManageRequests}
                        />
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </header>
    </section>
  );
};

export default RequestsTab;


