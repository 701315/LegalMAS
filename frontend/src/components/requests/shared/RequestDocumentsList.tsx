// =============================================================
// src/components/requests/shared/RequestDocumentsList.tsx
// Shared UI компонент для отображения списка документов DD-запроса.
// =============================================================

import React from "react";
import { FileText } from "lucide-react";
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
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-3">
        <p className="text-[12px] text-[var(--text-muted)]">
          Документы не указаны
        </p>
      </div>
    );
  }

  const visibleDocuments = documents.slice(0, maxVisible);
  const remainingCount = Math.max(0, documents.length - visibleDocuments.length);

  return (
    <div
      className={cn(
        "rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-2",
      )}
    >
      <ul
        role="list"
        className={cn(
          "space-y-1 overflow-y-auto",
          compact ? "max-h-32" : "max-h-48",
        )}
      >
        {visibleDocuments.map((doc, index) => {
          const displayName = doc.name;
          const hasRawId = doc.rawId && doc.rawId !== doc.name;

          return (
            <li key={doc.id ?? doc.rawId ?? index}>
              <div
                className={cn(
                  "flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)]",
                  compact ? "px-2.5 py-2" : "px-3 py-2.5",
                )}
                title={hasRawId ? doc.rawId || undefined : undefined}
              >
                <span
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]"
                  aria-hidden="true"
                >
                  <FileText className="h-3.5 w-3.5" />
                </span>

                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "truncate text-[var(--text-primary)]",
                      compact ? "text-xs" : "text-sm",
                    )}
                  >
                    {displayName}
                  </p>

                  {hasRawId && (
                    <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                      ID: {doc.rawId}
                    </p>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {remainingCount > 0 && (
        <div className="px-2 pt-2">
          <p className="text-center text-[12px] text-[var(--text-muted)]">
            Показано {visibleDocuments.length} из {documents.length} · ещё{" "}
            {remainingCount}
          </p>
        </div>
      )}
    </div>
  );
};

export default RequestDocumentsList;

