// =============================================================
// src/api/dealReview.ts
// API-функции и React Query-хуки для deal review UI.
// Работает поверх run-scoped backend endpoints:
// /api/v1/deals/{deal_id}/runs/{run_id}/...
// =============================================================

import {
  useQuery,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query";

import client from "./client";

import type {
  ConditionalCheckDTO,
  DDGridV1ResponseDTO,
  DDMatrixResponseDTO,
  DDRequestDTO,
  MatrixCellDTO,
  DocumentDetailDTO,
  DocumentStructuredDataDTO,
  DocumentSummaryDTO,
  ExtractedValueDTO,
} from "../types/dealReview";

// -------------------------------------------------------------
// Internal helpers
// -------------------------------------------------------------

function buildDealReviewBasePath(dealId: string, runId: string): string {
  return `/api/v1/deals/${dealId}/runs/${runId}`;
}

function requireParam(value: string | null | undefined, name: string): string {
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

// -------------------------------------------------------------
// React Query keys
// -------------------------------------------------------------

export const dealReviewKeys = {
  all: ["deal-review"] as const,

  documents: (dealId: string | null, runId: string | null) =>
    [...dealReviewKeys.all, "documents", dealId, runId] as const,

  documentDetail: (
    dealId: string | null,
    runId: string | null,
    documentId: string | null,
  ) =>
    [...dealReviewKeys.all, "document-detail", dealId, runId, documentId] as const,

  documentStructuredData: (
    dealId: string | null,
    runId: string | null,
    documentId: string | null,
  ) =>
    [
      ...dealReviewKeys.all,
      "document-structured-data",
      dealId,
      runId,
      documentId,
    ] as const,

  ddRequests: (dealId: string | null, runId: string | null) =>
    [...dealReviewKeys.all, "dd-requests", dealId, runId] as const,

  conditionalChecks: (dealId: string | null, runId: string | null) =>
    [...dealReviewKeys.all, "conditional-checks", dealId, runId] as const,

  extractedValues: (dealId: string | null, runId: string | null) =>
    [...dealReviewKeys.all, "extracted-values", dealId, runId] as const,

  ddMatrix: (dealId: string | null, runId: string | null) =>
    [...dealReviewKeys.all, "dd-matrix", dealId, runId] as const,

  ddGridV1: (dealId: string | null, runId: string | null) =>
    [...dealReviewKeys.all, "dd-grid-v1", dealId, runId] as const,
};

// -------------------------------------------------------------
// Low-level API
// -------------------------------------------------------------

export const dealReviewApi = {
  async getDocumentsForRun(
    dealId: string,
    runId: string,
  ): Promise<DocumentSummaryDTO[]> {
    const { data } = await client.get<DocumentSummaryDTO[]>(
      `${buildDealReviewBasePath(dealId, runId)}/documents`,
    );
    return data;
  },

  async getDocumentDetailForRun(
    dealId: string,
    runId: string,
    documentId: string,
  ): Promise<DocumentDetailDTO> {
    const { data } = await client.get<DocumentDetailDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/documents/${documentId}`,
    );
    return data;
  },

  async getDocumentStructuredDataForRun(
    dealId: string,
    runId: string,
    documentId: string,
  ): Promise<DocumentStructuredDataDTO> {
    const { data } = await client.get<DocumentStructuredDataDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/documents/${documentId}/structured-data`,
    );
    return data;
  },

  async getDdRequestsForRun(
    dealId: string,
    runId: string,
  ): Promise<DDRequestDTO[]> {
    const { data } = await client.get<DDRequestDTO[]>(
      `${buildDealReviewBasePath(dealId, runId)}/dd-requests`,
    );
    return data;
  },

  async getConditionalChecksForRun(
    dealId: string,
    runId: string,
  ): Promise<ConditionalCheckDTO[]> {
    const { data } = await client.get<ConditionalCheckDTO[]>(
      `${buildDealReviewBasePath(dealId, runId)}/conditional-checks`,
    );
    return data;
  },

  async getExtractedValuesForRun(
    dealId: string,
    runId: string,
  ): Promise<ExtractedValueDTO[]> {
    const { data } = await client.get<ExtractedValueDTO[]>(
      `${buildDealReviewBasePath(dealId, runId)}/extracted-values`,
    );
    return data;
  },

  async getDdMatrixForRun(
    dealId: string,
    runId: string,
  ): Promise<DDMatrixResponseDTO> {
    const { data } = await client.get<DDMatrixResponseDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/dd-matrix`,
    );
    return data;
  },

  /**
   * DD Grid V1 endpoint (иерархический контракт: global groups + doc-type classes → checks → runtime columns).
   * Backend: GET /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
   */
  async getDdGridV1ForRun(
    dealId: string,
    runId: string,
  ): Promise<DDGridV1ResponseDTO> {
    const { data } = await client.get<DDGridV1ResponseDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/dd-grid-v1`,
    );
    return data;
  },

  // Short aliases for cleaner usage in new review UI layer
  getDdMatrix(dealId: string, runId: string): Promise<DDMatrixResponseDTO> {
    return dealReviewApi.getDdMatrixForRun(dealId, runId);
  },

  getDdGridV1(dealId: string, runId: string): Promise<DDGridV1ResponseDTO> {
    return dealReviewApi.getDdGridV1ForRun(dealId, runId);
  },

  getDdRequests(dealId: string, runId: string): Promise<DDRequestDTO[]> {
    return dealReviewApi.getDdRequestsForRun(dealId, runId);
  },

  getConditionalChecks(
    dealId: string,
    runId: string,
  ): Promise<ConditionalCheckDTO[]> {
    return dealReviewApi.getConditionalChecksForRun(dealId, runId);
  },
};

// -------------------------------------------------------------
// Derived helpers for DD Matrix (Step 1)
// -------------------------------------------------------------

/**
 * Единичная ячейка review для конкретного документа и проверки.
 * Используется для document-scoped review представлений.
 */
export interface DocumentReviewCheckCell {
  checkId: string;
  checkName: string;
  cell: MatrixCellDTO;
}

/**
 * Из глобального dd-matrix достаёт все check-cells для конкретного документа.
 * Возвращает только непустые ячейки (по умолчанию фильтрует "пустые pass"
 * без snippet/segment-привязки).
 */
export function selectDocumentReviewCells(
  matrix: DDMatrixResponseDTO | null | undefined,
  documentId: string,
): DocumentReviewCheckCell[] {
  if (!matrix) return [];

  const docRow = matrix.documents.find(
    (d) => d.document_id === documentId,
  );
  if (!docRow?.results) return [];

  return matrix.checks
    .map((check) => {
      const cell = docRow.results?.[check.check_id];
      if (!cell) return null;

      // Отфильтровываем "пустые" pass без какого-либо evidence/provenance
      if (
        cell.result === "pass" &&
        !cell.snippet &&
        !cell.segment_id &&
        !cell.chunk_id
      ) {
        return null;
      }

      return {
        checkId: check.check_id,
        checkName: check.check_name || check.check_id,
        cell,
      };
    })
    .filter((x): x is DocumentReviewCheckCell => x !== null);
}

// -------------------------------------------------------------
// React Query hooks
// -------------------------------------------------------------

type QueryOptions<TData> = Omit<
  UseQueryOptions<TData, Error>,
  "queryKey" | "queryFn"
>;

export function useDealReviewDocuments(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DocumentSummaryDTO[]>,
): UseQueryResult<DocumentSummaryDTO[], Error> {
  return useQuery<DocumentSummaryDTO[], Error>({
    queryKey: dealReviewKeys.documents(dealId, runId),
    queryFn: () =>
      dealReviewApi.getDocumentsForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
      ),
    enabled: !!dealId && !!runId,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

export function useDealReviewDocumentDetail(
  dealId: string | null,
  runId: string | null,
  documentId: string | null,
  options?: QueryOptions<DocumentDetailDTO>,
): UseQueryResult<DocumentDetailDTO, Error> {
  return useQuery<DocumentDetailDTO, Error>({
    queryKey: dealReviewKeys.documentDetail(dealId, runId, documentId),
    queryFn: () =>
      dealReviewApi.getDocumentDetailForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        requireParam(documentId, "documentId"),
      ),
    enabled: !!dealId && !!runId && !!documentId,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

export function useDealReviewDocumentStructuredData(
  dealId: string | null,
  runId: string | null,
  documentId: string | null,
  options?: QueryOptions<DocumentStructuredDataDTO>,
): UseQueryResult<DocumentStructuredDataDTO, Error> {
  return useQuery<DocumentStructuredDataDTO, Error>({
    queryKey: dealReviewKeys.documentStructuredData(dealId, runId, documentId),
    queryFn: () =>
      dealReviewApi.getDocumentStructuredDataForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        requireParam(documentId, "documentId"),
      ),
    enabled: !!dealId && !!runId && !!documentId,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

export function useDealReviewDdRequests(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DDRequestDTO[]>,
): UseQueryResult<DDRequestDTO[], Error> {
  return useQuery<DDRequestDTO[], Error>({
    queryKey: dealReviewKeys.ddRequests(dealId, runId),
    queryFn: () =>
      dealReviewApi.getDdRequestsForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
      ),
    enabled: !!dealId && !!runId,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

export function useDealReviewConditionalChecks(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<ConditionalCheckDTO[]>,
): UseQueryResult<ConditionalCheckDTO[], Error> {
  return useQuery<ConditionalCheckDTO[], Error>({
    queryKey: dealReviewKeys.conditionalChecks(dealId, runId),
    queryFn: () =>
      dealReviewApi.getConditionalChecksForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
      ),
    enabled: !!dealId && !!runId,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

export function useDealReviewExtractedValues(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<ExtractedValueDTO[]>,
): UseQueryResult<ExtractedValueDTO[], Error> {
  return useQuery<ExtractedValueDTO[], Error>({
    queryKey: dealReviewKeys.extractedValues(dealId, runId),
    queryFn: () =>
      dealReviewApi.getExtractedValuesForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
      ),
    enabled: !!dealId && !!runId,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

export function useDealReviewDdMatrix(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DDMatrixResponseDTO>,
): UseQueryResult<DDMatrixResponseDTO, Error> {
  return useQuery<DDMatrixResponseDTO, Error>({
    queryKey: dealReviewKeys.ddMatrix(dealId, runId),
    queryFn: () =>
      dealReviewApi.getDdMatrixForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
      ),
    enabled: !!dealId && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

/**
 * React Query hook для DD Grid V1.
 *
 * Отдельный hook (а не переиспользование useDealReviewDdMatrix), потому что:
 * - другой backend endpoint;
 * - другой response schema;
 * - другой семантический контракт (иерархия / runtime columns / cell_state / formats).
 */
export function useDealReviewDdGridV1(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DDGridV1ResponseDTO>,
): UseQueryResult<DDGridV1ResponseDTO, Error> {
  return useQuery<DDGridV1ResponseDTO, Error>({
    queryKey: dealReviewKeys.ddGridV1(dealId, runId),
    queryFn: () =>
      dealReviewApi.getDdGridV1ForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
      ),
    enabled: !!dealId && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

// -------------------------------------------------------------
// Short aliases for the new review UI layer
// -------------------------------------------------------------

export const getDdMatrix = dealReviewApi.getDdMatrix;
export const getDdGridV1 = dealReviewApi.getDdGridV1;
export const getDdRequests = dealReviewApi.getDdRequests;
export const getConditionalChecks = dealReviewApi.getConditionalChecks;

export function useDdMatrix(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DDMatrixResponseDTO>,
): UseQueryResult<DDMatrixResponseDTO, Error> {
  return useDealReviewDdMatrix(dealId, runId, options);
}

/**
 * Короткий alias для новой review UI layer.
 * См. useDealReviewDdGridV1 для полного описания контракта.
 */
export function useDdGridV1(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DDGridV1ResponseDTO>,
): UseQueryResult<DDGridV1ResponseDTO, Error> {
  return useDealReviewDdGridV1(dealId, runId, options);
}

export function useDdRequests(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<DDRequestDTO[]>,
): UseQueryResult<DDRequestDTO[], Error> {
  return useDealReviewDdRequests(dealId, runId, options);
}

export function useConditionalChecks(
  dealId: string | null,
  runId: string | null,
  options?: QueryOptions<ConditionalCheckDTO[]>,
): UseQueryResult<ConditionalCheckDTO[], Error> {
  return useDealReviewConditionalChecks(dealId, runId, options);
}


