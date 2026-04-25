// =============================================================
// src/api/documents.viewAdapters.ts
// Адаптеры DTO → view-типов, переиспользуются контейнером и стейт-адаптерами.
// =============================================================

import type {
  DocumentDetail,
  DocumentFamilyDto,
  StructuredDataResult,
  SeverityLevel,
} from "../types";

import type { DocumentReviewCheckCell } from "./dealReview";

import type {
  DocumentDetailsViewClassification,
  DocumentFamilyView,
  StructuredDataView,
  DocumentReviewView,
  DocumentReviewCheckView,
} from "../components/documents/DocumentDetails";

// -------------------------------------------------------------
// Shared helpers
// -------------------------------------------------------------

function isRiskSeverity(
  value: string | null | undefined,
): value is SeverityLevel {
  return (
    value === "critical" ||
    value === "high" ||
    value === "medium" ||
    value === "pass" ||
    value === "unclear"
  );
}

// -------------------------------------------------------------
// Classification
// -------------------------------------------------------------

export function adaptClassification(
  detail: DocumentDetail | undefined,
): DocumentDetailsViewClassification | null {
  if (!detail || !detail.classification) return null;

  const c = detail.classification;
  return {
    doc_type: c.doc_type,
    classification_level: c.classification_level,
    classification_confidence: c.classification_confidence,
    applicable_triggers: c.applicable_triggers ?? [],
    yaml_instruction_available: c.yaml_instruction_available,
    low_confidence: c.low_confidence,
  };
}

// -------------------------------------------------------------
// Family
// -------------------------------------------------------------

export function adaptFamily(
  detail: DocumentDetail | undefined,
): DocumentFamilyView | null {
  if (!detail || !detail.family_id) {
    return null;
  }

  // Сейчас DocumentFamily приходит отдельным запросом /family,
  // поэтому здесь можно вернуть null, а фактический family собирать
  // в контейнере по данным из useDocumentFamily. Оставляем хелпер
  // как заготовку на будущее, если backend начнёт отдавать family
  // прямо в DocumentDetail.
  return null;
}

export function adaptFamilyFromDto(
  family: DocumentFamilyDto | undefined,
): DocumentFamilyView | null {
  if (!family) return null;

  return {
    // основной документ семьи — это master_document из backend'а
    master: family.master_document ?? null,

    // пока backend не делит связанные документы на типы связей,
    // кладём всех related_documents в appendices.
    // Позже, когда появятся типизированные relations, здесь можно
    // разбить их на appendices / amendments / versions по relation_type.
    appendices: family.related_documents ?? [],

    // временно пустые списки, заранее подготовленные под будущую логику
    amendments: [],
    versions: [],
  };
}

// -------------------------------------------------------------
// Structured data
// -------------------------------------------------------------

export function adaptStructuredDataView(
  structured: StructuredDataResult | undefined,
): StructuredDataView | null {
  if (!structured) return null;

  return {
    document_id: structured.document_id,
    filename: structured.filename,
    doc_type: structured.doc_type ?? undefined,
    extracted_values: structured.extracted_values,
    total_extracted: structured.total_extracted,
  };
}

// -------------------------------------------------------------
// Review data (DD Matrix → DocumentDetails view)
// -------------------------------------------------------------

export function adaptDocumentReviewView(
  cells: DocumentReviewCheckCell[],
): DocumentReviewView {
  const checks: DocumentReviewCheckView[] = cells.map(
    ({ checkId, checkName, cell }) => ({
      checkId,
      checkName,
      result: cell.result,
      severity: isRiskSeverity(cell.severity) ? cell.severity : null,
      snippet: cell.snippet ?? null,
      page: cell.page ?? null,
      clauseUid: cell.clause_uid ?? null,
      confidence: cell.confidence ?? null,

      segmentId: cell.segment_id ?? null,
      segmentTitle: cell.segment_title ?? null,
      segmentType: cell.segment_type ?? null,
      segmentOrder: cell.segment_order ?? null,
      isPrimarySegment: cell.is_primary_segment ?? null,

      chunkId: cell.chunk_id ?? null,
      chunkIndex: cell.chunk_index ?? null,

      extractedFields: Array.isArray(cell.extracted)
        ? cell.extracted.map((field) => ({
            fieldName: field.field_name,
            fieldValue: field.field_value,
            fieldFormat: field.field_format ?? null,
          }))
        : [],
    }),
  );

  return {
    checks,
    totalFail: checks.filter((c) => c.result === "fail").length,
    totalUnclear: checks.filter((c) => c.result === "unclear").length,
    totalCritical: checks.filter((c) => c.severity === "critical").length,
    totalHigh: checks.filter((c) => c.severity === "high").length,
  };
}


