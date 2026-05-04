// =============================================================
// src/components/documents/DocumentDetails.tsx
// Правая панель деталей документа на вкладке Documents (view).
// View-компонент:
// - не дергает API-хуки, не использует useAuth
// - получает все данные и capabilities через пропсы
// - содержит только UI и локальное состояние формы / DnD
// =============================================================

import React, { useMemo, useState } from "react";
import { ReviewCheckCard } from "./ReviewCheckCard";

import {
  FileText,
  Download,
  ExternalLink,
  Loader2,
  AlertTriangle,
  Upload,
} from "lucide-react";
import type { DocumentTypeOption } from "../../api/documentTypes";
import { DocumentPipelinePanel } from "./pipeline/DocumentPipelinePanel";

import {
  DOCUMENT_STATUS_CONFIG,
  getErrorStageLabel,
} from "../../utils/statusConfig";

import { ClassificationBadge } from "../ui/ClassificationBadge";
import { TriggerList } from "../ui/TriggerList";

import type {
  Document,
  ReclassifyInput,
  ClassificationLevel,
  ReclassifyResult,
  ExtractedValue,
  SeverityLevel,
  OpenViewerAtFn,
} from "../../types";

// =============================================================
// Типы для view-контракта (container → view)
// =============================================================

/**
 * Упрощённое представление классификации для view.
 * Основано на ClassificationMetadata из types/index.ts.
 *
 * Важно:
 * - Пара (doc_type, applicable_triggers) представляет собой
 *   «профиль документа» для фронта.
 *   doc_type  — базовый тип (например, "contract_1.6_real_estate").
 *   applicable_triggers — активные сценарии для этого документа
 *   (ипотека, маткапитал, наследование, судебная продажа и т.п.).
 * - UI может использовать этот профиль, чтобы показывать:
 *   * тип документа,
 *   * и набор сценариев/тегов рядом.
 */
export interface DocumentDetailsViewClassification {
  doc_type: string;
  classification_level: ClassificationLevel;
  classification_confidence: number;
  applicable_triggers: string[];
  yaml_instruction_available: boolean;
  low_confidence: boolean;
}

/**
 * Семейство документов в виде, удобном для рендера.
 * Совместимо с DocumentFamily из types/index.ts.
 */
export interface DocumentFamilyView {
  master: Document | null;
  appendices: Document[];
  amendments: Document[];
  versions: Document[];
}

/**
 * Структурированные данные для view.
 * Совместимо со StructuredDataResult из types/index.ts.
 */
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
  result: string; // "fail" | "unclear" | "pass"
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
  checks: DocumentReviewCheckView[]; // только fail/unclear
  totalFail: number;
  totalUnclear: number;
  totalCritical: number;
  totalHigh: number;
}

/**
 * Полный набор пропсов, которые должен получать
 * чистый view-компонент DocumentDetails.
 */
export interface DocumentDetailsViewProps {
  documentId: string;
  dealId: string;

  // Основные данные документа
  doc: Document | null;
  classification: DocumentDetailsViewClassification | null;
  family: DocumentFamilyView | null;
  structuredData: StructuredDataView | null;
  structuredNotAvailable?: boolean;
  /** Review data поверх dd-matrix DTO. Опционален — появляется только на Review вкладке. */
  reviewData?: DocumentReviewView | null;

  // Список доступных типов документов для ручной переклассификации.
  availableDocTypes: DocumentTypeOption[];
  initialDocType?: string;

  // Состояния загрузки / ошибок
  isLoading: boolean;
  notFound: boolean;
  error?: string | null;

  // Права и действия
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
  /** Открыть детали ячейки в DD Matrix side panel. */
  onOpenReviewCell?: (checkId: string, checkName: string) => void;
}

// =============================================================
// Вспомогательные функции для structured data
// =============================================================

/**
 * Человекочитаемые заголовки для групп структурированных данных.
 * Ключ — check_id или check_name из backend, значение — короткий русскоязычный заголовок.
 */
const STRUCTURED_CHECK_TITLES: Record<string, string> = {
  overall_risk: "Общий уровень риска",
  confidentiality: "Конфиденциальность",
  governing_law: "Применимое право и подсудность",
  authority_and_approvals: "Полномочия и корпоративные одобрения",
  price_and_payment: "Цена и порядок оплаты",
  real_estate_core: "Основные параметры объекта недвижимости",
};

type StructuredSegmentGroup = {
  segmentKey: string;
  segmentId: string | null;
  segmentType: string | null;
  segmentTitle: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;
  values: ExtractedValue[];
};

function getStructuredGroupTitle(checkName: string): string {
  const key = checkName.trim();
  if (STRUCTURED_CHECK_TITLES[key]) {
    return STRUCTURED_CHECK_TITLES[key];
  }
  return checkName || "Другие параметры";
}

function getSegmentLabel(segment: StructuredSegmentGroup): string {
  if (segment.segmentTitle && segment.segmentTitle.trim()) {
    return segment.segmentTitle.trim();
  }

  if (segment.segmentType && segment.segmentType.trim()) {
    return segment.segmentType.trim();
  }

  return "Документ целиком";
}

function getSegmentMetaLabel(segment: StructuredSegmentGroup): string | null {
  const parts: string[] = [];

  if (segment.isPrimarySegment) {
    parts.push("Основной сегмент");
  }

  if (segment.segmentType && segment.segmentTitle) {
    parts.push(segment.segmentType);
  }

  if (segment.segmentOrder !== null && segment.segmentOrder !== undefined) {
    parts.push(`Порядок: ${segment.segmentOrder}`);
  }

  return parts.length ? parts.join(" · ") : null;
}

/**
 * Группировка извлечённых значений сначала по сегменту,
 * затем внутри сегмента — по проверке.
 */
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

/**
 * Группировка значений внутри конкретного сегмента по проверке.
 */
function groupSegmentValuesByCheck(
  values: ExtractedValue[],
): Record<string, ExtractedValue[]> {
  return values.reduce<Record<string, ExtractedValue[]>>((acc, val) => {
    const rawKey = val.check_name || val.check_id || "other";
    const groupKey = getStructuredGroupTitle(rawKey);

    if (!acc[groupKey]) {
      acc[groupKey] = [];
    }

    acc[groupKey].push(val);
    return acc;
  }, {});
}

function getCompositionBannerText(segments: StructuredSegmentGroup[]): string {
  const actualSegments = segments.filter((s) => s.segmentId !== null);

  if (actualSegments.length <= 1) {
    return "Single-document";
  }

  return `Multi-document · ${actualSegments.length} segments`;
}

function getPrimarySegment(
  segments: StructuredSegmentGroup[],
): StructuredSegmentGroup | null {
  return (
    segments.find((segment) => segment.isPrimarySegment) ??
    segments.find((segment) => segment.segmentId !== null) ??
    null
  );
}

function getCompositionBannerDescription(
  segments: StructuredSegmentGroup[],
): string {
  const actualSegments = segments.filter((s) => s.segmentId !== null);

  if (actualSegments.length <= 1) {
    return "Файл анализируется как единый документ. Извлечённые значения показаны в одном общем контексте.";
  }

  return "Файл содержит несколько логических сегментов. Извлечённые значения сгруппированы по сегментам.";
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
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [showReclassifyForm, setShowReclassifyForm] = useState(false);
  const [reclassifyDocType, setReclassifyDocType] = useState(
    initialDocType || "",
  );
  const [reclassifyReason, setReclassifyReason] = useState("");

  // Активный сегмент для structured data tabs
  const [activeSegmentKey, setActiveSegmentKey] = useState<string | null>(null);

  const sortedReviewChecks = useMemo(() => {
    if (!reviewData?.checks?.length) return [];

    const severityRank: Record<string, number> = {
      critical: 0,
      high: 1,
      medium: 2,
      unclear: 3,
      pass: 4,
    };

    return [...reviewData.checks].sort((a, b) => {
      const aRank = severityRank[a.severity ?? a.result] ?? 99;
      const bRank = severityRank[b.severity ?? b.result] ?? 99;
      if (aRank !== bRank) return aRank - bRank;

      const aSeg = a.segmentOrder ?? Number.MAX_SAFE_INTEGER;
      const bSeg = b.segmentOrder ?? Number.MAX_SAFE_INTEGER;
      if (aSeg !== bSeg) return aSeg - bSeg;

      return a.checkName.localeCompare(b.checkName, "ru");
    });
  }, [reviewData]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-[var(--text-muted)]">
        <Loader2 className="mr-2 animate-spin" size={20} />
        Загрузка…
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
        Документ не найден
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-4 text-center">
        <AlertTriangle className="mb-2 text-[var(--color-error)]" size={20} />
        <p className="mb-1 text-sm text-[var(--color-error-strong)]">
          Ошибка загрузки документа
        </p>
        <p className="max-w-sm text-xs text-[var(--text-muted)]">{error}</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
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
  const statusHint =
    doc.status === "completed"
      ? "Проверки по playbook выполнены. Ниже доступны результаты анализа и DD Grid."
      : doc.status === "classified"
      ? "Классификация выполнена. Проверки по playbook могут ещё выполняться или не запускались."
      : null;

  const hasReviewData = !!reviewData && reviewData.checks.length > 0;

  const structuredSegments = groupExtractedValuesBySegment(structuredData);

  // ВАЖНО:
  // multi-segment для UI считаем по числу отображаемых групп,
  // а не только по числу "реальных" segment_id.
  // Это значит: если у пользователя есть больше одной вкладки,
  // мы показываем tabs.
  const hasMultipleSegments = structuredSegments.length > 1;

  const primarySegment = getPrimarySegment(structuredSegments);
  const primarySegmentLabel = primarySegment ? getSegmentLabel(primarySegment) : null;
  const compositionText = getCompositionBannerText(structuredSegments);
  const compositionDescription =
    getCompositionBannerDescription(structuredSegments);

  const resolvedActiveSegmentKey =
    activeSegmentKey &&
    structuredSegments.some((s) => s.segmentKey === activeSegmentKey)
      ? activeSegmentKey
      : structuredSegments[0]?.segmentKey ?? null;

  const visibleSegments = resolvedActiveSegmentKey
    ? structuredSegments.filter((s) => s.segmentKey === resolvedActiveSegmentKey)
    : structuredSegments;

  const visibleReviewChecks = resolvedActiveSegmentKey
    ? sortedReviewChecks.filter(
        (check) =>
          (check.segmentId ?? "__whole_document__") === resolvedActiveSegmentKey,
      )
    : sortedReviewChecks;

  const handleOpenExtractedValue = (
    val: ExtractedValue,
    segment: StructuredSegmentGroup,
  ) => {
    if (!onOpenAtLocation) return;

    onOpenAtLocation({
      documentId,
      page: val.page ?? undefined,
      clauseUid: val.clause_uid ?? undefined,
      elementId: undefined,
      segmentId: segment.segmentId ?? undefined,
      chunkId: val.chunk_id ?? undefined,
      chunkIndex: val.chunk_index ?? undefined,
    });
  };

  return (
    <div className="h-full space-y-5 overflow-y-auto bg-[var(--bg-base)] p-5">
      {/* Хедер документа */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="break-words text-base font-semibold text-[var(--text-primary)]">
            {doc.filename}
          </h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-faint)]">
            {doc.folder_path || "/"}
          </p>
        </div>

        <div className="shrink-0 space-y-1 text-right">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              statusConfig
                ? statusConfig.color === "success"
                  ? "bg-[var(--badge-success-bg)] text-[var(--badge-success-fg)]"
                  : statusConfig.color === "warning"
                  ? "bg-[var(--badge-warning-bg)] text-[var(--badge-warning-fg)]"
                  : statusConfig.color === "error"
                  ? "bg-[var(--badge-error-bg)] text-[var(--badge-error-fg)]"
                  : statusConfig.color === "info"
                  ? "bg-[var(--badge-info-bg)] text-[var(--badge-info-fg)]"
                  : "bg-[var(--badge-neutral-bg)] text-[var(--badge-neutral-fg)]"
                : "bg-[var(--badge-neutral-bg)] text-[var(--badge-neutral-fg)]"
            }`}
          >
            {statusConfig ? statusConfig.label : doc.status}
          </span>

          {statusHint && (
            <p className="max-w-[220px] text-[11px] text-[var(--text-muted)]">
              {statusHint}
            </p>
          )}
        </div>
      </div>

      {/* Информация */}
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
          <span className="text-xs text-[var(--text-muted)]">
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

      {/* Требуется действие (язык) */}
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
                  <button
                    type="button"
                    className="inline-flex items-center rounded-full bg-[var(--color-gold-strong)] px-3 py-1.5 text-[11px] font-medium text-white hover:bg-[var(--color-gold-deep)]"
                    onClick={() => {
                      // TODO: открыть модал/панель выбора основного языка документа
                    }}
                  >
                    Выбрать основной язык
                  </button>

                  <span className="text-[11px] text-[var(--color-gold-text)]">
                    Текущий язык по умолчанию: русский
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Section>
      )}

      {/* Классификация */}
      <Section title="Классификация документа">
        {classification ? (
          <div className="space-y-3">
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
                <span className="inline-flex items-center rounded-full border border-[var(--color-gold-soft-border)] bg-[var(--color-gold-soft-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-gold-strong)]">
                  Нужна ручная проверка
                </span>
              )}
            </div>

            {statusHint && (
              <p className="text-xs text-[var(--text-muted)]">{statusHint}</p>
            )}

            {classification.yaml_instruction_available ? (
              <p className="flex items-center gap-1 text-[11px] text-[var(--color-success)]">
                ✅ YAML-инструкция загружена
              </p>
            ) : (
              <p className="flex items-center gap-1 text-[11px] text-[var(--text-faint)]">
                ⬜ YAML-инструкция не найдена
              </p>
            )}

            {lowConfidence && (
              <div className="rounded-2xl border border-[var(--color-gold-soft-border)] bg-[var(--color-gold-soft-bg)] px-3 py-2">
                <p className="text-[11px] text-[var(--color-gold-strong)]">
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
                  <p className="text-[11px] text-[var(--text-faint)]">
                    Активные триггеры (профиль документа):
                  </p>
                  <TriggerList
                    triggers={classification.applicable_triggers}
                    maxVisible={4}
                  />
                  <p className="text-[11px] leading-4 text-[var(--text-faint)]">
                    Для непрофессионального пользователя: тип документа и эти
                    триггеры вместе описывают сценарии по документу (ипотека,
                    маткапитал, наследование, судебная продажа и т.п.).
                  </p>
                </div>
              )}

            {canReclassify && !showReclassifyForm && (
              <button
                type="button"
                onClick={() => {
                  setReclassifyDocType(classification.doc_type || "");
                  setShowReclassifyForm(true);
                }}
                className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-blue)] hover:underline"
              >
                ✏️ Переклассифицировать вручную
              </button>
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
                    className="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1.5 text-xs text-[var(--text-primary)] outline-none ring-0 focus:border-[var(--color-blue)] focus:ring-1 focus:ring-[var(--color-blue-soft)]"
                  >
                    <option value="">
                      — Выберите тип документа —
                    </option>
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
                    className="w-full resize-none rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1.5 text-xs text-[var(--text-primary)] outline-none ring-0 focus:border-[var(--color-blue)] focus:ring-1 focus:ring-[var(--color-blue-soft)]"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
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
                    disabled={
                      !reclassifyDocType.trim() || isReclassifyPending
                    }
                    className="flex-1 rounded-full bg-[var(--color-blue)] py-1.5 text-[11px] font-medium text-white transition hover:bg-[var(--color-blue-deep)] disabled:opacity-60"
                  >
                    {isReclassifyPending ? "Сохранение…" : "Применить"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowReclassifyForm(false)}
                    className="rounded-full border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] font-medium text-[var(--text-muted)] hover:bg-[var(--bg-subtle)]"
                  >
                    Отмена
                  </button>
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
        ) : (
          <p className="text-xs text-[var(--text-faint)]">
            Классификация не выполнена или документ в обработке
          </p>
        )}
      </Section>

      {/* Семейство документов */}
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

      {/* Структурированные данные */}
      <Section title="Структурированные данные">
        {structuredNotAvailable ? (
          <p className="text-xs text-[var(--text-faint)]">
            Для этого документа пока нет извлечённых значений. Запустите анализ
            или обновите страницу после завершения проверки.
          </p>
        ) : structuredData && structuredData.extracted_values.length > 0 ? (
          (() => {
            return (
              <div className="space-y-3">
                <div className="rounded-2xl border border-[var(--color-blue-soft-border)] bg-[var(--color-blue-soft-bg)] px-3 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] font-medium text-[var(--color-blue-strong)]">
                      Состав файла
                    </span>
                    <span className="text-[11px] text-[var(--color-blue-text)]">
                      {compositionText}
                    </span>
                  </div>

                  <p className="mt-1 text-[10px] leading-5 text-[var(--color-blue-text)]">
                    {compositionDescription}
                  </p>

                  {primarySegmentLabel && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-[10px] text-[var(--color-blue-text)]">
                        Основной сегмент:
                      </span>
                      <span className="inline-flex items-center rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-medium text-[var(--color-blue-strong)] shadow-sm">
                        {primarySegmentLabel}
                      </span>
                    </div>
                  )}
                </div>

                {hasMultipleSegments && (
                  <div className="space-y-1.5">
                    <div className="text-[11px] font-medium text-[var(--text-muted)]">
                      Сегменты
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {structuredSegments.map((segment) => {
                        const label = getSegmentLabel(segment);
                        const isActive =
                          resolvedActiveSegmentKey === segment.segmentKey;

                        return (
                          <button
                            key={segment.segmentKey}
                            type="button"
                            onClick={() =>
                              setActiveSegmentKey(segment.segmentKey)
                            }
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition ${
                              isActive
                                ? "bg-[var(--color-blue)] text-white shadow-sm"
                                : "bg-[var(--badge-neutral-bg)] text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]"
                            }`}
                          >
                            <span>{label}</span>
                            {segment.isPrimarySegment && (
                              <span
                                className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                                  isActive
                                    ? "bg-white/20 text-white"
                                    : "bg-[var(--color-blue-soft-bg)] text-[var(--color-blue-strong)]"
                                }`}
                              >
                                Основной
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
                  {visibleSegments.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-4 text-center">
                      <p className="text-xs font-medium text-[var(--text-muted)]">
                        Для выбранного сегмента пока нет данных.
                      </p>
                      <p className="mt-1 text-[11px] text-[var(--text-faint)]">
                        Попробуйте выбрать другой сегмент или обновите страницу
                        после завершения анализа.
                      </p>
                    </div>
                  ) : (
                    visibleSegments.map((segment) => {
                      const groups = groupSegmentValuesByCheck(segment.values);
                      const groupEntries = Object.entries(groups);
                      const segmentLabel = getSegmentLabel(segment);
                      const segmentMeta = getSegmentMetaLabel(segment);

                      return (
                        <div
                          key={segment.segmentKey}
                          className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2.5"
                        >
                          <div className="mb-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-xs font-semibold text-[var(--text-primary)]">
                                {segmentLabel}
                              </p>

                              {segment.isPrimarySegment && (
                                <span className="inline-flex items-center rounded-full bg-[var(--color-blue-soft-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-blue-strong)]">
                                  Основной сегмент
                                </span>
                              )}
                            </div>

                            {segmentMeta && (
                              <p className="mt-0.5 text-[11px] text-[var(--text-faint)]">
                                {segmentMeta}
                              </p>
                            )}

                            {segment.segmentId && (
                              <p className="mt-0.5 text-[10px] text-[var(--text-faint)]">
                                segment_id: {segment.segmentId}
                              </p>
                            )}
                          </div>

                          {groupEntries.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3 text-center">
                              <p className="text-xs text-[var(--text-muted)]">
                                В этом сегменте пока нет извлечённых значений.
                              </p>
                            </div>
                          ) : (
                            <div className="space-y-2">
                              {groupEntries.map(([groupTitle, values]) => (
                                <div
                                  key={`${segment.segmentKey}-${groupTitle}`}
                                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-2"
                                >
                                  <p className="mb-1 text-xs font-semibold text-[var(--text-primary)]">
                                    {groupTitle}
                                  </p>

                                  <div className="space-y-0.5">
                                    {values.map((val, idx) => (
                                      <div
                                        key={`${val.check_id}-${val.field_name}-${idx}`}
                                        className="flex justify-between gap-3 border-b border-[var(--border-subtle)] py-1 text-[11px] last:border-0"
                                      >
                                        <div className="min-w-0 flex-1">
                                          <span className="text-[var(--text-faint)]">
                                            {val.field_name.replace(/_/g, " ")}
                                          </span>

                                          {(val.page || val.clause_uid) && (
                                            <div className="mt-0.5 text-[10px] text-[var(--text-faint)]">
                                              {val.page
                                                ? `стр. ${val.page}`
                                                : ""}
                                              {val.page && val.clause_uid
                                                ? " · "
                                                : ""}
                                              {val.clause_uid
                                                ? `clause: ${val.clause_uid}`
                                                : ""}
                                            </div>
                                          )}
                                        </div>

                                        <div className="flex max-w-[60%] shrink-0 items-start gap-2">
                                          <span className="break-words text-right text-[11px] font-medium text-[var(--text-primary)]">
                                            {val.field_value}
                                          </span>

                                          {onOpenAtLocation && (
                                            <button
                                              type="button"
                                              onClick={() =>
                                                handleOpenExtractedValue(
                                                  val,
                                                  segment,
                                                )
                                              }
                                              className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-blue)] hover:border-[var(--color-blue-soft-border)] hover:bg-[var(--color-blue-soft-bg)]"
                                              title="Открыть в документе"
                                            >
                                              Открыть в документе
                                            </button>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })()
        ) : (
          <p className="text-xs text-[var(--text-faint)]">
            Структурированные данные находятся в обработке. Обновите страницу
            через несколько минут после завершения анализа.
          </p>
        )}
      </Section>

      {/* Результаты проверки */}
      {reviewData && (
        <Section title="Результаты проверки">
          {!hasReviewData ? (
            <p className="text-xs text-[var(--text-faint)]">
              Для этого документа пока нет review-результатов в DD Matrix.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {reviewData.totalCritical > 0 && (
                  <span className="inline-flex items-center rounded-full bg-[var(--badge-error-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--badge-error-fg)]">
                    Critical: {reviewData.totalCritical}
                  </span>
                )}
                {reviewData.totalHigh > 0 && (
                  <span className="inline-flex items-center rounded-full bg-[var(--badge-warning-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--badge-warning-fg)]">
                    High: {reviewData.totalHigh}
                  </span>
                )}
                {reviewData.totalUnclear > 0 && (
                  <span className="inline-flex items-center rounded-full bg-[var(--badge-info-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--badge-info-fg)]">
                    Unclear: {reviewData.totalUnclear}
                  </span>
                )}
                {reviewData.totalFail > 0 && (
                  <span className="inline-flex items-center rounded-full bg-[var(--badge-neutral-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-primary)]">
                    Fail: {reviewData.totalFail}
                  </span>
                )}
              </div>

              <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {visibleReviewChecks.map((check) => (
                  <ReviewCheckCard
                    key={`${check.checkId}-${check.segmentId ?? "doc"}-${
                      check.chunkId ?? "chunk"
                    }`}
                    check={check}
                    documentId={documentId}
                    onOpenCell={onOpenReviewCell}
                    onOpenAtLocation={onOpenAtLocation}
                  />
                ))}
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Информационный блок по документу */}
      <Section title="Информационный блок по документу">
        <DocumentPipelinePanel
          documentId={documentId}
          onOpenAtLocation={onOpenAtLocation}
        />
      </Section>

      {/* Действия */}
      <Section title="Действия">
        <div className="flex flex-col gap-2">
          {pdfUrl && canOpenPdf && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-full bg-[var(--color-blue)] px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[var(--color-blue-deep)]"
            >
              <FileText size={16} />
              Открыть PDF
            </a>
          )}

          {pdfUrl && canDownload && (
            <a
              href={pdfUrl}
              download={doc.filename}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-full bg-[var(--bg-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <Download size={16} />
              Скачать
            </a>
          )}

          {onNavigateToGrid && (
            <button
              type="button"
              onClick={() => onNavigateToGrid(dealId, doc.filename)}
              className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-[var(--color-blue)] hover:underline"
            >
              Открыть в DD Grid <ExternalLink size={12} />
            </button>
          )}
        </div>
      </Section>

      {/* Карантин / повторная загрузка */}
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
                ? "border-[var(--color-blue)] bg-[var(--color-blue-soft-bg)]"
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
            <label className="inline-flex cursor-pointer items-center rounded-full bg-[var(--color-blue)] px-4 py-1.5 text-sm font-medium text-white transition hover:bg-[var(--color-blue-deep)]">
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
  );
};

// =============================================================
// Вспомогательные компоненты
// =============================================================

interface SectionProps {
  title: string;
  children: React.ReactNode;
}

const Section: React.FC<SectionProps> = ({ title, children }) => (
  <section className="space-y-1.5">
    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-faint)]">
      {title}
    </h4>
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 shadow-xs">
      {children}
    </div>
  </section>
);

interface InfoRowProps {
  label: string;
  value: string;
}

const InfoRow: React.FC<InfoRowProps> = ({ label, value }) => (
  <div className="flex justify-between py-0.5 text-[11px]">
    <span className="text-[var(--text-faint)]">{label}</span>
    <span className="max-w-[60%] break-words text-right font-medium text-[var(--text-primary)]">
      {value}
    </span>
  </div>
);

interface FamilyRowProps {
  icon: string;
  label: string;
  doc: Document;
}

const FamilyRow: React.FC<FamilyRowProps> = ({ icon, label, doc }) => (
  <div className="flex items-center justify-between border-b border-[var(--border-subtle)] py-1 text-xs last:border-0">
    <div className="flex min-w-0 items-center gap-2">
      <span className="text-base">{icon}</span>
      <div className="min-w-0">
        <p className="truncate text-[var(--text-primary)]">{doc.filename}</p>
        <p className="truncate text-[10px] text-[var(--text-faint)]">
          {label} · {doc.doc_type || "тип не указан"}
        </p>
      </div>
    </div>
  </div>
);

export default DocumentDetails;


