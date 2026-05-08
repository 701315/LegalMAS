// src/components/grid/DDMatrixCellDetails.tsx

// =============================================================
// Side panel с подробностями по ячейке DD Matrix.
// Используется только в review-режиме поверх dd-matrix DTO.
// =============================================================

import React from "react";
import type {
  SeverityLevel,
  OpenViewerAtPayload,
  CheckResult,
} from "../../types";

import Drawer from "../ui/Drawer";
import Button from "../ui/Button";
import { SeverityBadge } from "../ui/SeverityBadge";

export interface MatrixCellDetailsCell {
  result: CheckResult["result"] | string;
  severity: SeverityLevel | null;
  snippet: string | null;
  page: number | null;
  clauseUid: string | null;
  confidence: number | null;
  qcStatus: CheckResult["qc_status"] | null;
  conditionalTriggered: boolean;
  triggerName: string | null;

  // segment/chunk provenance
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
  }>;
}

export interface MatrixCellDetailsProps {
  open: boolean;
  onClose: () => void;

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
          ? "subtle-panel p-3"
          : "card-surface p-3"
      }
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
  tone?: "neutral" | "accent";
}) {
  const toneClass =
    tone === "accent"
      ? "border-[var(--border-accent-soft)] bg-[var(--bg-elevated-soft)] text-[var(--accent-primary)]"
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
  documentName,
  documentId,
  checkName,
  checkId,
  cell,
  onOpenInViewer,
}) => {
  if (!open || !cell || !documentId) {
    return null;
  }

  const confidenceText = getConfidenceText(cell.confidence);
  const humanResultText = getHumanResultText(cell.result, cell.severity);
  const segmentHeading = getSegmentHeading(cell);
  const segmentMeta = getSegmentMeta(cell);

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
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] text-[var(--text-muted)]">
            Открыть документ в контексте evidence.
          </div>

          <div className="flex items-center gap-2">
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
          title="Результат"
          subtitle="Статус проверки, severity и базовые сигналы качества."
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
                <InfoRow label="QC статус" value={cell.qcStatus || "—"} />
                <InfoRow label="Confidence" value={confidenceText} />
                {cell.conditionalTriggered ? (
                  <InfoRow
                    label="Trigger"
                    value={cell.triggerName || "Conditional check triggered"}
                  />
                ) : null}
              </div>
            </div>
          </InfoCard>
        </Section>

        <Section
          title="Evidence"
          subtitle="Фрагмент текста и привязка к странице или clause UID."
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
            subtitle="Provenance для сегмента и чанка, если backend передал эти данные."
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
          subtitle="Нормализованные значения, извлечённые из evidence."
        >
          <InfoCard>
            {cell.extractedFields.length === 0 ? (
              <p className="text-xs text-[var(--text-faint)]">
                Извлечённые значения отсутствуют.
              </p>
            ) : (
              <div className="space-y-2">
                {cell.extractedFields.map((field, idx) => (
                  <div
                    key={`${field.fieldName}-${idx}`}
                    className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] pb-2 last:border-0 last:pb-0"
                  >
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
                ))}
              </div>
            )}
          </InfoCard>
        </Section>
      </div>
    </Drawer>
  );
};

export default DDMatrixCellDetails;


