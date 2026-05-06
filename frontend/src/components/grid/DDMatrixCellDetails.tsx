// =============================================================
// src/components/grid/DDMatrixCellDetails.tsx
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
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </h4>
      {children}
    </section>
  );
}

function InfoCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-3 shadow-sm">
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

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={checkName || checkId || "Без названия проверки"}
      description={`Документ: ${documentName || documentId}`}
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
        <Section title="Результат">
          <InfoCard>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                {cell.severity && <SeverityBadge severity={cell.severity} />}
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {humanResultText}
                </span>
                <span className="text-[11px] text-[var(--text-faint)]">
                  ({cell.result})
                </span>
              </div>

              <div className="space-y-2">
                <InfoRow
                  label="Severity"
                  value={cell.severity || "—"}
                />
                <InfoRow
                  label="QC статус"
                  value={cell.qcStatus || "—"}
                />
                <InfoRow
                  label="Confidence"
                  value={confidenceText}
                />
                {cell.conditionalTriggered && (
                  <InfoRow
                    label="Trigger"
                    value={cell.triggerName || "Conditional check triggered"}
                  />
                )}
              </div>
            </div>
          </InfoCard>
        </Section>

        <Section title="Evidence">
          <InfoCard>
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

              <div className="flex flex-wrap gap-3 text-[11px] text-[var(--text-muted)]">
                <span>Страница: {cell.page ?? "—"}</span>
                <span>Clause UID: {cell.clauseUid || "—"}</span>
              </div>
            </div>
          </InfoCard>
        </Section>

        {(cell.segmentId ||
          cell.segmentTitle ||
          cell.segmentType ||
          cell.chunkId ||
          cell.chunkIndex != null) && (
          <Section title="Segment / Chunk">
            <InfoCard>
              <div className="space-y-2 text-[11px]">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {segmentHeading}
                  </span>

                  {cell.isPrimarySegment && (
                    <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--accent-primary)_20%,transparent)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                      Основной сегмент
                    </span>
                  )}
                </div>

                {segmentMeta && (
                  <p className="text-[10px] text-[var(--text-muted)]">
                    {segmentMeta}
                  </p>
                )}

                {cell.segmentId && (
                  <p className="text-[10px] text-[var(--text-faint)]">
                    segment_id: {cell.segmentId}
                  </p>
                )}

                {cell.chunkId && (
                  <p className="text-[10px] text-[var(--text-muted)]">
                    chunk_id: {cell.chunkId}
                  </p>
                )}

                {cell.chunkIndex != null && (
                  <p className="text-[10px] text-[var(--text-muted)]">
                    Chunk #{cell.chunkIndex}
                  </p>
                )}
              </div>
            </InfoCard>
          </Section>
        )}

        <Section title="Извлечённые поля">
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

                      {field.fieldFormat && (
                        <div className="text-[10px] text-[var(--text-faint)]">
                          {field.fieldFormat}
                        </div>
                      )}

                      {field.fieldSource && (
                        <div className="text-[10px] text-[var(--text-faint)]">
                          {field.fieldSource}
                        </div>
                      )}
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


