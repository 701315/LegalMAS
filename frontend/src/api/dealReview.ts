// =============================================================
// src/api/dealReview.ts
// API functions and React Query hooks for the deal review UI.
// Operates on top of run-scoped backend endpoints:
// /api/v1/deals/{deal_id}/runs/{run_id}/...
// =============================================================

import {
  useMutation,
  useQuery,
  useQueryClient,
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
  ResultPresentationProgressDTO,
  ResultPresentationRequestDTO,
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

function toPresentationLocale(
  value: string | null | undefined,
): string | undefined {
  const normalized = value?.trim();
  return normalized || undefined;
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
    presentationLocale: string | null | undefined,
  ) =>
    [
      ...dealReviewKeys.all,
      "document-detail",
      dealId,
      runId,
      documentId,
      toPresentationLocale(presentationLocale) ?? null,
    ] as const,

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

  ddMatrix: (
    dealId: string | null,
    runId: string | null,
    presentationLocale: string | null | undefined,
  ) =>
    [
      ...dealReviewKeys.all,
      "dd-matrix",
      dealId,
      runId,
      toPresentationLocale(presentationLocale) ?? null,
    ] as const,

  ddGridV1Base: (
    dealId: string | null,
    runId: string | null,
  ) =>
    [
      ...dealReviewKeys.all,
      "dd-grid-v1",
      dealId,
      runId,
    ] as const,

  ddGridV1: (
    dealId: string | null,
    runId: string | null,
    presentationLocale?: string | null,
  ) =>
    [
      ...dealReviewKeys.ddGridV1Base(dealId, runId),
      toPresentationLocale(presentationLocale) ?? null,
    ] as const,

  resultPresentationProgress: (
    dealId: string | null,
    runId: string | null,
    locale: string | null | undefined,
  ) =>
    [
      ...dealReviewKeys.all,
      "result-presentation-progress",
      dealId,
      runId,
      toPresentationLocale(locale) ?? null,
    ] as const,
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
    presentationLocale?: string | null,
  ): Promise<DocumentDetailDTO> {
    const { data } = await client.get<DocumentDetailDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/documents/${documentId}`,
      {
        params: {
          presentationlocale: toPresentationLocale(presentationLocale),
        },
      },
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
    presentationLocale?: string | null,
  ): Promise<DDMatrixResponseDTO> {
    const { data } = await client.get<DDMatrixResponseDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/dd-matrix`,
      {
        params: {
          presentationlocale: toPresentationLocale(presentationLocale),
        },
      },
    );
    return data;
  },

  /**
   * DD Grid V1 endpoint (hierarchical contract: global groups + doc-type classes → checks → runtime columns).
   * Backend: GET /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
   */
  async getDdGridV1ForRun(
    dealId: string,
    runId: string,
    presentationLocale?: string | null,
  ): Promise<DDGridV1ResponseDTO> {
    const { data } = await client.get<DDGridV1ResponseDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/dd-grid-v1`,
      {
        params: {
          presentationlocale: toPresentationLocale(presentationLocale),
        },
      },
    );
    return data;
  },

  async requestResultPresentationsForRun(
    dealId: string,
    runId: string,
    payload: ResultPresentationRequestDTO,
  ): Promise<ResultPresentationProgressDTO> {
    const { data } = await client.post<ResultPresentationProgressDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/result-presentations/requests`,
      payload,
    );
    return data;
  },

  async getResultPresentationProgressForRun(
    dealId: string,
    runId: string,
    locale: string,
  ): Promise<ResultPresentationProgressDTO> {
    const { data } = await client.get<ResultPresentationProgressDTO>(
      `${buildDealReviewBasePath(dealId, runId)}/result-presentations/progress`,
      {
        params: {
          locale,
        },
      },
    );
    return data;
  },


  // Short aliases for cleaner usage in new review UI layer
  getDdMatrix(
    dealId: string,
    runId: string,
    presentationLocale?: string | null,
  ): Promise<DDMatrixResponseDTO> {
    return dealReviewApi.getDdMatrixForRun(
      dealId,
      runId,
      presentationLocale,
    );
  },

  getDdGridV1(
    dealId: string,
    runId: string,
    presentationLocale?: string | null,
  ): Promise<DDGridV1ResponseDTO> {
    return dealReviewApi.getDdGridV1ForRun(
      dealId,
      runId,
      presentationLocale,
    );
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
 * Single review cell for a specific document and check.
 * Used for document-scoped review views.
 */
export interface DocumentReviewCheckCell {
  checkId: string;
  checkName: string;
  cell: MatrixCellDTO;
}

/**
 * Extracts all check cells for a specific document from the global dd-matrix.
 * Returns only non-empty cells (by default filters "empty pass" cells
 * without any snippet/segment binding).
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

      // Filter out "empty" pass cells without any evidence/provenance
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
  presentationLocale?: string | null,
  options?: QueryOptions<DocumentDetailDTO>,
): UseQueryResult<DocumentDetailDTO, Error> {
  return useQuery<DocumentDetailDTO, Error>({
    queryKey: dealReviewKeys.documentDetail(
      dealId,
      runId,
      documentId,
      presentationLocale,
    ),
    queryFn: () =>
      dealReviewApi.getDocumentDetailForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        requireParam(documentId, "documentId"),
        presentationLocale,
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
  presentationLocale?: string | null,
  options?: QueryOptions<DDMatrixResponseDTO>,
): UseQueryResult<DDMatrixResponseDTO, Error> {
  return useQuery<DDMatrixResponseDTO, Error>({
    queryKey: dealReviewKeys.ddMatrix(
      dealId,
      runId,
      presentationLocale,
    ),
    queryFn: () =>
      dealReviewApi.getDdMatrixForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        presentationLocale,
      ),
    enabled: !!dealId && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

/**
 * React Query hook for DD Grid V1.
 *
 * Dedicated hook (not reusing useDealReviewDdMatrix) because:
 * - separate backend endpoint;
 * - completely different response schema;
 * - distinct semantic contract (hierarchy / runtime columns / cell_state / formats).
 */
export function useDealReviewDdGridV1(
  dealId: string | null,
  runId: string | null,
  presentationLocale?: string | null,
  options?: QueryOptions<DDGridV1ResponseDTO>,
): UseQueryResult<DDGridV1ResponseDTO, Error> {
  return useQuery<DDGridV1ResponseDTO, Error>({
    queryKey: dealReviewKeys.ddGridV1(
      dealId,
      runId,
      presentationLocale,
    ),
    queryFn: () =>
      dealReviewApi.getDdGridV1ForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        presentationLocale,
      ),
    enabled: !!dealId && !!runId,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    ...options,
  });
}

const RESULT_PRESENTATION_PROGRESS_POLL_INTERVAL_MS = 2_000;

export function useResultPresentationProgress(
  dealId: string | null,
  runId: string | null,
  presentationLocale: string | null | undefined,
): UseQueryResult<ResultPresentationProgressDTO, Error> {
  const locale = toPresentationLocale(presentationLocale);

  return useQuery<ResultPresentationProgressDTO, Error>({
    queryKey: dealReviewKeys.resultPresentationProgress(
      dealId,
      runId,
      locale,
    ),
    queryFn: () =>
      dealReviewApi.getResultPresentationProgressForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        requireParam(locale, "presentationLocale"),
      ),
    enabled: !!dealId && !!runId && !!locale,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      const progress = query.state.data;

      if (!progress) {
        return false;
      }

      return progress.pending > 0 || progress.processing > 0
        ? RESULT_PRESENTATION_PROGRESS_POLL_INTERVAL_MS
        : false;
    },
  });
}

export function useRequestResultPresentations(
  dealId: string | null,
  runId: string | null,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (locale: string) =>
      dealReviewApi.requestResultPresentationsForRun(
        requireParam(dealId, "dealId"),
        requireParam(runId, "runId"),
        {
          locale,
        },
      ),
    onSuccess: (progress, locale) => {
      queryClient.setQueryData(
        dealReviewKeys.resultPresentationProgress(
          dealId,
          runId,
          locale,
        ),
        progress,
      );
    },
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
  presentationLocale?: string | null,
  options?: QueryOptions<DDMatrixResponseDTO>,
): UseQueryResult<DDMatrixResponseDTO, Error> {
  return useDealReviewDdMatrix(
    dealId,
    runId,
    presentationLocale,
    options,
  );
}

/**
 * Short alias for the new review UI layer.
 * See useDealReviewDdGridV1 for full contract details.
 */
export function useDdGridV1(
  dealId: string | null,
  runId: string | null,
  presentationLocale?: string | null,
  options?: QueryOptions<DDGridV1ResponseDTO>,
): UseQueryResult<DDGridV1ResponseDTO, Error> {
  return useDealReviewDdGridV1(
    dealId,
    runId,
    presentationLocale,
    options,
  );
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


