// =============================================================
// src/api/deals.ts
// API-функции и React Query хуки для работы со сделками.
// =============================================================

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type { Deal, DealDetail, PaginatedResponse } from "../types";

// -------------------------------------------------------------
// НИЗКОУРОВНЕВЫЙ API-КЛИЕНТ
// -------------------------------------------------------------

export const dealApi = {
  /**
   * Список сделок.
   * GET /api/v1/deals?page=&per_page=
   */
  list: (page = 1, perPage = 20) =>
    client
      .get<PaginatedResponse<Deal>>("/api/v1/deals", {
        params: { page, per_page: perPage },
      })
      .then((response) => response.data),

  /**
   * Детали одной сделки.
   * GET /api/v1/deals/{deal_id}
   */
  get: (dealId: string) =>
    client
      .get<DealDetail>(`/api/v1/deals/${dealId}`)
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
export function useDeals(page = 1) {
  return useQuery({
    queryKey: ["deals", page],
    queryFn: () => dealApi.list(page),
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
    queryFn: () => dealApi.get(dealId!),
    enabled: !!dealId,
  });
}
