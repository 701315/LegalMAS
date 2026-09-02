// =============================================================
// ReviewSection.tsx
// =============================================================

import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
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
  const { t, i18n } = useTranslation("documents");
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

      return a.checkName.localeCompare(b.checkName, i18n.language);
    });
  }, [reviewData, i18n.language]);

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
        {t("reviewSection.emptyMessage")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {reviewData.totalCritical > 0 && (
          <span className="inline-flex items-center rounded-full border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-error-text)]">
            {t("reviewSection.badges.critical", { count: reviewData.totalCritical })}
          </span>
        )}
        {reviewData.totalHigh > 0 && (
          <span className="inline-flex items-center rounded-full border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-warning-text)]">
            {t("reviewSection.badges.high", { count: reviewData.totalHigh })}
          </span>
        )}
        {reviewData.totalUnclear > 0 && (
          <span className="inline-flex items-center rounded-full border border-[var(--color-blue)]/20 bg-[var(--color-blue-highlight)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-blue)]">
            {t("reviewSection.badges.unclear", { count: reviewData.totalUnclear })}
          </span>
        )}
        {reviewData.totalFail > 0 && (
          <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-primary)]">
            {t("reviewSection.badges.fail", { count: reviewData.totalFail })}
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


