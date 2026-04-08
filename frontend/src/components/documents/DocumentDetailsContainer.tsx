// =============================================================
// src/components/documents/DocumentDetailsContainer.tsx
// Контейнер для правой панели документа на вкладке Documents.
//
// Модель:
// - useDocumentDetailsState возвращает нормализованный стейт документа
// - контейнер адаптирует стейт → view-пропсы для DocumentDetails
// - structured-data теперь берём из /documents/{doc_id}/extracted-values
// =============================================================

import React from "react";
import {
  useDocumentFamily,
  useReclassifyDocument,
  useDocumentPdfUrl,
  useSetDocumentReviewed,
} from "../../api/documents";
import {
  useDocumentDetailsState,
  useStructuredDataState,
} from "../../api/documents.stateHooks";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useDocumentTypes } from "../../api/documentTypes";

import type {
  Document,
  ReclassifyInput,
} from "../../types";

import { DocumentDetails as DocumentDetailsView } from "./DocumentDetails";
import { adaptFamilyFromDto } from "../../api/documents.viewAdapters";
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

export const DocumentDetailsContainer: React.FC<Props> = ({
  docId,
  dealId,
  onNavigateToGrid,
}) => {
  // --- Стейт документа (детали + классификация) ---
  const detailsState = useDocumentDetailsState(docId);

  // --- Structured-data (извлечённые значения) ---
  const structuredState = useStructuredDataState(docId);

  // --- Типы документов для выпадающего списка переклассификации ---
  const { data: docTypesData } = useDocumentTypes();
  const availableDocTypes = docTypesData ?? [];

  // --- Дополнительные данные (DTO-хуки) ---
  const { data: familyDto } = useDocumentFamily(docId);
  const { data: pdfData } = useDocumentPdfUrl(docId);

  // --- Права доступа по сделке ---
  const {
    canDownloadDocuments,
    canReclassifyDocuments,
  } = useDealPermissions(dealId);

  // --- Capabilities ---
  const canDownload = canDownloadDocuments;
  const canOpenPdf = canDownloadDocuments;
  const canReclassify = canReclassifyDocuments;

  // --- Мутации ---
  const reclassifyMutation = useReclassifyDocument(docId);
  const setReviewedMutation = useSetDocumentReviewed(docId, dealId);

  // --- Адаптация стейтов к view-модели ---

  const doc: Document | null = detailsState.doc;
  const classification: DocumentDetailsViewClassification | null =
    detailsState.classification;

  const family: DocumentFamilyView | null = adaptFamilyFromDto(familyDto);

  let structuredData: StructuredDataView | null = null;
  if (!structuredState.isLoading && structuredState.total > 0 && doc) {
    structuredData = {
      document_id: docId,
      filename: doc.filename,
      doc_type: doc.doc_type ?? undefined,
      extracted_values: structuredState.items,
      total_extracted: structuredState.total,
    };
  }

  const structuredNotAvailable = structuredState.notAvailable;

  const handleSetReviewed = (checked: boolean) => {
    setReviewedMutation.mutate(checked);
  };

  const handleReclassify = async (input: ReclassifyInput) => {
    await reclassifyMutation.mutateAsync(input);
  };

  const handleReplaceFile = async (file: File) => {
    console.warn("Replace file not implemented yet", file.name);
  };

  const isLoading = detailsState.isLoading;

  return (
    <DocumentDetailsView
      documentId={docId}
      dealId={dealId}
      doc={doc}
      classification={classification}
      family={family}
      structuredData={structuredData}
      structuredNotAvailable={structuredNotAvailable}
      isLoading={isLoading}
      notFound={detailsState.notFound}
      error={detailsState.error}
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
      availableDocTypes={availableDocTypes}
      initialDocType={doc?.doc_type ?? ""}
    />
  );
};

export default DocumentDetailsContainer;

