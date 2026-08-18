// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1QcBulkActions.tsx
// Inline toolbar с QC-действиями для выбранных строк DD Grid V1.
// =============================================================

import React from "react";
import { CheckCircle2, RotateCcw, ShieldAlert } from "lucide-react";

import Button from "../../../components/ui/Button";
import { useBulkUpdateReviewQc } from "../../../api/qc";
import type { ReviewQcStatus } from "../../../types/dealReview";

import type { DDGridV1QcCapability } from "./ddGridV1.qc";
import { buildV1QcBulkPayload } from "./ddGridV1.qc";

interface DDGridV1QcBulkActionsProps {
  selectedRowsCount: number;
  selectedFindingsCount: number;
  selectedDrawers: Array<{
    findingId: string;
    rowId: string;
    documentId: string;
    documentName: string;
    segmentId: string | null;
    checkId: string;
    checkName: string;
    qcStatus: string | null;
  }>;
  runId: string;
  capability: DDGridV1QcCapability;
}

const DDGridV1QcBulkActions: React.FC<DDGridV1QcBulkActionsProps> = ({
  selectedRowsCount,
  selectedFindingsCount,
  selectedDrawers,
  runId,
  capability,
}) => {
  const [comment, setComment] = React.useState("");
  const [errorText, setErrorText] = React.useState<string | null>(null);
  const [pendingAction, setPendingAction] =
    React.useState<ReviewQcStatus | null>(null);

  const bulkMutation = useBulkUpdateReviewQc();
  const isBusy = bulkMutation.isPending;

  const handleApply = React.useCallback(
    async (qcStatus: ReviewQcStatus) => {
      setErrorText(null);

      const payload = buildV1QcBulkPayload(
        selectedDrawers,
        runId,
        qcStatus,
        comment,
      );

      if (!payload) {
        setErrorText(
          "Не удалось сформировать QC-запрос для текущей выборки.",
        );
        return;
      }

      try {
        setPendingAction(qcStatus);
        await bulkMutation.mutateAsync(payload);
        setComment("");
      } catch (err) {
        const message =
          err instanceof Error
            ? err.message
            : "Не удалось применить QC-действие.";
        setErrorText(message);
      } finally {
        setPendingAction(null);
      }
    },
    [bulkMutation, comment, runId, selectedDrawers],
  );

  if (!capability.supported) {
    return null;
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            QC: bulk action
          </p>
          <p className="mt-0.5 text-sm text-[var(--text-primary)]">
            Выбрано строк: <strong>{selectedRowsCount}</strong> · findings:{" "}
            <strong>{selectedFindingsCount}</strong>
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            Действие будет применено ко всем findings выбранных строк.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => handleApply("approved")}
            isLoading={isBusy && pendingAction === "approved"}
            disabled={isBusy && pendingAction !== "approved"}
            leftIcon={<CheckCircle2 className="h-4 w-4" />}
          >
            Approve
          </Button>

          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => handleApply("rejected")}
            isLoading={isBusy && pendingAction === "rejected"}
            disabled={isBusy && pendingAction !== "rejected"}
            leftIcon={<ShieldAlert className="h-4 w-4" />}
          >
            Reject
          </Button>

          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => handleApply("needs_review")}
            isLoading={isBusy && pendingAction === "needs_review"}
            disabled={isBusy && pendingAction !== "needs_review"}
            leftIcon={<RotateCcw className="h-4 w-4" />}
          >
            Needs review
          </Button>
        </div>
      </div>

      <div className="mt-3">
        <label
          htmlFor="v1-qc-bulk-comment"
          className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]"
        >
          Комментарий (опционально)
        </label>
        <input
          id="v1-qc-bulk-comment"
          type="text"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          disabled={isBusy}
          maxLength={4000}
          placeholder="Например: проверено вручную, источник — параграф 5.2"
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60"
        />
      </div>

      {errorText ? (
        <div className="mt-3 rounded-lg border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2 text-xs text-[var(--color-error-text)]">
          {errorText}
        </div>
      ) : null}
    </div>
  );
};

export default DDGridV1QcBulkActions;
