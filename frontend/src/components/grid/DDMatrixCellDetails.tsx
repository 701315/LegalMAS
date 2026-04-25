// =============================================================
// src/components/grid/DDMatrixCellDetails.tsx
// Side panel с подробностями по ячейке DD Matrix.
// Используется только в review-режиме поверх dd-matrix DTO.
// =============================================================

import React from "react";
import type {
  SeverityLevel,
  OpenViewerAtPayload,
  CheckResult,
} from "../../types";

export interface MatrixCellDetailsCell {
  result: CheckResult["result"] | string;
  severity: SeverityLevel | null;
  snippet: string | null;
  page: number | null;
  clauseUid: string | null;
  confidence: number | null;
  qcStatus: CheckResult["qc_status"] | null;
  conditionalTriggered: boolean;
  triggerName: string | null;

  // segment/chunk provenance
  segmentId?: string | null;
  segmentTitle?: string | null;
  segmentType?: string | null;
  segmentOrder?: number | null;
  isPrimarySegment?: boolean | null;
  chunkId?: string | null;
  chunkIndex?: number | null;

  extractedFields: Array<{
    fieldName: string;
    fieldValue: string;
    fieldFormat?: string | null;
    fieldSource?: string | null;
  }>;
}

export interface MatrixCellDetailsProps {
  open: boolean;
  onClose: () => void;

  documentName: string | null;
  documentId: string | null;

  checkName: string | null;
  checkId: string | null;

  cell: MatrixCellDetailsCell | null;

  onOpenInViewer?: (payload: OpenViewerAtPayload) => void;
}

function getHumanResultText(
  result: string,
  severity: SeverityLevel | null,
): string {
  if (result === "fail") {
    if (severity === "critical") return "Найдено критичное несоответствие";
    if (severity === "high") return "Найдено существенное несоответствие";
    if (severity === "medium") return "Найдено несоответствие";
    return "Найдено несоответствие";
  }

  if (result === "unclear") {
    return "Требует внимания юриста";
  }

  if (result === "pass") {
    return "Несоответствий не найдено";
  }

  return "Неизвестный статус";
}

function getConfidenceText(confidence: number | null): string {
  return typeof confidence === "number"
    ? `${Math.round(confidence * 100)}%`
    : "—";
}

function getSegmentHeading(cell: MatrixCellDetailsCell): string {
  if (cell.segmentTitle && cell.segmentTitle.trim()) {
    return cell.segmentTitle.trim();
  }
  if (cell.segmentType && cell.segmentType.trim()) {
    return cell.segmentType.trim();
  }
  if (cell.segmentId && cell.segmentId.trim()) {
    return cell.segmentId.trim();
  }
  return "Документ целиком";
}

function getSegmentMeta(cell: MatrixCellDetailsCell): string | null {
  const parts: string[] = [];

  if (cell.segmentType && cell.segmentTitle) {
    parts.push(cell.segmentType);
  }

  if (cell.segmentOrder !== null && cell.segmentOrder !== undefined) {
    parts.push(`Порядок: ${cell.segmentOrder}`);
  }

  return parts.length ? parts.join(" · ") : null;
}

export const DDMatrixCellDetails: React.FC<MatrixCellDetailsProps> = ({
  open,
  onClose,
  documentName,
  documentId,
  checkName,
  checkId,
  cell,
  onOpenInViewer,
}) => {
  if (!open || !cell || !documentId) {
    return null;
  }

  const titleId = "dd-matrix-cell-details-title";

  const handleOpenInViewer = () => {
    if (!onOpenInViewer || !documentId) return;

    onOpenInViewer({
      documentId,
      page: cell.page ?? null,
      clauseUid: cell.clauseUid ?? null,
      elementId: null,
      segmentId: cell.segmentId ?? null,
      chunkId: cell.chunkId ?? null,
      chunkIndex: cell.chunkIndex ?? null,
    });
  };

  const confidenceText = getConfidenceText(cell.confidence);
  const humanResultText = getHumanResultText(cell.result, cell.severity);
  const segmentHeading = getSegmentHeading(cell);
  const segmentMeta = getSegmentMeta(cell);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/30"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div
        className="flex h-full w-full max-w-xl flex-col bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4">
          <div className="space-y-1">
            <div className="text-xs uppercase tracking-wide text-gray-400">
              Проверка
            </div>
            <h3 id={titleId} className="text-base font-semibold text-gray-900">
              {checkName || checkId || "Без названия проверки"}
            </h3>
            <p className="text-xs text-gray-500">
              Документ:{" "}
              <span className="font-medium text-gray-800">
                {documentName || documentId}
              </span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-gray-200 px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-50"
              aria-label="Закрыть панель"
              title="Закрыть"
            >
              ✕
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
            >
              Закрыть
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {/* Result summary */}
          <section className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Результат
            </h4>

            <div className="space-y-1 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800">
              <div>
                <span className="text-gray-500">Статус:</span>{" "}
                <span className="font-semibold text-gray-900">
                  {humanResultText}
                </span>
                <span className="ml-1 text-[10px] text-gray-400">
                  ({cell.result})
                </span>
              </div>

              <div>
                <span className="text-gray-500">Severity:</span>{" "}
                <span className="font-medium text-gray-900">
                  {cell.severity || "—"}
                </span>
              </div>

              <div>
                <span className="text-gray-500">QC статус:</span>{" "}
                <span className="font-medium text-gray-900">
                  {cell.qcStatus || "—"}
                </span>
              </div>

              <div>
                <span className="text-gray-500">Confidence:</span>{" "}
                <span className="font-medium text-gray-900">
                  {confidenceText}
                </span>
              </div>

              {cell.conditionalTriggered && (
                <div>
                  <span className="text-gray-500">Trigger:</span>{" "}
                  <span className="font-medium text-gray-900">
                    {cell.triggerName || "Conditional check triggered"}
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* Evidence snippet */}
          <section className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Evidence
            </h4>

            <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-3 text-xs text-gray-800">
              {cell.snippet ? (
                <p className="leading-5 text-gray-900">{cell.snippet}</p>
              ) : (
                <p className="text-gray-400">Evidence snippet отсутствует.</p>
              )}

              <div className="flex flex-wrap gap-3 text-[11px] text-gray-500">
                <span>Страница: {cell.page ?? "—"}</span>
                <span>Clause UID: {cell.clauseUid || "—"}</span>
              </div>
            </div>
          </section>

          {/* Segment / Chunk provenance */}
          {(cell.segmentId ||
            cell.segmentTitle ||
            cell.segmentType ||
            cell.chunkIndex != null) && (
            <section className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Segment / Chunk
              </h4>

              <div className="space-y-1 rounded-lg border border-gray-200 bg-white p-3 text-[11px] text-gray-800">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-gray-900">
                    {segmentHeading}
                  </span>

                  {cell.isPrimarySegment && (
                    <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                      Основной сегмент
                    </span>
                  )}
                </div>

                {segmentMeta && (
                  <p className="text-[10px] text-gray-500">{segmentMeta}</p>
                )}

                {cell.segmentId && (
                  <p className="text-[10px] text-gray-400">
                    segment_id: {cell.segmentId}
                  </p>
                )}

                {cell.chunkIndex != null && (
                  <p className="text-[10px] text-gray-500">
                    Chunk #{cell.chunkIndex}
                  </p>
                )}
              </div>
            </section>
          )}

          {/* Extracted fields */}
          <section className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Извлечённые поля
            </h4>

            <div className="space-y-1 rounded-lg border border-gray-200 bg-white p-3 text-xs text-gray-800">
              {cell.extractedFields.length === 0 ? (
                <p className="text-gray-400">Извлечённые значения отсутствуют.</p>
              ) : (
                cell.extractedFields.map((f, idx) => (
                  <div
                    key={`${f.fieldName}-${idx}`}
                    className="flex items-start justify-between gap-3 border-b border-gray-100 pb-2 last:border-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <div className="text-[11px] font-medium text-gray-700">
                        {f.fieldName}
                      </div>

                      {f.fieldFormat && (
                        <div className="text-[10px] text-gray-400">
                          {f.fieldFormat}
                        </div>
                      )}

                      {f.fieldSource && (
                        <div className="text-[10px] text-gray-400">
                          {f.fieldSource}
                        </div>
                      )}
                    </div>

                    <div className="max-w-[55%] break-words text-right text-[11px] font-semibold text-gray-900">
                      {f.fieldValue}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-5 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] text-gray-400">
              Открыть документ в контексте evidence.
            </div>

            <button
              type="button"
              onClick={handleOpenInViewer}
              className="inline-flex items-center rounded-md bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              Открыть в документе
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DDMatrixCellDetails;


