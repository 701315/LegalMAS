// =============================================================
// src/components/documents/DocumentDetailsContainer.tsx
// Контейнер для правой панели документа на вкладке Documents.
//
// Отвечает за:
// - загрузку данных (detail, family, structured-data, pdf-url)
// - взаимодействие с React Query мутациями (reclassify, setReviewed)
// - получение ролей пользователя (useAuth) и расчёт capabilities
// - адаптацию "сырых" данных к view-пропсам
//
// View-компонент (UI-часть) — DocumentDetails.tsx
// =============================================================

import React from "react";
import {
  useDocumentDetail,
  useDocumentFamily,
  useStructuredData,
  useReclassifyDocument,
  useDocumentPdfUrl,
  useSetDocumentReviewed,
} from "../../api/documents";
import { useAuth } from "../../hooks/useAuth";
import {
  canReclassify as canReclassifyHelper,
} from "../../constants";

import type {
  Document,
  DocumentDetail,
  DocumentFamily as DocumentFamilyDto,
  StructuredDataResult,
  ReclassifyInput,
} from "../../types";

import { DocumentDetails as DocumentDetailsView } from "./DocumentDetails";
import type {
  DocumentDetailsViewClassification,
  DocumentFamilyView,
  StructuredDataView,
} from "./DocumentDetails";


interface Props {
  docId: string;
  dealId: string;
  /** Опциональный callback для навигации в DD Grid с фильтром по документу. */
  onNavigateToGrid?: (dealId: string, docName: string) => void;
}

// Вспомогательные адаптеры "сырого" ответа к view-типам

function adaptClassification(
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

function adaptFamily(
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

function adaptStructuredData(
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

export const DocumentDetailsContainer: React.FC<Props> = ({
  docId,
  dealId,
  onNavigateToGrid,
}) => {
  // --- Data-хуки ---
  const { data: detail, isLoading } = useDocumentDetail(docId);
  const { data: familyDto } = useDocumentFamily(docId);
  const { data: pdfData } = useDocumentPdfUrl(docId);
  const { data: structuredDataDto } = useStructuredData(docId);

  // --- Auth / роли ---
  const { userRole } = useAuth();

  // --- Мутации ---
  const reclassifyMutation = useReclassifyDocument(docId);
  const setReviewedMutation = useSetDocumentReviewed(docId, dealId);

  // --- Capabilities на текущем этапе (пока без отдельного permission-service) ---
  const isEditorOrAdmin = userRole === "editor" || userRole === "admin";
  const canDownload = isEditorOrAdmin;
  const canOpenPdf = isEditorOrAdmin;
  const canReclassify = canReclassifyHelper(userRole);

  // --- Адаптация данных к view-модели ---
  const doc: Document | null = detail?.document ?? null;
  const classification: DocumentDetailsViewClassification | null =
    adaptClassification(detail);
  const family: DocumentFamilyView | null = adaptFamily(familyDto);
  const structuredData: StructuredDataView | null =
    adaptStructuredData(structuredDataDto);

  const handleSetReviewed = (checked: boolean) => {
    setReviewedMutation.mutate(checked);
  };

  const handleReclassify = async (input: ReclassifyInput) => {
    await reclassifyMutation.mutateAsync(input);
  };

  const handleReplaceFile = async (file: File) => {
    // TODO: сюда позже будет подключён useReplaceDocument
    console.warn("Replace file not implemented yet", file.name);
  };

  return (
    <DocumentDetailsView
      dealId={dealId}
      doc={doc}
      classification={classification}
      family={family}
      structuredData={structuredData}
      isLoading={isLoading}
      canDownload={canDownload}
      canOpenPdf={canOpenPdf}
      canReclassify={canReclassify}
      pdfUrl={pdfData?.url ?? null}
      onSetReviewed={handleSetReviewed}
      isSetReviewedPending={setReviewedMutation.isPending}
      onReclassify={handleReclassify}
      isReclassifyPending={reclassifyMutation.isPending}
      lastReclassifyResult={
        reclassifyMutation.isSuccess
          ? reclassifyMutation.data ?? undefined
          : undefined
      }
      onNavigateToGrid={onNavigateToGrid}
      onReplaceFile={handleReplaceFile}
    />
  );
};

export default DocumentDetailsContainer;
