// =============================================================
// src/api/documents.ts
// API-функции и React Query хуки для работы с документами.
// Использует Axios-клиент из src/api/client.ts.
// =============================================================

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type {
  Document,
  DocumentDetail,
  DocumentFamily,
  PaginatedResponse,
  ReclassifyInput,
  ReclassifyResult,
  StructuredDataResult,
  DocumentColumnId,
} from "../types";

// -------------------------------------------------------------
// НИЗКОУРОВНЕВЫЙ API-КЛИЕНТ
// -------------------------------------------------------------

export const documentApi = {
  /**
   * Список документов по сделке.
   *
   * Базовый вариант:
   *   GET /api/v1/deals/{deal_id}/documents
   *
   * Если у тебя уже есть UI-API по run
   * (GET /deals/{deal_id}/runs/{run_id}/documents),
   * позже адаптируем сигнатуру: добавим runId.
   */
  list: (
    dealId: string,
    page = 1,
    perPage = 50,
    opts?: {
      include_classification?: boolean;
      status?: string;
      doc_type?: string;
    },
  ) =>
    client
      .get<PaginatedResponse<Document>>(`/api/v1/deals/${dealId}/documents`, {
        params: {
          page,
          per_page: perPage,
          include_classification: opts?.include_classification,
          status: opts?.status,
          doc_type: opts?.doc_type,
        },
      })
      .then((r) => r.data),

  /**
   * Детали документа.
   *
   * Базовый вариант:
   *   GET /api/v1/documents/{doc_id}
   *
   * Если будешь использовать UI-API по run
   * (GET /deals/{deal_id}/runs/{run_id}/documents/{doc_id}),
   * мы расширим сигнатуру и путь.
   */
  get: (docId: string) =>
    client
      .get<DocumentDetail>(`/api/v1/documents/${docId}`)
      .then((response) => response.data),

  // ...
  getFamily: (docId: string) =>
    client
      .get<DocumentFamily>(`/api/v1/documents/${docId}/family`)
      .then((response) => response.data),

  /**
   * Оригинальный PDF URL.
   * GET /api/v1/documents/{doc_id}/pdf-url
   */
  getPdfUrl: (docId: string) =>
    client
      .get<{ url: string }>(`/api/v1/documents/${docId}/pdf-url`)
      .then((r) => r.data),

  /**
   * Ручная переклассификация документа (Editor+).
   * POST /api/v1/documents/{doc_id}/reclassify
   */
  reclassify: (docId: string, data: ReclassifyInput) =>
    client
      .post<ReclassifyResult>(
        `/api/v1/documents/${docId}/reclassify`,
        data,
      )
      .then((response) => response.data),

  /**
   * Структурированные данные по документу.
   * GET /api/v1/documents/{doc_id}/structured-data
   */
  getStructuredData: (docId: string) =>
    client
      .get<StructuredDataResult>(
        `/api/v1/documents/${docId}/structured-data`,
      )
      .then((response) => response.data),

  /**
   * Загрузка новых документов в сделку.
   *
   * POST /api/v1/deals/{dealId}/documents/upload
   * Тело запроса: multipart/form-data с полем "files".
   * Дополнительно можно передать folder_path как query-параметр.
   */
  upload: (
    dealId: string,
    files: File[],
    options?: { folderPath?: string | null },
  ) => {
    const formData = new FormData();

    // Добавляем все файлы под ключом "files" (соответствует параметру в FastAPI)
    files.forEach((file) => {
      formData.append("files", file);
    });

    // Собираем URL с учётом folder_path (если есть)
    const params = new URLSearchParams();
    if (options?.folderPath) {
      params.set("folder_path", options.folderPath);
    }
    const query = params.toString();
    const url = query
      ? `/api/v1/deals/${dealId}/documents/upload?${query}`
      : `/api/v1/deals/${dealId}/documents/upload`;

    return client
      .post<Document[]>(url, formData, {
        headers: {
          // Axios сам добавит boundary, здесь важно указать тип тела
          "Content-Type": "multipart/form-data",
        },
      })
      .then((r) => r.data);
  },

  /**
   * Мягкое удаление документа (soft-delete).
   *
   * POST /api/v1/documents/{docId}/delete
   * Меняет статус документа на 'deleted'.
   */
  softDelete: (docId: string) =>
    client
      .post<{ status: string; document_id: string; new_status: string }>(
        `/api/v1/documents/${docId}/delete`,
      )
      .then((r) => r.data),

  /**
   * Установка флага reviewed_by_person для документа.
   *
   * PATCH /api/v1/documents/{docId}/reviewed
   * Тело: { reviewed_by_person: boolean }
   */
  setReviewed: (docId: string, reviewedByPerson: boolean) =>
    client
      .patch<Document>(
        `/api/v1/documents/${docId}/reviewed`,
        { reviewed_by_person: reviewedByPerson },
      )
      .then((r) => r.data),


  /**
   * Экспорт списка документов сделки в Excel.
   * POST /api/v1/documents/export/excel
   */
  exportExcel: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<ArrayBuffer>("/api/v1/documents/export/excel", {
        deal_id: dealId,
        visible_column_ids:
          visibleColumnIds && visibleColumnIds.length > 0
            ? visibleColumnIds
            : null,
      }, {
        responseType: "blob",
      })
      .then((r) => r.data),

  /**
   * Экспорт списка документов сделки в Word.
   * POST /api/v1/documents/export/word
   */
  exportWord: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<Blob>("/api/v1/documents/export/word", {
        deal_id: dealId,
        visible_column_ids:
          visibleColumnIds && visibleColumnIds.length > 0
            ? visibleColumnIds
            : null,
      }, {
        responseType: "blob",
      })
      .then((r) => r.data),

  /**
   * Экспорт списка документов сделки в PDF.
   * POST /api/v1/documents/export/pdf
   */
  exportPdf: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<Blob>("/api/v1/documents/export/pdf", {
        deal_id: dealId,
        visible_column_ids:
          visibleColumnIds && visibleColumnIds.length > 0
            ? visibleColumnIds
            : null,
      }, {
        responseType: "blob",
      })
      .then((r) => r.data),

};



function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function exportDocumentsExcel(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportExcel(dealId, visibleColumnIds);
  downloadBlob(blob as unknown as Blob, `deal_${dealId}_documents.xlsx`);
}

export async function exportDocumentsWord(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportWord(dealId, visibleColumnIds);
  downloadBlob(blob as unknown as Blob, `deal_${dealId}_documents.docx`);
}

export async function exportDocumentsPDF(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportPdf(dealId, visibleColumnIds);
  downloadBlob(blob as unknown as Blob, `deal_${dealId}_documents.pdf`);
}



// -------------------------------------------------------------
// REACT QUERY ХУКИ
// -------------------------------------------------------------

export function useDocumentsWithClassification(dealId: string, page = 1) {
  return useQuery({
    queryKey: ["documents-classified", dealId, page],
    queryFn: () =>
      documentApi.list(dealId, page, 50, { include_classification: true }),
    enabled: !!dealId,
    staleTime: 2 * 60_000,
  });
}

/**
 * Хук для получения списка документов по сделке.
 * Пример использования:
 *   const { data, isLoading } = useDocuments(dealId);
 */
export function useDocuments(dealId: string, page = 1) {
  return useQuery({
    queryKey: ["documents", dealId, page],
    queryFn: () => documentApi.list(dealId, page),
    enabled: !!dealId,
  });
}

/**
 * Хук для получения деталей документа.
 * Пример:
 *   const { data, isLoading } = useDocumentDetail(selectedDocId);
 */
export function useDocumentDetail(docId: string | null) {
  return useQuery({
    queryKey: ["document", docId],
    queryFn: () => documentApi.get(docId!),
    enabled: !!docId,
  });
}

export function useDocumentFamily(docId: string | null) {
  return useQuery({
    queryKey: ["document-family", docId],
    queryFn: () => documentApi.getFamily(docId!),
    enabled: !!docId,
  });
}

export function useDocumentPdfUrl(docId: string | null) {
  return useQuery({
    queryKey: ["document-pdf-url", docId],
    queryFn: () => documentApi.getPdfUrl(docId!),
    enabled: !!docId,
  });
}

/**
 * Хук для получения структурированных данных документа.
 * Загружается по требованию (enabled: !!docId).
 */
export function useStructuredData(docId: string | null) {
  return useQuery({
    queryKey: ["structured-data", docId],
    queryFn: () => documentApi.getStructuredData(docId!),
    enabled: !!docId,
    staleTime: 5 * 60_000, // 5 минут — данные редко меняются
  });
}

/**
 * Хук для ручной переклассификации документа.
 * Возвращает mutate, который можно вызывать из формы/кнопки.
 */
export function useReclassifyDocument(docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ReclassifyInput) =>
      documentApi.reclassify(docId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document", docId] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["documents-classified"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

/**
 * Хук для мягкого удаления документа.
 * После успешного удаления обновляет кэш документа и списков документов.
 */
export function useSoftDeleteDocument(dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (docId: string) => documentApi.softDelete(docId),
    onSuccess: (_data, docId) => {
      qc.invalidateQueries({ queryKey: ["document", docId] });
      qc.invalidateQueries({ queryKey: ["documents", dealId] });
      qc.invalidateQueries({ queryKey: ["documents-classified", dealId] });
    },
  });
}

/**
 * Хук для загрузки новых документов в сделку.
 *
 * Пример использования:
 *   const uploadMutation = useUploadDocuments(dealId);
 *   uploadMutation.mutate({ files, folderPath });
 */
export function useUploadDocuments(dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (params: { files: File[]; folderPath?: string | null }) =>
      documentApi.upload(dealId, params.files, {
        folderPath: params.folderPath,
      }),
    onSuccess: () => {
      // После успешной загрузки обновляем списки документов для этой сделки
      qc.invalidateQueries({ queryKey: ["documents", dealId] });
      qc.invalidateQueries({ queryKey: ["documents-classified", dealId] });
    },
  });
}

/**
 * Хук для установки флага reviewed_by_person у документа.
 *
 * Пример:
 *   const setReviewed = useSetDocumentReviewed(docId);
 *   setReviewed.mutate(true);
 */
export function useSetDocumentReviewed(docId: string, dealId?: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (reviewedByPerson: boolean) =>
      documentApi.setReviewed(docId, reviewedByPerson),
    onSuccess: () => {
      // Обновляем детальную карточку документа
      qc.invalidateQueries({ queryKey: ["document", docId] });

      // Обновляем списки документов, если есть dealId
      if (dealId) {
        qc.invalidateQueries({ queryKey: ["documents", dealId] });
        qc.invalidateQueries({
          queryKey: ["documents-classified", dealId],
        });
      }
    },
  });
}
