// =============================================================
// src/components/documents/DocumentDetailsContainer.tsx
// Контейнер для правой панели документа на вкладке Documents.
//
// Новая модель:
// - useDocumentDetailsState / useStructuredDataState возвращают
//   нормализованный стейт (DocumentDetailsState, StructuredDataState)
// - контейнер адаптирует стейт → view-пропсы для DocumentDetails
// =============================================================

import React from "react";
import {
  // DTO-хуки для других данных оставляем как есть
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

import type {
  Document,
  DocumentFamily as DocumentFamilyDto,
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

// Вспомогательный адаптер семейства документов (DTO -> view-тип)
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

export const DocumentDetailsContainer: React.FC<Props> = ({
  docId,
  dealId,
  onNavigateToGrid,
}) => {
  // --- Data-хуки на стейтах ---
  const detailsState = useDocumentDetailsState(docId); // DocumentDetailsState
  const structuredState = useStructuredDataState(docId); // StructuredDataState

  // --- Дополнительные данные (DTO-хуки) ---
  const { data: familyDto } = useDocumentFamily(docId);
  const { data: pdfData } = useDocumentPdfUrl(docId);

  // --- Права доступа по сделке ---
  const {
    canDownloadDocuments,
    canReclassifyDocuments,
  } = useDealPermissions(dealId);

  // --- Мутации ---
  const reclassifyMutation = useReclassifyDocument(docId);
  const setReviewedMutation = useSetDocumentReviewed(docId, dealId);

  // --- Capabilities ---
  const canDownload = canDownloadDocuments;
  const canOpenPdf = canDownloadDocuments;
  const canReclassify = canReclassifyDocuments;


  // --- Адаптация стейтов к view-модели ---

  // Детали документа и классификация — из нормализованного стейта
  const doc: Document | null = detailsState.doc;
  const classification: DocumentDetailsViewClassification | null =
    detailsState.classification;

  // Семейство документов — по-прежнему отдельным запросом
  const family: DocumentFamilyView | null = adaptFamily(
    familyDto as DocumentFamilyDto | undefined,
  );

  // Структурированные данные из стейта:
  // - если isLoading / error / notAvailable → не показываем блок (на этом этапе)
  let structuredData: StructuredDataView | null = null;
  if (
    !structuredState.isLoading &&
    !structuredState.error &&
    !structuredState.notAvailable
  ) {
    structuredData = {
      document_id: doc?.id ?? "",
      filename: doc?.filename ?? "",
      doc_type: doc?.doc_type ?? undefined,
      extracted_values: structuredState.items,
      total_extracted: structuredState.total,
    };
  }

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

  const isLoading =
    detailsState.isLoading || structuredState.isLoading;

  return (
    <DocumentDetailsView
      dealId={dealId}
      doc={doc}
      classification={classification}
      family={family}
      structuredData={structuredData}
      structuredNotAvailable={structuredState.notAvailable}
      isLoading={isLoading}
      notFound={detailsState.notFound}
      error={detailsState.error ?? structuredState.error}
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
