// src/hooks/instructions/useInstructionVersions.ts
// TanStack Query hooks для instruction management.
// Все функции строго соответствуют реальному backend contract.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveInstructionVersion,
  cloneInstructionDraft,
  createInstructionDraft,
  diffInstructionVersions,
  fetchGlobalPlaybooks,
  fetchGlobalPlaybookVersions,
  fetchInstructionCatalog,
  fetchInstructionVersionDetail,
  fetchVersionsForDocType,
  previewInstruction,
  publishInstructionDraft,
  validateInstructionDraft,
} from "../../api/instructions/playbooks";
import type {
  CloneDraftRequest,
  CreateInstructionDraftRequest,
} from "../../api/instructions/playbooks";

// ─────────────────────────────────────────────────────────────
// Query Keys
// ─────────────────────────────────────────────────────────────

export const instructionQueryKeys = {
  // Global playbooks list
  globalPlaybooks: () => ["global-playbooks"] as const,

  // Versions of a global playbook
  globalPlaybookVersions: (playbookId: string) =>
    ["global-playbook-versions", playbookId] as const,

  // Doc-type catalog (rich list)
  instructionCatalog: () => ["instruction-catalog"] as const,

  // Versions for a doc_type_code
  docTypeVersions: (docTypeCode: string) =>
    ["doc-type-versions", docTypeCode] as const,

  // Detail version (полные данные + source_yaml + compiled_payload)
  versionDetail: (versionId: string) =>
    ["instruction-version-detail", versionId] as const,

  // Diff между двумя версиями
  versionDiff: (versionId: string, againstId: string) =>
    ["instruction-version-diff", versionId, againstId] as const,
} as const;

// ─────────────────────────────────────────────────────────────
// Global Playbooks
// ─────────────────────────────────────────────────────────────

export function useGlobalPlaybooks() {
  return useQuery({
    queryKey: instructionQueryKeys.globalPlaybooks(),
    queryFn: fetchGlobalPlaybooks,
  });
}

export function useGlobalPlaybookVersions(playbookId: string | null) {
  return useQuery({
    queryKey: instructionQueryKeys.globalPlaybookVersions(playbookId ?? ""),
    queryFn: () => fetchGlobalPlaybookVersions(playbookId!),
    enabled: !!playbookId,
  });
}

// ─────────────────────────────────────────────────────────────
// Doc-Type Catalog & Versions
// ─────────────────────────────────────────────────────────────

export function useInstructionCatalog() {
  return useQuery({
    queryKey: instructionQueryKeys.instructionCatalog(),
    queryFn: fetchInstructionCatalog,
  });
}

export function useDocTypeVersions(docTypeCode: string | null) {
  return useQuery({
    queryKey: instructionQueryKeys.docTypeVersions(docTypeCode ?? ""),
    queryFn: () => fetchVersionsForDocType(docTypeCode!),
    enabled: !!docTypeCode,
  });
}

// ─────────────────────────────────────────────────────────────
// Version Detail
// ETag из этого запроса НЕ хранится в TanStack Query кэше —
// он живёт в useETagConcurrency ref.
// Этот hook используем только для отображения данных (read).
// ─────────────────────────────────────────────────────────────

export function useInstructionVersionDetail(versionId: string | null) {
  return useQuery({
    queryKey: instructionQueryKeys.versionDetail(versionId ?? ""),
    queryFn: async () => {
      const result = await fetchInstructionVersionDetail(versionId!);
      // В кэш попадает только data.item, ETag управляется в useETagConcurrency
      return result.data.item;
    },
    enabled: !!versionId,
    staleTime: 30_000,
  });
}

// ─────────────────────────────────────────────────────────────
// Diff
// ─────────────────────────────────────────────────────────────

export function useVersionDiff(
  versionId: string | null,
  againstId: string | null,
) {
  return useQuery({
    queryKey: instructionQueryKeys.versionDiff(
      versionId ?? "",
      againstId ?? "",
    ),
    queryFn: () => diffInstructionVersions(versionId!, againstId!),
    enabled: !!versionId && !!againstId,
    // Diff не меняется если версии не меняются — кэшируем надолго
    staleTime: 5 * 60_000,
  });
}

// ─────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────

/**
 * Создать новый draft для doc_type_code.
 */
export function useCreateInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      docTypeCode,
      body,
    }: {
      docTypeCode: string;
      body: CreateInstructionDraftRequest;
    }) => createInstructionDraft(docTypeCode, body),

    onSuccess: (_data, variables) => {
      // Инвалидируем список версий для этого doc_type
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.docTypeVersions(variables.docTypeCode),
      });
      // Инвалидируем каталог (draft_versions_count мог измениться)
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.instructionCatalog(),
      });
    },
  });
}

/**
 * Клонировать существующую версию в новый draft.
 * Canonical endpoint для "edit published" flow.
 */
export function useCloneInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      versionId,
      body,
    }: {
      versionId: string;
      body?: CloneDraftRequest;
    }) => cloneInstructionDraft(versionId, body),

    onSuccess: (newDraft) => {
      // Инвалидируем список версий для этого doc_type
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.docTypeVersions(newDraft.doc_type_code),
      });
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.instructionCatalog(),
      });
    },
  });
}

/**
 * Валидировать draft.
 */
export function useValidateInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId }: { versionId: string }) =>
      validateInstructionDraft(versionId),

    onSuccess: (result) => {
      // Инвалидируем detail — validation_report обновился
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.versionDetail(result.item.id),
      });
    },
  });
}

/**
 * Опубликовать draft.
 */
export function usePublishInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId }: { versionId: string }) =>
      publishInstructionDraft(versionId),

    onSuccess: (published) => {
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.docTypeVersions(published.doc_type_code),
      });
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.instructionCatalog(),
      });
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.versionDetail(published.id),
      });
    },
  });
}

/**
 * Архивировать версию.
 */
export function useArchiveInstructionVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId }: { versionId: string }) =>
      archiveInstructionVersion(versionId),

    onSuccess: (archived) => {
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.docTypeVersions(archived.doc_type_code),
      });
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.instructionCatalog(),
      });
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.versionDetail(archived.id),
      });
    },
  });
}

/**
 * Preview instruction YAML без сохранения.
 */
export function usePreviewInstruction() {
  return useMutation({
    mutationFn: ({
      docTypeCode,
      sourceYaml,
    }: {
      docTypeCode: string;
      sourceYaml: string;
    }) => previewInstruction(docTypeCode, { source_yaml: sourceYaml }),
  });
}


