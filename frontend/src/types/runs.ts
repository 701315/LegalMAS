// =============================================================
// src/types/runs.ts
// Типы для Run, статусов запуска анализа и SSE-прогресса.
// =============================================================

import type { ClassificationStats } from "./documents";

/**
 * Статусы синхронизированы с backend Run.status:
 * - pending  — Run создан, но пайплайн не запускался;
 * - running  — оркестратор поставил задачи, анализ идёт;
 * - completed — все документы успешно прошли checks;
 * - completed_with_errors — анализ завершён, но есть документы FAILED/QUARANTINE;
 * - failed   — критическая ошибка Run (конфигурация/инфраструктура);
 * - cancelled — зарезервирован для сценариев отмены Run из UI, если backend начнёт его возвращать.
 */
export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "cancelled";

export type RunProfile = "core" | "full" | "max";

export type RunChecksMode =
  | "global_only"
  | "doc_type_only"
  | "global_and_doc_type";

/**
 * Входные данные для старта нового анализа.
 *
 * Playbook и model_config берутся из настроек сделки (Deal.playbook_version_id),
 * поэтому их не нужно передавать в запросе.
 */
export interface RunCreateInput {
  /** Профиль запуска: core / full / max */
  profile?: RunProfile;

  /** Режим проверок: global_only / doc_type_only / global_and_doc_type */
  checks_mode?: RunChecksMode;

  /** Если true — HybridClassifier перезапустится для всех документов */
  force_reclassify?: boolean;
}

/**
 * Информация о запуске анализа.
 *
 * Используется для:
 *  - статус-бэджей в Overview;
 *  - прогрессбара по checks;
 *  - сводки по последнему Run в карточке сделки;
 *  - DD Grid (фильтрация по режиму и стратегии).
 */
export interface Run {
  id: string;
  deal_id: string;
  status: RunStatus;

  /** Профиль запуска: core / full / max */
  profile: RunProfile;

  /**
   * Режим проверок, в котором выполнялся Run:
   *  - "global_only"
   *  - "doc_type_only"
   *  - "global_and_doc_type"
   */
  checks_mode: RunChecksMode;

  /**
   * Стратегия пайплайна:
   *  - REUSE_STRUCTURE — переиспользовать уже рассчитанное дерево/структуру;
   *  - FULL_RERUN      — пересчитать всё с нуля;
   *  - другие значения по договорённости с backend.
   */
  pipeline_strategy: string;

  /** Сколько документов должны пройти checks */
  total_checks: number;

  /** Сколько документов уже прошли checks */
  completed_checks: number;

  /** Есть ли FAILED/QUARANTINE документы */
  has_errors?: boolean;

  /** Сколько документов в статусе FAILED */
  failed_docs_count?: number;

  /** Сколько документов в статусе QUARANTINE */
  quarantine_docs_count?: number;

  /** Время начала/окончания Run (ISO8601-строки) */
  started_at?: string;
  completed_at?: string;

  /**
   * Ошибка уровня Run (не отдельного документа).
   * Формат согласован с backend Run.error_details.
   */
  error_details?: Record<string, unknown>;

  /** Опциональная статистика — при include_classification_stats=true */
  classification_stats?: ClassificationStats;
}

/** Событие прогресса, получаемое через SSE во время анализа */
export interface ProgressEvent {
  run_id: string;
  status: RunStatus;
  completed_checks: number;
  total_checks: number;
  current_document?: string;
  error?: string;
}



