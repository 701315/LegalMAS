// =============================================================
// src/types/playbooks.ts
// Типы для playbooks и model configs.
// =============================================================

/** Логический плейбук (Playbook) — шаблон/продукт на странице выбора. */
export interface PlaybookLine {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  deal_type?: string | null;
  jurisdiction?: string | null;
  language?: string | null;
  risk_profile?: string | null;
}

/** Краткая информация о версии плейбука (для списков/селектора). */
export interface PlaybookVersionShort {
  id: string;
  name: string;
  semver: string;
  status: string;
  playbook_id?: string | null;
}

/** Детальная информация о версии плейбука (для просмотра состава). */
export interface PlaybookVersionDetail {
  id: string;
  name: string;
  semver: string;
  status: string;
  playbook_id?: string | null;
  model_config_id?: string | null;

  compiled_checks?: Record<string, unknown> | null;
  trigger_definitions?: Record<string, unknown> | null;
  dd_request_templates?: Record<string, unknown> | null;
  section_markers?: Record<string, unknown> | null;
  classification_config?: Record<string, unknown> | null;
}

/** Ответ после создания версии плейбука (POST /playbooks). */
export interface PlaybookCreateResponse {
  id: string;
  name: string;
  semver: string;
  status: string;
  playbook_id?: string | null;
}

export interface PlaybookCheckInfo {
  code: string;
  title: string;
  description?: string | null;
  topic_code: string;
  file_path: string;
}

export interface PlaybookTopicInfo {
  topic_code: string;
  topic_name: string;
  checks: PlaybookCheckInfo[];
}

/** Входные данные для создания версии плейбука. */
export interface PlaybookCreateRequest {
  name?: string | null;
  bundles: string[];
  include_ids: string[];
  exclude_ids: string[];
  profile?: string | null;
  model_config_id?: string;
  semver?: string | null;
  status?: string | null;
  playbook_id?: string | null;
  from_line_id?: string | null;
}

export interface ModelConfig {
  id: string;
  name: string;
  description?: string | null;
}

export interface ModelConfigCreateInput {
  name: string;
  embeddings_primary: string;
  embeddings_fallback?: string | null;
  candidate_n: number;
  llm_context_k: number;
  dense_weight: number;
  sparse_weight: number;
  metadata_boost: number;
}

export interface ModelConfigUpdateInput {
  name?: string;
  embeddings_primary?: string;
  embeddings_fallback?: string | null;
  candidate_n?: number;
  llm_context_k?: number;
  dense_weight?: number;
  sparse_weight?: number;
  metadata_boost?: number;
}

/** Одна запись истории смены playbook-версии сделки (из AuditLog). */
export interface DealPlaybookHistoryItem {
  created_at: string;
  actor: string;
  actor_role?: string | null;
  old_playbook_version_id?: string | null;
  new_playbook_version_id?: string | null;
  playbook_id?: string | null;
  playbook_name?: string | null;
  semver?: string | null;
}

export interface PlaybookLineShort {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  deal_type?: string | null;
  jurisdiction?: string | null;
  language?: string | null;
  risk_profile?: string | null;
}

export interface PlaybookLineItemPayload {
  kind: "topic" | "check";
  topic_code?: string | null;
  check_code?: string | null;
  order_index: number;
}

export interface PlaybookLineDetail extends PlaybookLineShort {
  items: PlaybookLineItemPayload[];
}

