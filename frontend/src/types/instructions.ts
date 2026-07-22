// src/types/instructions.ts
// Domain types для instruction management.
// Строго соответствует backend schemas.

// ─────────────────────────────────────────────────────────────
// Shared / базовые типы
// ─────────────────────────────────────────────────────────────

export type InstructionVersionStatus =
  | "draft"
  | "published"
  | "archived";

export type SourceFormat = "yaml" | "json";

// ─────────────────────────────────────────────────────────────
// Global Playbooks (Playbook domain — /admin/instructions/global)
// Это thin facade над существующим playbook domain.
// ─────────────────────────────────────────────────────────────

/**
 * PlaybookLineShort — ответ от GET /admin/instructions/global
 * Соответствует backend PlaybookLineShort schema.
 */
export interface GlobalPlaybookItem {
  id: string;
  code: string;
  title: string;
  description: string | null;
  deal_type: string | null;
  jurisdiction: string | null;
  language: string | null;
  risk_profile: string | null;
}

/**
 * PlaybookVersionShort — ответ от GET /admin/instructions/global/:id/versions
 * Соответствует backend PlaybookVersionShort schema.
 */
export interface GlobalPlaybookVersion {
  id: string;
  name: string;
  semver: string;
  status: string;
  playbook_id: string;
}

// ─────────────────────────────────────────────────────────────
// Doc-Type Instruction Catalog
// GET /admin/instructions/doc-types → InstructionCatalogResponse
// ─────────────────────────────────────────────────────────────

/**
 * Один элемент каталога doc-type инструкций.
 * Содержит rich metadata: статистика версий, published/draft info.
 */
export interface InstructionCatalogItem {
  doc_type_code: string;
  name: string;
  category: string | null;
  risk_level: string | null;
  language: string | null;
  jurisdiction: string | null;
  is_registry_available: boolean;
  total_versions_count: number;
  draft_versions_count: number;
  has_published: boolean;
  // Latest version (любого статуса)
  latest_version_id: string | null;
  latest_version_status: InstructionVersionStatus | null;
  latest_version_updated_at: string | null;
  // Latest published
  latest_published_version_id: string | null;
  latest_published_at: string | null;
  latest_published_immutable_content_hash: string | null;
  // Latest draft
  latest_draft_version_id: string | null;
  latest_draft_is_valid: boolean | null;
  latest_draft_updated_at: string | null;
}

export interface InstructionCatalogResponse {
  items: InstructionCatalogItem[];
}

// ─────────────────────────────────────────────────────────────
// Instruction Version
// GET /admin/instructions/doc-types/:code/versions → InstructionVersionListResponse
// GET /admin/instruction-versions/:id → InstructionVersionDetailResponse
// ─────────────────────────────────────────────────────────────

/**
 * Краткое представление версии — в списках.
 * Соответствует backend InstructionVersionItem.
 */
export interface InstructionVersionItem {
  id: string;
  doc_type_code: string;
  name: string;
  source_format: SourceFormat | null;
  source_sha256: string | null;
  version_status: InstructionVersionStatus;
  immutable_content_hash: string | null;
  validation_report: Record<string, unknown> | null;
  parent_version_id: string | null;
  published_at: string | null;
  created_by: string | null;
  change_summary: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/**
 * Полное представление версии — в detail endpoint.
 * Включает source_yaml, compiled_payload, checks_count.
 * Соответствует backend InstructionVersionDetailItem.
 */
export interface InstructionVersionDetailItem extends InstructionVersionItem {
  source_yaml: string | null;
  source_path: string | null;
  git_commit: string | null;
  semver: string | null;
  compiled_payload: Record<string, unknown> | null;
  checks_count: number | null;
}

export interface InstructionVersionListResponse {
  doc_type_code: string;
  items: InstructionVersionItem[];
}

export interface InstructionVersionDetailResponse {
  item: InstructionVersionDetailItem;
}

// ─────────────────────────────────────────────────────────────
// Validation
// POST /admin/instruction-versions/:id/validate
// ─────────────────────────────────────────────────────────────

export interface InstructionVersionValidationResponse {
  item: InstructionVersionItem;
  is_valid: boolean;
  checks_count: number;           // оставляем для doc-type (backend возвращает)
  validation_report: Record<string, unknown> | null;
}

// GlobalInstructionVersionValidationResponse — checks_count опциональный,
// потому что global instruction = один check, backend не возвращает это поле.
export interface GlobalInstructionVersionValidationResponse {
  item: GlobalInstructionVersionItem;
  is_valid: boolean;
  checks_count?: number | null;   // ← опциональный
  validation_report: Record<string, unknown> | null;
}

// ─────────────────────────────────────────────────────────────
// Preview
// POST /admin/instructions/doc-types/:code/preview
// POST /instruction-preview (unified)
// ─────────────────────────────────────────────────────────────

export interface PreviewInstructionRequest {
  source_yaml: string;
}

export interface PreviewInstructionResponse {
  is_valid: boolean;
  checks_count: number;
  triggers_used: string[] | null;
  diagnostics: PreviewDiagnostic[] | null;
  validation_report: Record<string, unknown> | null;
  compiled_payload: Record<string, unknown> | null;
  source_sha256: string | null;
  already_exists: boolean | null;
  existing_version_id: string | null;
}

export interface PreviewDiagnostic {
  level: "error" | "warning" | "info";
  message: string;
  path?: string | null;
}

// ─────────────────────────────────────────────────────────────
// Diff
// GET /admin/instruction-versions/:id/diff?against=:other_id
// ─────────────────────────────────────────────────────────────

export interface InstructionDiffResponse {
  from_version_id: string;
  to_version_id: string;
  from_source_sha256: string | null;
  to_source_sha256: string | null;
  are_identical: boolean;
  unified_diff: string[];
}

// ─────────────────────────────────────────────────────────────
// Request типы (для API вызовов)
// ─────────────────────────────────────────────────────────────

/**
 * POST /admin/instructions/doc-types/:code/drafts
 * Создать новый draft для doc_type_code.
 */
export interface CreateInstructionDraftRequest {
  source_yaml: string;
  name: string;
  source_path?: string | null;
  git_commit?: string | null;
  semver?: string | null;
  change_summary?: string | null;
  parent_version_id?: string | null;
}

/**
 * POST /admin/instruction-versions/:id/clone-draft
 * Клонировать существующую версию в новый draft.
 * Это canonical endpoint для "edit published" flow.
 */
export interface CloneDraftRequest {
  change_summary?: string | null;
}

/**
 * PATCH /admin/instruction-versions/:id
 * Обновить существующий draft. Требует If-Match.
 */
export interface UpdateInstructionDraftRequest {
  source_yaml?: string | null;
  name?: string | null;
  source_path?: string | null;
  git_commit?: string | null;
  semver?: string | null;
  change_summary?: string | null;
}

// ─────────────────────────────────────────────────────────────
// Утилитарные типы
// ─────────────────────────────────────────────────────────────

/**
 * Wrapper для detail response с ETag из response headers.
 * ETag не хранится в TanStack Query кэше — только в useETagConcurrency ref.
 */
export interface DetailWithETag<T> {
  data: T;
  etag: string | null;
}


// ─────────────────────────────────────────────────────────────
// Instruction Overrides
// ─────────────────────────────────────────────────────────────

export type OverrideScope = "tenant" | "deal";
export type OverrideStatus = "draft" | "active" | "archived";

/**
 * JSON Patch operation (RFC 6902).
 */
export interface JsonPatchOperation {
  op: "add" | "remove" | "replace" | "move" | "copy" | "test";
  path: string;
  value?: unknown;
  from?: string;
}

/**
 * Один override — tenant-level или deal-level.
 * Соответствует backend InstructionOverrideItem.
 */
export interface InstructionOverrideItem {
  id: string;
  instruction_version_id: string;
  override_scope: OverrideScope;
  tenant_id: string;
  deal_id: string | null;
  status: OverrideStatus;
  base_content_hash: string;
  patch_ops: JsonPatchOperation[];
  is_stale: boolean;
  change_summary: string | null;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InstructionOverrideListResponse {
  items: InstructionOverrideItem[];
}

export interface InstructionOverrideResponse {
  item: InstructionOverrideItem;
}

/**
 * Результат валидации override.
 */
export interface InstructionOverrideValidationResponse {
  override_id: string;
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  checks_count: number | null;
  effective_payload: Record<string, unknown> | null;
  validation_report: Record<string, unknown> | null;
}

// ─────────────────────────────────────────────────────────────
// Override Request types
// ─────────────────────────────────────────────────────────────

/**
 * POST .../instruction-overrides/draft
 */
export interface CreateOverrideDraftRequest {
  instruction_version_id: string;
  patch_ops: JsonPatchOperation[];
  change_summary?: string | null;
}

/**
 * POST .../instruction-overrides/:id/rebase (только deal)
 */
export interface RebaseOverrideRequest {
  new_base_version_id: string;
  new_patch_ops: JsonPatchOperation[];
  change_summary?: string | null;
}

// ─────────────────────────────────────────────────────────────
// Global Instruction Versions (lifecycle: draft → published → archived)
// GET /admin/instructions/global-checks → GlobalInstructionCatalogResponse
// ─────────────────────────────────────────────────────────────

export interface GlobalInstructionCatalogItem {
  instruction_code: string;
  name: string;
  group: string | null;
  total_versions_count: number;
  draft_versions_count: number;
  has_published: boolean;
  latest_version_id: string | null;
  latest_version_status: InstructionVersionStatus | null;
  latest_version_updated_at: string | null;
  latest_published_version_id: string | null;
  latest_published_at: string | null;
  latest_published_immutable_content_hash: string | null;
  latest_draft_version_id: string | null;
  latest_draft_is_valid: boolean | null;
  latest_draft_updated_at: string | null;
}

export interface GlobalInstructionCatalogResponse {
  items: GlobalInstructionCatalogItem[];
}

export interface GlobalInstructionVersionItem {
  id: string;
  instruction_code: string;
  name: string | null;
  group: string | null;
  source_format: SourceFormat | null;
  source_sha256: string | null;
  version_status: InstructionVersionStatus;
  immutable_content_hash: string | null;
  validation_report: Record<string, unknown> | null;
  parent_version_id: string | null;
  published_at: string | null;
  created_by: string | null;
  change_summary: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GlobalInstructionVersionDetailItem
  extends GlobalInstructionVersionItem {
  source_yaml: string | null;
  source_path: string | null;
  git_commit: string | null;
  semver: string | null;
  compiled_payload: Record<string, unknown> | null;
}

export interface GlobalInstructionVersionListResponse {
  instruction_code: string;
  items: GlobalInstructionVersionItem[];
}

export interface GlobalInstructionVersionDetailResponse {
  item: GlobalInstructionVersionDetailItem;
}

export interface GlobalInstructionVersionValidationResponse {
  item: GlobalInstructionVersionItem;
  is_valid: boolean;
  validation_report: Record<string, unknown> | null;
}

export interface CreateGlobalInstructionDraftRequest {
  source_yaml: string;
  name?: string | null;
  source_path?: string | null;
  git_commit?: string | null;
  semver?: string | null;
  change_summary?: string | null;
  parent_version_id?: string | null;
}

export interface UpdateGlobalInstructionDraftRequest {
  source_yaml: string;
  name?: string | null;
  source_path?: string | null;
  git_commit?: string | null;
  semver?: string | null;
  change_summary?: string | null;
}

export interface CloneGlobalDraftRequest {
  change_summary?: string | null;
}

export interface PreviewGlobalInstructionRequest {
  source_yaml: string;
}

export interface PreviewGlobalInstructionResponse {
  is_valid: boolean;
  instruction_code: string;
  group: string | null;
  diagnostics: PreviewDiagnostic[] | null;
  validation_report: Record<string, unknown> | null;
  compiled_payload: Record<string, unknown> | null;
  source_sha256: string | null;
  already_exists: boolean;
  existing_version_id: string | null;
}

export interface GlobalInstructionDiffResponse {
  from_version_id: string;
  to_version_id: string;
  from_source_sha256: string | null;
  to_source_sha256: string | null;
  are_identical: boolean;
  unified_diff: string[];
}


