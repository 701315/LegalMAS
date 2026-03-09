// =============================================================
// src/components/documents/DocumentDetailsContainer.tsx
// Контейнер для правой панели документа на вкладке Documents.
//
// Модель:
// - useDocumentDetailsState возвращает нормализованный стейт документа
// - контейнер адаптирует стейт → view-пропсы для DocumentDetails
// - structured-data в UI теперь загружаются только через модалку,
//   поэтому здесь мы их не запрашиваем и не прокидываем ошибки.
// =============================================================

import React from "react";
import {
  useDocumentFamily,
  useReclassifyDocument,
  useDocumentPdfUrl,
  useSetDocumentReviewed,
} from "../../api/documents";
import { useDocumentDetailsState } from "../../api/documents.stateHooks";
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
  // --- Стейт документа (детали + классификация) ---
  const detailsState = useDocumentDetailsState(docId); // DocumentDetailsState

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

  // Structured-data теперь загружаются только через модалку,
  // поэтому в правой панели мы:
  // - не запрашиваем их
  // - отображаем состояние "данные не сформированы / недоступны"
  const structuredData: StructuredDataView | null = null;
  const structuredNotAvailable = true;

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

  const isLoading = detailsState.isLoading;

  return (
    <DocumentDetailsView
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
    />
  );
};

export default DocumentDetailsContainer;
