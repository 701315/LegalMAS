// =============================================================
// src/api/documents.viewAdapters.ts
// Адаптеры DTO → view-типов, переиспользуются контейнером и стейт-адаптерами.
// =============================================================

import type {
  DocumentDetail,
  DocumentFamily as DocumentFamilyDto,
  StructuredDataResult,
} from "../types";
import type {
  DocumentDetailsViewClassification,
  DocumentFamilyView,
  StructuredDataView,
} from "../components/documents/DocumentDetails";

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
    master: family.master,
    appendices: family.appendices,
    amendments: family.amendments,
    versions: family.versions,
  };
}

export function adaptStructuredDataView(
  structured: StructuredDataResult | undefined,
): StructuredDataView | null {
  if (!structured) return null;
  return {
    document_id: structured.document_id,
    filename: structured.filename,
    doc_type: structured.doc_type,
    extracted_values: structured.extracted_values,
    total_extracted: structured.total_extracted,
  };
}
