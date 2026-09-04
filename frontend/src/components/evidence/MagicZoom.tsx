// =============================================================
// src/components/evidence/MagicZoom.tsx
// =============================================================

import React from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useEvidence } from "../../api/evidence";
import type { EvidenceDetail } from "../../api/evidence";
import type { CheckResult, OpenViewerAtFn, QCStatus } from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import Button from "../ui/Button";

interface MagicZoomProps {
  result: CheckResult;
  onClose: () => void;
  onOpenFull?: (result: CheckResult) => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: Exclude<QCStatus, "pending">,
  ) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

interface EvidenceDetailLike extends EvidenceDetail {
  quote?: string | null;
  page?: number | null;
  clause_uid?: string | null;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function getSnippet(
  evidence: EvidenceDetailLike | undefined,
  result: CheckResult,
  tFn: (key: string) => string,
): string {
  return (
    evidence?.snippet ||
    evidence?.quote ||
    result.value_text ||
    tFn("evidencePanel.noSnippet")
  );
}

function getEvidencePage(evidence: EvidenceDetailLike | undefined): number | undefined {
  return typeof evidence?.page === "number" ? evidence.page : undefined;
}

function getEvidenceClauseUid(
  evidence: EvidenceDetailLike | undefined,
): string | undefined {
  return typeof evidence?.clause_uid === "string" && evidence.clause_uid.trim()
    ? evidence.clause_uid
    : undefined;
}

function formatCreatedAt(value: string | null | undefined, locale: string): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleString(locale);
}

export const MagicZoom: React.FC<MagicZoomProps> = ({
  result,
  onClose,
  onOpenFull,
  onQcChange,
  onOpenAtLocation,
}) => {
  const { t, i18n } = useTranslation("findings");
  const { data: evidence, isLoading, error } = useEvidence(result.id);

  const modalRoot = typeof document !== "undefined" ? document.body : null;
  const modalRef = React.useRef<HTMLDivElement | null>(null);
  const previousFocusedElementRef = React.useRef<HTMLElement | null>(null);
  const titleId = React.useId();

  React.useEffect(() => {
    if (!modalRoot) return;

    previousFocusedElementRef.current = document.activeElement as HTMLElement | null;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      const firstFocusable = modalRef.current?.querySelector<HTMLElement>(
        FOCUSABLE_SELECTOR,
      );
      firstFocusable?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!modalRef.current) return;

      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusableElements = Array.from(
        modalRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => !element.hasAttribute("disabled"));

      if (!focusableElements.length) {
        event.preventDefault();
        return;
      }

      const first = focusableElements[0];
      const last = focusableElements[focusableElements.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (event.shiftKey) {
        if (active === first || !modalRef.current.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusedElementRef.current?.focus();
    };
  }, [modalRoot, onClose]);

  if (!modalRoot) {
    return null;
  }

  const evidenceObj = (evidence ?? undefined) as EvidenceDetailLike | undefined;

  const snippet = getSnippet(evidenceObj, result, t);
  const page = getEvidencePage(evidenceObj);
  const clauseUid = getEvidenceClauseUid(evidenceObj);

  const segmentId = evidenceObj?.segment_id ?? undefined;
  const chunkIndex = evidenceObj?.chunk_index ?? undefined;
  const chunkId = evidenceObj?.chunk_id ?? undefined;

  const triggered = result.conditional_check_triggered;
  const triggerName = result.trigger_name;
  const detector = result.detector_used;
  const qcStatus = result.qc_status;

  const canOpenInDocument =
    !!onOpenAtLocation &&
    !!result.document_id &&
    (page != null ||
      !!clauseUid ||
      !!segmentId ||
      !!chunkId ||
      chunkIndex != null);

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  const handleApprove = () => {
    onQcChange?.(result, "approved");
  };

  const handleReject = () => {
    onQcChange?.(result, "rejected");
  };

  const handleOpenFull = () => {
    onOpenFull?.(result);
  };

  const handleOpenInDocument = () => {
    if (!onOpenAtLocation || !result.document_id) return;

    onOpenAtLocation({
      documentId: result.document_id,
      page,
      clauseUid,
      elementId: undefined,
      segmentId,
      chunkId,
      chunkIndex,
    });
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 py-8"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div
        ref={modalRef}
        className="mt-12 w-full max-w-2xl rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div className="min-w-0 space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              {t("magicZoom.title")}
            </div>

            <h2
              id={titleId}
              className="truncate text-sm font-semibold text-[var(--text-primary)]"
            >
              {result.document_name || t("magicZoom.noName")}
            </h2>

            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-muted)]">
              {result.doc_type && <span>{t("magicZoom.typePrefix", { type: result.doc_type })}</span>}

              {triggered && (
                <span
                  className="inline-flex items-center gap-1 rounded-full border border-[color:color-mix(in_srgb,var(--color-purple)_20%,transparent)] bg-[var(--color-purple-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-purple)]"
                  title={
                    triggerName
                      ? t("magicZoom.conditionalTrigger", { name: triggerName })
                      : t("magicZoom.conditionalGeneric")
                  }
                >
                  ⚡ {triggerName || t("magicZoom.conditionalBadge")}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="flex flex-col items-end gap-1">
              <div className="flex flex-wrap items-center justify-end gap-1">
                <SeverityBadge severity={result.severity} />

                {result.doc_classification_level && (
                  <ClassificationBadge
                    level={result.doc_classification_level}
                    confidence={result.doc_classification_confidence ?? undefined}
                  />
                )}
              </div>

              <span className="text-[11px] text-[var(--text-muted)]">
                {t("magicZoom.resultPrefix", { result: result.result })}
              </span>

              <span className="text-[11px] text-[var(--text-muted)]">
                {t("magicZoom.qcPrefix", { status: qcStatus })}
                {result.qc_by ? ` · ${result.qc_by}` : ""}
              </span>
            </div>

            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              aria-label={t("actions.close", { ns: "common" })}
              className="px-2 py-1 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              ✕
            </Button>
          </div>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              {t("magicZoom.check")}
            </div>

            <div className="mt-0.5 text-sm font-medium text-[var(--text-primary)]">
              {result.check_name}
            </div>

            <div className="mt-1 text-[11px] text-[var(--text-muted)]">
              {detector ? t("magicZoom.sourcePrefix", { source: detector }) : t("magicZoom.sourceFallback")}
            </div>
          </div>

          {isLoading && (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-xs text-[var(--text-muted)]">
              {t("magicZoom.loading")}
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2 text-xs text-[var(--color-error-text)]">
              {t("magicZoom.loadError")}
            </div>
          )}

          {!isLoading && !error && (page || clauseUid || segmentId || chunkIndex != null || chunkId) && (
            <div className="flex flex-wrap gap-2 text-[11px] text-[var(--text-muted)]">
              {page != null && <span>{t("magicZoom.pageLabel", { page })}</span>}
              {clauseUid && <span>{t("magicZoom.clauseLabel", { clause: clauseUid })}</span>}

              {segmentId && (
                <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--accent-primary)_20%,transparent)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                  {t("magicZoom.segmentLabel", { segment: segmentId })}
                </span>
              )}

              {chunkIndex != null && (
                <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--color-gold)_20%,transparent)] bg-[var(--color-gold-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-gold-text)]">
                  {t("magicZoom.chunkNumber", { index: chunkIndex })}
                </span>
              )}

              {!segmentId && chunkId && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                  {t("magicZoom.chunkIdLabel", { id: chunkId })}
                </span>
              )}
            </div>
          )}

          {!isLoading && !error && (
            <div className="max-h-64 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-3 text-xs leading-relaxed text-[var(--text-primary)]">
              {snippet}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-4 border-t border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-3">
          <div className="text-[11px] text-[var(--text-faint)]">
            {result.confidence != null && (
              <>{t("magicZoom.confidencePrefix", { percent: Math.round(result.confidence * 100) })} · </>
            )}
            {t("magicZoom.createdAt", { date: formatCreatedAt(result.created_at, i18n.language) })}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            {onQcChange && (
              <>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleApprove}
                >
                  {t("magicZoom.agreeBtn")}
                </Button>

                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleReject}
                >
                  {t("magicZoom.disagreeBtn")}
                </Button>
              </>
            )}

            {onOpenAtLocation && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleOpenInDocument}
                disabled={!canOpenInDocument}
                title={
                  canOpenInDocument
                    ? t("magicZoom.viewInDocumentTitle")
                    : t("magicZoom.noDataToOpenDoc")
                }
              >
                {t("magicZoom.viewInDocument")}
              </Button>
            )}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClose}
            >
              {t("actions.close", { ns: "common" })}
            </Button>

            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleOpenFull}
              disabled={!onOpenFull}
            >
              {t("magicZoom.openFullBtn")}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    modalRoot,
  );
};

export default MagicZoom;


