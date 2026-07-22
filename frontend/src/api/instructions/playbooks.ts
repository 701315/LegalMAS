// src/api/instructions/playbooks.ts
// API функции для instruction management.
// Строго соответствует реальным backend endpoints.
//
// Backend prefix: /api/v1/admin/...
// Все endpoints требуют globalRole === "superadmin"

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

// Реэкспортируем request-типы чтобы hooks могли импортировать их отсюда
export type {
  CreateInstructionDraftRequest,
  CloneDraftRequest,
  UpdateInstructionDraftRequest,
};

// ─────────────────────────────────────────────────────────────
// Global Playbooks facade
// Thin adapter над существующим playbook domain.
// ─────────────────────────────────────────────────────────────

/**
 * Список global playbooks.
 * GET /api/v1/admin/instructions/global
 */
export async function fetchGlobalPlaybooks(): Promise<GlobalPlaybookItem[]> {
  const res = await client.get<GlobalPlaybookItem[]>(
    "/api/v1/admin/instructions/global",
  );
  return res.data;
}

/**
 * Список версий для конкретного global playbook.
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
 * Каталог doc-type инструкций — богатый список с метаданными.
 * GET /api/v1/admin/instructions/doc-types
 */
export async function fetchInstructionCatalog(): Promise<InstructionCatalogResponse> {
  const res = await client.get<InstructionCatalogResponse>(
    "/api/v1/admin/instructions/doc-types",
  );
  return res.data;
}

/**
 * Список версий для конкретного doc_type_code.
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
// Instruction Version Detail — с ETag
// ─────────────────────────────────────────────────────────────

/**
 * Детали версии + ETag из response headers.
 * GET /api/v1/admin/instruction-versions/:versionId
 *
 * ETag используется для optimistic concurrency в PATCH.
 * Backend должен включать ETag в Access-Control-Expose-Headers
 * если работаем cross-origin.
 */
export async function fetchInstructionVersionDetail(
  versionId: string,
): Promise<DetailWithETag<InstructionVersionDetailResponse>> {
  const res = await client.get<InstructionVersionDetailResponse>(
    `/api/v1/admin/instruction-versions/${versionId}`,
  );

  // Axios нормализует заголовки к нижнему регистру
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
 * Создать новый draft для doc_type_code.
 * POST /api/v1/admin/instructions/doc-types/:code/drafts
 *
 * Используется когда нет существующей версии для клонирования.
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
 * Клонировать существующую версию в новый draft.
 * POST /api/v1/admin/instruction-versions/:versionId/clone-draft
 *
 * Это canonical endpoint для "edit published" flow.
 * UI должен использовать этот endpoint когда пользователь нажимает
 * "Редактировать" на published версии.
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
// Draft CRUD — с ETag concurrency
// ─────────────────────────────────────────────────────────────

/**
 * Обновить draft.
 * PATCH /api/v1/admin/instruction-versions/:versionId
 *
 * ТРЕБУЕТ If-Match header с текущим ETag.
 * Без If-Match → 428 Precondition Required.
 * Устаревший ETag → 412 Precondition Failed.
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
 * Валидировать draft (server-side).
 * POST /api/v1/admin/instruction-versions/:versionId/validate
 *
 * Персистирует validation artifacts в БД.
 * Не требует If-Match — read-only с side effects на validation_report.
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
 * Опубликовать validated draft.
 * POST /api/v1/admin/instruction-versions/:versionId/publish
 *
 * Backend проверяет что draft валиден перед публикацией.
 * Переводит draft → published.
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
 * Архивировать версию.
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
 * Preview instruction YAML без сохранения.
 * POST /api/v1/admin/instructions/doc-types/:code/preview
 *
 * Возвращает: is_valid, diagnostics, compiled_payload, checks_count,
 * source_sha256, already_exists hint.
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
 * Diff между двумя версиями.
 * GET /api/v1/admin/instruction-versions/:versionId/diff?against=:otherId
 *
 * Возвращает unified diff текст и metadata обеих версий.
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


