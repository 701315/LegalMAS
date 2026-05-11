// =============================================================
// src/api/deals.ts
// API-функции и React Query хуки для работы со сделками.
// =============================================================

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type {
  Deal,
  DealDetail,
  DealUpdatePayload,
  PaginatedResponse,
} from "../types";

// -------------------------------------------------------------
// НИЗКОУРОВНЕВЫЙ API-КЛИЕНТ
// -------------------------------------------------------------

export const dealApi = {
  /**
   * Список сделок.
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
   * Детали одной сделки.
   * GET /api/v1/deals/{deal_id}
   */
  get: (dealId: string) =>
    client.get<DealDetail>(`/api/v1/deals/${dealId}`).then((response) => response.data),

  /**
   * Частично обновить сделку.
   * PATCH /api/v1/deals/{deal_id}
   */
  update: (dealId: string, payload: DealUpdatePayload) =>
    client
      .patch<DealDetail>(`/api/v1/deals/${dealId}`, payload)
      .then((response) => response.data),
};

// -------------------------------------------------------------
// REACT QUERY ХУКИ
// -------------------------------------------------------------

/**
 * Хук для списка сделок.
 * Пример:
 *   const { data, isLoading } = useDeals();
 */
export function useDeals(page = 1, status?: string, tenantId?: string) {
  return useQuery({
    queryKey: ["deals", page, status, tenantId],
    queryFn: () => dealApi.list(page, 20, status, tenantId),
  });
}

/**
 * Хук для одной сделки.
 * Пример:
 *   const { data, isLoading } = useDeal(dealId);
 */
export function useDeal(dealId: string | null) {
  return useQuery({
    queryKey: ["deal", dealId],
    queryFn: () => dealApi.get(dealId as string),
    enabled: !!dealId,
  });
}

/**
 * Хук для частичного обновления сделки.
 * Подходит для:
 * - summary;
 * - languages;
 * - primary_language.
 *
 * Пример:
 *   const updateDeal = useUpdateDeal(deal.id);
 *   updateDeal.mutate({ summary: "Новое описание проекта" });
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
 * Хук для установки основного языка сделки.
 *
 * Важно:
 * - backend больше не требует отдельный endpoint /primary-language;
 * - используем единый PATCH /api/v1/deals/{deal_id}.
 *
 * Пример:
 *   const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);
 *   setPrimaryLanguage.mutate({ primary_language: "RU" });
 */
export function useSetPrimaryLanguage(dealId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { primary_language: string | null }) =>
      dealApi.update(dealId, payload),

    onSuccess: async (updatedDeal) => {
      queryClient.setQueryData<DealDetail>(["deal", dealId], updatedDeal);

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["deals"] }),
        queryClient.invalidateQueries({ queryKey: ["latest-run", dealId, true] }),
        queryClient.invalidateQueries({ queryKey: ["latest-run", dealId, false] }),
      ]);
    },
  });
}



