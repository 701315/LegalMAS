/**
 * API-функции для журнала аудита.
 *
 * Backend endpoint:
 *   GET  /api/v1/deals/{deal_id}/audit — journal (Admin / Security Officer)
 *   POST /api/v1/audit-log            — создать запись аудита
 */

import { useQuery, useMutation } from "@tanstack/react-query";
import client from "./client";
import type { AuditLogEntry, PaginatedResponse } from "../types";

export const auditApi = {
  list: (
    dealId: string,
    params?: {
      action?: string;
      actor?: string;
      from_date?: string;
      to_date?: string;
      page?: number;
      per_page?: number;
    },
  ) =>
    client
      .get<PaginatedResponse<AuditLogEntry>>(
        `/api/v1/deals/${dealId}/audit`,
        { params },
      )
      .then((r) => r.data),

  // Создать запись аудита
  create: (payload: {
    deal_id: string | null;
    action: string;
    details: Record<string, unknown>;
  }) =>
    client
      .post<AuditLogEntry>("/api/v1/audit-log", payload)
      .then((r) => r.data),
};

export function useAuditLog(
  dealId: string,
  params?: { action?: string; page?: number; per_page?: number },
) {
  return useQuery({
    queryKey: ["audit", dealId, params],
    queryFn: () => auditApi.list(dealId, { per_page: 50, ...params }),
    enabled: !!dealId,
  });
}

// NEW: хук для записи в журнал
export function useCreateAuditLogEntry() {
  return useMutation({
    mutationFn: auditApi.create,
  });
}


