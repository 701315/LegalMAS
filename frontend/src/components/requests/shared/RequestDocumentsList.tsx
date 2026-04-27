// =============================================================
// src/components/requests/shared/RequestDocumentsList.tsx
// Shared UI компонент для отображения списка документов DD-запроса.
// Используется в:
// - RequestSidePanel (legacy) — показывает UUID с опциональными именами
// - ReviewRequestSidePanel (review) — показывает человекочитаемые имена
//
// Для непрофессионального программиста:
// Это список документов с иконкой файла и названием.
// В legacy mode показывает UUID, в review mode — нормальные имена файлов.
// =============================================================

import React from "react";
import type { DocumentView } from "../../../viewAdapters/requestPresentation";

interface RequestDocumentsListProps {
  documents: DocumentView[];
  /**
   * Максимальное количество документов для отображения.
   * Если больше — показываем "... и ещё N"
   */
  maxVisible?: number;
  /**
   * Компактный режим для таблиц (если понадобится).
   */
  compact?: boolean;
}

/**
 * Отображает список документов запроса.
 * Поддерживает оба режима:
 * - Legacy: document.id есть, document.name = UUID → показываем UUID
 * - Review: document.id = null, document.name = имя файла → показываем имя
 */
export const RequestDocumentsList: React.FC<RequestDocumentsListProps> = ({
  documents,
  maxVisible = 10,
  compact = false,
}) => {
  if (documents.length === 0) {
    return (
      <div className="text-xs text-gray-300 py-2">
        Документы не указаны
      </div>
    );
  }

  const visibleDocuments = documents.slice(0, maxVisible);
  const remainingCount = documents.length - maxVisible;

  return (
    <div className={`space-y-1 ${compact ? "max-h-32" : "max-h-48"} overflow-y-auto`}>
      {visibleDocuments.map((doc, index) => {
        const displayName = doc.name;
        // Если есть rawId и он отличается от name — это legacy UUID,
        // показываем его в title для копирования
        const hasRawId = doc.rawId && doc.rawId !== doc.name;

        return (
          <div
            key={doc.id ?? doc.rawId ?? index}
            className={`flex items-center gap-2 ${
              compact ? "p-1.5" : "p-2"
            } bg-gray-50 rounded`}
            title={hasRawId ? doc.rawId || undefined : undefined}
          >
            <span className="text-gray-400 shrink-0" aria-hidden="true">
              📄
            </span>
            <span className={`truncate ${compact ? "text-xs" : "text-sm"} text-gray-700`}>
              {displayName}
            </span>
          </div>
        );
      })}

      {remainingCount > 0 && (
        <p className="text-xs text-gray-400 py-1 text-center">
          … и ещё {remainingCount}
        </p>
      )}
    </div>
  );
};

export default RequestDocumentsList;


