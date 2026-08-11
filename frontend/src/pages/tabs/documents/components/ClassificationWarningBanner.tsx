// =============================================================
// src/pages/tabs/documents/components/ClassificationWarningBanner.tsx
// =============================================================

import React from "react";
import type { DocumentListItem } from "../../../../types";
import { ClassificationBadge } from "../../../../components/ui/ClassificationBadge";

interface ClassificationWarningBannerProps {
  count: number;
  docs: DocumentListItem[];
  isExpanded: boolean;
  onToggle: () => void;
  onSelectDoc: (id: string) => void;
}

const ClassificationWarningBanner: React.FC<
  ClassificationWarningBannerProps
> = ({ count, docs, isExpanded, onToggle, onSelectDoc }) => (
  <div className="border-b border-[var(--border-subtle)]">
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center justify-between gap-3 px-5 py-2 text-left transition hover:bg-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-warning-bg)] text-[10px] font-semibold text-[var(--color-warning-text)]">
          {count}
        </span>
        <span className="text-xs font-medium text-[var(--color-warning-text)]">
          Требуют проверки классификации
        </span>
      </div>
      <span className="text-[11px] text-[var(--text-muted)]">
        {isExpanded ? "Скрыть ▲" : "Показать ▼"}
      </span>
    </button>

    {isExpanded && (
      <div className="border-t border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-5 py-2">
        <div className="max-h-48 space-y-0.5 overflow-y-auto">
          {docs.map((doc) => (
            <button
              key={doc.id}
              type="button"
              onClick={() => onSelectDoc(doc.id)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-[var(--text-primary)]">
                  {doc.filename}
                </p>
                <p className="truncate text-[11px] text-[var(--text-muted)]">
                  {doc.doc_type || "Тип не определён"}
                </p>
              </div>
              <ClassificationBadge
                level={doc.classification_level}
                confidence={doc.classification_confidence}
                showConfidence={false}
                className="shrink-0"
              />
            </button>
          ))}
        </div>
      </div>
    )}
  </div>
);

export default ClassificationWarningBanner;


