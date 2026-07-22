// src/hooks/instructions/useGlobalInstructions.ts
// TanStack Query hooks для global instruction lifecycle.
// Зеркало useInstructionVersions.ts.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchGlobalInstructionCatalog,
  fetchVersionsForGlobalInstruction,
  fetchGlobalInstructionVersionDetail,
  createGlobalInstructionDraft,
  cloneGlobalInstructionDraft,
  validateGlobalInstructionDraft,
  publishGlobalInstructionDraft,
  archiveGlobalInstructionVersion,
  previewGlobalInstruction,
  diffGlobalInstructionVersions,
} from "../../api/instructions/globalInstructions";
import type {
  CreateGlobalInstructionDraftRequest,
  CloneGlobalDraftRequest,
} from "../../api/instructions/globalInstructions";

// ── Query Keys ─────────────────────────────────────────────────

export const globalInstructionQueryKeys = {
  catalog: () => ["global-instruction-catalog"] as const,
  versions: (instructionCode: string) =>
    ["global-instruction-versions", instructionCode] as const,
  versionDetail: (versionId: string) =>
    ["global-instruction-version-detail", versionId] as const,
  versionDiff: (versionId: string, againstId: string) =>
    ["global-instruction-version-diff", versionId, againstId] as const,
} as const;

// ── Catalog & Versions ─────────────────────────────────────────

export function useGlobalInstructionCatalog() {
  return useQuery({
    queryKey: globalInstructionQueryKeys.catalog(),
    queryFn: fetchGlobalInstructionCatalog,
  });
}

export function useGlobalInstructionVersions(
  instructionCode: string | null,
) {
  return useQuery({
    queryKey: globalInstructionQueryKeys.versions(instructionCode ?? ""),
    queryFn: () => fetchVersionsForGlobalInstruction(instructionCode!),
    enabled: !!instructionCode,
  });
}

// ── Version Detail ─────────────────────────────────────────────

export function useGlobalInstructionVersionDetail(
  versionId: string | null,
) {
  return useQuery({
    queryKey: globalInstructionQueryKeys.versionDetail(versionId ?? ""),
    queryFn: async () => {
      const result = await fetchGlobalInstructionVersionDetail(versionId!);
      // ETag управляется в useETagConcurrency, в кэш попадает только item
      return result.data.item;
    },
    enabled: !!versionId,
    staleTime: 30_000,
  });
}

// ── Diff ───────────────────────────────────────────────────────

export function useGlobalInstructionVersionDiff(
  versionId: string | null,
  againstId: string | null,
) {
  return useQuery({
    queryKey: globalInstructionQueryKeys.versionDiff(
      versionId ?? "",
      againstId ?? "",
    ),
    queryFn: () => diffGlobalInstructionVersions(versionId!, againstId!),
    enabled: !!versionId && !!againstId,
    staleTime: 5 * 60_000,
  });
}

// ── Mutations ──────────────────────────────────────────────────

export function useCreateGlobalInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      instructionCode,
      body,
    }: {
      instructionCode: string;
      body: CreateGlobalInstructionDraftRequest;
    }) => createGlobalInstructionDraft(instructionCode, body),

    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versions(variables.instructionCode),
      });
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.catalog(),
      });
    },
  });
}

export function useCloneGlobalInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      versionId,
      body,
    }: {
      versionId: string;
      body?: CloneGlobalDraftRequest;
    }) => cloneGlobalInstructionDraft(versionId, body),

    onSuccess: (newDraft) => {
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versions(
          newDraft.instruction_code,
        ),
      });
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.catalog(),
      });
    },
  });
}

export function useValidateGlobalInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId }: { versionId: string }) =>
      validateGlobalInstructionDraft(versionId),

    onSuccess: (result) => {
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versionDetail(result.item.id),
      });
    },
  });
}

export function usePublishGlobalInstructionDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId }: { versionId: string }) =>
      publishGlobalInstructionDraft(versionId),

    onSuccess: (published) => {
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versions(
          published.instruction_code,
        ),
      });
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.catalog(),
      });
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versionDetail(published.id),
      });
    },
  });
}

export function useArchiveGlobalInstructionVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId }: { versionId: string }) =>
      archiveGlobalInstructionVersion(versionId),

    onSuccess: (archived) => {
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versions(
          archived.instruction_code,
        ),
      });
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.catalog(),
      });
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versionDetail(archived.id),
      });
    },
  });
}

export function usePreviewGlobalInstruction() {
  return useMutation({
    mutationFn: ({
      instructionCode,
      sourceYaml,
    }: {
      instructionCode: string;
      sourceYaml: string;
    }) =>
      previewGlobalInstruction(instructionCode, { source_yaml: sourceYaml }),
  });
}


