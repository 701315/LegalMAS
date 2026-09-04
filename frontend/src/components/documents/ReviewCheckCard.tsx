// src/components/documents/ReviewCheckCard.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, ExternalLink, Table2 } from "lucide-react";
import type { DocumentReviewCheckView } from "./DocumentDetails";
import type { OpenViewerAtFn } from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import Button from "../ui/Button";

interface Props {
  check: DocumentReviewCheckView;
  documentId: string;
  onOpenCell?: (checkId: string, checkName: string) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

export const ReviewCheckCard: React.FC<Props> = ({
  check,
  documentId,
  onOpenCell,
  onOpenAtLocation,
}) => {
  const { t } = useTranslation("documents");
  const [expanded, setExpanded] = React.useState(false);

  const hasSegment = Boolean(check.segmentId || check.segmentTitle);
  const hasEvidence = Boolean(
    check.snippet ||
      check.page != null ||
      check.clauseUid ||
      check.segmentId ||
      check.chunkId ||
      check.chunkIndex != null,
  );

  const handleOpenInDocument = () => {
    if (!onOpenAtLocation) return;

    onOpenAtLocation({
      documentId,
      page: check.page ?? undefined,
      clauseUid: check.clauseUid ?? undefined,
      elementId: undefined,
      segmentId: check.segmentId ?? undefined,
      chunkId: check.chunkId ?? undefined,
      chunkIndex: check.chunkIndex ?? undefined,
    });
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-sm transition-shadow hover:shadow-md">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
              {check.checkName}
            </div>

            {check.result === "unclear" && (
              <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--color-gold)_20%,transparent)] bg-[var(--color-gold-highlight)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-gold-text)]">
                {t("reviewCheckCard.unclear")}
              </span>
            )}
          </div>

          {hasSegment && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-muted)]">
              <span className="truncate">
                {check.segmentTitle || check.segmentType || check.segmentId}
              </span>
              {check.chunkIndex != null && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                  {t("reviewCheckCard.chunkNumber", { index: check.chunkIndex })}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {check.severity && <SeverityBadge severity={check.severity} />}

          <span
            className="flex h-6 w-6 items-center justify-center rounded-full text-[var(--text-faint)]"
            aria-hidden="true"
          >
            {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-[var(--border-subtle)] px-4 py-4">
          {check.snippet && (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
                {t("reviewCheckCard.evidenceSnippet")}
              </div>
              <div className="text-sm italic leading-6 text-[var(--text-secondary)]">
                &ldquo;{check.snippet}&rdquo;
              </div>
            </div>
          )}

          {(check.page != null || check.clauseUid) && (
            <div className="flex flex-wrap gap-2">
              {check.page != null && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
                  {t("reviewCheckCard.pageLabel", { page: check.page })}
                </span>
              )}

              {check.clauseUid && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
                  {t("reviewCheckCard.clauseLabel", { clause: check.clauseUid })}
                </span>
              )}
            </div>
          )}

          {hasSegment && (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-3">
              <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
                {t("reviewCheckCard.segmentContext")}
              </div>

              <div className="space-y-1.5 text-xs text-[var(--text-secondary)]">
                {check.segmentTitle && (
                  <div>
                    <span className="text-[var(--text-faint)]">{t("reviewCheckCard.segmentLabel")}</span>
                    {check.segmentTitle}
                    {check.isPrimarySegment && (
                      <span className="ml-1.5 font-medium text-[var(--accent-primary)]">
                        {t("reviewCheckCard.primaryLabel")}
                      </span>
                    )}
                  </div>
                )}

                {check.segmentType && (
                  <div>
                    <span className="text-[var(--text-faint)]">{t("reviewCheckCard.typeLabel")}</span>
                    {check.segmentType}
                  </div>
                )}

                {check.chunkIndex != null && (
                  <div>
                    <span className="text-[var(--text-faint)]">{t("reviewCheckCard.chunkIndexLabel")}</span>
                    {check.chunkIndex}
                  </div>
                )}
              </div>
            </div>
          )}

          {check.extractedFields.length > 0 && (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-3">
              <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[var(--text-faint)]">
                {t("reviewCheckCard.extractedFields")}
              </div>

              <div className="space-y-2">
                {check.extractedFields.map((field, index) => (
                  <div
                    key={`${field.fieldName}-${index}`}
                    className="flex items-start justify-between gap-3 text-xs"
                  >
                    <span className="text-[var(--text-muted)]">
                      {field.fieldName}
                    </span>
                    <span className="max-w-[60%] break-words text-right font-medium text-[var(--text-primary)]">
                      {field.fieldValue}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            {onOpenCell && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => onOpenCell(check.checkId, check.checkName)}
                className="gap-1.5"
              >
                <Table2 size={14} />
                {t("reviewCheckCard.detailsInMatrix")}
              </Button>
            )}

            {onOpenAtLocation && hasEvidence && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleOpenInDocument}
                className="gap-1.5 text-[var(--accent-primary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--accent-primary)]"
              >
                <ExternalLink size={14} />
                {t("reviewCheckCard.openInDocument")}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};


