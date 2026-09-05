// =============================================================
// src/api/deals.ts
// API client functions and React Query hooks for managing deals.
// =============================================================

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import { documentKeys } from "./documents";
import { runKeys } from "./runs";
import type {
  Deal,
  DealDetail,
  DealUpdatePayload,
  PaginatedResponse,
} from "../types";

// -------------------------------------------------------------
// Low-level API client
// -------------------------------------------------------------

export const dealApi = {
  /**
   * List deals.
   * GET /api/v1/deals?page=&per_page=
   */
  list: (page = 1, perPage = 20, status?: string, tenantId?: string) =>
    client
      .get<PaginatedResponse<Deal>>("/api/v1/deals", {
        params: {
          page,
          per_page: perPage,
          status: status || undefined,
          tenant_id: tenantId || undefined,
        },
      })
      .then((response) => response.data),

  /**
   * Get single deal details.
   * GET /api/v1/deals/{deal_id}
   */
  get: (dealId: string) =>
    client
      .get<DealDetail>(`/api/v1/deals/${dealId}`)
      .then((response) => response.data),

  /**
   * Partially update a deal.
   * PATCH /api/v1/deals/{deal_id}
   *
   * Used for standard deal fields that do not trigger
   * special backend pipeline continuation logic.
   */
  update: (dealId: string, payload: DealUpdatePayload) =>
    client
      .patch<DealDetail>(`/api/v1/deals/${dealId}`, payload)
      .then((response) => response.data),

  /**
   * Set the primary language of the deal.
   * PATCH /api/v1/deals/{deal_id}/primary-language
   *
   * Dedicated domain operation:
   * backend validates language, reactivates documents,
   * and restarts the appropriate pipeline section.
   */
  setPrimaryLanguage: (
    dealId: string,
    payload: { primary_language: string | null },
  ) =>
    client
      .patch<DealDetail>(
        `/api/v1/deals/${dealId}/primary-language`,
        payload,
      )
      .then((response) => response.data),
};

// -------------------------------------------------------------
// React Query hooks
// -------------------------------------------------------------

/**
 * Hook for fetching paginated deals list.
 * Example:
 *   const { data, isLoading } = useDeals();
 */
export function useDeals(page = 1, status?: string, tenantId?: string) {
  return useQuery({
    queryKey: ["deals", page, status, tenantId],
    queryFn: () => dealApi.list(page, 20, status, tenantId),
  });
}

/**
 * Hook for fetching single deal detail.
 * Example:
 *   const { data, isLoading } = useDeal(dealId);
 */
export function useDeal(
  dealId: string | null,
  options?: { refetchInterval?: number | false | ((query: { state: { data?: DealDetail } }) => number | false) },
) {
  return useQuery({
    queryKey: ["deal", dealId],
    queryFn: () => dealApi.get(dealId as string),
    enabled: !!dealId,
    refetchInterval: options?.refetchInterval,
    // Refetch on window focus to prevent stale data
    refetchOnWindowFocus: true,
    // Retry up to 2 times on network errors
    retry: 2,
    retryDelay: 3000,
  });
}

/**
 * Hook for updating deal properties (e.g. summary).
 *
 * Do not use for primary_language, as choosing the main language
 * triggers separate pipeline continuation logic.
 *
 * Example:
 *   const updateDeal = useUpdateDeal(deal.id);
 *   updateDeal.mutate({ summary: "New project summary" });
 */
export function useUpdateDeal(dealId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: DealUpdatePayload) => dealApi.update(dealId, payload),

    onSuccess: async (updatedDeal) => {
      queryClient.setQueryData<DealDetail>(["deal", dealId], updatedDeal);

      await queryClient.invalidateQueries({ queryKey: ["deals"] });
    },
  });
}

/**
 * Hook for setting primary project language.
 *
 * Note:
 * - utilizes dedicated /primary-language endpoint;
 * - backend executes the required pipeline continuation logic;
 * - updates deal and related run queries on success.
 *
 * Example:
 *   const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);
 *   setPrimaryLanguage.mutate({ primary_language: "RU" });
 */
export function useSetPrimaryLanguage(dealId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { primary_language: string | null }) =>
      dealApi.setPrimaryLanguage(dealId, payload),

    onSuccess: async (updatedDeal) => {
      queryClient.setQueryData<DealDetail>(["deal", dealId], updatedDeal);

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["deal", dealId] }),
        queryClient.invalidateQueries({ queryKey: ["deals"] }),
        queryClient.invalidateQueries({ queryKey: documentKeys.byDeal(dealId) }),
        queryClient.invalidateQueries({ queryKey: runKeys.history(dealId, false) }),
        queryClient.invalidateQueries({ queryKey: runKeys.history(dealId, true) }),
      ]);
    },
  });
}

// =============================================================
// LLM USAGE SUMMARY
// =============================================================

export interface LLMStageUsage {
  stage: string;
  provider: string;
  model: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  avg_duration_ms: number | null;
  parse_failures: number;
}

export interface LLMDocumentUsage {
  document_id: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  parse_failures: number;
}

export interface LLMUsageSummary {
  deal_id: string;
  total_tokens: number;
  total_calls: number;
  by_stage: LLMStageUsage[];
  by_document: LLMDocumentUsage[];
}

export const dealUsageApi = {
  getLLMUsageSummary: (dealId: string) =>
    client
      .get<LLMUsageSummary>(`/api/v1/deals/${dealId}/llm-usage-summary`)
      .then((r) => r.data),
};

/**
 * Hook for fetching aggregated LLM usage summary for a project.
 *
 * refetchInterval:
 * - false (default) — no polling;
 * - 30_000 — poll every 30s if a run is active.
 *
 * staleTime 30s — prevents excessive refetches on window focus.
 */
export function useDealLLMUsage(
  dealId: string | null,
  options?: { refetchInterval?: number | false },
) {
  return useQuery({
    queryKey: ["deal-llm-usage", dealId],
    queryFn: () =>
      dealUsageApi.getLLMUsageSummary(dealId as string),
    enabled: !!dealId,
    refetchInterval: options?.refetchInterval ?? false,
    staleTime: 30_000,
  });
}


