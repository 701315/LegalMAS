/**
 * API-функции для журнала аудита.
 *
 * Backend endpoints:
 *   GET  /api/v1/deals/{deal_id}/audit                         — journal
 *   GET  /api/v1/deals/{deal_id}/classification-investigation  — classification investigation
 *   GET  /api/v1/documents/{document_id}/classification-investigation
 *   POST /api/v1/audit-log                                     — создать запись аудита
 */

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import client from "./client";
import type {
  AuditLogEntry,
  ClassificationInvestigationDetailResponse,
  ClassificationInvestigationListResponse,
  PaginatedResponse,
} from "../types";

type AuditLogListParams = {
  action?: string;
  actor?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  per_page?: number;
};

type ClassificationInvestigationParams = {
  page?: number;
  per_page?: number;
};

export const auditApi = {
  list: (dealId: string, params?: AuditLogListParams) =>
    client
      .get<PaginatedResponse<AuditLogEntry>>(`/api/v1/deals/${dealId}/audit`, {
        params,
      })
      .then((r) => r.data),

  listClassificationInvestigation: (
    dealId: string,
    params?: ClassificationInvestigationParams,
  ) =>
    client
      .get<ClassificationInvestigationListResponse>(
        `/api/v1/deals/${dealId}/classification-investigation`,
        { params },
      )
      .then((r) => r.data),

  getClassificationInvestigationDetail: (documentId: string) =>
    client
      .get<ClassificationInvestigationDetailResponse>(
        `/api/v1/documents/${documentId}/classification-investigation`,
      )
      .then((r) => r.data),

  create: (payload: {
    deal_id: string | null;
    action: string;
    details: Record<string, unknown>;
  }) =>
    client.post<AuditLogEntry>("/api/v1/audit-log", payload).then((r) => r.data),
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

export function useClassificationInvestigation(
  dealId: string,
  params?: ClassificationInvestigationParams,
) {
  return useQuery({
    queryKey: ["classification-investigation", dealId, params],
    queryFn: () =>
      auditApi.listClassificationInvestigation(dealId, {
        per_page: 20,
        ...params,
      }),
    enabled: !!dealId,
    placeholderData: keepPreviousData,
  });
}

export function useClassificationInvestigationDetail(documentId: string | null) {
  return useQuery({
    queryKey: ["classification-investigation-detail", documentId],
    queryFn: () => auditApi.getClassificationInvestigationDetail(documentId as string),
    enabled: !!documentId,
  });
}

export function useCreateAuditLogEntry() {
  return useMutation({
    mutationFn: auditApi.create,
  });
}




