// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1Drawer.tsx
// Side-panel drawer со сведениями о проверке и форме ручного QC.
//
// i18n: все UI-строки локализованы через namespace "ddGrid", ключи drawer.*
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink, MapPin, X } from "lucide-react";

import type { OpenViewerAtPayload } from "../../../types";
import type {
  DDGridV1DrawerContentDTO,
  ReviewQcStatus,
} from "../../../types/dealReview";

import Button from "../../../components/ui/Button";
import { useUpdateReviewQc } from "../../../api/qc";

import {
  buildDDGridV1DrawerFieldViews,
  normalizeDDGridV1EvidenceItems,
  resolveDDGridV1DrawerReason,
  resolveDDGridV1Confidence,
  resolveDDGridV1QualityFlags,
  resolveDDGridV1QcAuditInfo,
  resolveDDGridV1PresentationInfo,
  type DDGridV1DrawerFieldView,
  type DDGridV1ReasonSource,
} from "./ddGridV1.drawer";

// -------------------------------------------------------------
// Public types
// -------------------------------------------------------------

export interface DDGridV1DrawerProps {
  open: boolean;
  onClose: () => void;

  runId: string | null;
  documentId: string | null;
  documentName: string | null;

  drawerContent: DDGridV1DrawerContentDTO | null;

  /** @deprecated QC данные теперь читаются из drawerContent.qc_*. */
  currentQcStatus?: ReviewQcStatus | null;
  currentQcComment?: string | null;

  onOpenInViewer?: (payload: OpenViewerAtPayload) => void;
}

// -------------------------------------------------------------
// Reason source labels translation mapping
// -------------------------------------------------------------

const REASON_SOURCE_KEYS: Record<DDGridV1ReasonSource, string> = {
  reason: "drawer.reasonSources.reason",
  review_message: "drawer.reasonSources.review_message",
  display_text: "drawer.reasonSources.display_text",
  none: "drawer.reasonSources.none",
};

// -------------------------------------------------------------
// Review status labels
// -------------------------------------------------------------

function getReviewStatusLabel(
  status: string | null | undefined,
  tFn: (key: string) => string,
): string | null {
  if (!status || typeof status !== "string" || status.trim().length === 0) {
    return null;
  }

  const normalized = status.trim();

  switch (normalized) {
    case "needs_review":
      return tFn("drawer.reviewStatusLabels.needs_review");
    case "no_issue_detected":
    case "ok":
      return tFn("drawer.reviewStatusLabels.no_issue_detected");
    case "unclear":
      return tFn("drawer.reviewStatusLabels.unclear");
    default:
      return normalized;
  }
}

// -------------------------------------------------------------
// Cell state labels for badges
// -------------------------------------------------------------

function getCellStateLabel(
  state: DDGridV1DrawerFieldView["cellState"],
  tFn: (key: string) => string,
): string {
  switch (state) {
    case "defined":
      return tFn("drawer.cellStateLabels.defined");
    case "not_defined":
      return tFn("drawer.cellStateLabels.not_defined");
    case "not_executed":
      return tFn("drawer.cellStateLabels.not_executed");
    case "error":
      return tFn("drawer.cellStateLabels.error");
    default:
      return state;
  }
}

// -------------------------------------------------------------
// Location helpers
// -------------------------------------------------------------

function getLocationText(
  field: DDGridV1DrawerFieldView,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): string | null {
  const raw = field.raw;
  const parts: string[] = [];

  if (typeof raw.location_page === "number") {
    parts.push(tFn("location.pageAbbr", { page: raw.location_page }));
  }
  if (
    typeof raw.location_clause_ref === "string" &&
    raw.location_clause_ref.trim().length > 0
  ) {
    parts.push(raw.location_clause_ref.trim());
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

function extractPageFromClauseRef(clauseRef: string | null): number | null {
  if (!clauseRef || typeof clauseRef !== "string") return null;

  const patterns = [
    /стр\.?\s*(\d+)/i,
    /страниц[аеы]?\s*(\d+)/i,
    /page\s*(\d+)/i,
    /p\.?\s*(\d+)/i,
  ];

  for (const pattern of patterns) {
    const match = clauseRef.match(pattern);
    if (match && match[1]) {
      const page = parseInt(match[1], 10);
      if (Number.isFinite(page) && page > 0) {
        return page;
      }
    }
  }

  return null;
}

function buildViewerPayload(
  documentId: string,
  field: DDGridV1DrawerFieldView,
): OpenViewerAtPayload {
  const raw = field.raw;

  const explicitPage =
    typeof raw.location_page === "number" ? raw.location_page : undefined;

  const extractedPage = extractPageFromClauseRef(raw.location_clause_ref);

  const page = explicitPage ?? extractedPage ?? undefined;

  const clauseUid =
    typeof raw.location_clause_ref === "string" &&
    raw.location_clause_ref.trim().length > 0
      ? raw.location_clause_ref.trim()
      : undefined;

  return {
    documentId,
    page,
    clauseUid,
    elementId: undefined,
    segmentId: undefined,
    chunkId: undefined,
    chunkIndex: undefined,
  };
}

// -------------------------------------------------------------
// UI helpers
// -------------------------------------------------------------

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {title}
        </h4>
        {subtitle ? (
          <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
            {subtitle}
          </p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function InfoCard({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "subtle";
}) {
  return (
    <div
      className={
        tone === "subtle"
          ? "rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-3"
          : "rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-3 shadow-sm"
      }
    >
      {children}
    </div>
  );
}

/**
 * Pill бейдж — полностью на design tokens.
 */
function Pill({
  children,
  tone = "neutral",
  title,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "muted" | "warning" | "error" | "success";
  title?: string;
}) {
  const toneClass =
    tone === "success"
      ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]"
      : tone === "warning"
        ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]"
        : tone === "error"
          ? "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]"
          : tone === "muted"
            ? "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]"
            : "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)]";

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${toneClass}`}
    >
      {children}
    </span>
  );
}

// -------------------------------------------------------------
// Field row renderer
// -------------------------------------------------------------

const FieldRow: React.FC<{
  field: DDGridV1DrawerFieldView;
  documentId: string;
  onOpenInViewer?: (payload: OpenViewerAtPayload) => void;
}> = ({ field, documentId, onOpenInViewer }) => {
  const { t } = useTranslation("ddGrid"); // 🌟 Убрали неиспользуемый i18n

  const locationText = getLocationText(field, t);
  const availability = field.locationAvailability;
  const confidence = field.raw.location_confidence;

  const canOpen =
    !!onOpenInViewer &&
    (availability === "exact" || availability === "approximate");

  const handleOpen = () => {
    if (!onOpenInViewer) return;
    const payload = buildViewerPayload(documentId, field);
    onOpenInViewer(payload);
  };

  return (
    <div className="border-b border-[var(--border-subtle)] py-3 last:border-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-medium text-[var(--text-muted)]">
            {field.label}
          </div>
          <div className="mt-1 break-words text-sm font-semibold text-[var(--text-primary)]">
            {field.displayText}
          </div>
        </div>

        <Pill
          tone={
            field.cellState === "defined"
              ? "success"
              : field.cellState === "error"
                ? "error"
                : "neutral"
          }
        >
          {getCellStateLabel(field.cellState, t)}
        </Pill>
      </div>

      {locationText || availability !== "unavailable" ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {locationText ? (
            <Pill
              tone={
                availability === "exact"
                  ? "success"
                  : availability === "approximate"
                    ? "warning"
                    : "muted"
              }
              title={
                availability === "exact"
                  ? t("drawer.fieldRow.exactTooltip")
                  : availability === "approximate"
                    ? t("drawer.fieldRow.approximateTooltip")
                    : t("drawer.fieldRow.unavailableTooltip")
              }
            >
              <MapPin className="h-3 w-3" aria-hidden />
              <span>{locationText}</span>
            </Pill>
          ) : null}

          {confidence === "low" && locationText ? (
            <Pill tone="warning" title={t("drawer.fieldRow.lowConfidenceTooltip")}>
              Confidence: low
            </Pill>
          ) : null}

          {confidence === "high" && locationText ? (
            <Pill tone="success" title={t("drawer.fieldRow.highConfidenceTooltip")}>
              Confidence: high
            </Pill>
          ) : null}

          {canOpen ? (
            <button
              type="button"
              onClick={handleOpen}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--accent-primary)] underline decoration-dotted underline-offset-2 hover:decoration-solid focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35"
              title={t("drawer.fieldRow.openInDocumentTooltip")}
            >
              <ExternalLink className="h-3 w-3" aria-hidden />
              <span>{t("drawer.fieldRow.openInDocument")}</span>
            </button>
          ) : null}
        </div>
      ) : null}

      {field.raw.location_fallback_reason ? (
        <p className="mt-1.5 text-[11px] italic text-[var(--text-muted)]">
          {field.raw.location_fallback_reason}
        </p>
      ) : null}
    </div>
  );
};

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGridV1Drawer: React.FC<DDGridV1DrawerProps> = ({
  open,
  onClose,
  runId,
  documentId,
  documentName,
  drawerContent,
  currentQcStatus,
  currentQcComment,
  onOpenInViewer,
}) => {
  const { t, i18n } = useTranslation("ddGrid"); // 🌟 Добавили i18n
  const updateQc = useUpdateReviewQc();

  const [localQcStatus, setLocalQcStatus] = React.useState<ReviewQcStatus>(
    "pending",
  );
  const [localQcComment, setLocalQcComment] = React.useState<string>("");

  React.useEffect(() => {
    const qcFromDrawer = drawerContent?.qc_status ?? null;
    const commentFromDrawer = drawerContent?.qc_comment ?? null;
    setLocalQcStatus(qcFromDrawer ?? currentQcStatus ?? "pending");
    setLocalQcComment(commentFromDrawer ?? currentQcComment ?? "");
  }, [drawerContent, currentQcStatus, currentQcComment]);

  React.useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  const fieldViews = React.useMemo(
    () => buildDDGridV1DrawerFieldViews(drawerContent, t),
    [drawerContent, t],
  );

  const confidence = React.useMemo(
    () => resolveDDGridV1Confidence(drawerContent),
    [drawerContent],
  );

  const qualityFlags = React.useMemo(
    () => resolveDDGridV1QualityFlags(drawerContent, t),
    [drawerContent, t],
  );

  const qcAuditInfo = React.useMemo(
    () => resolveDDGridV1QcAuditInfo(drawerContent, i18n.language),
    [drawerContent, i18n.language],
  );

  const evidenceItems = React.useMemo(
    () => normalizeDDGridV1EvidenceItems(drawerContent),
    [drawerContent],
  );

  const resolvedReason = React.useMemo(
    () => resolveDDGridV1DrawerReason(drawerContent, t),
    [drawerContent, t],
  );

  const presentationInfo = React.useMemo(
    () => resolveDDGridV1PresentationInfo(drawerContent),
    [drawerContent],
  );

  if (!open || !drawerContent || !documentId) {
    return null;
  }

  const checkName = drawerContent.check_name || drawerContent.check_id;
  const drawerTitle = checkName || t("drawer.titleFallback");
  const drawerDescription = documentName
    ? t("drawer.documentLabel", { name: documentName })
    : t("drawer.documentIdLabel", { id: documentId });

  const displayText = drawerContent.display_text?.trim() || null;
  const reviewStatusLabel = getReviewStatusLabel(drawerContent.review_status, t);
  const executionStatus = drawerContent.execution_status?.trim() || null;
  const showExecutionStatus =
    executionStatus !== null && executionStatus !== "SUCCESS";

  const showReason =
    resolvedReason.text !== null &&
    resolvedReason.text.trim() !== (displayText ?? "").trim();

  const savedQcStatus: ReviewQcStatus =
    (drawerContent?.qc_status as ReviewQcStatus | null) ??
    currentQcStatus ??
    "pending";
  const savedQcComment = drawerContent?.qc_comment ?? currentQcComment ?? "";
  const normalizedLocalComment = localQcComment.trim();
  const normalizedSavedComment = savedQcComment.trim();
  const isQcDirty =
    localQcStatus !== savedQcStatus ||
    normalizedLocalComment !== normalizedSavedComment;
  const canSaveQc = isQcDirty && !updateQc.isPending && !!runId;

  const handleSaveQc = async () => {
    if (!runId || !documentId || !canSaveQc) return;
    try {
      await updateQc.mutateAsync({
        finding: {
          run_id: runId,
          document_id: documentId,
          check_id: drawerContent.check_id,
          segment_id: null,
        },
        qc_status: localQcStatus,
        comment: normalizedLocalComment ? normalizedLocalComment : null,
      });
    } catch (error) {
      console.error("Failed to save QC update:", error);
    }
  };

  const handleCancelQc = () => {
    setLocalQcStatus(savedQcStatus);
    setLocalQcComment(savedQcComment);
  };

  return (
    <aside
      role="complementary"
      aria-label={drawerTitle}
      className="flex h-full w-full flex-col"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
            {drawerTitle}
          </h2>
          <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">
            {drawerDescription}
          </p>

          {presentationInfo ? (
            <div className="mt-2">
              <Pill tone={presentationInfo.tone}>
                {t(
                  presentationInfo.labelKey,
                  presentationInfo.interpolation,
                )}
              </Pill>
            </div>
          ) : null}
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label={t("drawer.close")}
          className="px-2 py-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
        >
          <X size={16} />
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-5">
          {/* ── 0. Detection metadata ───────── */}
          {(confidence.formatted || qualityFlags.length > 0) && (
            <div className="flex flex-wrap items-center gap-2">
              {confidence.formatted && confidence.tier && (
                <Pill
                  tone={
                    confidence.tier === "high"
                      ? "success"
                      : confidence.tier === "medium"
                        ? "warning"
                        : "error"
                  }
                  title={t("drawer.confidenceTooltip", { value: confidence.formatted })}
                >
                  {t("drawer.confidenceLabel", { value: confidence.formatted })}
                </Pill>
              )}

              {qualityFlags.map((flag) => (
                <Pill key={flag.key} tone="warning" title={flag.key}>
                  ⚠ {flag.label}
                </Pill>
              ))}
            </div>
          )}

          {/* ── 1. Результат анализа + обоснование ─ */}
          <Section
            title={t("drawer.sections.analysisResult.title")}
            subtitle={t("drawer.sections.analysisResult.subtitle")}
          >
            <InfoCard>
              {displayText ? (
                <div className="text-sm font-semibold leading-6 text-[var(--text-primary)]">
                  {displayText}
                </div>
              ) : (
                <div className="text-xs italic text-[var(--text-faint)]">
                  {drawerContent?.review_status === "no_issue_detected" ||
                  drawerContent?.review_status === "ok"
                    ? t("drawer.fallbacks.noViolations")
                    : drawerContent?.review_status === "unclear"
                      ? t("drawer.fallbacks.unclearResult")
                      : drawerContent?.execution_status === "FAILED" ||
                        drawerContent?.execution_status === "TIMEOUT"
                        ? t("drawer.fallbacks.executionError")
                        : t("drawer.fallbacks.noResultText")}
                </div>
              )}

              {showReason ? (
                <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    {t(REASON_SOURCE_KEYS[resolvedReason.source] || "drawer.reasonSources.reason")}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text-secondary)]">
                    {resolvedReason.text}
                  </p>
                </div>
              ) : null}
            </InfoCard>
          </Section>

          {/* ── 3. Извлечённые поля ────────── */}
          <Section
            title={t("drawer.sections.extractedFields.title")}
            subtitle={t("drawer.sections.extractedFields.subtitle")}
          >
            <InfoCard>
              {fieldViews.length === 0 ? (
                <p className="text-xs italic text-[var(--text-faint)]">
                  {t("drawer.fallbacks.noFields")}
                </p>
              ) : (
                <div>
                  {fieldViews.map((field) => (
                    <FieldRow
                      key={field.key}
                      field={field}
                      documentId={documentId}
                      onOpenInViewer={onOpenInViewer}
                    />
                  ))}
                </div>
              )}
            </InfoCard>
          </Section>

          {/* ── 4. Evidence ────────────────── */}
          {evidenceItems.length > 0 ? (
            <Section
              title={t("drawer.sections.evidence.title")}
              subtitle={t("drawer.sections.evidence.subtitle")}
            >
              <InfoCard tone="subtle">
                <div className="space-y-2">
                  {evidenceItems.map((item, index) => (
                    <div
                      key={`evidence-${index}`}
                      className="border-b border-[var(--border-subtle)] pb-2 text-xs leading-5 text-[var(--text-primary)] last:border-0 last:pb-0"
                    >
                      <p className="whitespace-pre-wrap">{item}</p>
                    </div>
                  ))}
                </div>
              </InfoCard>
            </Section>
          ) : null}

          {/* ── 5. Статус проверки ────────── */}
          {reviewStatusLabel || showExecutionStatus ? (
            <Section
              title={t("drawer.sections.checkStatus.title")}
              subtitle={t("drawer.sections.checkStatus.subtitle")}
            >
              <InfoCard tone="subtle">
                <div className="flex flex-wrap gap-2">
                  {reviewStatusLabel ? (
                    <Pill tone="neutral">{reviewStatusLabel}</Pill>
                  ) : null}

                  {showExecutionStatus ? (
                    <Pill
                      tone={
                        executionStatus === "FAILED" ? "error" : "warning"
                      }
                      title={t("drawer.executionStatusTooltip")}
                    >
                      Execution: {executionStatus}
                    </Pill>
                  ) : null}
                </div>
              </InfoCard>
            </Section>
          ) : null}

          {/* ── 5b. QC Audit Trail ──────────────────── */}
          {qcAuditInfo.hasBeenActioned && (
            <Section
              title={t("drawer.sections.qcHistory.title")}
              subtitle={t("drawer.sections.qcHistory.subtitle")}
            >
              <InfoCard tone="subtle">
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill
                      tone={
                        qcAuditInfo.status === "approved"
                          ? "success"
                          : qcAuditInfo.status === "rejected"
                            ? "error"
                            : "warning"
                      }
                    >
                      {qcAuditInfo.status === "approved"
                        ? t("qc.approved")
                        : qcAuditInfo.status === "rejected"
                          ? t("qc.rejected")
                          : t("qc.needs_review")}
                    </Pill>

                    {qcAuditInfo.by && (
                      <span className="text-[11px] text-[var(--text-muted)]">
                        {qcAuditInfo.by}
                      </span>
                    )}

                    {qcAuditInfo.atFormatted && (
                      <span className="text-[11px] text-[var(--text-muted)]">
                        · {qcAuditInfo.atFormatted}
                      </span>
                    )}
                  </div>

                  {qcAuditInfo.comment && (
                    <p className="whitespace-pre-wrap text-xs leading-5 text-[var(--text-secondary)]">
                      {qcAuditInfo.comment}
                    </p>
                  )}
                </div>
              </InfoCard>
            </Section>
          )}

          {/* ── 6. QC Review ───────────────── */}
          <Section
            title={t("drawer.sections.qcReview.title")}
            subtitle={t("drawer.sections.qcReview.subtitle")}
          >
            <InfoCard>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-[var(--text-primary)]">
                    {t("drawer.qcReviewForm.statusLabel")}
                  </label>
                  <select
                    value={localQcStatus}
                    onChange={(e) =>
                      setLocalQcStatus(e.target.value as ReviewQcStatus)
                    }
                    disabled={updateQc.isPending}
                    className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                    <option value="needs_review">Needs Review</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-[var(--text-primary)]">
                    {t("drawer.qcReviewForm.commentLabel")}
                  </label>
                  <textarea
                    value={localQcComment}
                    onChange={(e) => setLocalQcComment(e.target.value)}
                    disabled={updateQc.isPending}
                    className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60"
                    rows={3}
                    placeholder={t("drawer.qcReviewForm.commentPlaceholder")}
                  />
                </div>

                {isQcDirty ? (
                  <div className="flex gap-2">
                    <Button
                      onClick={handleSaveQc}
                      disabled={!canSaveQc}
                      size="sm"
                      variant="primary"
                    >
                      {updateQc.isPending ? t("drawer.qcReviewForm.saving") : t("drawer.qcReviewForm.save")}
                    </Button>
                    <Button
                      onClick={handleCancelQc}
                      disabled={updateQc.isPending}
                      size="sm"
                      variant="secondary"
                    >
                      {t("drawer.qcReviewForm.cancel")}
                    </Button>
                  </div>
                ) : (
                  <div className="text-xs text-[var(--text-muted)]">
                    {t("drawer.qcReviewForm.noChanges")}
                  </div>
                )}

                {!runId ? (
                  <div className="rounded-lg border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-xs text-[var(--color-warning-text)]">
                    {t("drawer.qcReviewForm.noRunIdWarning")}
                  </div>
                ) : null}

                {updateQc.isError ? (
                  <div className="rounded-lg border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2 text-xs text-[var(--color-error-text)]">
                    {t("drawer.qcReviewForm.saveError")}
                  </div>
                ) : null}
              </div>
            </InfoCard>
          </Section>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] text-[var(--text-muted)]">
            V1 drawer · check_id: {drawerContent.check_id}
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("drawer.close")}
          </Button>
        </div>
      </div>
    </aside>
  );
};

export default DDGridV1Drawer;


