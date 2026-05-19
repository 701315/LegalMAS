// =============================================================
// src/api/deals.ts
// API-функции и React Query хуки для работы со сделками.
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
    client
      .get<DealDetail>(`/api/v1/deals/${dealId}`)
      .then((response) => response.data),

  /**
   * Частично обновить сделку.
   * PATCH /api/v1/deals/{deal_id}
   *
   * Используется только для обычных полей сделки,
   * которые не требуют отдельной бизнес-логики продолжения пайплайна.
   */
  update: (dealId: string, payload: DealUpdatePayload) =>
    client
      .patch<DealDetail>(`/api/v1/deals/${dealId}`, payload)
      .then((response) => response.data),

  /**
   * Установить основной язык сделки.
   * PATCH /api/v1/deals/{deal_id}/primary-language
   *
   * Это отдельная доменная операция:
   * backend валидирует язык, может реактивировать документы
   * и перезапустить нужный участок пайплайна.
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
export function useDeal(
  dealId: string | null,
  options?: { refetchInterval?: number | false | ((query: { state: { data?: DealDetail } }) => number | false) },
) {
  return useQuery({
    queryKey: ["deal", dealId],
    queryFn: () => dealApi.get(dealId as string),
    enabled: !!dealId,
    refetchInterval: options?.refetchInterval,
  });
}

/**
 * Хук для частичного обновления сделки.
 * Подходит для обычных полей, например:
 * - summary;
 * - другие простые поля сделки.
 *
 * Не используем этот хук для primary_language,
 * потому что выбор основного языка запускает отдельную
 * backend-логику продолжения пайплайна.
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
 * - используем специальный endpoint /primary-language;
 * - backend сам выполнит всю нужную continuation logic;
 * - после успешного ответа обновляем deal и связанные run-query.
 *
 * Пример:
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



