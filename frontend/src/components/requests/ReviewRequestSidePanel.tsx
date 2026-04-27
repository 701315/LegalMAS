// =============================================================
// src/components/requests/ReviewRequestSidePanel.tsx
// Read-only side panel для DD-запроса в review-режиме.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDRequestDTO из run-scoped API.
// Использует shared presentation components и adapter для преобразования DTO.
// =============================================================

import React, { useEffect, useMemo, useCallback } from "react";
import { X } from "lucide-react";
import type { DDRequestDTO } from "../../types/dealReview";
import type { OpenViewerAtFn, OpenViewerAtPayload } from "../../types";
import {
  toRequestPanelViewFromReview,
  getRequestViewerTarget,
} from "../../viewAdapters/requestPresentation";

// Shared components
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
  // Закрытие по Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Преобразуем DDRequestDTO в UI read-model через adapter
  const viewModel = useMemo(() => {
    if (!request) return null;
    return toRequestPanelViewFromReview(request);
  }, [request]);

  // Единый viewer target через shared helper
  const viewerTarget = useMemo(() => {
    if (!viewModel) return null;
    return getRequestViewerTarget(viewModel);
  }, [viewModel]);

  /**
   * Определяем, можем ли мы выполнить viewer jump.
   *
   * Условия:
   * 1. onOpenAtLocation callback передан
   * 2. helper смог определить target document с id
   * 3. есть segment context (segment_id или chunk_id)
   *
   * Если все условия выполнены — включаем viewer jump.
   */
  const canJumpToViewer = useMemo(() => {
    if (!onOpenAtLocation || !viewModel || !viewerTarget) return false;

    const hasSegmentContext = !!(
      viewerTarget.segmentId ||
      viewerTarget.chunkId
    );

    return hasSegmentContext;
  }, [onOpenAtLocation, viewModel, viewerTarget]);

  /**
   * Причина блокировки viewer jump для UI-подсказки.
   */
  const viewerJumpDisabledReason = useMemo(() => {
    if (!onOpenAtLocation) return undefined;
    if (!viewModel) return undefined;

    if (!viewerTarget) {
      return "Переход к месту в документе будет доступен после обновления API (document_id в запросе).";
    }

    const hasSegmentContext = !!(
      viewerTarget.segmentId ||
      viewerTarget.chunkId
    );
    if (!hasSegmentContext) {
      return "Segment context отсутствует — переход невозможен.";
    }

    return undefined;
  }, [onOpenAtLocation, viewModel, viewerTarget]);

  /**
   * Handler для viewer jump.
   * Использует единый helper getRequestViewerTarget(viewModel),
   * чтобы не дублировать логику выбора документа.
   */
  const handleJumpToViewer = useCallback(() => {
    if (!canJumpToViewer || !onOpenAtLocation || !viewerTarget) return;

    const payload: OpenViewerAtPayload = {
      documentId: viewerTarget.documentId,
      segmentId: viewerTarget.segmentId,
      chunkId: viewerTarget.chunkId,
      chunkIndex: viewerTarget.chunkIndex,
      // page/clauseUid/elementId сейчас не проброшены через DDRequestDTO,
      // но payload их поддерживает для будущего расширения
      page: null,
      clauseUid: null,
      elementId: null,
    };

    onOpenAtLocation(payload);
  }, [canJumpToViewer, onOpenAtLocation, viewerTarget]);

  if (!viewModel) return null;

  return (
    <>
      {/* Затемнение */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      {/* Панель */}
      <div className="fixed right-0 top-0 h-full w-[420px] bg-white shadow-2xl z-50 border-l flex flex-col animate-in slide-in-from-right">
        {/* Шапка */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex flex-col gap-0.5">
            <h3 className="text-lg font-semibold text-gray-900">
              {viewModel.title}
            </h3>
            {viewModel.addressee && (
              <p className="text-xs text-blue-600">→ {viewModel.addressee}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-100 rounded transition"
            aria-label="Закрыть"
          >
            <X size={20} />
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Приоритет — shared component */}
          <Field label="Приоритет">
            <RequestPriorityBadge priority={viewModel.priority} />
          </Field>

          {/* Текст запроса */}
          <Field label="Текст запроса">
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {viewModel.text}
            </p>
          </Field>

          {/* Документы — shared component */}
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
                    className="px-2 py-0.5 rounded-full bg-gray-100 text-xs text-gray-600"
                  >
                    {dt}
                  </span>
                ))}
              </div>
            </Field>
          )}

          {/* Segment context — shared component */}
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
              <p className="text-sm text-gray-700 font-mono">
                {viewModel.checkId}
              </p>
            </Field>
          )}

          {/* Structured values — shared component */}
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

        {/* Подвал — read-only метка */}
        <div className="border-t px-5 py-3">
          <p className="text-xs text-gray-400 text-center">
            Review-режим · только просмотр
          </p>
        </div>
      </div>
    </>
  );
};

// -------------------------------------------------------------
// Вспомогательный компонент Field (оставляем локальным)
// -------------------------------------------------------------

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

export default ReviewRequestSidePanel;




