// =============================================================
// src/components/requests/shared/RequestSegmentSummary.tsx
// Shared UI компонент для отображения segment context DD-запроса.
// =============================================================

import React from "react";
import { ExternalLink } from "lucide-react";
import type { SegmentProvenanceView } from "../../../viewAdapters/requestPresentation";
import Button from "../../ui/Button";

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

export const RequestSegmentSummary: React.FC<RequestSegmentSummaryProps> = ({
  segment,
  onJumpToViewer,
  viewerJumpDisabled = false,
  viewerJumpDisabledReason,
}) => {
  const humanSegmentOrder = formatSegmentOrder(segment.segmentOrder);
  const showViewerJumpButton = !!onJumpToViewer;

  return (
    <section className="space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            Контекст сегмента
          </p>
          {segment.segmentTitle && (
            <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {segment.segmentTitle}
            </p>
          )}
        </div>

        {segment.isPrimarySegment && (
          <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_oklab,var(--accent-primary)_20%,transparent)] bg-[var(--bg-card)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--accent-primary)]">
            Основной сегмент
          </span>
        )}
      </header>

      <div className="space-y-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2.5 text-[12px]">
        {segment.segmentType && (
          <Row label="Тип сегмента">
            <span className="text-[var(--text-secondary)]">
              {segment.segmentType}
            </span>
          </Row>
        )}

        {humanSegmentOrder && (
          <Row label="Порядок">
            <span className="text-[var(--text-secondary)]">
              {humanSegmentOrder}
            </span>
          </Row>
        )}

        {segment.chunkIndex != null && (
          <Row label="Chunk">
            <span className="font-mono text-[var(--text-secondary)]">
              #{segment.chunkIndex}
            </span>
          </Row>
        )}
      </div>

      {showViewerJumpButton && (
        <div className="space-y-1.5">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              if (viewerJumpDisabled || !onJumpToViewer) return;
              onJumpToViewer();
            }}
            disabled={viewerJumpDisabled}
            leftIcon={<ExternalLink className="h-4 w-4" />}
            className="w-full justify-center"
          >
            Открыть в viewer
          </Button>

          {viewerJumpDisabled && viewerJumpDisabledReason && (
            <p className="text-[11px] leading-5 text-[var(--text-muted)]">
              {viewerJumpDisabledReason}
            </p>
          )}
        </div>
      )}
    </section>
  );
};

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div className="flex items-start justify-between gap-3">
    <span className="shrink-0 text-[var(--text-muted)]">{label}</span>
    <div className="min-w-0 text-right">{children}</div>
  </div>
);

export default RequestSegmentSummary;


