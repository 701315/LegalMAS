// =============================================================
// src/components/requests/ReviewRequestSidePanel.tsx
// Read-only side panel для DD-запроса в review-режиме.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDRequestDTO из run-scoped API.
// Использует shared presentation components и adapter для DTO.
// =============================================================

import React, { useEffect, useMemo, useCallback } from "react";
import { X } from "lucide-react";
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
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

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
    <>
      {/* Затемнение */}
      <div
        className="fixed inset-0 z-40 bg-[oklch(0.2_0.03_260/0.5)] backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Панель */}
      <div className="fixed right-0 top-0 z-50 flex h-full w-[440px] flex-col border-l border-[var(--border)] bg-[var(--bg-panel)] shadow-[0_0_40px_rgba(15,23,42,0.7)] animate-in slide-in-from-right">
        {/* Шапка */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
          <div className="flex flex-col gap-0.5">
            <h3 className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
              {viewModel.title}
            </h3>
            {viewModel.addressee && (
              <p className="text-xs text-[var(--accent-primary)]">
                → {viewModel.addressee}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)]"
            aria-label="Закрыть"
          >
            <X size={18} />
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {/* Приоритет */}
          <Field label="Приоритет">
            <RequestPriorityBadge priority={viewModel.priority} />
          </Field>

          {/* Текст запроса */}
          <Field label="Текст запроса">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
              {viewModel.text}
            </p>
          </Field>

          {/* Документы */}
          {viewModel.documents.length > 0 && (
            <Field label={`Документы (${viewModel.documents.length})`}>
              <RequestDocumentsList documents={viewModel.documents} />
            </Field>
          )}

          {/* Типы документов */}
          {viewModel.docTypes.length > 0 && (
            <Field label="Типы документов">
              <div className="flex flex-wrap gap-1">
                {viewModel.docTypes.map((dt, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-xs text-[var(--text-secondary)]"
                  >
                    {dt}
                  </span>
                ))}
              </div>
            </Field>
          )}

          {/* Segment context */}
          {viewModel.segment && (
            <Field label="Контекст сегмента">
              <RequestSegmentSummary
                segment={viewModel.segment}
                onJumpToViewer={handleJumpToViewer}
                viewerJumpDisabled={!canJumpToViewer}
                viewerJumpDisabledReason={viewerJumpDisabledReason}
              />
            </Field>
          )}

          {/* Проверка */}
          {viewModel.checkId && (
            <Field label="Проверка (check_id)">
              <p className="font-mono text-sm text-[var(--text-secondary)]">
                {viewModel.checkId}
              </p>
            </Field>
          )}

          {/* Structured values */}
          {viewModel.structuredValues.length > 0 && (
            <Field
              label={`Извлечённые данные (${viewModel.structuredValues.length})`}
            >
              <RequestStructuredValuesList
                values={viewModel.structuredValues}
              />
            </Field>
          )}
        </div>

        {/* Подвал */}
        <div className="border-t border-[var(--border)] px-5 py-3">
          <p className="text-center text-xs text-[var(--text-muted)]">
            Review-режим · только просмотр
          </p>
        </div>
      </div>
    </>
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
    <div>
      <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </label>
      {children}
    </div>
  );
}

export default ReviewRequestSidePanel;




