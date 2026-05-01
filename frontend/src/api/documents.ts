// =============================================================
// src/api/documents.ts
// API-функции и React Query хуки для работы с документами.
// Использует Axios-клиент из src/api/client.ts.
// =============================================================

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type {
  Document,
  DocumentDetail,
  DocumentFamilyDto,
  DocumentListItem,
  PaginatedResponse,
  ReclassifyInput,
  ReclassifyResult,
  StructuredDataResult,
  DocumentColumnId,
} from "../types";

export interface DocumentLayoutsDebugResponse {
  document_id: string;
  deal_id: string;
  raw_layout_ref: string | null;
  sanitized_layout_ref: string | null;
  raw_layout: Record<string, unknown> | null;
  sanitized_layout: Record<string, unknown> | null;
}

const ACTIVE_PROCESSING_STATUSES = new Set<string>([
  "created",
  "uploaded",
  "pending",
  "converting",
  "primary_ready",
  "extracting",
  "extracted",
  "sanitizing",
  "sanitized",
  "structuring",
  "structured",
  "chunking",
  "chunked",
  "classifying",
  "language_selection_required",
]);

const DOCUMENTS_POLL_INTERVAL_MS = 2000;

function shouldPollDocuments(
  data?: PaginatedResponse<DocumentListItem>,
): boolean {
  const items = data?.items ?? [];
  return items.some((doc) => ACTIVE_PROCESSING_STATUSES.has(doc.status));
}

function shouldPollDocumentDetail(data?: DocumentDetail): boolean {
  const status = data?.document?.status;
  return !!status && ACTIVE_PROCESSING_STATUSES.has(status);
}

// -------------------------------------------------------------
// НИЗКОУРОВНЕВЫЙ API-КЛИЕНТ
// -------------------------------------------------------------

export const documentApi = {
  list: (
    dealId: string,
    page = 1,
    perPage = 50,
    opts?: {
      include_classification?: boolean;
      status?: string;
      doc_type?: string;
    },
  ) =>
    client
      .get<PaginatedResponse<DocumentListItem>>(
        `/api/v1/deals/${dealId}/documents`,
        {
          params: {
            page,
            per_page: perPage,
            include_classification: opts?.include_classification,
            status: opts?.status,
            doc_type: opts?.doc_type,
          },
        },
      )
      .then((r) => r.data),

  get: (docId: string) =>
    client
      .get<DocumentDetail>(`/api/v1/documents/${docId}`)
      .then((response) => response.data),

  getFamily: (docId: string) =>
    client
      .get<DocumentFamilyDto>(`/api/v1/documents/${docId}/family`)
      .then((response) => response.data),

  getPdfUrl: (docId: string) =>
    client
      .get<{ url: string }>(`/api/v1/documents/${docId}/pdf-url`)
      .then((r) => r.data),

  getChunkViewUrl: (docId: string) =>
    client
      .get<{ url: string }>(`/api/v1/documents/${docId}/chunk-view`)
      .then((r) => r.data),

  reclassify: (docId: string, data: ReclassifyInput) =>
    client
      .post<ReclassifyResult>(
        `/api/v1/documents/${docId}/reclassify`,
        data,
      )
      .then((response) => response.data),

  getStructuredData: (docId: string) =>
    client
      .get<StructuredDataResult>(
        `/api/v1/documents/${docId}/extracted-values`,
      )
      .then((response) => response.data),

  getLayoutsDebug: (docId: string) =>
    client
      .get<DocumentLayoutsDebugResponse>(
        `/api/v1/documents/${docId}/debug/layouts`,
        {
          params: {
            includeraw: true,
            includesanitized: true,
          },
        },
      )
      .then((r) => r.data),

  upload: (
    dealId: string,
    files: File[],
    options?: { folderPath?: string | null },
  ): Promise<{
    status?: string;
    files_uploaded?: number;
    [key: string]: unknown;
  }> => {
    const formData = new FormData();

    files.forEach((file) => {
      formData.append("files", file);
    });

    const params = new URLSearchParams();
    if (options?.folderPath) {
      params.set("folder_path", options.folderPath);
    }

    const query = params.toString();
    const url = query
      ? `/api/v1/deals/${dealId}/documents/upload?${query}`
      : `/api/v1/deals/${dealId}/documents/upload`;

    return client
      .post(url, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      })
      .then((r) => {
        const data = r.data ?? {};
        if (Array.isArray(data)) {
          return {
            status: "queued",
            files_uploaded: 0,
          } as {
            status?: string;
            files_uploaded?: number;
            [key: string]: unknown;
          };
        }
        return data as {
          status?: string;
          files_uploaded?: number;
          [key: string]: unknown;
        };
      });
  },

  softDelete: (docId: string) =>
    client
      .post<{ status: string; document_id: string; new_status: string }>(
        `/api/v1/documents/${docId}/delete`,
      )
      .then((r) => r.data),

  setReviewed: (docId: string, reviewedByPerson: boolean) =>
    client
      .patch<Document>(
        `/api/v1/documents/${docId}/reviewed`,
        { reviewed_by_person: reviewedByPerson },
      )
      .then((r) => r.data),

  exportExcel: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<ArrayBuffer>(
        "/api/v1/documents/export/excel",
        {
          deal_id: dealId,
          visible_column_ids:
            visibleColumnIds && visibleColumnIds.length > 0
              ? visibleColumnIds
              : null,
        },
        {
          responseType: "blob",
        },
      )
      .then((r) => r.data),

  exportWord: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<Blob>(
        "/api/v1/documents/export/word",
        {
          deal_id: dealId,
          visible_column_ids:
            visibleColumnIds && visibleColumnIds.length > 0
              ? visibleColumnIds
              : null,
        },
        {
          responseType: "blob",
        },
      )
      .then((r) => r.data),

  exportPdf: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<Blob>(
        "/api/v1/documents/export/pdf",
        {
          deal_id: dealId,
          visible_column_ids:
            visibleColumnIds && visibleColumnIds.length > 0
              ? visibleColumnIds
              : null,
        },
        {
          responseType: "blob",
        },
      )
      .then((r) => r.data),
};

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function exportDocumentsExcel(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportExcel(dealId, visibleColumnIds);
  downloadBlob(blob as unknown as Blob, `deal_${dealId}_documents.xlsx`);
}

export async function exportDocumentsWord(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportWord(dealId, visibleColumnIds);
  downloadBlob(blob as unknown as Blob, `deal_${dealId}_documents.docx`);
}

export async function exportDocumentsPDF(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportPdf(dealId, visibleColumnIds);
  downloadBlob(blob as unknown as Blob, `deal_${dealId}_documents.pdf`);
}

// -------------------------------------------------------------
// REACT QUERY ХУКИ
// -------------------------------------------------------------

export function useDocumentsWithClassification(dealId: string, page = 1) {
  return useQuery({
    queryKey: ["documents-classified", dealId, page],
    queryFn: () =>
      documentApi.list(dealId, page, 50, { include_classification: true }),
    enabled: !!dealId,
    staleTime: 2 * 60_000,
    refetchInterval: (query) => {
      const data = query.state.data as
        | PaginatedResponse<DocumentListItem>
        | undefined;
      return shouldPollDocuments(data) ? DOCUMENTS_POLL_INTERVAL_MS : false;
    },
    refetchOnWindowFocus: true,
  });
}

export function useDocuments(dealId: string, page = 1) {
  return useQuery({
    queryKey: ["documents", dealId, page],
    queryFn: () => documentApi.list(dealId, page),
    enabled: !!dealId,
    refetchInterval: (query) => {
      const data = query.state.data as
        | PaginatedResponse<DocumentListItem>
        | undefined;
      return shouldPollDocuments(data) ? DOCUMENTS_POLL_INTERVAL_MS : false;
    },
    refetchOnWindowFocus: true,
  });
}

/**
 * Лёгкий хук для получения общего количества документов по сделке.
 * Использует тот же paginated endpoint, но запрашивает только 1 элемент,
 * чтобы получить total без загрузки полного списка.
 */
export function useDocumentsCount(dealId: string) {
  return useQuery({
    queryKey: ["documents-count", dealId],
    queryFn: async () => {
      const response = await documentApi.list(dealId, 1, 1);
      return response.total;
    },
    enabled: !!dealId,
    staleTime: 2 * 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useDocumentDetail(docId: string | null) {
  return useQuery({
    queryKey: ["document", docId],
    queryFn: () => documentApi.get(docId!),
    enabled: !!docId,
    refetchInterval: (query) => {
      const data = query.state.data as DocumentDetail | undefined;
      return shouldPollDocumentDetail(data) ? DOCUMENTS_POLL_INTERVAL_MS : false;
    },
    refetchOnWindowFocus: true,
  });
}

export function useDocumentFamily(docId: string | null) {
  return useQuery({
    queryKey: ["document-family", docId],
    queryFn: () => documentApi.getFamily(docId!),
    enabled: !!docId,
  });
}

export function useDocumentPdfUrl(docId: string | null) {
  return useQuery({
    queryKey: ["document-pdf-url", docId],
    queryFn: () => documentApi.getPdfUrl(docId!),
    enabled: !!docId,
  });
}

export function useDocumentChunkViewUrl(docId: string | null) {
  return useQuery({
    queryKey: ["document-chunk-view-url", docId],
    queryFn: () => documentApi.getChunkViewUrl(docId!),
    enabled: !!docId,
  });
}

export function useDocumentLayoutsDebug(
  docId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["document-layouts-debug", docId],
    queryFn: () => documentApi.getLayoutsDebug(docId!),
    enabled: !!docId && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useStructuredData(docId: string | null) {
  return useQuery({
    queryKey: ["structured-data", docId],
    queryFn: () => documentApi.getStructuredData(docId!),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });
}

export function useReclassifyDocument(docId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (data: ReclassifyInput) =>
      documentApi.reclassify(docId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document", docId] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["documents-classified"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function useSoftDeleteDocument(dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (docId: string) => documentApi.softDelete(docId),
    onSuccess: (_data, docId) => {
      qc.invalidateQueries({ queryKey: ["document", docId] });
      qc.invalidateQueries({ queryKey: ["documents", dealId] });
      qc.invalidateQueries({ queryKey: ["documents-classified", dealId] });
      qc.invalidateQueries({ queryKey: ["deal", dealId] });
      qc.invalidateQueries({ queryKey: ["documents-count", dealId] });
    },
  });
}

export function useUploadDocuments(dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (params: { files: File[]; folderPath?: string | null }) =>
      documentApi.upload(dealId, params.files, {
        folderPath: params.folderPath,
      }),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["documents", dealId] }),
        qc.invalidateQueries({ queryKey: ["documents-classified", dealId] }),
        qc.invalidateQueries({ queryKey: ["documents-count", dealId] }),
        qc.invalidateQueries({ queryKey: ["deal", dealId] }),
      ]);
    },
  });
}

export function useSetDocumentReviewed(docId: string, dealId?: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (reviewedByPerson: boolean) =>
      documentApi.setReviewed(docId, reviewedByPerson),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document", docId] });

      if (dealId) {
        qc.invalidateQueries({ queryKey: ["documents", dealId] });
        qc.invalidateQueries({
          queryKey: ["documents-classified", dealId],
        });
      }
    },
  });
}

