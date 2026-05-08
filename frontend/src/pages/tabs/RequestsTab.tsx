// =============================================================
// src/pages/tabs/RequestsTab.tsx
// Вкладка "Запросы": таблица DD‑запросов + embedded side panel деталей.
// Панель открывается примерно на уровне выбранной строки, но не уходит
// за нижнюю границу видимой рабочей области: если строка расположена низко,
// панель автоматически сдвигается вверх.
// Дополнительно выровнены внутренние gutters панели: слева, справа и снизу.
// Позиционирование панели — гибридное: около строки, если строка недалеко
// от центра видимой области; иначе панель центрируется относительно рабочей зоны.
// Фон контейнера панели синхронизирован с цветом выделенной строки запроса.
// =============================================================

import React, { useCallback, useMemo, useRef, useState } from "react";
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
import { useDealReviewDdRequests } from "../../api/dealReview";
import type { DDRequestDTO } from "../../types/dealReview";
import { ReviewRequestsTable } from "../../components/requests/ReviewRequestsTable";
import { ReviewRequestSidePanel } from "../../components/requests/ReviewRequestSidePanel";
import Button from "../../components/ui/Button";
import { toRequestTableRowFromReview } from "../../viewAdapters/requestPresentation";

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

const InlineBanner: React.FC<{
  tone: InlineMessageTone;
  title: string;
  description: string;
  onDismiss?: () => void;
}> = ({ tone, title, description, onDismiss }) => {
  const toneClassName =
    tone === "error"
      ? "border-[var(--color-error-border)] bg-[var(--color-error-subtle)] text-[var(--color-error)]"
      : tone === "warning"
        ? "border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] text-[var(--color-warning)]"
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
            Закрыть
          </Button>
        )}
      </div>
    </div>
  );
};

const LoadingState: React.FC = () => (
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
            Загружаем запросы
          </p>
          <p className="text-[12px] text-[var(--text-muted)]">
            Подготавливаем таблицу и детали запроса.
          </p>
        </div>
      </div>
    </div>
  </section>
);

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
    return {
      offsetTop: 0,
      maxHeight: MIN_PANEL_HEIGHT,
    };
  }

  const layoutRect = layoutElement.getBoundingClientRect();
  const rowRect = rowElement?.getBoundingClientRect() ?? null;

  const viewportTop = VIEWPORT_GUTTER;
  const viewportBottom = window.innerHeight - VIEWPORT_GUTTER;

  const visibleTop = Math.max(layoutRect.top, viewportTop);
  const visibleBottom = Math.min(layoutRect.bottom, viewportBottom);

  const safeTop = visibleTop + PANEL_GUTTER;
  const safeBottom = visibleBottom - PANEL_GUTTER;

  const availableHeight = Math.max(
    MIN_PANEL_HEIGHT,
    safeBottom - safeTop,
  );

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

export const RequestsTab: React.FC<Props> = ({
  dealId,
  runId,
  onOpenViewerAt,
}) => {
  const { data: requests, isLoading } = useRequests(dealId);

  const updateMutation = useUpdateRequest(dealId);
  const deleteMutation = useDeleteRequest(dealId);
  const exportRequestsMutation = useExportRequests();

  const { canManageRequests } = useDealPermissions(dealId);

  const [selectedReq, setSelectedReq] = useState<DDRequest | null>(null);
  const [selectedReviewReqKey, setSelectedReviewReqKey] = useState<string | null>(
    null,
  );
  const [inlineMessage, setInlineMessage] = useState<InlineMessageState | null>(
    null,
  );

  const [legacyPanelOffsetTop, setLegacyPanelOffsetTop] = useState(0);
  const [reviewPanelOffsetTop, setReviewPanelOffsetTop] = useState(0);
  const [legacyPanelMaxHeight, setLegacyPanelMaxHeight] =
    useState(MIN_PANEL_HEIGHT);
  const [reviewPanelMaxHeight, setReviewPanelMaxHeight] =
    useState(MIN_PANEL_HEIGHT);

  const legacyLayoutRef = useRef<HTMLDivElement | null>(null);
  const reviewLayoutRef = useRef<HTMLDivElement | null>(null);
  const legacyPanelRef = useRef<HTMLDivElement | null>(null);
  const reviewPanelRef = useRef<HTMLDivElement | null>(null);

  const { data: reviewRequests, isLoading: isLoadingReview } =
    useDealReviewDdRequests(dealId, runId ?? null, {
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

  const clearInlineMessage = useCallback(() => {
    setInlineMessage(null);
  }, []);

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

  const handleSave = useCallback(
    async (reqId: string, data: Partial<DDRequest>) => {
      if (!canManageRequests) {
        setInlineMessage({
          tone: "warning",
          title: "Недостаточно прав",
          description:
            "Редактирование запросов доступно только редакторам и администраторам проекта.",
        });
        return;
      }

      setInlineMessage(null);
      await updateMutation.mutateAsync({ reqId, data });
    },
    [updateMutation, canManageRequests],
  );

  const handleDelete = useCallback(
    async (reqId: string) => {
      if (!canManageRequests) {
        setInlineMessage({
          tone: "warning",
          title: "Недостаточно прав",
          description:
            "Удаление запросов доступно только редакторам и администраторам проекта.",
        });
        return;
      }

      setInlineMessage(null);
      await deleteMutation.mutateAsync(reqId);
      setSelectedReq((current) => (current?.id === reqId ? null : current));
    },
    [deleteMutation, canManageRequests],
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
      const blob = await exportRequestsMutation.mutateAsync({
        dealId,
        format: "word",
      });
      downloadBlob(blob, `dd_requests_${dealId}.docx`);
    } catch (e) {
      console.error(e);
      setInlineMessage({
        tone: "error",
        title: "Не удалось экспортировать в Word",
        description:
          "Попробуйте повторить экспорт позже. Если ошибка сохраняется, проверьте состояние сервиса экспорта.",
      });
    }
  }, [dealId, exportRequestsMutation, downloadBlob]);

  const handleExportExcel = useCallback(async () => {
    try {
      setInlineMessage(null);
      const blob = await exportRequestsMutation.mutateAsync({
        dealId,
        format: "excel",
      });
      downloadBlob(blob, `dd_requests_${dealId}.xlsx`);
    } catch (e) {
      console.error(e);
      setInlineMessage({
        tone: "error",
        title: "Не удалось экспортировать в Excel",
        description:
          "Попробуйте повторить экспорт позже. Если ошибка сохраняется, проверьте состояние сервиса экспорта.",
      });
    }
  }, [dealId, exportRequestsMutation, downloadBlob]);

  const handleCreate = useCallback(() => {
    if (!canManageRequests) {
      setInlineMessage({
        tone: "warning",
        title: "Создание недоступно",
        description:
          "Создание запросов доступно только редакторам и администраторам проекта.",
      });
      return;
    }

    setInlineMessage({
      tone: "info",
      title: "Создание нового запроса",
      description:
        "Функция создания нового DD-запроса пока не реализована в текущем интерфейсе.",
    });
  }, [canManageRequests]);

  const isBusy =
    exportRequestsMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending;

  if (isLoading && !isReviewMode) {
    return (
      <div className="space-y-4">
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          Загружаем запросы
        </div>
        <LoadingState />
      </div>
    );
  }

  const hasLegacyPanel = !!selectedReq;
  const hasReviewPanel = !!selectedReviewReqKey && !!selectedReviewReq;

  return (
    <section className="space-y-4" aria-labelledby="requests-tab-title">
      <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-5">
          <div className="border-b border-[var(--border-subtle)] py-4">
            <h2
              id="requests-tab-title"
              className="text-base font-semibold text-[var(--text-primary)]"
            >
              Запросы
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {isReviewMode
                ? visibleCount > 0
                  ? `Сформированы запросы по результатам анализа: ${visibleCount}`
                  : "Запросы по результатам анализа пока не сформированы"
                : visibleCount > 0
                  ? `Рабочий список DD-запросов по сделке: ${visibleCount}.`
                  : "Запросы по сделке пока не добавлены."}
            </p>
          </div>

          {!isReviewMode && (
            <div className="flex flex-wrap items-center justify-end gap-2 border-b border-[var(--border-subtle)] py-4">
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
                Новый запрос
              </Button>
            </div>
          )}

          {!isReviewMode && !canManageRequests && (
            <div className="border-b border-[var(--border-subtle)] py-3">
              <div className="rounded-2xl border border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] px-4 py-3 text-[var(--color-warning)]">
                <p className="text-sm font-medium">Режим только для просмотра</p>
                <p className="mt-1 text-sm leading-6">
                  Экспорт доступен, но создание, редактирование и удаление запросов
                  ограничены правами проекта.
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

          <div className="py-4">
            {isReviewMode ? (
              <div
                ref={reviewLayoutRef}
                className={
                  hasReviewPanel
                    ? "grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"
                    : "min-w-0"
                }
              >
                <div className="min-w-0">
                  <ReviewRequestsTable
                    requests={reviewRequests ?? []}
                    selectedRequestId={selectedReviewReqKey}
                    onRowClick={(req, rowElement) => {
                      const view = toRequestTableRowFromReview(req);
                      setSelectedReviewReqKey(view.id);
                      requestAnimationFrame(() =>
                        updateReviewPanelPlacement(rowElement),
                      );
                    }}
                  />
                </div>

                {hasReviewPanel && selectedReviewReq && (
                  <div
                    className="min-w-0 self-start overflow-hidden pr-4"
                    style={{
                      marginTop: reviewPanelOffsetTop,
                      maxHeight: reviewPanelMaxHeight,
                    }}
                  >
                    <div
                      ref={reviewPanelRef}
                      className="min-h-0 rounded-2xl bg-[var(--bg-elevated-soft)]"
                    >
                      <ReviewRequestSidePanel
                        request={selectedReviewReq}
                        onClose={() => setSelectedReviewReqKey(null)}
                        onOpenAtLocation={onOpenViewerAt}
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div
                ref={legacyLayoutRef}
                className={
                  hasLegacyPanel
                    ? "grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]"
                    : "min-w-0"
                }
              >
                <div className="min-w-0">
                  <RequestsTable
                    requests={requests ?? []}
                    selectedRequestId={selectedReq?.id ?? null}
                    onRowClick={(req, rowElement) => {
                      setSelectedReq(req);
                      requestAnimationFrame(() =>
                        updateLegacyPanelPlacement(rowElement),
                      );
                    }}
                    onCreateClick={handleCreate}
                    onExportWord={handleExportWord}
                    onExportExcel={handleExportExcel}
                    canManageRequests={canManageRequests}
                  />
                </div>

                {hasLegacyPanel && (
                  <div
                    className="min-w-0 self-start overflow-hidden pr-4 pb-4"
                    style={{
                      marginTop: legacyPanelOffsetTop,
                      maxHeight: legacyPanelMaxHeight,
                    }}
                  >
                    <div
                      ref={legacyPanelRef}
                      className="min-h-0 rounded-2xl bg-[var(--bg-elevated-soft)]"
                    >
                      <RequestSidePanel
                        request={selectedReq}
                        onClose={() => setSelectedReq(null)}
                        onSave={handleSave}
                        onDelete={handleDelete}
                        isSaving={updateMutation.isPending}
                        canManageRequests={canManageRequests}
                      />
                    </div>
                  </div>
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


