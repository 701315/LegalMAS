// src/api/instructions/globalInstructions.ts
// API функции для global instruction lifecycle.
// Зеркало playbooks.ts под /admin/instructions/global-checks.

import client from "../client";
import type {
  GlobalInstructionCatalogResponse,
  GlobalInstructionVersionListResponse,
  GlobalInstructionVersionDetailResponse,
  GlobalInstructionVersionValidationResponse,
  GlobalInstructionVersionItem,
  PreviewGlobalInstructionRequest,
  PreviewGlobalInstructionResponse,
  GlobalInstructionDiffResponse,
  DetailWithETag,
  CreateGlobalInstructionDraftRequest,
  CloneGlobalDraftRequest,
  UpdateGlobalInstructionDraftRequest,
} from "../../types/instructions";

export type {
  CreateGlobalInstructionDraftRequest,
  CloneGlobalDraftRequest,
  UpdateGlobalInstructionDraftRequest,
};

// ── Catalog ────────────────────────────────────────────────────

export async function fetchGlobalInstructionCatalog(): Promise<GlobalInstructionCatalogResponse> {
  const res = await client.get<GlobalInstructionCatalogResponse>(
    "/api/v1/admin/instructions/global-checks",
  );
  return res.data;
}

export async function fetchVersionsForGlobalInstruction(
  instructionCode: string,
): Promise<GlobalInstructionVersionListResponse> {
  const res = await client.get<GlobalInstructionVersionListResponse>(
    `/api/v1/admin/instructions/global-checks/${instructionCode}/versions`,
  );
  return res.data;
}

// ── Version detail + ETag ──────────────────────────────────────

export async function fetchGlobalInstructionVersionDetail(
  versionId: string,
): Promise<DetailWithETag<GlobalInstructionVersionDetailResponse>> {
  const res = await client.get<GlobalInstructionVersionDetailResponse>(
    `/api/v1/admin/global-instruction-versions/${versionId}`,
  );
  const etag =
    (res.headers["etag"] as string | undefined) ??
    (res.headers["ETag"] as string | undefined) ??
    null;
  return { data: res.data, etag };
}

// ── Draft creation ─────────────────────────────────────────────

export async function createGlobalInstructionDraft(
  instructionCode: string,
  body: CreateGlobalInstructionDraftRequest,
): Promise<GlobalInstructionVersionItem> {
  const res = await client.post<{ item: GlobalInstructionVersionItem }>(
    `/api/v1/admin/instructions/global-checks/${instructionCode}/drafts`,
    body,
  );
  return res.data.item;
}

export async function cloneGlobalInstructionDraft(
  versionId: string,
  body?: CloneGlobalDraftRequest,
): Promise<GlobalInstructionVersionItem> {
  const res = await client.post<{ item: GlobalInstructionVersionItem }>(
    `/api/v1/admin/global-instruction-versions/${versionId}/clone-draft`,
    body ?? {},
  );
  return res.data.item;
}

// ── Draft update (ETag) ────────────────────────────────────────

export async function updateGlobalInstructionDraft(
  versionId: string,
  body: UpdateGlobalInstructionDraftRequest,
  etag: string,
): Promise<GlobalInstructionVersionItem> {
  const res = await client.patch<{ item: GlobalInstructionVersionItem }>(
    `/api/v1/admin/global-instruction-versions/${versionId}`,
    body,
    { headers: { "If-Match": etag } },
  );
  return res.data.item;
}

// ── Lifecycle ──────────────────────────────────────────────────

export async function validateGlobalInstructionDraft(
  versionId: string,
): Promise<GlobalInstructionVersionValidationResponse> {
  const res = await client.post<GlobalInstructionVersionValidationResponse>(
    `/api/v1/admin/global-instruction-versions/${versionId}/validate`,
  );
  return res.data;
}

export async function publishGlobalInstructionDraft(
  versionId: string,
): Promise<GlobalInstructionVersionItem> {
  const res = await client.post<{ item: GlobalInstructionVersionItem }>(
    `/api/v1/admin/global-instruction-versions/${versionId}/publish`,
  );
  return res.data.item;
}

export async function archiveGlobalInstructionVersion(
  versionId: string,
): Promise<GlobalInstructionVersionItem> {
  const res = await client.post<{ item: GlobalInstructionVersionItem }>(
    `/api/v1/admin/global-instruction-versions/${versionId}/archive`,
  );
  return res.data.item;
}

// ── Preview & Diff ─────────────────────────────────────────────

export async function previewGlobalInstruction(
  instructionCode: string,
  body: PreviewGlobalInstructionRequest,
): Promise<PreviewGlobalInstructionResponse> {
  const res = await client.post<PreviewGlobalInstructionResponse>(
    `/api/v1/admin/instructions/global-checks/${instructionCode}/preview`,
    body,
  );
  return res.data;
}

export async function diffGlobalInstructionVersions(
  versionId: string,
  againstVersionId: string,
): Promise<GlobalInstructionDiffResponse> {
  const res = await client.get<GlobalInstructionDiffResponse>(
    `/api/v1/admin/global-instruction-versions/${versionId}/diff`,
    { params: { against: againstVersionId } },
  );
  return res.data;
}



