// =============================================================
// src/api/evidence.ts
// Загрузка доказательств (evidence) и URL для просмотра PDF.
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type { Evidence } from "../types";

/**
 * Расширенный тип evidence, который возвращает backend.
 * Берём всё из базового Evidence и добавляем пару полезных полей.
 */
export interface EvidenceDetail extends Evidence {
  doc_type?: string;
  yaml_instruction_ref?: string;

  clause_uid?: string | null;
  structured_data?: Record<string, unknown> | null;

  segment_id?: string | null;
  chunk_id?: string | null;
  chunk_index?: number | null;
}

/**
 * Простые обёртки над HTTP-запросами для evidence.
 */
export const evidenceApi = {
  /**
   * Получить доказательства по resultId.
   * GET /api/v1/results/{result_id}/evidence
   */
  get: (resultId: string) =>
    client
      .get<EvidenceDetail>(`/api/v1/results/${resultId}/evidence`)
      .then((r) => r.data),

  /**
   * Получить временный URL для PDF-документа.
   * GET /api/v1/documents/{document_id}/pdf-url
   */
  getPdfUrl: (documentId: string) =>
    client
      .get<{ url: string; filename: string }>(
        `/api/v1/documents/${documentId}/pdf-url`,
      )
      .then((r) => r.data),
};

/**
 * Хук для получения evidence по resultId.
 *
 * Пример:
 * const { data, isLoading, error } = useEvidence(selectedResultId);
 */
export function useEvidence(resultId: string | null) {
  return useQuery({
    queryKey: ["evidence", resultId],
    queryFn: () => evidenceApi.get(resultId!),
    enabled: !!resultId,
  });
}

/**
 * Хук для получения PDF-URL по documentId.
 *
 * Пример:
 * const { data } = usePdfUrl(docId);
 * <iframe src={data?.url} ... />
 */
export function usePdfUrl(documentId: string | null) {
  return useQuery({
    queryKey: ["pdf-url", documentId],
    queryFn: () => evidenceApi.getPdfUrl(documentId!),
    enabled: !!documentId,
    staleTime: 50 * 60_000, // кэшируем подольше, чтобы не дёргать backend лишний раз
  });
}
