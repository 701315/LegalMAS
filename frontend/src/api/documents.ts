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
  PaginatedResponse,
  ReclassifyInput,
  ReclassifyResult,
  StructuredDataResult,
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
  list: (dealId: string, page = 1, perPage = 50) =>
    client
      .get<PaginatedResponse<Document>>(
        `/api/v1/deals/${dealId}/documents`,
        { params: { page, per_page: perPage } },
      )
      .then((response) => response.data),

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
};

// -------------------------------------------------------------
// REACT QUERY ХУКИ
// -------------------------------------------------------------

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
      // Обновляем кэш документа и списка документов
      qc.invalidateQueries({ queryKey: ["document", docId] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
