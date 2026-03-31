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
  useDocumentChunkViewUrl,
} from "../../api/documents";
import {
  useDocumentDetailsState,
  useStructuredDataState,
} from "../../api/documents.stateHooks";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useDocumentTypes } from "../../api/documentTypes";

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

import { LayoutDebugModal } from "./LayoutDebugModal";
import { DocumentChunksModal } from "./DocumentChunksModal";

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

  // --- Structured-data (извлечённые значения) ---
  const structuredState = useStructuredDataState(docId);

  // --- Типы документов для выпадающего списка переклассификации ---
  const { data: docTypesData } = useDocumentTypes();
  const availableDocTypes = docTypesData ?? [];

  // --- Дополнительные данные (DTO-хуки) ---
  const { data: familyDto } = useDocumentFamily(docId);
  const { data: pdfData } = useDocumentPdfUrl(docId);
  const { data: chunkViewData } = useDocumentChunkViewUrl(docId); 
  console.log("chunkViewData:", chunkViewData);


  // --- Права доступа по сделке ---
  const {
    canDownloadDocuments,
    canReclassifyDocuments,
  } = useDealPermissions(dealId);

  // --- Capabilities ---
  const canDownload = canDownloadDocuments;
  const canOpenPdf = canDownloadDocuments;
  const canReclassify = canReclassifyDocuments;

  // Можно ли показывать кнопку «документ в формате чанка».
  // Логика простая: если пользователь может скачивать документы,
  // он же может открыть и debug‑представление документа.
  const canOpenChunkView = canDownloadDocuments;


  // --- Мутации ---
  const reclassifyMutation = useReclassifyDocument(docId);
  const setReviewedMutation = useSetDocumentReviewed(docId, dealId);

  // --- Адаптация стейтов к view-модели ---

  // Детали документа и классификация — из нормализованного стейта
  const doc: Document | null = detailsState.doc;
  const classification: DocumentDetailsViewClassification | null =
    detailsState.classification;

  // Семейство документов — по-прежнему отдельным запросом
  const family: DocumentFamilyView | null = adaptFamily(
    familyDto as DocumentFamilyDto | undefined,
  );

  // Structured-data: маппим из StructuredDataState в view-тип
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

  // Для непрофессионального программиста:
  // - Здесь мы просто смотрим, отдал ли backend ссылки на layout'ы.
  // - Если поле есть и не равно null/пустой строке, считаем, что макет доступен.
  const rawLayoutAvailable =
    !!doc && !!doc.text_layout_raw_ref && doc.text_layout_raw_ref.trim() !== "";
  const sanitizedLayoutAvailable =
    !!doc &&
    !!doc.text_layout_sanitized_ref &&
    doc.text_layout_sanitized_ref.trim() !== "";

  const [showLayoutDebug, setShowLayoutDebug] = React.useState(false);
  const [showChunksModal, setShowChunksModal] = React.useState(false);

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
    <>
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
        availableDocTypes={availableDocTypes}
        initialDocType={doc?.doc_type ?? ""}
        // Новые флаги наличия layout'ов — view сможет по ним отрисовать кнопки/иконки.
        rawLayoutAvailable={rawLayoutAvailable}
        sanitizedLayoutAvailable={sanitizedLayoutAvailable}
        // Колбэк для открытия debug-модалки
        onOpenLayoutDebug={() => setShowLayoutDebug(true)}
        canOpenChunkView={canOpenChunkView}
        chunkViewUrl={chunkViewData?.url ?? null}
        onOpenChunkView={
          canOpenChunkView && chunkViewData?.url
            ? () => setShowChunksModal(true)
            : undefined
        }
      />

      <LayoutDebugModal
        docId={docId}
        isOpen={showLayoutDebug}
        onClose={() => setShowLayoutDebug(false)}
      />
      <DocumentChunksModal
        isOpen={showChunksModal}
        onClose={() => setShowChunksModal(false)}
        chunkViewUrl={chunkViewData?.url ?? null}
        docName={doc?.filename ?? ""}
      />
    </>
  );
};

export default DocumentDetailsContainer;

