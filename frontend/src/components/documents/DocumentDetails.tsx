// =============================================================
// src/components/documents/DocumentDetails.tsx
// Правая панель деталей документа на вкладке Documents (view).
// View-компонент:
// - не дергает API-хуки, не использует useAuth
// - получает все данные и capabilities через пропсы
// - содержит только UI и локальное состояние формы / DnD
// =============================================================

import React, { useEffect, useState } from "react";
import { AlertTriangle, Loader2, Upload } from "lucide-react";
import { ProcessingTracePanel } from "./pipeline/ProcessingTracePanel";
import type { DocumentTypeOption } from "../../api/documentTypes";
import { DocumentPipelinePanel } from "./pipeline/DocumentPipelinePanel";
import {
  DOCUMENT_STATUS_CONFIG,
  getErrorStageLabel,
} from "../../utils/statusConfig";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { TriggerList } from "../ui/TriggerList";
import Button from "../ui/Button";
import { StructuredDataSection } from "./DocumentDetails/sections/StructuredDataSection";
import type {
  ClassificationLevel,
  Document,
  ExtractedValue,
  OpenViewerAtFn,
  ReclassifyInput,
  ReclassifyResult,
  SeverityLevel,
  PipelineStageViewDTO,
} from "../../types";
import { PdfPreviewModal } from "./DocumentDetails/PdfPreviewModal";
import { Section, InfoRow, FamilyRow } from "./DocumentDetails/shared";
import { HeaderSection } from "./DocumentDetails/sections/HeaderSection";
import { ReviewSection } from "./DocumentDetails/sections/ReviewSection";

// =============================================================
// Типы для view-контракта (container → view)
// =============================================================

export interface DocumentDetailsViewClassification {
  doc_type: string;
  classification_level: ClassificationLevel;
  classification_confidence: number;
  applicable_triggers: string[];
  yaml_instruction_available: boolean;
  low_confidence: boolean;
}

export interface DocumentFamilyView {
  master: Document | null;
  appendices: Document[];
  amendments: Document[];
  versions: Document[];
}

export interface StructuredDataView {
  document_id: string;
  filename: string;
  doc_type?: string;
  extracted_values: ExtractedValue[];
  total_extracted: number;
}

export interface DocumentReviewCheckView {
  checkId: string;
  checkName: string;
  result: string;
  severity: SeverityLevel | null;
  snippet: string | null;
  page: number | null;
  clauseUid: string | null;
  confidence: number | null;

  segmentId: string | null;
  segmentTitle: string | null;
  segmentType: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;

  chunkId: string | null;
  chunkIndex: number | null;

  extractedFields: Array<{
    fieldName: string;
    fieldValue: string;
    fieldFormat?: string | null;
  }>;
}

export interface DocumentReviewView {
  checks: DocumentReviewCheckView[];
  totalFail: number;
  totalUnclear: number;
  totalCritical: number;
  totalHigh: number;
}

export interface DocumentDetailsViewProps {
  documentId: string;
  dealId: string;

  doc: Document | null;
  classification: DocumentDetailsViewClassification | null;
  family: DocumentFamilyView | null;
  structuredData: StructuredDataView | null;
  structuredNotAvailable?: boolean;
  reviewData?: DocumentReviewView | null;

  availableDocTypes: DocumentTypeOption[];
  initialDocType?: string;

  isLoading: boolean;
  notFound: boolean;
  error?: string | null;

  canDownload: boolean;
  canOpenPdf: boolean;
  canReclassify: boolean;
  pdfUrl: string | null;

  onSetReviewed: (checked: boolean) => void;
  isSetReviewedPending: boolean;

  onReclassify: (input: ReclassifyInput) => Promise<void>;
  isReclassifyPending: boolean;
  lastReclassifyResult?: ReclassifyResult;

  onNavigateToGrid?: (dealId: string, docName: string) => void;
  onOpenAtLocation?: OpenViewerAtFn;
  onReplaceFile?: (file: File) => Promise<void> | void;
  onOpenReviewCell?: (checkId: string, checkName: string) => void;

  /** Открыть preview стадии pipeline в средней панели layout. */
  onOpenPipelineStagePreview?: (
    stage: PipelineStageViewDTO,
    stages: PipelineStageViewDTO[],
  ) => void;
}

// =============================================================
// Вспомогательные функции для structured data
// =============================================================

type StructuredSegmentGroup = {
  segmentKey: string;
  segmentId: string | null;
  segmentType: string | null;
  segmentTitle: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;
  values: ExtractedValue[];
};

function getSegmentLabel(segment: StructuredSegmentGroup): string {
  if (segment.segmentTitle && segment.segmentTitle.trim()) {
    return segment.segmentTitle.trim();
  }

  if (segment.segmentType && segment.segmentType.trim()) {
    return segment.segmentType.trim();
  }

  return "Документ целиком";
}

function groupExtractedValuesBySegment(
  structured: StructuredDataView | null,
): StructuredSegmentGroup[] {
  if (!structured || !structured.extracted_values.length) {
    return [];
  }

  const segmentsMap = new Map<string, StructuredSegmentGroup>();

  for (const val of structured.extracted_values) {
    const segmentKey = val.segment_id || "__whole_document__";

    if (!segmentsMap.has(segmentKey)) {
      segmentsMap.set(segmentKey, {
        segmentKey,
        segmentId: val.segment_id ?? null,
        segmentType: val.segment_type ?? null,
        segmentTitle: val.segment_title ?? null,
        segmentOrder: val.segment_order ?? null,
        isPrimarySegment: val.is_primary_segment ?? null,
        values: [],
      });
    }

    segmentsMap.get(segmentKey)!.values.push(val);
  }

  return Array.from(segmentsMap.values()).sort((a, b) => {
    if (a.segmentId === null && b.segmentId !== null) return -1;
    if (a.segmentId !== null && b.segmentId === null) return 1;

    const aOrder =
      a.segmentOrder === null || a.segmentOrder === undefined
        ? Number.MAX_SAFE_INTEGER
        : a.segmentOrder;
    const bOrder =
      b.segmentOrder === null || b.segmentOrder === undefined
        ? Number.MAX_SAFE_INTEGER
        : b.segmentOrder;

    if (aOrder !== bOrder) return aOrder - bOrder;

    return getSegmentLabel(a).localeCompare(getSegmentLabel(b), "ru");
  });
}

// =============================================================
// View-компонент (чистый UI)
// =============================================================

export const DocumentDetails: React.FC<DocumentDetailsViewProps> = ({
  documentId,
  dealId,
  doc,
  classification,
  family,
  structuredData,
  structuredNotAvailable,
  reviewData,
  isLoading,
  notFound,
  error,
  canDownload,
  canOpenPdf,
  canReclassify,
  pdfUrl,
  onSetReviewed,
  isSetReviewedPending,
  onReclassify,
  isReclassifyPending,
  lastReclassifyResult,
  onNavigateToGrid,
  onOpenReviewCell,
  onOpenAtLocation,
  onReplaceFile,
  availableDocTypes,
  initialDocType,
  onOpenPipelineStagePreview,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [showReclassifyForm, setShowReclassifyForm] = useState(false);
  const [reclassifyDocType, setReclassifyDocType] = useState(
    initialDocType || "",
  );
  const [reclassifyReason, setReclassifyReason] = useState("");
  const [activeSegmentKey, setActiveSegmentKey] = useState<string | null>(null);
  const [isPdfPreviewOpen, setIsPdfPreviewOpen] = useState(false);
  const [isDownloadingOriginal, setIsDownloadingOriginal] = useState(false);

  useEffect(() => {
    if (!isPdfPreviewOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsPdfPreviewOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isPdfPreviewOpen]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]">
        <Loader2 className="mr-2 animate-spin" size={20} />
        Загрузка…
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]">
        Документ не найден
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-[var(--accent-muted)] px-4 text-center">
        <AlertTriangle className="mb-2 text-[var(--color-error)]" size={20} />
        <p className="mb-1 text-sm font-semibold text-[var(--color-error-strong)]">
          Ошибка загрузки документа
        </p>
        <p className="max-w-sm text-xs text-[var(--text-muted)]">{error}</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--accent-muted)] text-sm text-[var(--text-muted)]">
        Документ не найден
      </div>
    );
  }

  const hasFamily: boolean =
    !!family &&
    (family.master !== null ||
      family.appendices.length > 0 ||
      family.amendments.length > 0 ||
      family.versions.length > 0);

  const lowConfidence =
    classification?.classification_confidence !== undefined &&
    classification?.classification_confidence !== null &&
    classification.classification_confidence < 0.6;

  const needsManualReview = !!doc.classification_requires_review;

  const handleFile = async (file: File) => {
    if (onReplaceFile) {
      await onReplaceFile(file);
    } else {
      console.warn("Replace file not implemented yet", file.name);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      void handleFile(file);
    }
  };

  const processingError = doc.processing_error_details || null;
  const statusConfig = DOCUMENT_STATUS_CONFIG[doc.status];

  const structuredSegments = groupExtractedValuesBySegment(structuredData);

  const resolvedActiveSegmentKey =
    activeSegmentKey &&
    structuredSegments.some((s) => s.segmentKey === activeSegmentKey)
      ? activeSegmentKey
      : structuredSegments[0]?.segmentKey ?? null;

  const handleOpenOriginalFile = () => {
    if (!pdfUrl || !canOpenPdf) return;
    setIsPdfPreviewOpen(true);
  };

  const handleDownloadOriginalFile = async () => {
    if (!pdfUrl || !canDownload || isDownloadingOriginal) return;

    try {
      setIsDownloadingOriginal(true);

      const response = await fetch(pdfUrl);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = doc.filename || "document.pdf";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      window.URL.revokeObjectURL(objectUrl);
    } catch (downloadError) {
      console.error("Failed to download original file", downloadError);
      alert("Не удалось скачать оригинал файла.");
    } finally {
      setIsDownloadingOriginal(false);
    }
  };

  return (
    <>
      <div className="h-full space-y-5 overflow-y-auto bg-[var(--bg-elevated-soft)] p-5">
        <HeaderSection
          pdfUrl={pdfUrl}
          canOpenPdf={canOpenPdf}
          canDownload={canDownload}
          isDownloadingOriginal={isDownloadingOriginal}
          onOpenOriginalFile={handleOpenOriginalFile}
          onDownloadOriginalFile={handleDownloadOriginalFile}
          onOpenInGrid={
            onNavigateToGrid
              ? () => onNavigateToGrid(dealId, doc.filename)
              : undefined
          }
        />

        <Section title="Информация">
          <InfoRow
            label="Тип документа"
            value={doc.doc_type || "Не определён"}
          />
          <InfoRow label="Язык" value={doc.language || "—"} />
          <InfoRow
            label="Страниц"
            value={doc.page_count ? String(doc.page_count) : "—"}
          />
          <InfoRow
            label="Загружен"
            value={new Date(doc.created_at).toLocaleDateString("ru-RU", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          />

          {processingError && (
            <div className="mt-3 rounded-2xl border border-[var(--color-error-soft-border)] bg-[var(--color-error-soft-bg)] px-3 py-2 text-xs text-[var(--color-error-strong)]">
              <div className="flex items-start gap-2">
                <AlertTriangle
                  size={14}
                  className="mt-0.5 shrink-0 text-[var(--color-error)]"
                />
                <div className="space-y-1">
                  <p className="font-semibold">
                    {processingError.type === "quarantine"
                      ? "Документ в карантине"
                      : "Ошибка обработки"}
                    {(() => {
                      const stageLabel = getErrorStageLabel(processingError);
                      return stageLabel && stageLabel !== "Неизвестная стадия"
                        ? ` · ${stageLabel}`
                        : "";
                    })()}
                  </p>

                  {processingError.message && (
                    <p className="break-words text-[var(--text-primary)]">
                      {processingError.message}
                    </p>
                  )}

                  <div className="flex flex-wrap gap-1 text-[11px]">
                    {processingError.reason && (
                      <span className="rounded-full bg-[var(--color-error-chip-bg)] px-2 py-0.5 text-[var(--color-error-chip-fg)]">
                        Причина: {processingError.reason}
                      </span>
                    )}
                    {processingError.timestamp && (
                      <span className="rounded-full bg-[var(--badge-neutral-bg)] px-2 py-0.5 text-[var(--text-muted)]">
                        Время:{" "}
                        {new Date(processingError.timestamp).toLocaleString(
                          "ru-RU",
                        )}
                      </span>
                    )}
                    {processingError.run_id && (
                      <span className="rounded-full bg-[var(--badge-info-bg)] px-2 py-0.5 text-[var(--badge-info-fg)]">
                        Run: {processingError.run_id}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="mt-2 flex items-center justify-between">
            <span className="font-medium text-[var(--text-primary)] text-[11px]">
              Проверка юриста не требуется
            </span>
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 cursor-pointer rounded border-[var(--border-subtle)] text-[var(--color-blue)] focus:ring-[var(--color-blue-soft)]"
                checked={!!doc.reviewed_by_person}
                disabled={isSetReviewedPending}
                onChange={(e) => onSetReviewed(e.target.checked)}
              />
            </label>
          </div>
        </Section>

        {doc.status === "language_selection_required" && (
          <Section title="Требуется действие">
            <div className="rounded-2xl border border-[var(--color-gold-soft-border)] bg-[var(--color-gold-soft-bg)] px-3 py-2.5">
              <div className="flex items-start gap-2">
                <span className="mt-0.5 text-[var(--color-gold-strong)]">
                  🌐
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-[var(--color-gold-strong)]">
                    Нужно выбрать основной язык проверки
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--color-gold-text)]">
                    {statusConfig?.description ||
                      "Загрузка документов завершена. Для документов, в которых определено несколько языков, дальнейшая обработка не будет продолжена, пока не выбран основной язык проверки. По умолчанию установлен русский язык."}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        // TODO: открыть модал/панель выбора основного языка документа
                      }}
                    >
                      Выбрать основной язык
                    </Button>

                    <span className="text-[11px] text-[var(--color-gold-text)]">
                      Текущий язык по умолчанию: русский
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </Section>
        )}

        <Section title="Классификация документа">
          <div className="space-y-3">
            {classification ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <ClassificationBadge
                    level={classification.classification_level}
                    confidence={classification.classification_confidence}
                    showConfidence
                  />
                  {classification.doc_type && (
                    <span className="text-xs font-medium text-[var(--text-primary)]">
                      {classification.doc_type}
                    </span>
                  )}
                  {needsManualReview && (
                    <span className="inline-flex items-center rounded-full border border-[var(--color-gold-soft-border)] bg-[var(--color-gold-soft-bg)] px-2 py-0.5 text-xs font-medium text-[var(--text-primary)]">
                      Нужна ручная проверка
                    </span>
                  )}
                </div>

                {classification.yaml_instruction_available ? (
                  <p className="flex items-center gap-1 text-xs text-[var(--text-primary)]">
                    ✅ YAML-инструкция загружена
                  </p>
                ) : (
                  <p className="flex items-center gap-1 text-xs text-[var(--text-primary)]">
                    ⬜ YAML-инструкция не найдена
                  </p>
                )}

                {lowConfidence && (
                  <div className="rounded-2xl border border-[var(--color-gold-soft-border)] bg-[var(--color-gold-soft-bg)] px-3 py-2">
                    <p className="text-xs text-[var(--text-primary)]">
                      ⚠️ Низкая уверенность классификации (
                      {Math.round(
                        (classification.classification_confidence || 0) * 100,
                      )}
                      %) — рекомендуется проверить тип документа
                    </p>
                  </div>
                )}

                {classification.applicable_triggers &&
                  classification.applicable_triggers.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-[var(--text-primary)]">
                        Активные триггеры (профиль документа):
                      </p>
                      <TriggerList
                        triggers={classification.applicable_triggers}
                        maxVisible={4}
                      />
                      <p className="text-xs leading-5 text-[var(--text-primary)]">
                        Тип документа и перечисленные триггеры вместе описывают 
                        сценарии по проверке документа
                      </p>
                    </div>
                  )}
              </>
            ) : (
              <p className="text-xs text-[var(--text-primary)]">
                Классификация не выполнена или документ в обработке
              </p>
            )}

            {canReclassify && !showReclassifyForm && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  setReclassifyDocType(classification?.doc_type || "");
                  setShowReclassifyForm(true);
                }}
              >
                Изменить классификацию вручную
              </Button>
            )}

            {showReclassifyForm && (
              <div className="mt-2.5 space-y-3 rounded-2xl border border-[var(--color-blue-soft-border)] bg-[var(--color-blue-soft-bg)] p-3">
                <p className="text-xs font-semibold text-[var(--color-blue-strong)]">
                  Ручная переклассификация
                </p>

                <div className="space-y-1">
                  <label className="block text-[11px] text-[var(--text-muted)]">
                    Новый тип документа
                  </label>

                  <select
                    value={reclassifyDocType}
                    onChange={(e) => setReclassifyDocType(e.target.value)}
                    className="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1.5 text-xs text-[var(--text-primary)] outline-none ring-0 focus:border-[var(--accent-primary)] focus:ring-1 focus:ring-[var(--accent-muted)]"
                  >
                    <option value="">— Выберите тип документа —</option>
                    {availableDocTypes.map((opt) => (
                      <option key={opt.type} value={opt.type}>
                        {opt.name}
                      </option>
                    ))}
                  </select>

                  {reclassifyDocType && (
                    <p className="text-[11px] text-[var(--text-faint)]">
                      Выбран код типа: <code>{reclassifyDocType}</code>
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label className="block text-[11px] text-[var(--text-muted)]">
                    Причина изменения
                  </label>
                  <textarea
                    value={reclassifyReason}
                    onChange={(e) => setReclassifyReason(e.target.value)}
                    rows={2}
                    placeholder="Опишите причину..."
                    className="w-full resize-none rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1.5 text-xs text-[var(--text-primary)] outline-none ring-0 focus:border-[var(--accent-primary)] focus:ring-1 focus:ring-[var(--accent-muted)]"
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={async () => {
                      if (!reclassifyDocType.trim()) return;
                      try {
                        await onReclassify({
                          doc_type: reclassifyDocType,
                          reason: reclassifyReason,
                        } as ReclassifyInput);
                        setShowReclassifyForm(false);
                      } catch {
                        alert("Ошибка переклассификации");
                      }
                    }}
                    disabled={!reclassifyDocType.trim() || isReclassifyPending}
                    isLoading={isReclassifyPending}
                    className="min-w-[120px]"
                  >
                    Применить
                  </Button>

                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowReclassifyForm(false)}
                    className="min-w-[120px]"
                  >
                    Отмена
                  </Button>
                </div>

                {lastReclassifyResult && (
                  <>
                    <p className="text-[11px] text-[var(--color-success)]">
                      ✅ Тип изменён на «{lastReclassifyResult.new_doc_type}»
                      {lastReclassifyResult.yaml_instruction_found
                        ? " · YAML-инструкция найдена"
                        : " · YAML-инструкция не найдена"}
                    </p>

                    <div className="mt-2 rounded-2xl border border-[var(--color-error-soft-border)] bg-[var(--color-error-soft-bg)] px-3 py-2">
                      <p className="text-[11px] text-[var(--color-error-text)]">
                        Документ переклассифицирован. Анализ рисков по новому
                        типу будет произведён только после перезапуска анализа
                        рисков по всей сделке. После будет внедрён механизм
                        отдельного пересчёта рисков по одному документу.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </Section>

        {hasFamily && family && (
          <Section title="Семейство документов">
            {family.master && (
              <FamilyRow icon="📄" label="Основной" doc={family.master} />
            )}
            {family.appendices.map((d) => (
              <FamilyRow key={d.id} icon="📎" label="Приложение" doc={d} />
            ))}
            {family.amendments.map((d) => (
              <FamilyRow key={d.id} icon="✏️" label="Дополнение" doc={d} />
            ))}
            {family.versions.map((d) => (
              <FamilyRow key={d.id} icon="🔄" label="Версия" doc={d} />
            ))}
          </Section>
        )}

        <Section title="Структурированные данные">
          <div id="document-structured-data-panel" className="sr-only" />

          <StructuredDataSection
            structuredNotAvailable={structuredNotAvailable}
            structuredData={structuredData}
            structuredSegments={structuredSegments}
            resolvedActiveSegmentKey={resolvedActiveSegmentKey}
            onSetActiveSegmentKey={setActiveSegmentKey}
            onOpenAtLocation={
              onOpenAtLocation
                ? (payload) =>
                    onOpenAtLocation({
                      documentId,
                      page: payload.page,
                      clauseUid: payload.clauseUid,
                      elementId: undefined,
                      segmentId: payload.segmentId,
                      chunkId: payload.chunkId,
                      chunkIndex: payload.chunkIndex,
                    })
                : undefined
            }
          />
        </Section>

        {reviewData && (
          <Section title="Результаты проверки">
            <ReviewSection
              documentId={documentId}
              reviewData={reviewData}
              resolvedActiveSegmentKey={resolvedActiveSegmentKey}
              onOpenReviewCell={onOpenReviewCell}
              onOpenAtLocation={onOpenAtLocation}
            />
          </Section>
        )}

        <Section title="История обработки">
          <ProcessingTracePanel documentId={documentId} />
        </Section>

        <Section title="Информационный блок по документу">
          <DocumentPipelinePanel
            documentId={documentId}
            onOpenAtLocation={onOpenAtLocation}
            onOpenStagePreview={onOpenPipelineStagePreview}
          />
        </Section>

        {doc.status === "quarantine" && (
          <Section title="Карантин / повторная загрузка">
            <div className="mb-3 rounded-2xl border border-[var(--color-error-soft-border)] bg-[var(--color-error-soft-bg)] p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle
                  size={16}
                  className="mt-0.5 shrink-0 text-[var(--color-error)]"
                />
                <div className="text-xs text-[var(--color-error-text)]">
                  <p className="mb-1 font-medium">Документ в карантине</p>
                  <p className="text-[11px]">
                    Замените файл корректной версией, чтобы запустить повторную
                    обработку.
                  </p>
                </div>
              </div>
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={`rounded-2xl border-2 border-dashed p-6 text-center transition ${
                isDragging
                  ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-subtle)]"
              }`}
            >
              <Upload
                className="mx-auto mb-2 text-[var(--text-muted)]"
                size={28}
              />
              <p className="mb-2 text-sm text-[var(--text-primary)]">
                Перетащите файл сюда
              </p>
              <label className="inline-flex cursor-pointer items-center rounded-full bg-[var(--accent-primary)] px-4 py-1.5 text-sm font-medium text-[var(--text-inverse)] transition hover:bg-[var(--accent-hover)]">
                Выбрать файл
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void handleFile(file);
                  }}
                />
              </label>
            </div>
          </Section>
        )}
      </div>

      <PdfPreviewModal
        open={isPdfPreviewOpen}
        pdfUrl={pdfUrl}
        filename={doc.filename}
        isDownloading={isDownloadingOriginal}
        onDownload={handleDownloadOriginalFile}
        onClose={() => setIsPdfPreviewOpen(false)}
      />
    </>
  );
};

export default DocumentDetails;


