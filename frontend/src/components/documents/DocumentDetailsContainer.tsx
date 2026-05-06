// =============================================================
// src/components/documents/DocumentDetailsContainer.tsx
// Контейнер для правой панели документа на вкладке Documents.
//
// Модель:
// - useDocumentDetailsState возвращает нормализованный стейт документа
// - контейнер адаптирует state → view props для DocumentDetails
// - structured-data берём из /documents/{doc_id}/extracted-values
// - review-data берём из dd-matrix DTO (document-scoped adapter)
// =============================================================

import React, { useMemo } from "react";

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
import { selectDocumentReviewCells } from "../../api/dealReview";
import {
  adaptFamilyFromDto,
  adaptDocumentReviewView,
} from "../../api/documents.viewAdapters";

import type {
  Document,
  ReclassifyInput,
  OpenViewerAtFn,
  PipelineStageViewDTO,
} from "../../types";
import type { DDMatrixResponseDTO } from "../../types/dealReview";

import { DocumentDetails as DocumentDetailsView } from "./DocumentDetails";
import type {
  DocumentDetailsViewClassification,
  DocumentFamilyView,
  StructuredDataView,
  DocumentReviewView,
} from "./DocumentDetails";

interface Props {
  docId: string;
  dealId: string;

  /** Опциональный callback для навигации в DD Grid с фильтром по документу. */
  onNavigateToGrid?: (dealId: string, docName: string) => void;

  /** Опциональный callback для открытия viewer в точке документа. */
  onOpenAtLocation?: OpenViewerAtFn;

  /** Открыть preview стадии pipeline в средней панели layout. */
  onOpenPipelineStagePreview?: (
    stage: PipelineStageViewDTO,
    stages: PipelineStageViewDTO[],
  ) => void;

  /** DD Matrix data, если контейнер используется в review-контексте. */
  ddMatrix?: DDMatrixResponseDTO | null;

  /** Открыть детали review-ячейки (например, DDMatrixCellDetails). */
  onOpenReviewCell?: (checkId: string, checkName: string) => void;
}

export const DocumentDetailsContainer: React.FC<Props> = ({
  docId,
  dealId,
  onNavigateToGrid,
  onOpenAtLocation,
  onOpenPipelineStagePreview,
  ddMatrix,
  onOpenReviewCell,
}) => {
  // --- Основной state документа ---
  const detailsState = useDocumentDetailsState(docId);

  // --- Structured-data / extracted values ---
  const structuredState = useStructuredDataState(docId);

  // --- Справочник типов документов ---
  const { data: docTypesData } = useDocumentTypes();
  const availableDocTypes = docTypesData ?? [];

  // --- Дополнительные DTO-данные ---
  const { data: familyDto } = useDocumentFamily(docId);
  const { data: pdfData } = useDocumentPdfUrl(docId);

  // --- Права доступа ---
  const { canDownloadDocuments, canReclassifyDocuments } =
    useDealPermissions(dealId);

  const canDownload = canDownloadDocuments;
  const canOpenPdf = canDownloadDocuments;
  const canReclassify = canReclassifyDocuments;

  // --- Мутации ---
  const reclassifyMutation = useReclassifyDocument(docId);
  const setReviewedMutation = useSetDocumentReviewed(docId, dealId);

  // --- Базовая view-model ---
  const doc: Document | null = detailsState.doc;
  const classification: DocumentDetailsViewClassification | null =
    detailsState.classification;

  const family: DocumentFamilyView | null = useMemo(
    () => adaptFamilyFromDto(familyDto),
    [familyDto],
  );

  const structuredData: StructuredDataView | null = useMemo(() => {
    if (structuredState.isLoading || structuredState.total <= 0 || !doc) {
      return null;
    }

    return {
      document_id: docId,
      filename: doc.filename,
      doc_type: doc.doc_type ?? undefined,
      extracted_values: structuredState.items,
      total_extracted: structuredState.total,
    };
  }, [
    doc,
    docId,
    structuredState.isLoading,
    structuredState.items,
    structuredState.total,
  ]);

  const structuredNotAvailable = structuredState.notAvailable;

  const reviewData: DocumentReviewView | null = useMemo(() => {
    if (!ddMatrix || !docId) return null;

    const cells = selectDocumentReviewCells(ddMatrix, docId);
    if (!cells.length) return null;

    return adaptDocumentReviewView(cells);
  }, [ddMatrix, docId]);

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
  const lastReclassifyResult = reclassifyMutation.isSuccess
    ? reclassifyMutation.data ?? undefined
    : undefined;

  const resolvedPdfUrl =
    typeof pdfData === "string" ? pdfData : pdfData?.url ?? null;

  return (
    <DocumentDetailsView
      documentId={docId}
      dealId={dealId}
      doc={doc}
      classification={classification}
      family={family}
      structuredData={structuredData}
      structuredNotAvailable={structuredNotAvailable}
      reviewData={reviewData}
      isLoading={isLoading}
      notFound={detailsState.notFound}
      error={detailsState.error}
      canDownload={canDownload}
      canOpenPdf={canOpenPdf}
      canReclassify={canReclassify}
      pdfUrl={resolvedPdfUrl}
      onSetReviewed={handleSetReviewed}
      isSetReviewedPending={setReviewedMutation.isPending}
      onReclassify={handleReclassify}
      isReclassifyPending={reclassifyMutation.isPending}
      lastReclassifyResult={lastReclassifyResult}
      onNavigateToGrid={onNavigateToGrid}
      onOpenAtLocation={onOpenAtLocation}
      onOpenPipelineStagePreview={onOpenPipelineStagePreview}
      onOpenReviewCell={onOpenReviewCell}
      onReplaceFile={handleReplaceFile}
      availableDocTypes={availableDocTypes}
      initialDocType={doc?.doc_type ?? ""}
    />
  );
};

export default DocumentDetailsContainer;



