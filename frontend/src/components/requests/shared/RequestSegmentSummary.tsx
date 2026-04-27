// =============================================================
// src/components/requests/shared/RequestSegmentSummary.tsx
// Shared UI компонент для отображения segment context DD-запроса.
// Используется ТОЛЬКО в:
// - ReviewRequestSidePanel (review mode)
//
// НЕ используется в legacy mode, потому что DDRequest не имеет segment полей.
//
// Для непрофессионального программиста:
// Это информационный блок, который показывает из какой части документа
// (сегмента) был извлечён этот запрос. Например: "Приложение №1", "Chunk #5"
// =============================================================

import React from "react";
import type { SegmentProvenanceView } from "../../../viewAdapters/requestPresentation";

interface RequestSegmentSummaryProps {
  segment: SegmentProvenanceView;

  /**
   * Callback для перехода к месту в документе (viewer jump).
   * Опционален — если не передан, кнопка перехода не показывается.
   */
  onJumpToViewer?: () => void;

  /**
   * Блокировка viewer jump (например, когда нет document_id).
   */
  viewerJumpDisabled?: boolean;

  /**
   * Текст подсказки, почему viewer jump недоступен.
   */
  viewerJumpDisabledReason?: string;
}

/**
 * Преобразует технический 0-based segment_order в человекочитаемый номер.
 *
 * Для непрофессионального программиста:
 * Внутри системы сегменты часто нумеруются с нуля:
 * 0 = первый, 1 = второй, 2 = третий.
 * Но пользователю понятнее видеть нумерацию с единицы:
 * 1 = первый, 2 = второй, 3 = третий.
 */
function formatSegmentOrder(segmentOrder: number | null): string | null {
  if (segmentOrder == null) return null;
  return `#${segmentOrder + 1}`;
}

/**
 * Отображает информацию о сегменте и chunk для review request.
 * Показывает:
 * - Название сегмента (segment_title)
 * - Тип сегмента (segment_type)
 * - Порядок сегмента (segment_order)
 * - Номер chunk (chunk_index)
 * - Метку "Основной сегмент" если is_primary_segment = true
 * - Кнопку перехода к месту в документе (если доступна)
 */
export const RequestSegmentSummary: React.FC<RequestSegmentSummaryProps> = ({
  segment,
  onJumpToViewer,
  viewerJumpDisabled = false,
  viewerJumpDisabledReason,
}) => {
  const humanSegmentOrder = formatSegmentOrder(segment.segmentOrder);

  /**
   * Показываем кнопку viewer jump, если родитель вообще передал callback.
   * Даже если переход сейчас заблокирован, кнопку лучше оставить видимой,
   * но disabled — так интерфейс более понятный и предсказуемый.
   */
  const showViewerJumpButton = !!onJumpToViewer;

  return (
    <div className="rounded border border-blue-100 bg-blue-50 p-3 space-y-1.5">
      {/* Segment title */}
      {segment.segmentTitle && (
        <div className="flex justify-between text-xs gap-3">
          <span className="text-gray-500 shrink-0">Сегмент</span>
          <span className="text-gray-800 font-medium text-right">
            {segment.segmentTitle}
          </span>
        </div>
      )}

      {/* Segment type */}
      {segment.segmentType && (
        <div className="flex justify-between text-xs gap-3">
          <span className="text-gray-500 shrink-0">Тип сегмента</span>
          <span className="text-gray-700 text-right">{segment.segmentType}</span>
        </div>
      )}

      {/* Segment order */}
      {humanSegmentOrder && (
        <div className="flex justify-between text-xs gap-3">
          <span className="text-gray-500 shrink-0">Порядок</span>
          <span className="text-gray-700">{humanSegmentOrder}</span>
        </div>
      )}

      {/* Chunk index */}
      {segment.chunkIndex != null && (
        <div className="flex justify-between text-xs gap-3">
          <span className="text-gray-500 shrink-0">Chunk</span>
          <span className="text-gray-700 font-mono">#{segment.chunkIndex}</span>
        </div>
      )}

      {/* Primary segment badge */}
      {segment.isPrimarySegment && (
        <div className="mt-1 text-[11px] text-blue-600">
          ✦ Основной сегмент документа
        </div>
      )}

      {/* Viewer jump button */}
      {showViewerJumpButton && (
        <button
          type="button"
          disabled={viewerJumpDisabled}
          title={viewerJumpDisabled ? viewerJumpDisabledReason : "Открыть в документе"}
          className={
            viewerJumpDisabled
              ? "mt-2 w-full text-xs text-gray-400 text-left cursor-not-allowed"
              : "mt-2 w-full text-xs text-blue-700 hover:underline text-left"
          }
          onClick={() => {
            if (viewerJumpDisabled || !onJumpToViewer) return;
            onJumpToViewer();
          }}
        >
          Открыть в документе →
        </button>
      )}

      {/* Viewer jump disabled notice */}
      {viewerJumpDisabled && viewerJumpDisabledReason && (
        <p className="mt-1 text-[10px] text-gray-400 italic">
          {viewerJumpDisabledReason}
        </p>
      )}
    </div>
  );
};

export default RequestSegmentSummary;


