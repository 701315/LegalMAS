// =============================================================
// src/api/documents.ts
// API-функции и React Query хуки для работы с документами.
// Использует Axios-клиент из src/api/client.ts.
//
// Архитектурный принцип:
// - список документов сделки имеет канонический query key: ["deal-documents", ...]
// - invalidation адресная и касается только нужной сделки;
// - total/count всегда берётся из канонического list-query ответа,
//   а не из отдельного count-query.
// =============================================================

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";
import type {
  Document,
  DocumentColumnId,
  DocumentDetail,
  DocumentFamilyDto,
  DocumentListItem,
  PaginatedResponse,
  ReclassifyInput,
  ReclassifyResult,
  StructuredDataResult,
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

/**
 * Единая фабрика query keys для документов.
 */
export const documentKeys = {
  all: ["deal-documents"] as const,
  byDeal: (dealId: string) => ["deal-documents", dealId] as const,
  list: (
    dealId: string,
    page: number,
    opts?: {
      includeClassification?: boolean;
      status?: string;
      docType?: string;
    },
  ) =>
    [
      ...documentKeys.byDeal(dealId),
      page,
      {
        includeClassification: opts?.includeClassification ?? false,
        status: opts?.status ?? null,
        docType: opts?.docType ?? null,
      },
    ] as const,
  detail: (docId: string) => ["document", docId] as const,
  family: (docId: string) => ["document-family", docId] as const,
  pdfUrl: (docId: string) => ["document-pdf-url", docId] as const,
  chunkViewUrl: (docId: string) => ["document-chunk-view-url", docId] as const,
  layoutsDebug: (docId: string) => ["document-layouts-debug", docId] as const,
  structuredData: (docId: string) => ["structured-data", docId] as const,
};

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
      .post<ReclassifyResult>(`/api/v1/documents/${docId}/reclassify`, data)
      .then((response) => response.data),

  getStructuredData: (docId: string) =>
    client
      .get<StructuredDataResult>(`/api/v1/documents/${docId}/extracted-values`)
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
      .patch<Document>(`/api/v1/documents/${docId}/reviewed`, {
        reviewed_by_person: reviewedByPerson,
      })
      .then((r) => r.data),

  exportExcel: (dealId: string, visibleColumnIds: DocumentColumnId[] | null) =>
    client
      .post<Blob>(
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
  downloadBlob(blob, `deal_${dealId}_documents.xlsx`);
}

export async function exportDocumentsWord(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportWord(dealId, visibleColumnIds);
  downloadBlob(blob, `deal_${dealId}_documents.docx`);
}

export async function exportDocumentsPDF(
  dealId: string,
  visibleColumnIds: DocumentColumnId[] | null,
): Promise<void> {
  const blob = await documentApi.exportPdf(dealId, visibleColumnIds);
  downloadBlob(blob, `deal_${dealId}_documents.pdf`);
}

export function useDocumentsWithClassification(dealId: string, page = 1) {
  return useQuery({
    queryKey: documentKeys.list(dealId, page, {
      includeClassification: true,
    }),
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
    queryKey: documentKeys.list(dealId, page),
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

export function useDocumentDetail(docId: string | null) {
  return useQuery({
    queryKey: docId ? documentKeys.detail(docId) : ["document", null],
    queryFn: () => documentApi.get(docId as string),
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
    queryKey: docId ? documentKeys.family(docId) : ["document-family", null],
    queryFn: () => documentApi.getFamily(docId as string),
    enabled: !!docId,
  });
}

export function useDocumentPdfUrl(docId: string | null) {
  return useQuery({
    queryKey: docId ? documentKeys.pdfUrl(docId) : ["document-pdf-url", null],
    queryFn: () => documentApi.getPdfUrl(docId as string),
    enabled: !!docId,
  });
}

export function useDocumentChunkViewUrl(docId: string | null) {
  return useQuery({
    queryKey: docId
      ? documentKeys.chunkViewUrl(docId)
      : ["document-chunk-view-url", null],
    queryFn: () => documentApi.getChunkViewUrl(docId as string),
    enabled: !!docId,
  });
}

export function useDocumentLayoutsDebug(
  docId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: docId
      ? documentKeys.layoutsDebug(docId)
      : ["document-layouts-debug", null],
    queryFn: () => documentApi.getLayoutsDebug(docId as string),
    enabled: !!docId && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useStructuredData(docId: string | null) {
  return useQuery({
    queryKey: docId
      ? documentKeys.structuredData(docId)
      : ["structured-data", null],
    queryFn: () => documentApi.getStructuredData(docId as string),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  });
}

export function useReclassifyDocument(docId: string, dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (data: ReclassifyInput) => documentApi.reclassify(docId, data),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: documentKeys.detail(docId) }),
        qc.invalidateQueries({ queryKey: documentKeys.byDeal(dealId) }),
        qc.invalidateQueries({ queryKey: ["audit", dealId] }),
      ]);
    },
  });
}

export function useSoftDeleteDocument(dealId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (docId: string) => documentApi.softDelete(docId),
    onSuccess: async (_data, docId) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: documentKeys.detail(docId) }),
        qc.invalidateQueries({ queryKey: documentKeys.byDeal(dealId) }),
        qc.invalidateQueries({ queryKey: ["deal", dealId] }),
      ]);
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
        qc.invalidateQueries({ queryKey: documentKeys.byDeal(dealId) }),
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
    onSuccess: async () => {
      const tasks = [qc.invalidateQueries({ queryKey: documentKeys.detail(docId) })];

      if (dealId) {
        tasks.push(
          qc.invalidateQueries({ queryKey: documentKeys.byDeal(dealId) }),
        );
      }

      await Promise.all(tasks);
    },
  });
}

