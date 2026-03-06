// =============================================================
// src/api/requests.ts
// API-функции и React Query хуки для работы с DD-запросами.
// =============================================================

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type { DDRequest, DDRequestCreateInput } from "../types";

export const requestsApi = {
  list: (
    dealId: string,
    params?: { status?: string; priority?: string },
  ) =>
    client
      .get<DDRequest[]>(`/api/v1/deals/${dealId}/requests`, { params })
      .then((r) => r.data),

  create: (dealId: string, data: DDRequestCreateInput) =>
    client
      .post<DDRequest>(`/api/v1/deals/${dealId}/requests`, data)
      .then((r) => r.data),

  update: (reqId: string, data: Partial<DDRequest>) =>
    client
      .patch<DDRequest>(`/api/v1/requests/${reqId}`, data)
      .then((r) => r.data),

  remove: (reqId: string) =>
    client.delete<void>(`/api/v1/requests/${reqId}`).then((r) => r.data),

  /** Экспорт DD-запросов по сделке в Word/Excel. */
  export: (dealId: string, format: "word" | "excel") =>
    client
      .post<Blob>(
        `/api/v1/deals/${dealId}/requests/export`,
        null,
        {
          params: { format },
          responseType: "blob",
        },
      )
      .then((r) => r.data),
};


// хуки

export function useRequests(
  dealId: string,
  params?: { status?: string; priority?: string },
) {
  return useQuery({
    queryKey: ["requests", dealId, params],
    queryFn: () => requestsApi.list(dealId, params),
    enabled: !!dealId,
  });
}

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { dealId: string; data: DDRequestCreateInput }) =>
      requestsApi.create(args.dealId, args.data),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ["requests", vars.dealId] });
    },
  });
}

export function useUpdateRequest(dealId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { reqId: string; data: Partial<DDRequest> }) =>
      requestsApi.update(args.reqId, args.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["requests", dealId] });
    },
  });
}

export function useDeleteRequest(dealId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reqId: string) => requestsApi.remove(reqId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["requests", dealId] });
    },
  });
}

export function useExportRequests() {
  return useMutation({
    mutationFn: (args: { dealId: string; format: "word" | "excel" }) =>
      requestsApi.export(args.dealId, args.format),
  });
}

