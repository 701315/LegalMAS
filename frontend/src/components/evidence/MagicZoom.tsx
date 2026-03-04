// =============================================================
// src/components/evidence/MagicZoom.tsx
// Magic Zoom: быстрый просмотр результата проверки для юриста.
// =============================================================

import React from "react";
import { createPortal } from "react-dom";

import type { CheckResult, QCStatus } from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { useEvidence } from "../../api/evidence";

interface MagicZoomProps {
  result: CheckResult;
  onClose: () => void;
  onOpenFull?: (result: CheckResult) => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: Exclude<QCStatus, "pending">,
  ) => void;
}

export const MagicZoom: React.FC<MagicZoomProps> = ({
  result,
  onClose,
  onOpenFull,
  onQcChange,
}) => {
  const { data: evidence, isLoading, error } = useEvidence(result.id);

  const modalRoot = document.body;

  const handleBackdropClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClose();
  };

  const handleContentClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  const handleOpenFull = () => {
    onOpenFull?.(result);
  };

  const handleApprove = () => {
    onQcChange?.(result, "approved");
  };

  const handleReject = () => {
    onQcChange?.(result, "rejected");
  };

  const snippet =
    (evidence as any)?.snippet ||
    (evidence as any)?.quote ||
    result.value_text ||
    "(нет фрагмента текста)";

  const page = (evidence as any)?.page as number | undefined;
  const clauseUid = (evidence as any)?.clause_uid as string | undefined;

  const triggered = result.conditional_check_triggered;
  const triggerName = result.trigger_name;

  const detector = result.detector_used;

  const qcStatus = result.qc_status;

  return createPortal(
    <div
      className="fixed inset-0 z-40 flex items-start justify-center bg-black/40"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="mt-20 w-full max-w-2xl rounded-lg bg-white shadow-lg border p-4 text-sm"
        onClick={handleContentClick}
      >
        {/* Шапка: документ + риск + QC */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="space-y-1">
            <div className="text-[11px] uppercase text-gray-400">Документ</div>
            <div className="text-xs font-medium text-gray-900">
              {result.document_name || "Без имени"}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-gray-500">
              {result.doc_type && <span>Тип: {result.doc_type}</span>}
              {triggered && (
                <span
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200"
                  title={
                    triggerName
                      ? `Условная проверка по триггеру: ${triggerName}`
                      : "Условная проверка (conditional)"
                  }
                >
                  ⚡ {triggerName || "условная"}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-1">
                <SeverityBadge severity={result.severity} />
                {/* Бейдж классификации документа (денормализовано в CheckResult) */}
                {result.doc_classification_level && (
                  <ClassificationBadge
                    level={result.doc_classification_level}
                    confidence={result.doc_classification_confidence}
                  />
                )}
              </div>
              <span className="text-[11px] text-gray-500">
                Результат: {result.result}
              </span>
              <span className="text-[11px] text-gray-500">
                QC: {qcStatus}
                {result.qc_by && ` · ${result.qc_by}`}
              </span>
            </div>
            <button
              type="button"
              className="text-gray-400 hover:text-gray-600 text-lg"
              onClick={onClose}
              aria-label="Закрыть"
            >
              ×
            </button>
          </div>
        </div>

        {/* Информация о проверке */}
        <div className="mb-2">
          <div className="text-[11px] uppercase text-gray-400">Проверка</div>
          <div className="text-xs font-medium text-gray-900">
            {result.check_name}
          </div>
          <div className="text-[11px] text-gray-500 mt-0.5">
            {detector && <>Источник: {detector}</>}
          </div>
        </div>

        {/* Состояние загрузки evidence */}
        {isLoading && (
          <div className="text-xs text-gray-500 py-2">
            Загружаем фрагмент документа…
          </div>
        )}
        {error && (
          <div className="text-xs text-red-600 py-2">
            Не удалось загрузить evidence.
          </div>
        )}

        {/* Метаданные фрагмента */}
        {!isLoading && !error && (page || clauseUid) && (
          <div className="mb-1 text-[11px] text-gray-500 flex gap-3">
            {page && <span>Стр. {page}</span>}
            {clauseUid && <span>Clause: {clauseUid}</span>}
          </div>
        )}

        {/* Фрагмент / цитата */}
        {!isLoading && !error && (
          <div className="mt-1 border rounded bg-gray-50 p-3 text-xs leading-relaxed max-h-64 overflow-auto">
            {snippet}
          </div>
        )}

        {/* Нижняя панель действий */}
        <div className="mt-4 flex justify-between items-center">
          <div className="text-[11px] text-gray-400">
            {result.confidence != null && (
              <>Уверенность: {Math.round(result.confidence * 100)}% · </>
            )}
            Создано:{" "}
            {result.created_at
              ? new Date(result.created_at).toLocaleString()
              : "—"}
          </div>
          <div className="flex gap-2">
            {onQcChange && (
              <>
                <button
                  type="button"
                  className="px-3 py-1 rounded border text-xs text-green-700 border-green-300 hover:bg-green-50"
                  onClick={handleApprove}
                >
                  ✅ Согласен
                </button>
                <button
                  type="button"
                  className="px-3 py-1 rounded border text-xs text-red-700 border-red-300 hover:bg-red-50"
                  onClick={handleReject}
                >
                  ❌ Не согласен
                </button>
              </>
            )}
            <button
              type="button"
              className="px-3 py-1 rounded border text-xs text-gray-700 hover:bg-gray-50"
              onClick={onClose}
            >
              Закрыть
            </button>
            <button
              type="button"
              className="px-3 py-1 rounded bg-blue-600 text-white text-xs hover:bg-blue-700"
              onClick={handleOpenFull}
            >
              Открыть полностью
            </button>
          </div>
        </div>
      </div>
    </div>,
    modalRoot,
  );
};

export default MagicZoom;
