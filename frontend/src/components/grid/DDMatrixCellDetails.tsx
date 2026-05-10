// =============================================================
// src/components/grid/DDMatrixCellDetails.tsx
// Unified review detail drawer for DD Matrix cell details.
// Production-grade side panel for legal review evidence context.
// С встроенным QC редактированием.
// =============================================================

import React from "react";
import type {
  SeverityLevel,
  OpenViewerAtPayload,
  ClassificationLevel,
} from "../../types";
import type { ReviewQcStatus } from "../../types/dealReview";

import Drawer from "../ui/Drawer";
import Button from "../ui/Button";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { useUpdateReviewQc } from "../../api/qc";

export interface MatrixCellDetailsCell {
  result: "pass" | "fail" | "unclear" | string;
  severity: SeverityLevel | null;
  snippet: string | null;
  page: number | null;
  clauseUid: string | null;
  confidence: number | null;
  qcStatus: ReviewQcStatus | null;
  conditionalTriggered: boolean;
  triggerName: string | null;

  origin?: string | null;
  createdAt?: string | null;
  qcComment?: string | null;
  qualityFlags?: Record<string, boolean> | null;

  docType?: string | null;
  docClassificationLevel?: ClassificationLevel | string | null;
  docClassificationConfidence?: number | null;

  segmentId?: string | null;
  segmentTitle?: string | null;
  segmentType?: string | null;
  segmentOrder?: number | null;
  isPrimarySegment?: boolean | null;
  chunkId?: string | null;
  chunkIndex?: number | null;

  extractedFields: Array<{
    fieldName: string;
    fieldValue: string;
    fieldFormat?: string | null;
    fieldSource?: string | null;
    page?: number | null;
    clauseUid?: string | null;
    segmentId?: string | null;
    chunkId?: string | null;
    chunkIndex?: number | null;
  }>;
}

export interface MatrixCellDetailsProps {
  open: boolean;
  onClose: () => void;
  runId: string | null;
  documentName: string | null;
  documentId: string | null;
  checkName: string | null;
  checkId: string | null;
  cell: MatrixCellDetailsCell | null;
  onOpenInViewer?: (payload: OpenViewerAtPayload) => void;
}

function getHumanResultText(
  result: string,
  severity: SeverityLevel | null,
): string {
  if (result === "fail") {
    if (severity === "critical") return "Найдено критичное несоответствие";
    if (severity === "high") return "Найдено существенное несоответствие";
    if (severity === "medium") return "Найдено несоответствие";
    return "Найдено несоответствие";
  }

  if (result === "unclear") {
    return "Требует внимания юриста";
  }

  if (result === "pass") {
    return "Несоответствий не найдено";
  }

  return "Неизвестный статус";
}

function getConfidenceText(confidence: number | null): string {
  return typeof confidence === "number"
    ? `${Math.round(confidence * 100)}%`
    : "—";
}

function getSegmentHeading(cell: MatrixCellDetailsCell): string {
  if (cell.segmentTitle && cell.segmentTitle.trim()) {
    return cell.segmentTitle.trim();
  }
  if (cell.segmentType && cell.segmentType.trim()) {
    return cell.segmentType.trim();
  }
  if (cell.segmentId && cell.segmentId.trim()) {
    return cell.segmentId.trim();
  }
  return "Документ целиком";
}

function getSegmentMeta(cell: MatrixCellDetailsCell): string | null {
  const parts: string[] = [];

  if (cell.segmentType && cell.segmentTitle) {
    parts.push(cell.segmentType);
  }

  if (cell.segmentOrder !== null && cell.segmentOrder !== undefined) {
    parts.push(`Порядок: ${cell.segmentOrder}`);
  }

  return parts.length ? parts.join(" · ") : null;
}

function formatCreatedAt(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleString();
}

function summarizeQualityFlags(
  flags: Record<string, boolean> | null | undefined,
): string {
  if (!flags || !Object.keys(flags).length) {
    return "Флаги качества не установлены.";
  }

  const active: string[] = [];

  if (flags.structure_degraded) {
    active.push("Структура документа нарушена");
  }
  if (flags.llm_fallback_used) {
    active.push("Использован LLM fallback");
  }

  if (!active.length) {
    return "Есть технические флаги качества.";
  }

  return active.join(" · ");
}

function hasAnyQualityFlags(
  flags: Record<string, boolean> | null | undefined,
): boolean {
  if (!flags) return false;
  return Object.values(flags).some(Boolean);
}

function getFieldLocationLabel(
  field: MatrixCellDetailsCell["extractedFields"][number],
): string {
  const pageText = field.page != null ? `Стр. ${field.page}` : null;
  const clauseText = field.clauseUid ? `Clause ${field.clauseUid}` : null;
  const chunkText =
    field.chunkIndex != null ? `Chunk #${field.chunkIndex}` : null;

  return (
    [pageText, clauseText, chunkText].filter(Boolean).join(" · ") ||
    "Открыть фрагмент"
  );
}

function isLowClassificationConfidence(
  confidence: number | null | undefined,
): boolean {
  return typeof confidence === "number" && confidence < 0.6;
}

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
      className={tone === "subtle" ? "subtle-panel p-3" : "card-surface p-3"}
    >
      {children}
    </div>
  );
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 text-xs">
      <span className="shrink-0 text-[var(--text-muted)]">{label}</span>
      <span className="text-right font-medium text-[var(--text-primary)]">
        {value}
      </span>
    </div>
  );
}

function MetaPill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "accent" | "warning";
}) {
  const toneClass =
    tone === "accent"
      ? "border-[var(--border-accent-soft)] bg-[var(--bg-elevated-soft)] text-[var(--accent-primary)]"
      : tone === "warning"
        ? "border-[color:color-mix(in_srgb,var(--color-gold)_20%,transparent)] bg-[var(--color-gold-highlight)] text-[var(--color-gold-hover)]"
        : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)]";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${toneClass}`}
    >
      {children}
    </span>
  );
}

export const DDMatrixCellDetails: React.FC<MatrixCellDetailsProps> = ({
  open,
  onClose,
  runId,
  documentName,
  documentId,
  checkName,
  checkId,
  cell,
  onOpenInViewer,
}) => {
  const updateQc = useUpdateReviewQc();

  const [localQcStatus, setLocalQcStatus] = React.useState<ReviewQcStatus>(
    "pending",
  );
  const [localQcComment, setLocalQcComment] = React.useState<string>("");

  React.useEffect(() => {
    if (!cell) return;
    setLocalQcStatus(cell.qcStatus ?? "pending");
    setLocalQcComment(cell.qcComment ?? "");
  }, [cell]);

  if (!open || !cell || !documentId) {
    return null;
  }

  const savedQcStatus = cell.qcStatus ?? "pending";
  const savedQcComment = cell.qcComment ?? "";

  const isDirty =
    localQcStatus !== savedQcStatus || localQcComment !== savedQcComment;

  const canSave = isDirty && !updateQc.isPending && !!runId && !!checkId;

  const handleSave = async () => {
    if (!runId || !checkId || !documentId || !canSave) {
      return;
    }

    try {
      await updateQc.mutateAsync({
        finding: {
          run_id: runId,
          document_id: documentId,
          check_id: checkId,
          segment_id: cell.segmentId ?? null,
        },
        qc_status: localQcStatus,
        comment: localQcComment.trim() ? localQcComment.trim() : null,
      });

      onClose();
    } catch (error) {
      console.error("Failed to save QC update:", error);
    }
  };

  const handleCancel = () => {
    setLocalQcStatus(savedQcStatus);
    setLocalQcComment(savedQcComment);
  };

  const confidenceText = getConfidenceText(cell.confidence);
  const humanResultText = getHumanResultText(cell.result, cell.severity);
  const segmentHeading = getSegmentHeading(cell);
  const segmentMeta = getSegmentMeta(cell);
  const createdAtText = formatCreatedAt(cell.createdAt);
  const qualitySummary = summarizeQualityFlags(cell.qualityFlags);
  const showQualityFlags =
    !!cell.qualityFlags && Object.keys(cell.qualityFlags).length > 0;

  const canOpenInViewer =
    !!onOpenInViewer &&
    (cell.page != null ||
      !!cell.clauseUid ||
      !!cell.segmentId ||
      !!cell.chunkId ||
      cell.chunkIndex != null);

  const handleOpenInViewer = () => {
    if (!onOpenInViewer) return;

    onOpenInViewer({
      documentId,
      page: cell.page ?? undefined,
      clauseUid: cell.clauseUid ?? undefined,
      elementId: undefined,
      segmentId: cell.segmentId ?? undefined,
      chunkId: cell.chunkId ?? undefined,
      chunkIndex: cell.chunkIndex ?? undefined,
    });
  };

  const handleOpenExtractedFieldLocation = (
    field: MatrixCellDetailsCell["extractedFields"][number],
  ) => {
    if (!onOpenInViewer) return;

    const hasLocation =
      field.page != null ||
      !!field.clauseUid ||
      !!field.segmentId ||
      !!field.chunkId ||
      field.chunkIndex != null;

    if (!hasLocation) return;

    onOpenInViewer({
      documentId,
      page: field.page ?? undefined,
      clauseUid: field.clauseUid ?? undefined,
      elementId: undefined,
      segmentId: field.segmentId ?? undefined,
      chunkId: field.chunkId ?? undefined,
      chunkIndex: field.chunkIndex ?? undefined,
    });
  };

  const drawerTitle = checkName || checkId || "Без названия проверки";
  const drawerDescription = documentName
    ? `Документ: ${documentName}`
    : `Документ ID: ${documentId}`;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={drawerTitle}
      description={drawerDescription}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-[11px] text-[var(--text-muted)]">
            Открыть документ в контексте evidence и review provenance.
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onClose}>
              Закрыть
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleOpenInViewer}
              disabled={!canOpenInViewer}
              title={
                canOpenInViewer
                  ? "Открыть в документе"
                  : "Недостаточно данных для перехода в viewer"
              }
            >
              Открыть в документе
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-5">
        <Section
          title="QC Review"
          subtitle="Статус и комментарий юридического review. Изменения применяются после нажатия Save."
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

              {isDirty ? (
                <div className="flex gap-2">
                  <Button
                    onClick={handleSave}
                    disabled={!canSave}
                    size="sm"
                    variant="primary"
                  >
                    {updateQc.isPending ? "Сохранение..." : "Save"}
                  </Button>
                  <Button
                    onClick={handleCancel}
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

              {!runId || !checkId ? (
                <div className="rounded-lg border border-[var(--color-gold)]/20 bg-[var(--color-gold-highlight)] px-3 py-2 text-xs text-[var(--color-gold-hover)]">
                  Сохранение QC временно недоступно: отсутствует runId или checkId.
                </div>
              ) : null}

              {updateQc.isError ? (
                <div className="rounded-lg border border-[var(--color-error)]/20 bg-[var(--color-error)]/10 px-3 py-2 text-xs text-[var(--color-error)]">
                  Ошибка сохранения. Попробуйте снова.
                </div>
              ) : null}
            </div>
          </InfoCard>
        </Section>

        <Section
          title="Контекст документа"
          subtitle="Документ, тип и сигналы классификации, которые помогают интерпретировать finding в review workflow."
        >
          <InfoCard>
            <div className="space-y-3">
              <div className="space-y-1">
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  {documentName || "Без имени"}
                </div>
                <div className="flex flex-wrap gap-2">
                  <MetaPill>{cell.docType || "Тип не указан"}</MetaPill>

                  {cell.docClassificationLevel ? (
                    <span className="inline-flex">
                      <ClassificationBadge
                        level={
                          cell.docClassificationLevel as ClassificationLevel
                        }
                        confidence={
                          cell.docClassificationConfidence ?? undefined
                        }
                        showConfidence={false}
                      />
                    </span>
                  ) : null}

                  {isLowClassificationConfidence(
                    cell.docClassificationConfidence,
                  ) ? (
                    <MetaPill tone="warning">Низкая уверенность</MetaPill>
                  ) : null}
                </div>
              </div>

              <div className="space-y-2">
                <InfoRow label="Тип документа" value={cell.docType || "—"} />
                <InfoRow
                  label="Классификация"
                  value={cell.docClassificationLevel || "—"}
                />
                <InfoRow
                  label="Уверенность классификации"
                  value={getConfidenceText(
                    cell.docClassificationConfidence ?? null,
                  )}
                />
              </div>
            </div>
          </InfoCard>
        </Section>

        <Section
          title="Результат"
          subtitle="Статус проверки, severity, QC и основные сигналы для юридической оценки."
        >
          <InfoCard>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                {cell.severity ? (
                  <SeverityBadge severity={cell.severity} />
                ) : null}

                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {humanResultText}
                </span>

                <span className="text-[11px] text-[var(--text-faint)]">
                  ({cell.result})
                </span>

                {cell.conditionalTriggered ? (
                  <MetaPill tone="accent">Conditional</MetaPill>
                ) : null}
              </div>

              <div className="space-y-2">
                <InfoRow label="Severity" value={cell.severity || "—"} />
                <InfoRow
                  label="QC статус (текущий)"
                  value={cell.qcStatus || "—"}
                />
                <InfoRow label="Confidence" value={confidenceText} />
                <InfoRow label="Создано" value={createdAtText} />
                {cell.conditionalTriggered ? (
                  <InfoRow
                    label="Trigger"
                    value={cell.triggerName || "Conditional check triggered"}
                  />
                ) : null}
              </div>

              {cell.qcComment ? (
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2">
                  <div className="text-[11px] font-medium text-[var(--text-secondary)]">
                    Комментарий QC (сохранённый)
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-[var(--text-primary)]">
                    {cell.qcComment}
                  </p>
                </div>
              ) : null}
            </div>
          </InfoCard>
        </Section>

        <Section
          title="Проверка"
          subtitle="Контекст конкретной проверки и source metadata для interpretation layer."
        >
          <InfoCard tone="subtle">
            <div className="space-y-2">
              <InfoRow label="Проверка" value={checkName || checkId || "—"} />
              <InfoRow label="Источник" value={cell.origin || "—"} />
              <InfoRow
                label="Условная логика"
                value={
                  cell.conditionalTriggered
                    ? cell.triggerName || "Conditional check triggered"
                    : "Нет"
                }
              />
            </div>
          </InfoCard>
        </Section>

        <Section
          title="Evidence"
          subtitle="Фрагмент текста и привязка к странице, clause UID и viewer location."
        >
          <InfoCard tone="subtle">
            <div className="space-y-3">
              {cell.snippet ? (
                <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text-primary)]">
                  {cell.snippet}
                </p>
              ) : (
                <p className="text-xs text-[var(--text-faint)]">
                  Evidence snippet отсутствует.
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <MetaPill>Страница: {cell.page ?? "—"}</MetaPill>
                <MetaPill>Clause UID: {cell.clauseUid || "—"}</MetaPill>
                {cell.chunkIndex != null ? (
                  <MetaPill>Chunk #{cell.chunkIndex}</MetaPill>
                ) : null}
              </div>
            </div>
          </InfoCard>
        </Section>

        {(cell.segmentId ||
          cell.segmentTitle ||
          cell.segmentType ||
          cell.chunkId ||
          cell.chunkIndex != null) && (
          <Section
            title="Segment / Chunk"
            subtitle="Source-linked provenance для сегмента и чанка внутри review matrix."
          >
            <InfoCard>
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {segmentHeading}
                  </span>

                  {cell.isPrimarySegment ? (
                    <MetaPill tone="accent">Основной сегмент</MetaPill>
                  ) : null}
                </div>

                {segmentMeta ? (
                  <p className="text-[11px] text-[var(--text-muted)]">
                    {segmentMeta}
                  </p>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  {cell.segmentId ? (
                    <MetaPill>segment_id: {cell.segmentId}</MetaPill>
                  ) : null}

                  {cell.chunkId ? (
                    <MetaPill>chunk_id: {cell.chunkId}</MetaPill>
                  ) : null}

                  {cell.chunkIndex != null ? (
                    <MetaPill>Chunk #{cell.chunkIndex}</MetaPill>
                  ) : null}
                </div>
              </div>
            </InfoCard>
          </Section>
        )}

        <Section
          title="Извлечённые поля"
          subtitle="Нормализованные значения, извлечённые из evidence, с возможностью перейти к source location."
        >
          <InfoCard>
            {cell.extractedFields.length === 0 ? (
              <p className="text-xs text-[var(--text-faint)]">
                Извлечённые значения отсутствуют.
              </p>
            ) : (
              <div className="space-y-2">
                {cell.extractedFields.map((field, idx) => {
                  const hasLocation =
                    field.page != null ||
                    !!field.clauseUid ||
                    !!field.segmentId ||
                    !!field.chunkId ||
                    field.chunkIndex != null;

                  return (
                    <div
                      key={`${field.fieldName}-${idx}`}
                      className="border-b border-[var(--border-subtle)] pb-2 last:border-0 last:pb-0"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[11px] font-medium text-[var(--text-secondary)]">
                            {field.fieldName}
                          </div>

                          {field.fieldFormat ? (
                            <div className="text-[10px] text-[var(--text-faint)]">
                              {field.fieldFormat}
                            </div>
                          ) : null}

                          {field.fieldSource ? (
                            <div className="text-[10px] text-[var(--text-faint)]">
                              {field.fieldSource}
                            </div>
                          ) : null}
                        </div>

                        <div className="max-w-[55%] break-words text-right text-[11px] font-semibold text-[var(--text-primary)]">
                          {field.fieldValue}
                        </div>
                      </div>

                      {hasLocation ? (
                        <div className="mt-2 flex justify-end">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              handleOpenExtractedFieldLocation(field)
                            }
                            className="h-auto min-h-0 px-0 py-0 text-[11px] font-medium text-[var(--accent-primary)] hover:bg-transparent hover:text-[var(--accent-primary)] hover:underline"
                          >
                            {getFieldLocationLabel(field)}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </InfoCard>
        </Section>

        <Section
          title="Качество"
          subtitle="Флаги качества и технические caveats, влияющие на доверие к finding."
        >
          <InfoCard>
            <div className="space-y-3">
              <p className="text-xs leading-5 text-[var(--text-secondary)]">
                {qualitySummary}
              </p>

              {hasAnyQualityFlags(cell.qualityFlags) ? (
                <div className="flex flex-wrap gap-2">
                  {Object.entries(cell.qualityFlags ?? {})
                    .filter(([, enabled]) => Boolean(enabled))
                    .map(([flag]) => (
                      <MetaPill key={flag}>{flag}</MetaPill>
                    ))}
                </div>
              ) : null}

              {showQualityFlags ? (
                <details>
                  <summary className="cursor-pointer text-[11px] font-medium text-[var(--accent-primary)]">
                    Показать тех. детали
                  </summary>
                  <pre className="mt-2 overflow-auto rounded-xl bg-[var(--bg-elevated-soft)] p-2 text-[10px] text-[var(--text-secondary)]">
                    {JSON.stringify(cell.qualityFlags, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          </InfoCard>
        </Section>
      </div>
    </Drawer>
  );
};

export default DDMatrixCellDetails;
