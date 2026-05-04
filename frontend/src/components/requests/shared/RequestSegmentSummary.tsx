// =============================================================
// src/components/requests/shared/RequestSegmentSummary.tsx
// Shared UI компонент для отображения segment context DD-запроса.
// =============================================================

import React from "react";
import type { SegmentProvenanceView } from "../../../viewAdapters/requestPresentation";

interface RequestSegmentSummaryProps {
  segment: SegmentProvenanceView;
  onJumpToViewer?: () => void;
  viewerJumpDisabled?: boolean;
  viewerJumpDisabledReason?: string;
}

function formatSegmentOrder(segmentOrder: number | null): string | null {
  if (segmentOrder == null) return null;
  return `#${segmentOrder + 1}`;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const RequestSegmentSummary: React.FC<RequestSegmentSummaryProps> = ({
  segment,
  onJumpToViewer,
  viewerJumpDisabled = false,
  viewerJumpDisabledReason,
}) => {
  const humanSegmentOrder = formatSegmentOrder(segment.segmentOrder);
  const showViewerJumpButton = !!onJumpToViewer;

  return (
    <div className="space-y-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-3">
      {segment.segmentTitle && (
        <div className="flex items-start justify-between gap-3 text-xs">
          <span className="shrink-0 text-[var(--text-muted)]">Сегмент</span>
          <span className="text-right font-medium text-[var(--text-primary)]">
            {segment.segmentTitle}
          </span>
        </div>
      )}

      {segment.segmentType && (
        <div className="flex items-start justify-between gap-3 text-xs">
          <span className="shrink-0 text-[var(--text-muted)]">
            Тип сегмента
          </span>
          <span className="text-right text-[var(--text-secondary)]">
            {segment.segmentType}
          </span>
        </div>
      )}

      {humanSegmentOrder && (
        <div className="flex items-start justify-between gap-3 text-xs">
          <span className="shrink-0 text-[var(--text-muted)]">Порядок</span>
          <span className="text-right text-[var(--text-secondary)]">
            {humanSegmentOrder}
          </span>
        </div>
      )}

      {segment.chunkIndex != null && (
        <div className="flex items-start justify-between gap-3 text-xs">
          <span className="shrink-0 text-[var(--text-muted)]">Chunk</span>
          <span className="font-mono text-right text-[var(--text-secondary)]">
            #{segment.chunkIndex}
          </span>
        </div>
      )}

      {segment.isPrimarySegment && (
        <div className="pt-1">
          <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--accent-primary)_20%,transparent)] bg-[var(--accent-muted)] px-2 py-0.5 text-[11px] font-medium text-[var(--accent-primary)]">
            Основной сегмент документа
          </span>
        </div>
      )}

      {showViewerJumpButton && (
        <button
          type="button"
          disabled={viewerJumpDisabled}
          title={
            viewerJumpDisabled
              ? viewerJumpDisabledReason
              : "Открыть в документе"
          }
          className={cn(
            "mt-2 inline-flex w-full items-center justify-between rounded-lg border px-2.5 py-2 text-xs transition",
            viewerJumpDisabled
              ? "cursor-not-allowed border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-faint)]"
              : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--accent-primary)] hover:bg-[var(--bg-card-hover)]",
          )}
          onClick={() => {
            if (viewerJumpDisabled || !onJumpToViewer) return;
            onJumpToViewer();
          }}
        >
          <span>Открыть в документе</span>
          <span aria-hidden="true">→</span>
        </button>
      )}

      {viewerJumpDisabled && viewerJumpDisabledReason && (
        <p className="text-[10px] italic text-[var(--text-faint)]">
          {viewerJumpDisabledReason}
        </p>
      )}
    </div>
  );
};

export default RequestSegmentSummary;



