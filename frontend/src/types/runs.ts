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

  /** Актуальный контракт */
  completed_checks?: number;
  total_checks?: number;

  /** Временная совместимость со старым/фактическим payload */
  completed?: number;
  total?: number;

  current_document?: string;
  error?: string;
}

// =============================================================
// Pipeline progress types
// Используются для детального отображения стадий пайплайна
// на странице обзора сделки.
// =============================================================

/**
 * Статус одного product-этапа pipeline.
 * pending           — ещё не начат
 * running           — идёт прямо сейчас
 * completed         — успешно завершён
 * completed_with_errors — завершён, но с ошибками в части документов
 * failed            — завершён с ошибкой
 */
export type PipelineStepStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed";

/**
 * Статус технического substep внутри product-этапа.
 * planned   — запланирован, ещё не начат
 * running   — выполняется
 * completed — успешно завершён
 * failed    — завершился с ошибкой
 * cancelled — отменён
 */
export type PipelineSubstepStatus =
  | "planned"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

/**
 * Тип живого прогресса внутри долгого этапа.
 * legal_units — обогащение semantic-блоков
 * segments    — классификация сегментов
 * checks      — DD-проверки
 * documents   — общий прогресс по документам
 */
export type PipelineSubProgressKind =
  | "legal_units"
  | "segments"
  | "checks"
  | "documents";

/**
 * Живой прогресс внутри долгого этапа (из progress_details в БД).
 */
export interface PipelineSubProgress {
  kind: PipelineSubProgressKind;
  current: number;
  total: number;
  total_units_in_document?: number;
  current_document_id?: string;
  current_document_name?: string;
  current_segment_id?: string;
  current_segment_title?: string;
  current_unit_label?: string;
  updated_at?: string;
}

/**
 * Один технический substep внутри product-этапа.
 * Например: workers.extract_document внутри "Подготовка документа".
 */
export interface PipelineSubstep {
  code: string;
  title: string;
  status: PipelineSubstepStatus;
  started_at?: string;
  finished_at?: string;
  duration_seconds?: number;
  error_message?: string;
}

/**
 * Один product-этап pipeline, который видит пользователь.
 * Например: "Подготовка документа", "Семантическое обогащение".
 */
export interface PipelineStep {
  code: string;
  title: string;
  status: PipelineStepStatus;
  documents_total: number;
  documents_completed: number;
  documents_running: number;
  documents_failed: number;
  started_at?: string;
  finished_at?: string;
  duration_seconds?: number;
  message?: string;
  error_message?: string;
  substeps: PipelineSubstep[];
  sub_progress?: PipelineSubProgress | null;
}

/**
 * Подробный user-facing прогресс pipeline по run.
 * Возвращается эндпоинтом GET /api/v1/runs/{run_id}/progress.
 *
 * Показывает не только checks, но и document pipeline до них:
 * подготовка → структура → классификация → обогащение → проверки → финализация.
 */
export interface RunPipelineProgress {
  run_id: string;
  deal_id: string;
  run_status: RunStatus;
  started_at?: string;
  completed_at?: string;
  elapsed_seconds?: number;
  last_activity_at?: string;
  is_stale: boolean;
  stale_threshold_minutes: number;
  documents_total: number;
  documents_failed: number;
  documents_quarantine: number;
  current_step_code?: string;
  current_step_title?: string;
  active_step_codes: string[];
  steps: PipelineStep[];
}


