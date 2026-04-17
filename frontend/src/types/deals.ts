// =============================================================
// src/types/deals.ts
// Типы для сделок и импорта документов.
// =============================================================

import type { Run } from "./runs";

export type DealStatus = "active" | "archived" | "draft";

export type DealChecksMode =
  | "global_only"
  | "doc_type_only"
  | "global_and_doc_type";

/** Payload для PATCH /deals/{deal_id}/primary-language */
export interface DealPrimaryLanguageUpdatePayload {
  primary_language: string | null;
}

/** Краткая информация о сделке (для списка) */
export interface Deal {
  id: string;
  name: string;
  status: DealStatus;
  deal_type?: string | null;
  bundle_id?: string | null;

  /** Юрисдикция сделки (например, RU, EN, RU/EN). */
  jurisdiction?: string | null;

  /** Список языков документов по сделке (как в DealResponse.languages). */
  languages?: string[] | null;

  /** Основной язык сделки, выбираемый юристом. */
  primary_language?: string | null;

  /** ID последнего запуска анализа по сделке (если был) */
  last_run_id?: string | null;

  /**
   * Режим проверок последнего запуска анализа.
   */
  last_run_checks_mode?: DealChecksMode | null;

  /**
   * Стратегия пайплайна для последнего запуска.
   */
  last_run_pipeline_strategy?: string | null;

  /** ID выбранной версии плейбука для сделки */
  playbook_version_id?: string | null;

  created_at: string;
  updated_at: string;

  /** Имя/код конфигурации модели, используемой для анализа сделки */
  model_config_name?: string | null;

  /** Есть ли незавершённые ручные переклассификации */
  has_pending_manual_reclassifications: boolean;

  metadata_?: {
    contact_person?: string | null;
    [key: string]: unknown;
  } | null;
}

/** Детальная информация о сделке */
export interface DealDetail extends Deal {
  description?: string | null;
  counterparty?: string | null;
  runs?: Run[] | null;
}

// -------------------------------------------------------------
// ИМПОРТ ДОКУМЕНТОВ
// -------------------------------------------------------------

export type ImportStatus =
  | "uploading"
  | "processing"
  | "completed"
  | "failed";

export interface ImportJob {
  id: string;
  deal_id: string;
  status: ImportStatus;
  total_files: number;
  processed_files: number;
  failed_files: number;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
}

