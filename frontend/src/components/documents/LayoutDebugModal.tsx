// =============================================================
// src/components/documents/LayoutDebugModal.tsx
// Простая модалка для просмотра raw/sanitized layout JSON.
// =============================================================

import React from "react";
import { X, Loader2, AlertTriangle } from "lucide-react";
import { useDocumentLayoutsDebug } from "../../api/documents";

interface Props {
  docId: string;
  isOpen: boolean;
  onClose: () => void;
}

export const LayoutDebugModal: React.FC<Props> = ({
  docId,
  isOpen,
  onClose,
}) => {
  const { data, isLoading, error } = useDocumentLayoutsDebug(
    isOpen ? docId : null,
    isOpen,
  );

  if (!isOpen) return null;

  const pretty = (obj: unknown) =>
    obj ? JSON.stringify(obj, null, 2) : "// нет данных";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] flex flex-col">
        {/* header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              Debug: текстовый макет документа
            </h2>
            <p className="text-xs text-gray-500">
              Raw vs sanitized layout для документа {docId}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 text-gray-500"
          >
            <X size={16} />
          </button>
        </div>

        {/* body */}
        <div className="flex-1 p-4 overflow-hidden">
          {isLoading && (
            <div className="h-full flex items-center justify-center text-gray-400 text-sm">
              <Loader2 className="animate-spin mr-2" size={18} />
              Загрузка layout JSON…
            </div>
          )}

          {error && !isLoading && (
            <div className="h-full flex flex-col items-center justify-center text-center text-xs text-red-700">
              <AlertTriangle size={18} className="mb-1 text-red-500" />
              <p>Ошибка загрузки debug‑layout'а</p>
              <p className="mt-1 text-[11px] text-gray-500 break-words">
                {(error as Error).message ?? "Неизвестная ошибка"}
              </p>
            </div>
          )}

          {!isLoading && !error && data && (
            <div className="grid grid-cols-2 gap-4 h-full">
              {/* raw */}
              <div className="flex flex-col min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-700">
                    Raw layout (после extract)
                  </span>
                  <span className="text-[11px] text-gray-400">
                    ref: {data.raw_layout_ref || "—"}
                  </span>
                </div>
                <div className="flex-1 border rounded bg-gray-50 overflow-auto text-xs">
                  <pre className="p-2 whitespace-pre text-[11px] leading-snug">
                    {pretty(data.raw_layout)}
                  </pre>
                </div>
              </div>

              {/* sanitized */}
              <div className="flex flex-col min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-700">
                    Sanitized layout (после PII)
                  </span>
                  <span className="text-[11px] text-gray-400">
                    ref: {data.sanitized_layout_ref || "—"}
                  </span>
                </div>
                <div className="flex-1 border rounded bg-gray-50 overflow-auto text-xs">
                  <pre className="p-2 whitespace-pre text-[11px] leading-snug">
                    {pretty(data.sanitized_layout)}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {!isLoading && !error && !data && (
            <div className="h-full flex items-center justify-center text-xs text-gray-500">
              Нет данных debug‑layout'а для этого документа.
            </div>
          )}
        </div>

        {/* footer */}
        <div className="px-4 py-2 border-t flex justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded border text-gray-700 hover:bg-gray-50"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default LayoutDebugModal;
