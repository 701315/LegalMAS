// =============================================================
// ReviewSection.tsx
// Секция "Результаты проверки" внутри DocumentDetails.
// =============================================================

import React, { useMemo } from "react";
import { ReviewCheckCard } from "../../ReviewCheckCard";
import type {
  DocumentReviewCheckView,
  DocumentReviewView,
} from "../../DocumentDetails";
import type { OpenViewerAtFn } from "../../../../types";

interface ReviewSectionProps {
  documentId: string;
  reviewData: DocumentReviewView | null | undefined;
  resolvedActiveSegmentKey: string | null;
  onOpenReviewCell?: (checkId: string, checkName: string) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

export const ReviewSection: React.FC<ReviewSectionProps> = ({
  documentId,
  reviewData,
  resolvedActiveSegmentKey,
  onOpenReviewCell,
  onOpenAtLocation,
}) => {
  const hasReviewData = !!reviewData && reviewData.checks.length > 0;

  const sortedReviewChecks = useMemo<DocumentReviewCheckView[]>(() => {
    if (!reviewData?.checks?.length) return [];

    const severityRank: Record<string, number> = {
      critical: 0,
      high: 1,
      medium: 2,
      unclear: 3,
      pass: 4,
    };

    return [...reviewData.checks].sort((a, b) => {
      const aRank = severityRank[a.severity ?? a.result] ?? 99;
      const bRank = severityRank[b.severity ?? b.result] ?? 99;
      if (aRank !== bRank) return aRank - bRank;

      const aSeg = a.segmentOrder ?? Number.MAX_SAFE_INTEGER;
      const bSeg = b.segmentOrder ?? Number.MAX_SAFE_INTEGER;
      if (aSeg !== bSeg) return aSeg - bSeg;

      return a.checkName.localeCompare(b.checkName, "ru");
    });
  }, [reviewData]);

  const visibleReviewChecks = resolvedActiveSegmentKey
    ? sortedReviewChecks.filter(
        (check) =>
          (check.segmentId ?? "__whole_document__") ===
          resolvedActiveSegmentKey,
      )
    : sortedReviewChecks;

  if (!reviewData) {
    return null;
  }

  if (!hasReviewData) {
    return (
      <p className="text-xs text-[var(--text-faint)]">
        Для этого документа пока нет review-результатов в DD Matrix.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {reviewData.totalCritical > 0 && (
          <span className="inline-flex items-center rounded-full bg-[var(--badge-error-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--badge-error-fg)]">
            Critical: {reviewData.totalCritical}
          </span>
        )}
        {reviewData.totalHigh > 0 && (
          <span className="inline-flex items-center rounded-full bg-[var(--badge-warning-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--badge-warning-fg)]">
            High: {reviewData.totalHigh}
          </span>
        )}
        {reviewData.totalUnclear > 0 && (
          <span className="inline-flex items-center rounded-full bg-[var(--badge-info-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--badge-info-fg)]">
            Unclear: {reviewData.totalUnclear}
          </span>
        )}
        {reviewData.totalFail > 0 && (
          <span className="inline-flex items-center rounded-full bg-[var(--badge-neutral-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-primary)]">
            Fail: {reviewData.totalFail}
          </span>
        )}
      </div>

      <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
        {visibleReviewChecks.map((check) => (
          <ReviewCheckCard
            key={`${check.checkId}-${check.segmentId ?? "doc"}-${
              check.chunkId ?? "chunk"
            }`}
            check={check}
            documentId={documentId}
            onOpenCell={onOpenReviewCell}
            onOpenAtLocation={onOpenAtLocation}
          />
        ))}
      </div>
    </div>
  );
};

