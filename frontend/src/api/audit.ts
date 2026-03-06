/**
 * API-функции для журнала аудита.
 *
 * Backend endpoint:
 *   GET /api/v1/deals/{deal_id}/audit — journal (Admin / Security Officer)
 */

import { useQuery } from "@tanstack/react-query";
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
