import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import {
  dealReviewKeys,
  useRequestResultPresentations,
  useResultPresentationProgress,
} from "../../../api/dealReview";

interface ResultPresentationStatusProps {
  dealId: string;
  runId: string;
  presentationLocale: string;
  canRequest: boolean;
}

function getLocalizedCount(progress: {
  ready: number;
  reviewed: number;
  approved: number;
}): number {
  return progress.ready + progress.reviewed + progress.approved;
}

export const ResultPresentationStatus: React.FC<
  ResultPresentationStatusProps
> = ({
  dealId,
  runId,
  presentationLocale,
}) => {
  const { t } = useTranslation("ddGrid");
  const queryClient = useQueryClient();

  const progressQuery = useResultPresentationProgress(
    dealId,
    runId,
    presentationLocale,
  );

  const requestMutation = useRequestResultPresentations(
    dealId,
    runId,
  );

  const hadActiveWorkRef = React.useRef(false);

  React.useEffect(() => {
    const progress = progressQuery.data;

    if (!progress) {
      return;
    }

    const hasActiveWork =
      progress.pending > 0 || progress.processing > 0;

    if (hasActiveWork) {
      hadActiveWorkRef.current = true;
      return;
    }

    if (!progress.is_complete || !hadActiveWorkRef.current) {
      return;
    }

    hadActiveWorkRef.current = false;

    void queryClient.invalidateQueries({
      queryKey: dealReviewKeys.ddGridV1Base(
        dealId,
        runId,
      ),
    });
  }, [
    dealId,
    progressQuery.data,
    queryClient,
    runId,
  ]);

  if (progressQuery.isLoading) {
    return (
      <div
        className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]"
        role="status"
      >
        <Loader2
          className="h-3.5 w-3.5 animate-spin"
          aria-hidden="true"
        />
        <span>{t("v1Tab.presentations.checking")}</span>
      </div>
    );
  }

  if (progressQuery.isError || !progressQuery.data) {
    return null;
  }

  const progress = progressQuery.data;
  const localizedCount = getLocalizedCount(progress);

  const hasActiveWork =
    progress.pending > 0 || progress.processing > 0;

  const hasFailures = progress.failed > 0;
  const hasStale = progress.stale > 0;
  const hasMissing = progress.missing > 0;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {hasActiveWork ? (
        <div
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-2.5 py-1.5 text-[11px] text-[var(--color-warning-text)]"
          role="status"
        >
          <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
          <span>
            {progress.processing > 0
              ? t("v1Tab.presentations.processing", {
                  completed: localizedCount,
                  total: progress.total,
                })
              : t("v1Tab.presentations.queued", {
                  pending: progress.pending,
                  total: progress.total,
                })}
          </span>
        </div>
      ) : null}

      {!hasActiveWork &&
      progress.total > 0 &&
      !hasMissing &&
      !hasFailures &&
      !hasStale ? (
        <div
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-2.5 py-1.5 text-[11px] text-[var(--color-success-text)]"
          role="status"
        >
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          <span>
            {t("v1Tab.presentations.ready", {
              completed: localizedCount,
              total: progress.total,
            })}
          </span>
        </div>
      ) : null}

      {hasFailures ? (
        <div
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-2.5 py-1.5 text-[11px] text-[var(--color-error-text)]"
          role="status"
        >
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          <span>
            {t("v1Tab.presentations.failed", {
              count: progress.failed,
            })}
          </span>
        </div>
      ) : null}

      {hasStale ? (
        <div
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-2.5 py-1.5 text-[11px] text-[var(--color-warning-text)]"
          role="status"
        >
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          <span>
            {t("v1Tab.presentations.stale", {
              count: progress.stale,
            })}
          </span>
        </div>
      ) : null}

      {/* Manual request button removed: auto-translation handles all cases */}

      {requestMutation.isError ? (
        <div
          className="w-full text-right text-[11px] text-[var(--color-error-text)]"
          role="alert"
        >
          {t("v1Tab.presentations.requestError")}
        </div>
      ) : null}
    </div>
  );
};

export default ResultPresentationStatus;


