// =============================================================
// src/components/requests/shared/RequestDocumentsList.tsx
// Shared UI компонент для отображения списка документов DD-запроса.
// =============================================================

import React from "react";
import type { DocumentView } from "../../../viewAdapters/requestPresentation";

interface RequestDocumentsListProps {
  documents: DocumentView[];
  maxVisible?: number;
  compact?: boolean;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/**
 * Отображает список документов запроса.
 */
export const RequestDocumentsList: React.FC<RequestDocumentsListProps> = ({
  documents,
  maxVisible = 10,
  compact = false,
}) => {
  if (documents.length === 0) {
    return (
      <div className="py-2 text-xs text-[var(--text-faint)]">
        Документы не указаны
      </div>
    );
  }

  const visibleDocuments = documents.slice(0, maxVisible);
  const remainingCount = documents.length - maxVisible;

  return (
    <div
      className={cn(
        "space-y-1 overflow-y-auto",
        compact ? "max-h-32" : "max-h-48",
      )}
    >
      {visibleDocuments.map((doc, index) => {
        const displayName = doc.name;
        const hasRawId = doc.rawId && doc.rawId !== doc.name;

        return (
          <div
            key={doc.id ?? doc.rawId ?? index}
            className={cn(
              "flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]",
              compact ? "px-2 py-1.5" : "px-2.5 py-2",
            )}
            title={hasRawId ? doc.rawId || undefined : undefined}
          >
            <span
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--bg-card)] text-[11px] text-[var(--text-muted)]"
              aria-hidden="true"
            >
              📄
            </span>

            <span
              className={cn(
                "truncate text-[var(--text-primary)]",
                compact ? "text-xs" : "text-sm",
              )}
            >
              {displayName}
            </span>
          </div>
        );
      })}

      {remainingCount > 0 && (
        <p className="py-1 text-center text-xs text-[var(--text-muted)]">
          … и ещё {remainingCount}
        </p>
      )}
    </div>
  );
};

export default RequestDocumentsList;

