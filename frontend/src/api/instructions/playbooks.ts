// =============================================================
// src/api/instructions/playbooks.ts
// API functions for instruction management.
// Mirrors backend endpoints on the /api/v1/admin/ prefix.
// Access restricted to globalRole === "superadmin" users.
// =============================================================

import client from "../client";
import type {
  GlobalPlaybookItem,
  GlobalPlaybookVersion,
  InstructionCatalogResponse,
  InstructionVersionListResponse,
  InstructionVersionDetailResponse,
  InstructionVersionValidationResponse,
  InstructionVersionItem,
  PreviewInstructionRequest,
  PreviewInstructionResponse,
  InstructionDiffResponse,
  DetailWithETag,
  CreateInstructionDraftRequest,
  CloneDraftRequest,
  UpdateInstructionDraftRequest,
} from "../../types/instructions";

// Re-export request payloads for easier imports in hook modules
export type {
  CreateInstructionDraftRequest,
  CloneDraftRequest,
  UpdateInstructionDraftRequest,
};

// ─────────────────────────────────────────────────────────────
// Global Playbooks facade
// Thin adapter on top of the existing playbook domain.
// ─────────────────────────────────────────────────────────────

/**
 * Lists global playbooks.
 * GET /api/v1/admin/instructions/global
 */
export async function fetchGlobalPlaybooks(): Promise<GlobalPlaybookItem[]> {
  const res = await client.get<GlobalPlaybookItem[]>(
    "/api/v1/admin/instructions/global",
  );
  return res.data;
}

/**
 * Lists versions for a specific global playbook.
 * GET /api/v1/admin/instructions/global/:playbookId/versions
 */
export async function fetchGlobalPlaybookVersions(
  playbookId: string,
): Promise<GlobalPlaybookVersion[]> {
  const res = await client.get<GlobalPlaybookVersion[]>(
    `/api/v1/admin/instructions/global/${playbookId}/versions`,
  );
  return res.data;
}

// ─────────────────────────────────────────────────────────────
// Doc-Type Instruction Catalog
// ─────────────────────────────────────────────────────────────

/**
 * Fetches doc-type instructions catalog with extensive metadata.
 * GET /api/v1/admin/instructions/doc-types
 */
export async function fetchInstructionCatalog(): Promise<InstructionCatalogResponse> {
  const res = await client.get<InstructionCatalogResponse>(
    "/api/v1/admin/instructions/doc-types",
  );
  return res.data;
}

/**
 * Lists versions for a specific doc_type_code.
 * GET /api/v1/admin/instructions/doc-types/:code/versions
 */
export async function fetchVersionsForDocType(
  docTypeCode: string,
): Promise<InstructionVersionListResponse> {
  const res = await client.get<InstructionVersionListResponse>(
    `/api/v1/admin/instructions/doc-types/${docTypeCode}/versions`,
  );
  return res.data;
}

// ─────────────────────────────────────────────────────────────
// Instruction Version Detail — with ETag
// ─────────────────────────────────────────────────────────────

/**
 * Fetches version details and extracts the ETag header.
 * GET /api/v1/admin/instruction-versions/:versionId
 *
 * ETag is utilized for optimistic concurrency in subsequent PATCH requests.
 * Backend should include ETag in Access-Control-Expose-Headers
 * when working cross-origin.
 */
export async function fetchInstructionVersionDetail(
  versionId: string,
): Promise<DetailWithETag<InstructionVersionDetailResponse>> {
  const res = await client.get<InstructionVersionDetailResponse>(
    `/api/v1/admin/instruction-versions/${versionId}`,
  );

  // Axios normalizes headers to lowercase
  const etag =
    (res.headers["etag"] as string | undefined) ??
    (res.headers["ETag"] as string | undefined) ??
    null;

  return { data: res.data, etag };
}

// ─────────────────────────────────────────────────────────────
// Draft Creation
// ─────────────────────────────────────────────────────────────

/**
 * Creates a new draft for a doc_type_code.
 * POST /api/v1/admin/instructions/doc-types/:code/drafts
 *
 * Invoked when no pre-existing version is available to clone.
 */
export async function createInstructionDraft(
  docTypeCode: string,
  body: CreateInstructionDraftRequest,
): Promise<InstructionVersionItem> {
  const res = await client.post<{ item: InstructionVersionItem }>(
    `/api/v1/admin/instructions/doc-types/${docTypeCode}/drafts`,
    body,
  );
  return res.data.item;
}

/**
 * Clones an existing version into a new draft.
 * POST /api/v1/admin/instruction-versions/:versionId/clone-draft
 *
 * Canonical endpoint for "edit published" workflow.
 * The UI invokes this endpoint when the user clicks "Edit" on a published version.
 */
export async function cloneInstructionDraft(
  versionId: string,
  body?: CloneDraftRequest,
): Promise<InstructionVersionItem> {
  const res = await client.post<{ item: InstructionVersionItem }>(
    `/api/v1/admin/instruction-versions/${versionId}/clone-draft`,
    body ?? {},
  );
  return res.data.item;
}

// ─────────────────────────────────────────────────────────────
// Draft CRUD — with ETag concurrency
// ─────────────────────────────────────────────────────────────

/**
 * Updates a draft.
 * PATCH /api/v1/admin/instruction-versions/:versionId
 *
 * REQUIRES an If-Match header with the current ETag.
 * Missing If-Match → 428 Precondition Required.
 * Outdated ETag → 412 Precondition Failed.
 */
export async function updateInstructionDraft(
  versionId: string,
  body: UpdateInstructionDraftRequest,
  etag: string,
): Promise<InstructionVersionItem> {
  const res = await client.patch<{ item: InstructionVersionItem }>(
    `/api/v1/admin/instruction-versions/${versionId}`,
    body,
    {
      headers: {
        "If-Match": etag,
      },
    },
  );
  return res.data.item;
}

// ─────────────────────────────────────────────────────────────
// Lifecycle: Validate / Publish / Archive
// ─────────────────────────────────────────────────────────────

/**
 * Performs server-side validation on a draft.
 * POST /api/v1/admin/instruction-versions/:versionId/validate
 *
 * Persists validation report artifacts in the database.
 * Does not require If-Match headers.
 */
export async function validateInstructionDraft(
  versionId: string,
): Promise<InstructionVersionValidationResponse> {
  const res = await client.post<InstructionVersionValidationResponse>(
    `/api/v1/admin/instruction-versions/${versionId}/validate`,
  );
  return res.data;
}

/**
 * Publishes a validated draft.
 * POST /api/v1/admin/instruction-versions/:versionId/publish
 *
 * Backend validates the draft again before publishing.
 * Transitions state from "draft" to "published".
 */
export async function publishInstructionDraft(
  versionId: string,
): Promise<InstructionVersionItem> {
  const res = await client.post<{ item: InstructionVersionItem }>(
    `/api/v1/admin/instruction-versions/${versionId}/publish`,
  );
  return res.data.item;
}

/**
 * Archives a version.
 * POST /api/v1/admin/instruction-versions/:versionId/archive
 */
export async function archiveInstructionVersion(
  versionId: string,
): Promise<InstructionVersionItem> {
  const res = await client.post<{ item: InstructionVersionItem }>(
    `/api/v1/admin/instruction-versions/${versionId}/archive`,
  );
  return res.data.item;
}

// ─────────────────────────────────────────────────────────────
// Preview & Diff
// ─────────────────────────────────────────────────────────────

/**
 * Previews instruction YAML compilation without saving.
 * POST /api/v1/admin/instructions/doc-types/:code/preview
 *
 * Returns: is_valid, diagnostics, compiled_payload, checks_count,
 * source_sha256, and already_exists hint.
 */
export async function previewInstruction(
  docTypeCode: string,
  body: PreviewInstructionRequest,
): Promise<PreviewInstructionResponse> {
  const res = await client.post<PreviewInstructionResponse>(
    `/api/v1/admin/instructions/doc-types/${docTypeCode}/preview`,
    body,
  );
  return res.data;
}

/**
 * Unified diff between two versions.
 * GET /api/v1/admin/instruction-versions/:versionId/diff?against=:otherId
 */
export async function diffInstructionVersions(
  versionId: string,
  againstVersionId: string,
): Promise<InstructionDiffResponse> {
  const res = await client.get<InstructionDiffResponse>(
    `/api/v1/admin/instruction-versions/${versionId}/diff`,
    {
      params: { against: againstVersionId },
    },
  );
  return res.data;
}


