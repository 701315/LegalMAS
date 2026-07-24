// frontend/src/api/baseInstructions.ts
//
// Read-only API для базовых platform instructions.
// Используется tenant_admin и member.
// Не ходит в /admin/* — только в /api/v1/instructions/base/*.

import { useQuery } from "@tanstack/react-query";
import client from "./client";
import type {
  GlobalInstructionCatalogResponse,
  GlobalInstructionVersionDetailResponse,
  GlobalInstructionVersionListResponse,
  InstructionCatalogResponse,
  InstructionVersionDetailResponse,
  InstructionVersionListResponse,
} from "../types/instructions";

// ── Query keys ─────────────────────────────────────────────────────────────────

export const baseInstructionQueryKeys = {
  globalCatalog: () =>
    ["base-instructions", "global-catalog"] as const,
  globalVersions: (code: string) =>
    ["base-instructions", "global-versions", code] as const,
  globalVersionDetail: (versionId: string) =>
    ["base-instructions", "global-version-detail", versionId] as const,
  docTypeCatalog: () =>
    ["base-instructions", "doc-type-catalog"] as const,
  docTypeVersions: (code: string) =>
    ["base-instructions", "doc-type-versions", code] as const,
  docTypeVersionDetail: (versionId: string) =>
    ["base-instructions", "doc-type-version-detail", versionId] as const,
} as const;

// ── Global checks ──────────────────────────────────────────────────────────────

export function useBaseGlobalChecksCatalog() {
  return useQuery({
    queryKey: baseInstructionQueryKeys.globalCatalog(),
    queryFn: async () => {
      const res = await client.get<GlobalInstructionCatalogResponse>(
        "/api/v1/instructions/base/global-checks",
      );
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useBaseGlobalCheckVersions(
  instructionCode: string | null,
) {
  return useQuery({
    queryKey: baseInstructionQueryKeys.globalVersions(
      instructionCode ?? "",
    ),
    queryFn: async () => {
      const res = await client.get<GlobalInstructionVersionListResponse>(
        `/api/v1/instructions/base/global-checks/${instructionCode}/versions`,
      );
      return res.data;
    },
    enabled: !!instructionCode,
    staleTime: 60_000,
  });
}

export function useBaseGlobalCheckVersionDetail(
  versionId: string | null,
) {
  return useQuery({
    queryKey: baseInstructionQueryKeys.globalVersionDetail(
      versionId ?? "",
    ),
    queryFn: async () => {
      const res = await client.get<GlobalInstructionVersionDetailResponse>(
        `/api/v1/instructions/base/global-checks/versions/${versionId}`,
      );
      return res.data.item;
    },
    enabled: !!versionId,
    staleTime: 60_000,
  });
}

// ── Doc-type ───────────────────────────────────────────────────────────────────

export function useBaseDocTypeCatalog() {
  return useQuery({
    queryKey: baseInstructionQueryKeys.docTypeCatalog(),
    queryFn: async () => {
      const res = await client.get<InstructionCatalogResponse>(
        "/api/v1/instructions/base/doc-types",
      );
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useBaseDocTypeVersions(
  docTypeCode: string | null,
) {
  return useQuery({
    queryKey: baseInstructionQueryKeys.docTypeVersions(
      docTypeCode ?? "",
    ),
    queryFn: async () => {
      const res = await client.get<InstructionVersionListResponse>(
        `/api/v1/instructions/base/doc-types/${docTypeCode}/versions`,
      );
      return res.data;
    },
    enabled: !!docTypeCode,
    staleTime: 60_000,
  });
}

export function useBaseDocTypeVersionDetail(
  versionId: string | null,
) {
  return useQuery({
    queryKey: baseInstructionQueryKeys.docTypeVersionDetail(
      versionId ?? "",
    ),
    queryFn: async () => {
      const res = await client.get<InstructionVersionDetailResponse>(
        `/api/v1/instructions/base/doc-types/versions/${versionId}`,
      );
      return res.data.item;
    },
    enabled: !!versionId,
    staleTime: 60_000,
  });
}


