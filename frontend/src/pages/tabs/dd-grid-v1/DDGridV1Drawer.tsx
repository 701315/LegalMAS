// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1Drawer.tsx
// V1-specific drawer для DD Grid.
//
// Отличия от базового Drawer компонента:
// - НЕ использует модальный backdrop (без blur, без затемнения)
// - Работает как side panel: таблица остаётся видимой и интерактивной
// - Клик вне drawer не закрывает его — только явные действия
//
// Содержимое (порядок):
// 1. Заголовок: check name + document name
// 2. Секция "Результат анализа" — display_text (canonical result)
// 3. Секция "Обоснование" — resolved reason с меткой источника
// 4. Секция "Извлечённые поля" — все runtime fields как список
//    "Label: value" с бейджами cell_state, location availability,
//    location confidence, и кнопкой "Открыть в документе"
// 5. Секция "Evidence" — нормализованные evidence items
// 6. Секция "Workflow" — review_status label + execution_status
//    (только если execution_status != "SUCCESS")
// 7. Секция "QC Review" — полный блок редактирования QC status/comment
//
// Правила:
// - source of truth — DDGridV1DrawerContentDTO из V1 модели;
// - никаких хардкодов check_id / column_id;
// - все view-модели строятся через ddGridV1.drawer helpers;
// - QC editing работает через тот же useUpdateReviewQc mutation, что
//   и legacy drawer, чтобы не дублировать backend integration.
// =============================================================

import React from "react";
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

  /** Drawer content напрямую из V1 модели. */
  drawerContent: DDGridV1DrawerContentDTO | null;

  /**
   * @deprecated QC данные теперь читаются из drawerContent.qc_*.
   * Пропсы оставлены для backward-compatibility.
   * Если оба источника доступны — drawerContent побеждает.
   */
  currentQcStatus?: ReviewQcStatus | null;
  currentQcComment?: string | null;

  onOpenInViewer?: (payload: OpenViewerAtPayload) => void;
}

// -------------------------------------------------------------
// Reason source labels
// -------------------------------------------------------------

const REASON_SOURCE_LABELS: Record<DDGridV1ReasonSource, string> = {
  reason: "Обоснование",
  review_message: "Комментарий системы",
  display_text: "Результат анализа",
  none: "",
};

// -------------------------------------------------------------
// Review status labels
// -------------------------------------------------------------

function getReviewStatusLabel(status: string | null | undefined): string | null {
  if (!status || typeof status !== "string" || status.trim().length === 0) {
    return null;
  }

  const normalized = status.trim();

  switch (normalized) {
    case "needs_review":
      return "Требует внимания юриста";
    case "no_issue_detected":
    case "ok":
      return "Проверка завершена без замечаний";
    case "not_applicable":
      return "Неприменимо";
    case "unclear":
      return "Результат не определён";
    default:
      return normalized;
  }
}

// -------------------------------------------------------------
// Cell state labels for badges
// -------------------------------------------------------------

function getCellStateLabel(state: DDGridV1DrawerFieldView["cellState"]): string {
  switch (state) {
    case "defined":
      return "Определено";
    case "not_defined":
      return "Не найдено";
    case "not_applicable":
      return "Неприменимо";
    case "not_executed":
      return "Не выполнялось";
    case "error":
      return "Ошибка";
    default:
      return state;
  }
}

// -------------------------------------------------------------
// Location helpers
// -------------------------------------------------------------

function getLocationText(field: DDGridV1DrawerFieldView): string | null {
  const raw = field.raw;
  const parts: string[] = [];

  if (typeof raw.location_page === "number") {
    parts.push(`стр. ${raw.location_page}`);
  }
  if (typeof raw.location_clause_ref === "string" && raw.location_clause_ref.trim().length > 0) {
    parts.push(raw.location_clause_ref.trim());
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * Извлекает номер страницы из текстового location_clause_ref.
 * Backend может присылать location_page = null, но при этом clause_ref
 * содержит текстовое упоминание страницы, например "п. 7.3.3, стр. 8".
 *
 * Универсальный regex: ищет "стр. NNN", "страница NNN", "page NNN".
 * Возвращает null если ничего не найдено.
 */
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

/**
 * Строит payload для viewer из field DTO.
 * Приоритет:
 * 1. location_page (число из backend)
 * 2. page извлечённая из location_clause_ref через regex
 * 3. location_clause_ref как clauseUid (fallback)
 */
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
 * Универсальный бейдж с явными контрастными цветами.
 * Все цвета выбраны так, чтобы текст был чётко читаем и в светлой,
 * и в тёмной теме.
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
      ? "border-emerald-500/40 bg-emerald-100 text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-900/40 dark:text-emerald-100"
      : tone === "warning"
        ? "border-amber-500/40 bg-amber-100 text-amber-900 dark:border-amber-700/60 dark:bg-amber-900/40 dark:text-amber-100"
        : tone === "error"
          ? "border-red-500/40 bg-red-100 text-red-900 dark:border-red-700/60 dark:bg-red-900/40 dark:text-red-100"
          : tone === "muted"
            ? "border-gray-300 bg-gray-100 text-gray-800 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            : "border-gray-400 bg-gray-50 text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100";

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
  const locationText = getLocationText(field);
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
      {/* Label + value */}
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
                : field.cellState === "not_applicable"
                  ? "muted"
                  : "neutral"
          }
        >
          {getCellStateLabel(field.cellState)}
        </Pill>
      </div>

      {/* Location + confidence + open button */}
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
                  ? "Точное расположение"
                  : availability === "approximate"
                    ? "Приблизительное расположение"
                    : "Расположение недоступно"
              }
            >
              <MapPin className="h-3 w-3" aria-hidden />
              <span>{locationText}</span>
            </Pill>
          ) : null}

          {confidence === "low" && locationText ? (
            <Pill tone="warning" title="Низкая уверенность в расположении">
              Confidence: low
            </Pill>
          ) : null}

          {confidence === "high" && locationText ? (
            <Pill tone="success" title="Высокая уверенность в расположении">
              Confidence: high
            </Pill>
          ) : null}

          {canOpen ? (
            <button
              type="button"
              onClick={handleOpen}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--accent-primary)] underline decoration-dotted underline-offset-2 hover:decoration-solid"
              title="Открыть фрагмент в документе"
            >
              <ExternalLink className="h-3 w-3" aria-hidden />
              <span>Открыть в документе</span>
            </button>
          ) : null}
        </div>
      ) : null}

      {/* Location fallback reason */}
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
  const updateQc = useUpdateReviewQc();

  const [localQcStatus, setLocalQcStatus] = React.useState<ReviewQcStatus>(
    "pending",
  );
  const [localQcComment, setLocalQcComment] = React.useState<string>("");

  // Синхронизация локального QC state с изменением drawerContent.
  // Приоритет: drawerContent.qc_* (B3) → пропсы (legacy fallback).
  React.useEffect(() => {
    const qcFromDrawer = drawerContent?.qc_status ?? null;
    const commentFromDrawer = drawerContent?.qc_comment ?? null;
    setLocalQcStatus(qcFromDrawer ?? currentQcStatus ?? "pending");
    setLocalQcComment(commentFromDrawer ?? currentQcComment ?? "");
  }, [drawerContent, currentQcStatus, currentQcComment]);

  // ESC key handler
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
    () => buildDDGridV1DrawerFieldViews(drawerContent),
    [drawerContent],
  );

  const confidence = React.useMemo(
    () => resolveDDGridV1Confidence(drawerContent),
    [drawerContent],
  );

  const qualityFlags = React.useMemo(
    () => resolveDDGridV1QualityFlags(drawerContent),
    [drawerContent],
  );

  const qcAuditInfo = React.useMemo(
    () => resolveDDGridV1QcAuditInfo(drawerContent),
    [drawerContent],
  );

  const evidenceItems = React.useMemo(
    () => normalizeDDGridV1EvidenceItems(drawerContent),
    [drawerContent],
  );

  const resolvedReason = React.useMemo(
    () => resolveDDGridV1DrawerReason(drawerContent),
    [drawerContent],
  );

  if (!open || !drawerContent || !documentId) {
    return null;
  }

  const checkName = drawerContent.check_name || drawerContent.check_id;
  const drawerTitle = checkName || "Без названия проверки";
  const drawerDescription = documentName
    ? `Документ: ${documentName}`
    : `Документ ID: ${documentId}`;

  const displayText = drawerContent.display_text?.trim() || null;
  const reviewStatusLabel = getReviewStatusLabel(drawerContent.review_status);
  const executionStatus = drawerContent.execution_status?.trim() || null;
  const showExecutionStatus =
    executionStatus !== null && executionStatus !== "SUCCESS";

  const showReason =
    resolvedReason.text !== null &&
    resolvedReason.text.trim() !== (displayText ?? "").trim();

  // QC editing logic.
  // Источник истины — drawer (B3). Пропсы — legacy fallback.
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

  // -----------------------------------------------------------
  // Render as side panel (без backdrop, без blur)
  // -----------------------------------------------------------

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
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label="Закрыть"
          className="px-2 py-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
        >
          <X size={16} />
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-5">
          {/* ── 0. Detection metadata (B3 badges) ───────── */}
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
                  title={`Уверенность модели: ${confidence.formatted}`}
                >
                  Conf: {confidence.formatted}
                </Pill>
              )}

              {qualityFlags.map((flag) => (
                <Pill key={flag.key} tone="warning" title={flag.key}>
                  ⚠ {flag.label}
                </Pill>
              ))}
            </div>
          )}

          {/* ── 1. Результат анализа + обоснование (объединённая секция) ─ */}
          <Section
            title="Результат анализа"
            subtitle="Основной вывод системы и его обоснование."
          >
            <InfoCard>
              {displayText ? (
                <div className="text-sm font-semibold leading-6 text-[var(--text-primary)]">
                  {displayText}
                </div>
              ) : (
                <div className="text-xs italic text-[var(--text-faint)]">
                  Результат не сформирован.
                </div>
              )}

              {showReason ? (
                <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    {REASON_SOURCE_LABELS[resolvedReason.source] || "Обоснование"}
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
            title="Извлечённые поля"
            subtitle="Все параметры, извлечённые системой в рамках этой проверки."
          >
            <InfoCard>
              {fieldViews.length === 0 ? (
                <p className="text-xs italic text-[var(--text-faint)]">
                  Извлечённые поля отсутствуют.
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
              title="Evidence"
              subtitle="Фрагменты документа, на которые опирался анализ."
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
              title="Статус проверки"
              subtitle="Workflow-статус и техническое состояние выполнения."
            >
              <InfoCard tone="subtle">
                <div className="flex flex-wrap gap-2">
                  {reviewStatusLabel ? (
                    <Pill tone="neutral">{reviewStatusLabel}</Pill>
                  ) : null}

                  {showExecutionStatus ? (
                    <Pill
                      tone={executionStatus === "FAILED" ? "error" : "warning"}
                      title="Техническое состояние выполнения check-а"
                    >
                      Execution: {executionStatus}
                    </Pill>
                  ) : null}
                </div>
              </InfoCard>
            </Section>
          ) : null}

          {/* ── 5b. QC Audit Trail (B3) ──────────────────── */}
          {qcAuditInfo.hasBeenActioned && (
            <Section
              title="История QC"
              subtitle="Предыдущее решение юриста по этой проверке."
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
                        ? "Одобрено"
                        : qcAuditInfo.status === "rejected"
                          ? "Отклонено"
                          : "Требует проверки"}
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
            title="QC Review"
            subtitle="Статус ручной проверки и комментарий юриста. Изменения применяются после нажатия Save."
          >
            <InfoCard>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-[var(--text-primary)]">
                    QC Status
                  </label>
                  <select
                    value={localQcStatus}
                    onChange={(e) =>
                      setLocalQcStatus(e.target.value as ReviewQcStatus)
                    }
                    disabled={updateQc.isPending}
                    className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                    <option value="needs_review">Needs Review</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-[var(--text-primary)]">
                    Comment
                  </label>
                  <textarea
                    value={localQcComment}
                    onChange={(e) => setLocalQcComment(e.target.value)}
                    disabled={updateQc.isPending}
                    className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60"
                    rows={3}
                    placeholder="Оставьте комментарий к review (опционально)"
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
                      {updateQc.isPending ? "Сохранение..." : "Save"}
                    </Button>
                    <Button
                      onClick={handleCancelQc}
                      disabled={updateQc.isPending}
                      size="sm"
                      variant="secondary"
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <div className="text-xs text-[var(--text-muted)]">
                    Нет изменений для сохранения.
                  </div>
                )}

                {!runId ? (
                  <div className="rounded-lg border border-amber-500/40 bg-amber-100 px-3 py-2 text-xs text-amber-900">
                    Сохранение QC временно недоступно: отсутствует runId.
                  </div>
                ) : null}

                {updateQc.isError ? (
                  <div className="rounded-lg border border-red-500/40 bg-red-100 px-3 py-2 text-xs text-red-900">
                    Ошибка сохранения. Попробуйте снова.
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
            Закрыть
          </Button>
        </div>
      </div>
    </aside>
  );
};

export default DDGridV1Drawer;


