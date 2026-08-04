// =============================================================
// src/components/requests/ReviewRequestSidePanel.tsx
// =============================================================

import React, { useEffect, useMemo, useCallback } from "react";
import { ExternalLink } from "lucide-react";
import type { DDRequestDTO } from "../../types/dealReview";
import type { OpenViewerAtFn, OpenViewerAtPayload } from "../../types";
import {
  toRequestPanelViewFromReview,
  getRequestViewerTarget,
} from "../../viewAdapters/requestPresentation";

import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { RequestDocumentsList } from "./shared/RequestDocumentsList";
import { RequestStructuredValuesList } from "./shared/RequestStructuredValuesList";
import { RequestSegmentSummary } from "./shared/RequestSegmentSummary";
import Button from "../ui/Button";

interface Props {
  request: DDRequestDTO | null;
  onClose: () => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

export const ReviewRequestSidePanel: React.FC<Props> = ({
  request,
  onClose,
  onOpenAtLocation,
}) => {
  useEffect(() => {
    if (!request) return;

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [request, onClose]);

  const viewModel = useMemo(() => {
    if (!request) return null;
    return toRequestPanelViewFromReview(request);
  }, [request]);

  const viewerTarget = useMemo(() => {
    if (!viewModel) return null;
    return getRequestViewerTarget(viewModel);
  }, [viewModel]);

  const canJumpToViewer = useMemo(() => {
    if (!onOpenAtLocation || !viewModel || !viewerTarget) return false;
    const hasSegmentContext = !!(
      viewerTarget.segmentId || viewerTarget.chunkId
    );
    return hasSegmentContext;
  }, [onOpenAtLocation, viewModel, viewerTarget]);

  const viewerJumpDisabledReason = useMemo(() => {
    if (!onOpenAtLocation) return undefined;
    if (!viewModel) return undefined;

    if (!viewerTarget) {
      return "Переход к месту в документе будет доступен после обновления API (document_id в запросе).";
    }

    const hasSegmentContext = !!(
      viewerTarget.segmentId || viewerTarget.chunkId
    );

    if (!hasSegmentContext) {
      return "Segment context отсутствует — переход невозможен.";
    }

    return undefined;
  }, [onOpenAtLocation, viewModel, viewerTarget]);

  const handleJumpToViewer = useCallback(() => {
    if (!canJumpToViewer || !onOpenAtLocation || !viewerTarget) return;

    const payload: OpenViewerAtPayload = {
      documentId: viewerTarget.documentId,
      segmentId: viewerTarget.segmentId ?? undefined,
      chunkId: viewerTarget.chunkId ?? undefined,
      chunkIndex: viewerTarget.chunkIndex ?? undefined,
      page: undefined,
      clauseUid: undefined,
      elementId: undefined,
    };

    onOpenAtLocation(payload);
  }, [canJumpToViewer, onOpenAtLocation, viewerTarget]);

  if (!viewModel) return null;

  return (
    <aside
      className="flex min-h-0 flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] shadow-[inset_3px_0_0_var(--accent-primary)]"
      aria-labelledby="review-request-panel-title"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            Review-запрос
          </p>
          <h2
            id="review-request-panel-title"
            className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
          >
            {viewModel.title}
          </h2>
          {viewModel.addressee && (
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Адресат: {viewModel.addressee}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть панель запроса"
          className="rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-3">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            Режим
          </p>
          <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
            Только просмотр
          </p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Запрос сформирован в review-контексте run-scoped API и не
            редактируется из этой панели.
          </p>
        </div>

        <Field label="Приоритет">
          <div className="mt-1">
            <RequestPriorityBadge priority={viewModel.priority} />
          </div>
        </Field>

        <Field label="Текст запроса">
          <div className="mt-1 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-3">
            <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text-secondary)]">
              {viewModel.text}
            </p>
          </div>
        </Field>

        {viewModel.documents.length > 0 && (
          <Field label={`Документы (${viewModel.documents.length})`}>
            <div className="mt-1">
              <RequestDocumentsList documents={viewModel.documents} />
            </div>
          </Field>
        )}

        {viewModel.docTypes.length > 0 && (
          <Field label="Типы документов">
            <div className="mt-1 flex flex-wrap gap-1.5">
              {viewModel.docTypes.map((dt, i) => (
                <span
                  key={`${dt}-${i}`}
                  className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                >
                  {dt}
                </span>
              ))}
            </div>
          </Field>
        )}

        {viewModel.segment && (
          <Field label="Контекст сегмента">
            <div className="mt-1 space-y-3">
              <RequestSegmentSummary
                segment={viewModel.segment}
                onJumpToViewer={handleJumpToViewer}
                viewerJumpDisabled={!canJumpToViewer}
                viewerJumpDisabledReason={viewerJumpDisabledReason}
              />

              {onOpenAtLocation && (
                <div className="flex justify-start">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={handleJumpToViewer}
                    disabled={!canJumpToViewer}
                    leftIcon={<ExternalLink className="h-4 w-4" />}
                  >
                    Открыть в viewer
                  </Button>
                </div>
              )}

              {!canJumpToViewer && viewerJumpDisabledReason && (
                <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-[12px] leading-5 text-[var(--color-warning-text)]">
                  {viewerJumpDisabledReason}
                </div>
              )}
            </div>
          </Field>
        )}

        {viewModel.checkId && (
          <Field label="Проверка (check_id)">
            <div className="mt-1 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-3">
              <p className="font-mono text-sm text-[var(--text-secondary)]">
                {viewModel.checkId}
              </p>
            </div>
          </Field>
        )}

        {viewModel.structuredValues.length > 0 && (
          <Field
            label={`Извлечённые данные (${viewModel.structuredValues.length})`}
          >
            <div className="mt-1">
              <RequestStructuredValuesList values={viewModel.structuredValues} />
            </div>
          </Field>
        )}
      </div>
    </aside>
  );
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <label className="block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </label>
      {children}
    </section>
  );
}

export default ReviewRequestSidePanel;


