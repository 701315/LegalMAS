// =============================================================
// src/components/requests/ReviewRequestSidePanel.tsx
// Read-only side panel для DD-запроса в review-режиме.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDRequestDTO из run-scoped API.
// Поддерживает:
// - segment/chunk provenance (из SegmentProvenanceDTO)
// - viewer jump через onOpenAtLocation
// - document_names (уже имена, не голые ID)
// - structured_values через normalizeStructuredValue
// Не содержит CRUD-операций — это read-only review view.
// =============================================================

import React, { useEffect } from "react";
import { X } from "lucide-react";
import type { DDRequestDTO } from "../../types/dealReview";
import type { OpenViewerAtFn } from "../../types";
import { normalizeStructuredValue } from "../../types/ddRequests";

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

  if (!request) return null;

  // Segment context: есть ли данные для viewer jump
  const hasSegmentContext = !!(
    request.segment_id ||
    request.chunk_id ||
    request.chunk_index != null
  );

  // Viewer jump payload — собирается из segment provenance DTO
  // document_names[0] используется только как отображаемое имя,
  // для viewer jump нужен document_id — его в DDRequestDTO нет.
  // TODO(MR4): запросить у backend добавить document_ids[] в DDRequestDTO
  // рядом с document_names[]. Пока viewer jump недоступен из этой панели.
  const canJumpToViewer = false; // заблокировано до получения document_id в DTO

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
              {request.check_name ?? "Запрос"}
            </h3>
            {request.addressee && (
              <p className="text-xs text-blue-600">→ {request.addressee}</p>
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
          {/* Приоритет */}
          <Field label="Приоритет">
            <PriorityBadge priority={request.priority} />
          </Field>

          {/* Текст запроса */}
          <Field label="Текст запроса">
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {request.text}
            </p>
          </Field>

          {/* Документы — уже имена */}
          {request.document_names.length > 0 && (
            <Field label={`Документы (${request.document_names.length})`}>
              <div className="space-y-1">
                {request.document_names.map((name, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 p-2 bg-gray-50 rounded"
                  >
                    <span className="text-gray-400 shrink-0" aria-hidden>📄</span>
                    <span className="text-sm text-gray-700 truncate">{name}</span>
                  </div>
                ))}
              </div>
            </Field>
          )}

          {/* Типы документов */}
          {request.doc_types.length > 0 && (
            <Field label="Типы документов">
              <div className="flex flex-wrap gap-1">
                {request.doc_types.map((dt, i) => (
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

          {/* Segment provenance */}
          {hasSegmentContext && (
            <Field label="Контекст сегмента">
              <div className="rounded border border-blue-100 bg-blue-50 p-3 space-y-1.5">
                {request.segment_title && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Сегмент</span>
                    <span className="text-gray-800 font-medium text-right">
                      {request.segment_title}
                    </span>
                  </div>
                )}
                {request.segment_type && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Тип сегмента</span>
                    <span className="text-gray-700">{request.segment_type}</span>
                  </div>
                )}
                {request.segment_order != null && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Порядок</span>
                    <span className="text-gray-700">#{request.segment_order}</span>
                  </div>
                )}
                {request.chunk_index != null && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Chunk</span>
                    <span className="text-gray-700 font-mono">
                      #{request.chunk_index}
                    </span>
                  </div>
                )}
                {request.is_primary_segment && (
                  <div className="mt-1 text-[11px] text-blue-600">
                    ✦ Основной сегмент документа
                  </div>
                )}

                {/* Viewer jump — заблокирован до получения document_id */}
                {canJumpToViewer && onOpenAtLocation && (
                  <button
                    type="button"
                    className="mt-2 w-full text-xs text-blue-700 hover:underline text-left"
                    onClick={() => {
                      // Будет реализовано после добавления document_id в DDRequestDTO
                    }}
                  >
                    Открыть в документе →
                  </button>
                )}

                {/* Явная заглушка до MR4 */}
                {!canJumpToViewer && onOpenAtLocation && (
                  <p className="mt-1 text-[10px] text-gray-400 italic">
                    Переход к месту в документе будет доступен
                    после обновления API (document_id в запросе).
                  </p>
                )}
              </div>
            </Field>
          )}

          {/* Проверка */}
          {request.check_id && (
            <Field label="Проверка (check_id)">
              <p className="text-sm text-gray-700 font-mono">{request.check_id}</p>
            </Field>
          )}

          {/* Structured values */}
          {request.structured_values && request.structured_values.length > 0 && (
            <Field
              label={`Извлечённые данные (${request.structured_values.length})`}
            >
              <div className="space-y-1 bg-gray-50 rounded p-2 max-h-48 overflow-y-auto">
                {request.structured_values.map((sv, i) => {
                  const { key, value, format } = normalizeStructuredValue(sv);
                  return (
                    <div
                      key={i}
                      className="flex justify-between gap-2 text-xs py-0.5 border-b border-gray-100 last:border-0"
                    >
                      <span className="text-gray-400 capitalize shrink-0">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className="text-gray-700 font-medium text-right">
                        {value}
                        {format && (
                          <span className="ml-1 text-gray-400 font-normal">
                            ({format})
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
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
// Вспомогательные компоненты
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

function PriorityBadge({ priority }: { priority: string }) {
  if (priority === "critical") {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800">
        Критичный
      </span>
    );
  }
  if (priority === "high") {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-orange-100 text-orange-800">
        Высокий
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-yellow-100 text-yellow-800">
      Средний
    </span>
  );
}

export default ReviewRequestSidePanel;


