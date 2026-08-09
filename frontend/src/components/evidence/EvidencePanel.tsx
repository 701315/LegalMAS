// =============================================================
// src/components/evidence/EvidencePanel.tsx
// =============================================================

import React from "react";

import type {
  CheckResult,
  QCStatus,
  OpenViewerAtFn,
  StructuredField,
} from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import Button from "../ui/Button";
import { useEvidence } from "../../api/evidence";
import type { EvidenceDetail } from "../../api/evidence";
import { useCheckProvenance } from "../../api/provenance";

interface EvidencePanelProps {
  result: CheckResult;
  onClose: () => void;
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

function getSnippet(
  evidence: EvidenceDetailLike | undefined,
  result: CheckResult,
): string {
  return (
    evidence?.quote ||
    evidence?.snippet ||
    result.value_text ||
    "(нет фрагмента текста)"
  );
}

function formatCreatedAt(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function getFieldStatus(field: StructuredField): "yes" | "no" | "unclear" {
  const found = field.found ?? true;
  const confidence =
    typeof field.confidence === "number" ? field.confidence : 0;
  if (!found) return "no";
  if (confidence >= 0.6) return "yes";
  return "unclear";
}

function renderStatusLabel(field: StructuredField): string {
  const status = getFieldStatus(field);
  if (status === "yes") return "Есть";
  if (status === "no") return "Нет";
  return "Требует уточнения";
}

function renderLocationLabel(field: StructuredField): string {
  if (!field.location) return "—";
  const { page, clause_uid: clauseUid } = field.location;
  if (!page && !clauseUid) return "Фрагмент";
  if (page && clauseUid) return `Стр. ${page}, п. ${clauseUid}`;
  if (page) return `Стр. ${page}`;
  return clauseUid || "Фрагмент";
}

function renderQcLabel(field: StructuredField): string {
  const status = field.qc?.status || "pending";
  if (status === "pending") return "pending";
  if (status === "accepted") return "accepted";
  if (status === "rejected") return "rejected";
  if (status === "auto_accepted") return "auto_accepted";
  return status;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  result,
  onClose,
  onQcChange,
  onOpenAtLocation,
}) => {
  const { data: evidence, isLoading, error } = useEvidence(result.id);
  const { data: provenance } = useCheckProvenance(result.id);
  const contextTrace = provenance?.context_trace ?? [];

  const evidenceObj = (evidence ?? undefined) as EvidenceDetailLike | undefined;
  const snippet = getSnippet(evidenceObj, result);

  const page =
    typeof evidenceObj?.page === "number" ? evidenceObj.page : undefined;
  const clauseUid =
    typeof evidenceObj?.clause_uid === "string" &&
    evidenceObj.clause_uid.trim()
      ? evidenceObj.clause_uid
      : undefined;

  const segmentId = evidenceObj?.segment_id ?? undefined;
  const chunkIndex = evidenceObj?.chunk_index ?? undefined;
  const chunkId = evidenceObj?.chunk_id ?? undefined;

  const evidenceDetails = evidenceObj?.structured_data ?? undefined;
  const hasEvidenceDetails =
    !!evidenceDetails &&
    typeof evidenceDetails === "object" &&
    Object.keys(evidenceDetails).length > 0;

  const qcStatus = result.qc_status;
  const isPendingQc = qcStatus === "pending";

  const qualitySummary = React.useMemo(() => {
    const flags: Record<string, boolean> = result.quality_flags ?? {};
    const active: string[] = [];
    if (flags.structure_degraded) active.push("Структура документа нарушена");
    if (flags.llm_fallback_used) active.push("Использован LLM fallback");
    if (!active.length && Object.keys(flags).length)
      active.push("Есть технические флаги (см. детали ниже)");
    if (!active.length) return "Флаги качества не установлены.";
    return active.join(" · ");
  }, [result.quality_flags]);

  const structuredEntries: [string, StructuredField][] = React.useMemo(() => {
    if (!result.structured_data || typeof result.structured_data !== "object")
      return [];
    return Object.entries(result.structured_data) as [
      string,
      StructuredField,
    ][];
  }, [result.structured_data]);

  const hasStructuredData = structuredEntries.length > 0;

  const isLowConfidence =
    typeof result.doc_classification_confidence === "number" &&
    result.doc_classification_confidence < 0.6;

  const canOpenOriginal =
    !!onOpenAtLocation &&
    !!result.document_id &&
    (page != null ||
      !!clauseUid ||
      !!segmentId ||
      !!chunkId ||
      chunkIndex != null);

  const handleApprove = () => {
    onQcChange?.(result, "approved");
  };

  const handleReject = () => {
    onQcChange?.(result, "rejected");
  };

  const handleViewOriginal = () => {
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

  const handleOpenFieldLocation = (field: StructuredField) => {
    if (!field.location || !onOpenAtLocation || !result.document_id) return;
    onOpenAtLocation({
      documentId: result.document_id,
      page: field.location.page ?? field.location.start_page ?? undefined,
      clauseUid: field.location.clause_uid ?? undefined,
      elementId: field.location.element_id ?? undefined,
      segmentId: field.location.segment_id ?? undefined,
      chunkId: field.location.chunk_id ?? undefined,
      chunkIndex: field.location.chunk_index ?? undefined,
    });
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-3xl translate-x-0 transform flex-col border-l border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-2xl transition-transform duration-200 ease-out">
      {/* Шапка */}
      <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
        <div className="min-w-0 space-y-1">
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
            Документ
          </div>
          <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {result.document_name || "Без имени"}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-muted)]">
            {result.doc_type && <span>Тип: {result.doc_type}</span>}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleViewOriginal}
              disabled={!canOpenOriginal}
              className="h-auto min-h-0 px-0 py-0 text-[11px] font-medium text-[var(--accent-primary)] hover:bg-transparent hover:text-[var(--accent-primary)] hover:underline"
            >
              Просмотреть исходный документ
            </Button>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="flex flex-col items-end gap-1">
            <div className="flex flex-wrap items-center justify-end gap-1">
              <SeverityBadge severity={result.severity} />
              {result.conditional_check_triggered && (
                <span
                  className="inline-flex items-center gap-1 rounded-full border border-[color:color-mix(in_srgb,var(--color-purple)_20%,transparent)] bg-[var(--color-purple-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-purple)]"
                  title={result.trigger_name || "Conditional check triggered"}
                >
                  ⚡ {result.trigger_name || "Conditional"}
                </span>
              )}
            </div>
            <span className="text-[11px] text-[var(--text-muted)]">
              Результат: {result.result}
            </span>
            <span className="text-[11px] text-[var(--text-muted)]">
              QC: {qcStatus}
              {result.qc_by ? ` · ${result.qc_by}` : ""}
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Закрыть"
            className="px-2 py-1 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            ✕
          </Button>
        </div>
      </div>

      {/* Основное содержимое */}
      <div className="grid flex-1 grid-cols-1 gap-4 overflow-y-auto overflow-x-hidden px-5 py-4 md:grid-cols-3 md:overflow-hidden">        {/* Левая колонка */}
        <div className="col-span-1 space-y-4 overflow-y-auto border-r border-[var(--border-subtle)] pr-4">
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              Документ
            </div>
            <div className="text-sm text-[var(--text-primary)]">
              {result.document_name || "Без имени"}
            </div>
            {result.doc_type && (
              <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                Тип: {result.doc_type}
              </div>
            )}
          </div>

          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              Классификация документа
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-[var(--text-secondary)]">
              {result.doc_classification_level ? (
                <ClassificationBadge
                  level={result.doc_classification_level}
                  confidence={
                    result.doc_classification_confidence ?? undefined
                  }
                />
              ) : (
                <span className="text-[11px] text-[var(--text-faint)]">
                  Нет данных классификации
                </span>
              )}
              {isLowConfidence && (
                <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--color-gold)_20%,transparent)] bg-[var(--color-gold-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-gold-text)]">
                  Низкая уверенность
                </span>
              )}
            </div>
          </div>

          {result.conditional_check_triggered && (
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
                Условная проверка
              </div>
              <div className="space-y-1">
                <div className="inline-flex items-center gap-1 rounded-full border border-[color:color-mix(in_srgb,var(--color-purple)_20%,transparent)] bg-[var(--color-purple-highlight)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-purple)]">
                  ⚡ {result.trigger_name || "Условная проверка"}
                </div>
                <div className="text-[11px] leading-5 text-[var(--text-muted)]">
                  Эта проверка запущена условным правилом
                  {result.trigger_name ? ` «${result.trigger_name}»` : ""}.
                </div>
              </div>
            </div>
          )}

          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              Проверка
            </div>
            <div className="text-sm text-[var(--text-primary)]">
              {result.check_name}
            </div>
            {result.detector_used && (
              <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                Источник: {result.detector_used}
              </div>
            )}
          </div>

          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              Метаданные
            </div>
            <div className="space-y-0.5 text-[11px] text-[var(--text-muted)]">
              {result.confidence != null && (
                <div>
                  Уверенность детектора:{" "}
                  {Math.round(result.confidence * 100)}%
                </div>
              )}
              <div>Создано: {formatCreatedAt(result.created_at)}</div>
            </div>
          </div>
        </div>

        {/* Средняя колонка */}
        <div className="col-span-1 flex flex-col gap-3 overflow-hidden">
          <div className="flex flex-col">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              Цитата / фрагмент
            </div>

            {isLoading && (
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-xs text-[var(--text-muted)]">
                Загружаем evidence…
              </div>
            )}

            {error && (
              <div className="rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2 text-xs text-[var(--color-error-text)]">
                Не удалось загрузить evidence.
              </div>
            )}

            {!isLoading && !error && (
              <>
                {(page ||
                  clauseUid ||
                  segmentId ||
                  chunkIndex != null ||
                  chunkId) && (
                  <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-muted)]">
                    {page != null && <span>Стр. {page}</span>}
                    {clauseUid && <span>Clause: {clauseUid}</span>}
                    {segmentId && (
                      <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--accent-primary)_20%,transparent)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                        Сегмент: {segmentId}
                      </span>
                    )}
                    {chunkIndex != null && (
                      <span className="inline-flex items-center rounded-full border border-[color:color-mix(in_srgb,var(--color-gold)_20%,transparent)] bg-[var(--color-gold-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-gold-text)]">
                        Chunk #{chunkIndex}
                      </span>
                    )}
                    {!segmentId && chunkId && (
                      <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                        Chunk ID: {chunkId}
                      </span>
                    )}
                  </div>
                )}
                <div className="max-h-48 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-3 text-xs leading-relaxed text-[var(--text-primary)]">
                  {snippet}
                </div>
              </>
            )}
          </div>

          {hasStructuredData && (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
                Извлечённые данные
              </div>
              <div className="max-h-48 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        Поле
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        Значение
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        Статус
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        Источник
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        Увер.
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        Фрагмент
                      </th>
                      <th className="px-2 py-1 text-left font-medium text-[var(--text-muted)]">
                        QC
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {structuredEntries.map(([key, field]) => {
                      const value =
                        field.value != null ? String(field.value) : "—";
                      const source = field.source || "—";
                      const confidence =
                        typeof field.confidence === "number"
                          ? `${Math.round(field.confidence * 100)}%`
                          : "—";
                      const hasLocation = !!field.location;
                      return (
                        <tr
                          key={key}
                          className="border-b border-[var(--border-subtle)] last:border-b-0"
                        >
                          <td className="whitespace-nowrap bg-[var(--bg-elevated-soft)] px-2 py-1 align-top text-[var(--text-secondary)]">
                            {key}
                          </td>
                          <td className="px-2 py-1 align-top text-[var(--text-primary)]">
                            {value}
                          </td>
                          <td className="whitespace-nowrap px-2 py-1 align-top text-[var(--text-secondary)]">
                            {renderStatusLabel(field)}
                          </td>
                          <td className="whitespace-nowrap px-2 py-1 align-top text-[var(--text-secondary)]">
                            {source}
                          </td>
                          <td className="whitespace-nowrap px-2 py-1 align-top text-[var(--text-secondary)]">
                            {confidence}
                          </td>
                          <td className="whitespace-nowrap px-2 py-1 align-top">
                            {hasLocation ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  handleOpenFieldLocation(field)
                                }
                                className="h-auto min-h-0 px-0 py-0 text-[11px] font-medium text-[var(--accent-primary)] hover:bg-transparent hover:text-[var(--accent-primary)] hover:underline"
                              >
                                {renderLocationLabel(field)}
                              </Button>
                            ) : (
                              <span className="text-[var(--text-faint)]">
                                —
                              </span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-2 py-1 align-top text-[var(--text-secondary)]">
                            {renderQcLabel(field)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {hasEvidenceDetails && (
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
                Детали проверки
              </div>
              <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[11px]">
                {result.qc_comment && (
                  <>
                    <div className="mb-1 text-[var(--text-muted)]">
                      Комментарий QC:
                    </div>
                    <div className="mb-2 whitespace-pre-wrap text-xs text-[var(--text-primary)]">
                      {result.qc_comment}
                    </div>
                  </>
                )}
                <details>
                  <summary className="cursor-pointer text-[var(--accent-primary)]">
                    Показать тех. детали
                  </summary>
                  <pre className="mt-2 overflow-auto rounded-xl bg-[var(--bg-elevated-soft)] p-2 text-[10px] text-[var(--text-secondary)]">
                    {JSON.stringify(evidenceDetails, null, 2)}
                  </pre>
                </details>
              </div>
            </div>
          )}
        </div>

        {/* Правая колонка */}
        <div className="col-span-1 flex flex-col gap-3 overflow-hidden">
          {/* QC-статус */}
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              QC-статус
            </div>
            <div className="mb-1 text-sm text-[var(--text-primary)]">
              {qcStatus}
              {result.qc_by ? ` · ${result.qc_by}` : ""}
            </div>
            <div className="mb-2 text-[11px] leading-5 text-[var(--text-muted)]">
              {isPendingQc
                ? "Требуется QC-решение по этому результату."
                : "QC по этому результату уже выставлен."}
            </div>
            {onQcChange && (
              <div className="mt-1 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleApprove}
                  disabled={!isPendingQc}
                >
                  ✅ Согласен
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleReject}
                  disabled={!isPendingQc}
                >
                  ❌ Не согласен
                </Button>
              </div>
            )}
          </div>

          {/* Флаги качества */}
          <div className="flex-1">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
              Флаги качества
            </div>
            <div className="max-h-64 overflow-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[11px]">
              <div className="mb-2 text-[var(--text-secondary)]">
                {qualitySummary}
              </div>
              {result.quality_flags &&
                Object.keys(result.quality_flags).length > 0 && (
                  <details>
                    <summary className="cursor-pointer text-[var(--accent-primary)]">
                      Показать тех. детали
                    </summary>
                    <pre className="mt-2 overflow-auto rounded-xl bg-[var(--bg-elevated-soft)] p-2 text-[10px] text-[var(--text-secondary)]">
                      {JSON.stringify(result.quality_flags, null, 2)}
                    </pre>
                  </details>
                )}
            </div>
          </div>

          {/* Retrieval trace */}
          {contextTrace.length > 0 && (
            <div className="flex-1">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-faint)]">
                Retrieval trace ({contextTrace.length})
              </div>
              <div className="max-h-56 space-y-1.5 overflow-auto">
                {contextTrace.map((item, i) => {
                  const score = item.score != null ? item.score : null;
                  const pct =
                    score != null ? Math.round(score * 100) : null;
                  const isTop = i === 0;
                  return (
                    <div
                      key={i}
                      className={[
                        "rounded-lg border p-2 text-[10px]",
                        isTop
                          ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)]"
                          : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={[
                            "font-medium",
                            isTop
                              ? "text-[var(--color-success-text)]"
                              : "text-[var(--text-secondary)]",
                          ].join(" ")}
                        >
                          #{(item.rank ?? i) + 1}{" "}
                          {item.clause_uid ?? item.chunk_id ?? "—"}
                        </span>
                        {pct != null && (
                          <span
                            className={[
                              "font-bold",
                              isTop
                                ? "text-[var(--color-success-text)]"
                                : "text-[var(--text-muted)]",
                            ].join(" ")}
                          >
                            {pct}%
                          </span>
                        )}
                      </div>
                      {pct != null && (
                        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--bg-card)]">
                          <div
                            className={[
                              "h-full rounded-full",
                              isTop
                                ? "bg-[var(--color-success)]"
                                : "bg-[var(--text-muted)]",
                            ].join(" ")}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      )}
                      {(item.page != null || item.segment_title) && (
                        <div className="mt-1 text-[var(--text-faint)]">
                          {item.page != null ? `Стр. ${item.page}` : ""}
                          {item.page != null && item.segment_title
                            ? " · "
                            : ""}
                          {item.segment_title ?? ""}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EvidencePanel;



