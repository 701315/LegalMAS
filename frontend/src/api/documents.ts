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

// Debug-ответ для /documents/{doc_id}/debug/layouts.
//
// Для непрофессионального программиста:
// - raw_layout_ref / sanitized_layout_ref — это строки-ссылки на JSON в хранилище;
// - raw_layout / sanitized_layout — сами JSON-объекты (если их запросить флагами).
export interface DocumentLayoutsDebugResponse {
  document_id: string;
  deal_id: string;
  raw_layout_ref: string | null;
  sanitized_layout_ref: string | null;
  raw_layout: Record<string, unknown> | null;
  sanitized_layout: Record<string, unknown> | null;
}

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
   * Извлечённые структурированные значения по документу.
   * GET /api/v1/documents/{doc_id}/extracted-values
   *
   * Важно: StructuredDataResult здесь — это DocumentExtractedValuesResponse,
   * а не дерево clause tree.
   */
  getStructuredData: (docId: string) =>
    client
      .get<StructuredDataResult>(
        `/api/v1/documents/${docId}/extracted-values`,
      )
      .then((response) => response.data),

  /**
   * Debug: получить ссылки и, опционально, сами JSON layout'ы
   * для raw и sanitized макетов документа.
   *
   * GET /api/v1/documents/{doc_id}/debug/layouts
   *
   * Для непрофессионального программиста:
   * - includeRaw / includeSanitized управляют тем, вернёт ли backend
   *   полные JSON-объекты layout'ов, а не только ссылки.
   * - По умолчанию можно запрашивать только ссылки (оба флага false),
   *   чтобы не тянуть тяжёлые JSON без необходимости.
   */
  getLayoutsDebug: (
    docId: string,
    includeRaw = true,
    includeSanitized = true,
  ) =>
    client
      .get<DocumentLayoutsDebugResponse>(
        `/api/v1/documents/${docId}/debug/layouts`,
        {
          params: {
            include_raw: includeRaw,
            include_sanitized: includeSanitized,
          },
        },
      )
      .then((r) => r.data),

  /**
   * Загрузка новых документов в сделку.
   *
   * POST /api/v1/deals/{dealId}/documents/upload
   * Тело запроса: multipart/form-data с полем "files".
   * Дополнительно можно передать folder_path как query-параметр.
   *
   * Бэкенд:
   * - ставит import_bundle и сразу возвращает простой объект статуса
   *   (сейчас это может быть пустой массив/объект, но контракт в будущем
   *   можно расширить, не ломая фронт).
   */
  upload: (
    dealId: string,
    files: File[],
    options?: { folderPath?: string | null },
  ): Promise<{
    status?: string;
    files_uploaded?: number;
    // оставляем поле для будущего расширения (bundle_id, etc.)
    [key: string]: unknown;
  }> => {
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
      .post(url, formData, {
        headers: {
          // Axios сам добавит boundary, здесь важно указать тип тела
          "Content-Type": "multipart/form-data",
        },
      })
      .then((r) => {
        const data = r.data ?? {};
        // Нормализуем ответ: гарантируем наличие status/files_uploaded,
        // даже если бэкенд пока возвращает просто []
        if (Array.isArray(data)) {
          return {
            status: "queued",
            files_uploaded: 0,
          } as {
            status?: string;
            files_uploaded?: number;
            [key: string]: unknown;
          };
        }
        return data as {
          status?: string;
          files_uploaded?: number;
          [key: string]: unknown;
        };
      });
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
 * Хук для получения «сырых» деталей документа (DTO) по docId.
 *
 * Нормализованный стейт для UI (DocumentDetailsState) строится
 * поверх этого хука в useDocumentDetailsState (documents.stateHooks.ts).
 *
 * Пример:
 *   const { data, isLoading, error } = useDocumentDetail(selectedDocId);
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
 * Debug-хук для получения raw/sanitized layout'ов документа.
 *
 * Для непрофессионального программиста:
 * - Этот хук обращается к debug-эндпоинту backend'а и возвращает:
 *   ссылки на layout'ы и, при желании, сами JSON-объекты.
 * - Параметр enabled позволяет не дергать эндпоинт, пока модалка
 *   с debug-информацией не открыта.
 */
export function useDocumentLayoutsDebug(
  docId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["document-layouts-debug", docId],
    queryFn: () => documentApi.getLayoutsDebug(docId!),
    enabled: !!docId && enabled,
    staleTime: 5 * 60_000, // debug-данные почти не меняются
  });
}

/**
 * Хук для получения «сырых» структурированных данных документа (DTO).
 *
 * Нормализованный стейт для UI (StructuredDataState) строится
 * поверх этого хука в useStructuredDataState (documents.stateHooks.ts).
 *
 * Пример:
 *   const { data, isLoading, error } = useStructuredData(docId);
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
