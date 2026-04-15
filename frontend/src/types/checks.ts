// =============================================================
// src/types/checks.ts
// Типы для результатов проверок (checks), structured fields и evidence.
// =============================================================

import type { JsonValue } from "./common";
import type { ClassificationLevel } from "./documents";

// -------------------------------------------------------------
// РЕЗУЛЬТАТЫ ПРОВЕРОК (CHECK RESULTS)
// -------------------------------------------------------------

export type CheckResultValue = "fail" | "pass" | "unclear";

export type SeverityLevel =
  | "critical"
  | "high"
  | "medium"
  | "pass"
  | "unclear";

export type QCStatus = "pending" | "approved" | "rejected" | "needs_review";

// Сырые значения origin, которые приходят от бэкенда.
export type CheckResultOrigin =
  | "GLOBAL_PLAYBOOK"
  | "global_playbook"
  | "project_playbook"
  | "DOCUMENT_TYPE"
  | string;

export type CheckResultOriginType = "global" | "doctype" | "custom";

/** Результат одной проверки документа */
export interface CheckResult {
  id: string;
  run_id: string;
  document_id: string;
  document_name?: string;
  doc_type?: string;
  check_id: string;
  check_name: string;
  result: CheckResultValue;
  severity: SeverityLevel;
  value_text?: string;
  confidence?: number;
  detector_used?: string;
  quality_flags?: Record<string, boolean>;
  qc_status: QCStatus;
  qc_by?: string;
  qc_comment?: string;
  qc_at?: string;
  created_at: string;
  structured_data?: Record<string, StructuredField>;
  conditional_check_triggered?: boolean;
  trigger_name?: string;
  doc_classification_level?: ClassificationLevel;
  doc_classification_confidence?: number;
  origin?: CheckResultOrigin;
  origin_type?: CheckResultOriginType;
  doc_requires_manual_review?: boolean | null;
}

export interface StructuredField {
  value: JsonValue;
  unit?: string | null;
  source?: string | null;
  confidence?: number | null;
  found?: boolean;
  location?: {
    page?: number | null;
    clause_uid?: string | null;
    element_id?: string | null;
    start_page?: number | null;
    end_page?: number | null;
    path_titles?: string[] | null;

    // v2-расширение (если backend их отдаёт)
    segment_id?: string | null;
    chunk_id?: string | null;
    chunk_index?: number | null;
  } | null;
  // "pending" | "accepted" | "rejected" | "auto_accepted"
  qc?: {
    status?: string | null;
    by?: string | null;
    comment?: string | null;
    at?: string | null;
  } | null;
}

// -------------------------------------------------------------
// EVIDENCE (ДОКАЗАТЕЛЬСТВА ДЛЯ РЕЗУЛЬТАТОВ ПРОВЕРОК)
// -------------------------------------------------------------

/**
 * Базовый тип доказательства (evidence) для одного результата проверки.
 * Поля синхронизированы по смыслу с Pydantic-схемой backend-а.
 */
export interface Evidence {
  id: string;
  result_id: string;
  document_id: string;

  // Краткий фрагмент текста (для списка / быстрого просмотра)
  snippet?: string | null;

  // Полная цитата или более длинный фрагмент
  quote?: string | null;

  // Страница документа, если backend её отдаёт
  page?: number | null;

  // Привязка к clause tree / STRUCTURE
  clause_uid?: string | null;

  // Технические детали evidence / structured payload от backend
  structured_data?: Record<string, unknown> | null;

  // Дополнительные произвольные поля (для расширений backend-а)
  [key: string]: unknown;
}

