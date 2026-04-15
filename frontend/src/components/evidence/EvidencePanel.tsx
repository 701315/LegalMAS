// =============================================================
// src/components/evidence/EvidencePanel.tsx
// Полноценная панель доказательств для одного результата проверки.
// Правый сайдбар: контекст документа, фрагмент, QC, флаги качества,
// классификация документа, условная проверка, извлечённые данные.
// =============================================================

import React from "react";

import type {
  CheckResult,
  QCStatus,
  OpenViewerAtFn,
  StructuredField,
} from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { useEvidence } from "../../api/evidence";
import type { EvidenceDetail } from "../../api/evidence";


interface EvidencePanelProps {
  result: CheckResult;
  onClose: () => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: Exclude<QCStatus, "pending">,
  ) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  result,
  onClose,
  onQcChange,
  onOpenAtLocation,
}) => {
  const { data: evidence, isLoading, error } = useEvidence(result.id);

  // evidence уже один объект, а не массив
  const evidenceObj: EvidenceDetail | undefined = evidence ?? undefined;

  const snippet =
    evidenceObj?.quote ||
    evidenceObj?.snippet ||
    result.value_text ||
    "(нет фрагмента текста)";

  const page = evidenceObj?.page;
  const clauseUid = evidenceObj?.clause_uid ?? null;

  const evidenceDetails = evidenceObj?.structured_data ?? undefined;

  const hasEvidenceDetails =
    !!evidenceDetails &&
    typeof evidenceDetails === "object" &&
    Object.keys(evidenceDetails).length > 0;

  const qcStatus = result.qc_status;
  const isPendingQc = qcStatus === "pending";

  const handleApprove = () => {
    onQcChange?.(result, "approved");
  };

  const handleReject = () => {
    onQcChange?.(result, "rejected");
  };

  const handleViewOriginal = () => {
    if (!onOpenAtLocation) return;

    onOpenAtLocation({
      documentId: result.document_id,
      page: evidenceObj?.page ?? null,
      clauseUid: clauseUid ?? null,
      elementId: null,

      segmentId: evidenceObj?.segment_id ?? null,
      chunkId: evidenceObj?.chunk_id ?? null,
      chunkIndex: evidenceObj?.chunk_index ?? null,
    });
  };

  const qualitySummary = React.useMemo(() => {
    // quality_flags: Record<string, boolean> | undefined
    const flags: Record<string, boolean> = result.quality_flags ?? {};
    const active: string[] = [];

    if (flags.structure_degraded) {
      active.push("Структура документа нарушена");
    }
    if (flags.llm_fallback_used) {
      active.push("Использован LLM fallback");
    }
    if (!active.length && Object.keys(flags).length) {
      active.push("Есть технические флаги (см. детали ниже)");
    }
    if (!active.length) {
      return "Флаги качества не установлены.";
    }
    return active.join(" · ");
  }, [result.quality_flags]);

  // Секция "Извлечённые данные": из structured_data CheckResult.
  const structuredEntries: [string, StructuredField][] = React.useMemo(() => {
    if (!result.structured_data || typeof result.structured_data !== "object") {
      return [];
    }
    return Object.entries(result.structured_data) as [
      string,
      StructuredField,
    ][];
  }, [result.structured_data]);

  const hasStructuredData = structuredEntries.length > 0;

  // Простейшая логика статуса по полю: found + confidence.
  const getFieldStatus = (
    field: StructuredField,
  ): "yes" | "no" | "unclear" => {
    const found = field.found ?? true;
    const conf = typeof field.confidence === "number" ? field.confidence : 0;
    if (!found) return "no";
    if (conf >= 0.6) return "yes";
    return "unclear";
  };

  const renderStatusLabel = (field: StructuredField) => {
    const status = getFieldStatus(field);
    if (status === "yes") return "Есть";
    if (status === "no") return "Нет";
    return "Требует уточнения";
  };

  // Человекочитаемый текст для location.
  const renderLocationLabel = (field: StructuredField) => {
    if (!field.location) return "—";
    const { page: locPage, clause_uid } = field.location;
    if (!locPage && !clause_uid) return "Фрагмент";
    if (locPage && clause_uid) return `Стр. ${locPage}, п. ${clause_uid}`;
    if (locPage) return `Стр. ${locPage}`;
    return clause_uid || "Фрагмент";
  };

  // Краткий QC-статус по полю. Пока только текст, без кнопок.
  const renderQcLabel = (field: StructuredField) => {
    const status = field.qc?.status || "pending";
    if (status === "pending") return "pending";
    if (status === "accepted") return "accepted";
    if (status === "rejected") return "rejected";
    if (status === "auto_accepted") return "auto_accepted";
    return status;
  };

  // Открытие viewer на конкретном поле.
  const handleOpenFieldLocation = (field: StructuredField) => {
    if (!field.location || !onOpenAtLocation) return;
    onOpenAtLocation({
      documentId: result.document_id,
      page: field.location.page ?? field.location.start_page ?? null,
      clauseUid: field.location.clause_uid ?? null,
      elementId: field.location.element_id ?? null,

      segmentId: field.location.segment_id ?? null,
      chunkId: field.location.chunk_id ?? null,
      chunkIndex: field.location.chunk_index ?? null,
    });
  };

  // Низкая уверенность классификации
  const isLowConfidence =
    typeof result.doc_classification_confidence === "number" &&
    result.doc_classification_confidence < 0.6;

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-3xl bg-white shadow-xl border-l flex flex-col transform transition-transform duration-200 ease-out translate-x-0">
      {/* Шапка */}
      <div className="flex items-start justify-between gap-4 px-4 py-3 border-b">
        <div className="space-y-1">
          <div className="text-[11px] uppercase text-gray-400">Документ</div>
          <div className="text-xs font-medium text-gray-900">
            {result.document_name || "Без имени"}
          </div>
          <div className="flex items-center gap-2 text-[11px] text-gray-500">
            {result.doc_type && <span>Тип: {result.doc_type}</span>}
            <button
              type="button"
              className="text-blue-600 hover:underline px-0 py-0"
              onClick={handleViewOriginal}
            >
              Просмотреть исходный документ
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-1">
              <SeverityBadge severity={result.severity} />
              {result.conditional_check_triggered && (
                <span
                  className="text-[13px]"
                  title={result.trigger_name || "Conditional check triggered"}
                >
                  ⚡
                </span>
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

      {/* Основное содержимое */}
      <div className="flex-1 grid grid-cols-3 gap-4 px-4 py-3 overflow-hidden">
        {/* Левая колонка: контекст */}
        <div className="col-span-1 border-r pr-4 overflow-y-auto space-y-4">
          {/* Документ */}
          <div>
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              Документ
            </div>
            <div className="text-xs text-gray-800">
              {result.document_name || "Без имени"}
            </div>
            {result.doc_type && (
              <div className="text-[11px] text-gray-500 mt-0.5">
                Тип: {result.doc_type}
              </div>
            )}
          </div>

          {/* Классификация документа */}
          <div>
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              Классификация документа
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-700">
              {result.doc_classification_level ? (
                <ClassificationBadge
                  level={result.doc_classification_level}
                  confidence={result.doc_classification_confidence}
                />
              ) : (
                <span className="text-[11px] text-gray-400">
                  Нет данных классификации
                </span>
              )}
              {isLowConfidence && (
                <span className="px-1.5 py-0.5 rounded bg-yellow-50 text-[11px] text-yellow-700 border border-yellow-200">
                  Низкая уверенность
                </span>
              )}
            </div>
          </div>

          {/* Условная проверка */}
          {result.conditional_check_triggered && (
            <div>
              <div className="text-[11px] uppercase text-gray-400 mb-1">
                Условная проверка
              </div>
              <div className="space-y-1">
                <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 text-[11px]">
                  ⚡ {result.trigger_name || "Условная проверка"}
                </div>
                <div className="text-[11px] text-gray-500">
                  Эта проверка запущена условным правилом
                  {result.trigger_name ? ` «${result.trigger_name}»` : ""}.
                </div>
              </div>
            </div>
          )}

          {/* Проверка */}
          <div>
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              Проверка
            </div>
            <div className="text-xs text-gray-800">{result.check_name}</div>
            {result.detector_used && (
              <div className="text-[11px] text-gray-500 mt-0.5">
                Источник: {result.detector_used}
              </div>
            )}
          </div>

          {/* Метаданные */}
          <div>
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              Метаданные
            </div>
            <div className="text-[11px] text-gray-500 space-y-0.5">
              {result.confidence != null && (
                <div>
                  Уверенность детектора:{" "}
                  {Math.round(result.confidence * 100)}%
                </div>
              )}
              <div>
                Создано:{" "}
                {result.created_at
                  ? new Date(result.created_at).toLocaleString()
                  : "—"}
              </div>
            </div>
          </div>
        </div>

        {/* Средняя колонка: фрагмент + структурированные данные */}
        <div className="col-span-1 flex flex-col gap-3 overflow-hidden">
          {/* Цитата / фрагмент */}
          <div className="flex flex-col">
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              Цитата / фрагмент
            </div>
            {isLoading && (
              <div className="text-xs text-gray-500 py-2">
                Загружаем evidence…
              </div>
            )}
            {error && (
              <div className="text-xs text-red-600 py-2">
                Не удалось загрузить evidence.
              </div>
            )}
            {!isLoading && !error && (
              <>
                {(page || clauseUid) && (
                  <div className="mb-1 text-[11px] text-gray-500 flex gap-3">
                    {page && <span>Стр. {page}</span>}
                    {clauseUid && <span>Clause: {clauseUid}</span>}
                  </div>
                )}
                <div className="border rounded bg-gray-50 p-3 text-xs leading-relaxed max-h-48 overflow-auto">
                  {snippet}
                </div>
              </>
            )}
          </div>

          {/* Извлечённые данные (structured_data) */}
          {hasStructuredData && (
            <div className="flex flex-col flex-1 overflow-hidden">
              <div className="text-[11px] uppercase text-gray-400 mb-1">
                Извлечённые данные
              </div>
              <div className="border rounded overflow-auto max-h-48">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="px-2 py-1 text-left text-gray-500">
                        Поле
                      </th>
                      <th className="px-2 py-1 text-left text-gray-500">
                        Значение
                      </th>
                      <th className="px-2 py-1 text-left text-gray-500">
                        Статус
                      </th>
                      <th className="px-2 py-1 text-left text-gray-500">
                        Источник
                      </th>
                      <th className="px-2 py-1 text-left text-gray-500">
                        Увер.
                      </th>
                      <th className="px-2 py-1 text-left text-gray-500">
                        Фрагмент
                      </th>
                      <th className="px-2 py-1 text-left text-gray-500">
                        QC
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {structuredEntries.map(([key, field]) => {
                      const value =
                        field.value != null ? String(field.value) : "—";
                      const source = field.source || "—";
                      const conf =
                        typeof field.confidence === "number"
                          ? `${Math.round(field.confidence * 100)}%`
                          : "—";
                      const hasLocation = !!field.location;

                      return (
                        <tr key={key} className="border-b last:border-b-0">
                          <td className="px-2 py-1 align-top text-gray-600 bg-gray-50 whitespace-nowrap">
                            {key}
                          </td>
                          <td className="px-2 py-1 align-top text-gray-800">
                            {value}
                          </td>
                          <td className="px-2 py-1 align-top text-gray-700 whitespace-nowrap">
                            {renderStatusLabel(field)}
                          </td>
                          <td className="px-2 py-1 align-top text-gray-700 whitespace-nowrap">
                            {source}
                          </td>
                          <td className="px-2 py-1 align-top text-gray-700 whitespace-nowrap">
                            {conf}
                          </td>
                          <td className="px-2 py-1 align-top whitespace-nowrap">
                            {hasLocation ? (
                              <button
                                type="button"
                                className="text-blue-600 hover:underline"
                                onClick={() =>
                                  handleOpenFieldLocation(field)
                                }
                              >
                                {renderLocationLabel(field)}
                              </button>
                            ) : (
                              <span className="text-gray-400">—</span>
                            )}
                          </td>
                          <td className="px-2 py-1 align-top text-gray-700 whitespace-nowrap">
                            {renderQcLabel(field)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Детали из evidence.structured_data (технические) */}
          {hasEvidenceDetails && (
            <div>
              <div className="text-[11px] uppercase text-gray-400 mb-1">
                Детали проверки
              </div>
              <div className="border rounded bg-white p-2 text-[11px]">
                {result.qc_comment && (
                  <>
                    <div className="mb-1 text-gray-500">
                      Комментарий QC:
                    </div>
                    <div className="text-xs whitespace-pre-wrap mb-2">
                      {result.qc_comment}
                    </div>
                  </>
                )}
                <details>
                  <summary className="cursor-pointer text-blue-600">
                    Показать тех. детали
                  </summary>
                  <pre className="mt-1 text-[10px] bg-gray-50 rounded p-2 overflow-auto">
                    {JSON.stringify(evidenceDetails, null, 2)}
                  </pre>
                </details>
              </div>
            </div>
          )}
        </div>

        {/* Правая колонка: QC и флаги качества */}
        <div className="col-span-1 flex flex-col gap-3 overflow-hidden">
          {/* QC-статус */}
          <div>
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              QC-статус
            </div>
            <div className="text-xs text-gray-800 mb-1">
              {qcStatus}
              {result.qc_by && ` · ${result.qc_by}`}
            </div>
            <div className="text-[11px] text-gray-500 mb-2">
              {isPendingQc
                ? "Требуется QC-решение по этому результату."
                : "QC по этому результату уже выставлен."}
            </div>
            {onQcChange && (
              <div className="flex gap-2 mt-1">
                <button
                  type="button"
                  className="px-3 py-1 rounded border text-xs text-green-700 border-green-300 hover:bg-green-50 disabled:opacity-40"
                  onClick={handleApprove}
                  disabled={!isPendingQc}
                >
                  ✅ Согласен
                </button>
                <button
                  type="button"
                  className="px-3 py-1 rounded border text-xs text-red-700 border-red-300 hover:bg-red-50 disabled:opacity-40"
                  onClick={handleReject}
                  disabled={!isPendingQc}
                >
                  ❌ Не согласен
                </button>
              </div>
            )}
          </div>

          {/* Флаги качества */}
          <div className="flex-1">
            <div className="text-[11px] uppercase text-gray-400 mb-1">
              Флаги качества
            </div>
            <div className="border rounded bg-white p-2 text-[11px] max-h-64 overflow-auto">
              <div className="mb-2 text-gray-700">{qualitySummary}</div>
              {result.quality_flags &&
                Object.keys(result.quality_flags).length > 0 && (
                  <details>
                    <summary className="cursor-pointer text-blue-600">
                      Показать тех. детали
                    </summary>
                    <pre className="mt-1 text-[10px] bg-gray-50 rounded p-2 overflow-auto">
                      {JSON.stringify(result.quality_flags, null, 2)}
                    </pre>
                  </details>
                )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EvidencePanel;

