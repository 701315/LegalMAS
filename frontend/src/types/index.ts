// =============================================================
// src/types/index.ts
// Центральный файл TypeScript-типов для MAS-DD фронтенда.
// Все интерфейсы соответствуют Pydantic-схемам бэкенда (Этап 10).
// =============================================================

// -------------------------------------------------------------
// ВСПОМОГАТЕЛЬНЫЕ ТИПЫ
// -------------------------------------------------------------

/** Универсальный ответ с пагинацией для списков */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;

  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

/** Стандартная ошибка API */
export interface ApiError {
  detail: string;
  code?: string;
  status?: number; // HTTP-статус (404, 500 и т.п.)
}

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

// -------------------------------------------------------------
// РОЛИ И ПРАВА ДОСТУПА
// -------------------------------------------------------------

/**
 * Роли пользователей в системе.
 * Уровни: viewer=1, editor=2, reviewer=3, admin=4
 */
export type UserRole = "superadmin" | "admin" | "reviewer" | "editor" | "viewer";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  name?: string;
}

// -------------------------------------------------------------
// КЛАССИФИКАЦИЯ ДОКУМЕНТОВ (Этап 6 / Этап 10)
// -------------------------------------------------------------

/**
 * Уровни классификации HybridClassifier.
 * L0 — тип не определён, L4 — подтверждено LLM, L_manual — задан вручную.
 * Порог low_confidence = 0.6 (синхронизировано с бэкендом).
 */
export type ClassificationLevel =
  | "L0"       // нет совпадений
  | "L1"       // по имени файла
  | "L2"       // по ключевым словам
  | "L3"       // семантический поиск (эмбеддинги)
  | "L4"       // подтверждено LLM
  | "L_manual" // ручной override (POST /reclassify)

/** Полные метаданные классификации одного документа */
export interface ClassificationMetadata {
  doc_type: string;
  classification_level: ClassificationLevel;
  classification_confidence: number;       // 0.0 – 1.0
  applicable_triggers: string[];           // имена YAML-триггеров
  yaml_instruction_available: boolean;     // есть ли *.yaml для этого типа
  low_confidence: boolean;                 // true если confidence < 0.6
}

/** Сводная статистика классификации по всем документам run */
export interface ClassificationStats {
  total_documents: number;
  l0_no_match: number;
  l1_filename: number;
  l2_keyword: number;
  l3_semantic: number;
  l4_llm: number;
  low_confidence_count: number;
  unknown_doc_type_count: number;
}

/** Полный отчёт по классификации — GET /runs/{run_id}/classification-report */
export interface ClassificationReport {
  run_id: string;
  deal_id: string;
  total_documents: number;
  stats: ClassificationStats;
  low_confidence_docs: {
    doc_id: string;
    filename: string;
    doc_type?: string;
    confidence: number;
    classification_level: string;
  }[];
  unknown_type_docs: {
    doc_id: string;
    filename: string;
    detected_type?: string;
  }[];
  /** Покрытие триггеров: { имя_триггера: кол-во_документов }.
   *  Поле опциональное — может отсутствовать в ранних версиях бэка. */
  trigger_coverage?: Record<string, number>;
}

// -------------------------------------------------------------
// ДОКУМЕНТЫ
// -------------------------------------------------------------

/** Краткая информация о документе (для списков) */
export type DocumentStatus =
  | "pending"
  | "extracting"
  | "extracted"
  | "sanitized"
  | "structured"
  | "classified"
  | "analyzing"
  | "completed"
  | "quarantine"
  | "failed"
  | "duplicate"
  | "language_selection_required";

/** Детали ошибки обработки документа (JSONB из backend: Document.processing_error_details).
 *
 * Формат синхронизирован с backend DocumentRepository.set_failed/set_quarantined:
 *
 * {
 *   stage: "import" | "extract" | "pii" | "structure" | "classify" | "checks" | "export";
 *   type: "failed" | "quarantine";
 *   reason?: string;      // короткий машинный код причины (pdf_corrupted, no_clause_tree, ...)
 *   message: string;      // человекочитаемое описание для юриста
 *   timestamp: string;    // ISO8601 UTC, когда ошибка зафиксирована
 *   run_id?: string;      // ID Run, в рамках которого произошла ошибка
 *   ...extra: any;        // запас под расширения (debug-инфо и т.п.)
 * }
 */
export interface ProcessingErrorDetails {
  stage?: string;
  type?: "failed" | "quarantine";
  reason?: string;
  message?: string;
  timestamp?: string;
  run_id?: string;
  [key: string]: unknown;
}

export interface Document {
  // Идентификация
  id: string;
  deal_id: string;

  // Технически в БД есть bundle_id, но в текущем API списка документов
  // он, судя по коду, не используется. Если backend его вернёт — добавишь:
  // bundle_id?: string;

  // Базовое описание
  filename: string;
  folder_path?: string | null;

  // Статусы и тип
  status: DocumentStatus;          // backend: DocumentStatus enum
  doc_type?: string | null;

  // Язык и юрисдикция
  language?: string | null;
  jurisdiction_guess?: string | null;

  // Размер/страницы
  page_count?: number | null;

  // Классификация
  classification_level?: ClassificationLevel | null;
  classification_confidence?: number | null;
  applicable_triggers?: string[];  // всегда массив (может быть пустой)

  /** 
   * Флаг, что гибридный классификатор пометил документ
   * как требующий ручной проверки (низкая уверенность / зона unknown).
   */
  classification_requires_review?: boolean;


  // Layout-артефакты (сырые и санитизированные макеты текста).
  //
  // Для непрофессионального программиста:
  // - text_layout_raw_ref — это ссылка (строка) на "сырой" текстовый макет
  //   документа после этапа extract (multi-lang JSON в хранилище).
  // - text_layout_sanitized_ref — это ссылка на санитизированный макет,
  //   в котором уже вычищены PII-данные (ФИО, телефоны и т.п.).
  // - Оба поля опциональные: backend может не заполнять их для старых документов
  //   или на ранних стадиях пайплайна.
  text_layout_raw_ref?: string | null;
  text_layout_sanitized_ref?: string | null;

  // NEW — новая архитектура layout'ов
  layout_primary_ref?: string | null;
  layout_primary_sanitized_ref?: string | null;

  // Проверка юристом и риск
  reviewed_by_person: boolean;
  human_review_status?: string | null;  // производное поле из backend
  risk_level?: string | null;           // "low" | "medium" | "high" | "critical" (по договорённости)

  // Детали ошибки обработки (могут отсутствовать или быть null)
  processing_error_details?: ProcessingErrorDetails | null;

  // Время
  created_at: string;
  updated_at: string;
}

/** Версия документа (для истории изменений) */
export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  created_at: string;
}

/**
 * Детальная информация о документе.
 * Используется с GET /deals/{deal_id}/runs/{run_id}/documents/{doc_id}
 */
export interface DocumentDetail {
  document: Document;
  latest_version?: DocumentVersion;
  family_id?: string;
  /** Полный блок классификации — включает triggers, yaml, low_confidence */
  classification?: ClassificationMetadata;
}

/** Семейство документов для правой панели DocumentsTab. */
export interface DocumentFamily {
  master: Document | null;
  appendices: Document[];
  amendments: Document[];
  versions: Document[];
}

/** Входные данные для ручной переклассификации документа (Editor+) */
export interface ReclassifyInput {
  doc_type: string;
  reason: string;
}

/** Ответ после переклассификации */
export interface ReclassifyResult {
  document_id: string;
  previous_doc_type?: string;
  new_doc_type: string;
  new_applicable_triggers: string[];
  yaml_instruction_found: boolean;
  /** Всегда false в новой версии backend-а; поле оставлено для обратной совместимости. */
  checks_requeued: boolean;
}

// -------------------------------------------------------------
// СТРУКТУРИРОВАННЫЕ ДАННЫЕ (Этап 10)
// -------------------------------------------------------------

// Структурированное дерево (clause tree), как раньше
export interface ClauseNode {
  clause_uid: string;
  title: string;
  level: number;
  element_ids: string[];
  start_page: number;
  end_page: number;
  children: ClauseNode[];
}

// Всё дерево по документу
export type StructuredClauseTree = ClauseNode[];

// Извлечённые значения (то, что даёт агрегатор/новый эндпоинт)
export interface ExtractedValue {
  check_id: string;
  check_name: string;
  field_name: string;
  field_value: string;
  field_format: string; // "money" | "date" | "entity_name" | "text"
  page?: number | null;
  clause_uid?: string | null;
}

// Ответ GET /documents/{doc_id}/structured-data (теперь объект, а не массив)
export interface StructuredDataResult {
  document_id: string;
  filename: string;
  doc_type?: string | null;
  extracted_values: ExtractedValue[];
  total_extracted: number;
}

// Единый payload для viewer'a
export type OpenViewerAtPayload = {
  documentId: string;
  page?: number | null;
  clauseUid?: string | null;
  elementId?: string | null;
};

// Единая сигнатура коллбэка
export type OpenViewerAtFn = (payload: OpenViewerAtPayload) => void;


// -------------------------------------------------------------
// RUNS (ЗАПУСКИ АНАЛИЗА)
// -------------------------------------------------------------


// Статусы синхронизированы с backend Run.status:
// - pending  — Run создан, но пайплайн не запускался;
// - running  — оркестратор поставил задачи, анализ идёт;
// - completed — все документы успешно прошли checks;
// - completed_with_errors — анализ завершён, но есть документы FAILED/QUARANTINE;
// - failed   — критическая ошибка Run (конфигурация/инфраструктура).
// cancelled — зарезервирован для сценариев отмены Run из UI.
// В текущей реализации backend может хранить его как failed/pending,
// но фронт уже умеет отображать отдельный статус "Отменён".
export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "cancelled";


/**
 * Входные данные для старта нового анализа.
 *
 * Playbook и model_config берутся из настроек сделки (Deal.playbook_version_id),
 * поэтому их не нужно передавать в запросе.
 *
 * profile:
 *  - "core"  — минимальный набор проверок;
 *  - "full"  — полный набор;
 *  - "max"   — максимум, что умеет система (может быть медленнее/дороже).
 *
 * checks_mode:
 *  - "global_only"         — запускать только проверки из глобального плейбука;
 *  - "doc_type_only"       — запускать только проверки из инструкций по типам;
 *  - "global_and_doc_type" — запускать оба слоя (текущая логика по умолчанию).
 *
 * force_reclassify:
 *  - false (по умолчанию) — переиспользовать уже готовую классификацию,
 *    запускать только checks;
 *  - true — перед запуском checks ещё раз прогнать классификацию по всем
 *    документам (hybrid/LLM), чтобы учесть новые модели/правила.
 */
export interface RunCreateInput {
  /** Профиль запуска: core / full / max */
  profile?: string;
  /** Режим проверок: global_only / doc_type_only / global_and_doc_type */
  checks_mode?: "global_only" | "doc_type_only" | "global_and_doc_type";
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
  profile: string;

  /**
   * Режим проверок, в котором выполнялся Run:
   *  - "global_only"
   *  - "doc_type_only"
   *  - "global_and_doc_type"
   */
  checks_mode: "global_only" | "doc_type_only" | "global_and_doc_type";

  /**
   * Стратегия пайплайна:
   *  - REUSE_STRUCTURE — переиспользовать уже рассчитанное дерево/структуру;
   *  - FULL_RERUN      — пересчитать всё с нуля;
   *  - другие значения по договорённости с backend.
   *
   * Тип string оставлен более широким, чтобы не ломать фронт при
   * добавлении новых стратегий.
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
   * Формат согласован с backend Run.error_details:
   * {
   *   type: "infrastructure_error" | "config_error" | "...",
   *   stage: "orchestrator" | "checks" | "...",
   *   reason: "<краткий код причины>",
   *   message: "<человекочитаемое описание>",
   *   timestamp: "<ISO8601 UTC>"
   * }
   */
  error_details?: Record<string, unknown>;

  /** Опциональная статистика — заполняется при include_classification_stats=true */
  classification_stats?: ClassificationStats;
}


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
// Важно: это именно то, что возвращает API, и оно может меняться
// по мере эволюции модели данных на сервере.
export type CheckResultOrigin =
  | "GLOBAL_PLAYBOOK"
  | "global_playbook"
  | "project_playbook"
  | "DOCUMENT_TYPE"
  | string; // запасной вариант на будущее

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
  origin?: CheckResultOrigin; // "global_playbook" | "doctype_playbook" | ...
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
  snippet?: string;
  // Полная цитата или более длинный фрагмент
  quote?: string;
  // Страница документа, если backend её отдаёт
  page?: number;
  // Дополнительные произвольные поля (для расширений backend-а)
  [key: string]: unknown;
}







// -------------------------------------------------------------
// DD ЗАПРОСЫ (DUE DILIGENCE REQUESTS)
// -------------------------------------------------------------

/** Один DD-запрос — требование предоставить документ/информацию */
export interface DDRequest {
  id: string;
  deal_id: string;
  priority: "critical" | "high" | "medium";
  text: string;
  status: "open" | "in_progress" | "resolved";
  // Расширенные поля (Этап 10)
  check_id?: string;
  /** Адресат запроса (из YAML dd_request_templates) */
  addressee?: string;
  structured_values?: Record<string, unknown>[];
  /** Источник запроса */
  source?: "yaml_template" | "manual" | "aggregator";
  document_refs: string[];
  evidence_refs: string[];
  created_at: string;
  updated_at?: string;
}

export interface DDRequestCreateInput {
  check_id: string;
  check_name: string;
  text: string;
  priority: "critical" | "high" | "medium";
  addressee?: string;
  source?: "manual";
}

// ===== ЭКСПОРТЫ (REPORT / GRID / SUMMARY) =====

export interface ExportRecord {
  id: string;
  deal_id: string;
  run_id: string;
  export_type: string;         // "grid_xlsx" | "deal_summary_xlsx" | "report_docx" | "report_pdf" и т.п.
  file_ref: string;
  file_size_bytes: number;
  status: "pending" | "processing" | "completed" | "failed";
  requested_by: string;
  requester_role: string;
  created_at: string;
  download_url?: string;
}

export interface AuditLogEntry {
  id: string;
  tenant_id: string;
  deal_id: string | null;
  action: string;
  actor: string;
  actor_role: string;
  details: Record<string, unknown>;
  created_at: string;
}

// -------------------------------------------------------------
// СДЕЛКИ (DEALS)
// -------------------------------------------------------------

export type DealStatus = "active" | "archived" | "draft";

/** Краткая информация о сделке (для списка) */
export interface Deal {
  id: string;
  name: string;
  status: DealStatus;
  deal_type?: string;
  bundle_id?: string;

  /** Юрисдикция сделки (например, RU, EN, RU/EN). */
  jurisdiction?: string | null;

  /** Список языков документов по сделке (как в DealResponse.languages). */
  languages?: string[] | null;

  /** Основной язык сделки, выбираемый юристом. */
  primary_language?: string | null;

  /** ID последнего запуска анализа по сделке (если был) */
  last_run_id?: string;

  /**
   * Режим проверок последнего запуска анализа:
   *  - "global_only"         — только глобальный плейбук;
   *  - "doc_type_only"       — только проверки по типам документов;
   *  - "global_and_doc_type" — оба слоя.
   *
   * Поле агрегированное, заполняется на бэкенде на основе последнего Run.
   * Может быть null/undefined, если анализ ещё не запускался
   * или бэкенд пока не отдаёт эту информацию.
   */
  last_run_checks_mode?:
    | "global_only"
    | "doc_type_only"
    | "global_and_doc_type"
    | null;

  /**
   * Стратегия пайплайна для последнего запуска:
   *  - "REUSE_STRUCTURE" / "FULL_RERUN" / другие значения по договорённости.
   *
   * Тип string оставлен более широким, чтобы новые стратегии
   * не требовали немедленных правок на фронте.
   */
  last_run_pipeline_strategy?: string | null;

  /** ID выбранной версии плейбука для сделки */
  playbook_version_id?: string;

  created_at: string;
  updated_at: string;

  /** Имя/код конфигурации модели, используемой для анализа сделки */
  model_config_name?: string | null;

  /** Есть ли незавершённые ручные переклассификации, требующие перезапуска анализа */
  has_pending_manual_reclassifications: boolean;

  metadata_?: {
    contact_person?: string | null;
    [key: string]: unknown;
  } | null;
}

/** Детальная информация о сделке */
export interface DealDetail extends Deal {
  description?: string;
  counterparty?: string;
  runs?: Run[];
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
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

// -------------------------------------------------------------
// SSE (ПРОГРЕСС АНАЛИЗА В РЕАЛЬНОМ ВРЕМЕНИ)
// -------------------------------------------------------------

/** Событие прогресса, получаемое через SSE во время анализа */
export interface ProgressEvent {
  run_id: string;
  status: RunStatus;
  completed_checks: number;
  total_checks: number;
  current_document?: string;
  error?: string;
}

// -------------------------------------------------------------
// ДОКУМЕНТЫ: ОПИСАНИЯ КОЛОНОК ДЛЯ ТАБЛИЦ/ЭКСПОРТА
// -------------------------------------------------------------

export type DocumentColumnId =
  | "filename"
  | "folder_path"
  | "doc_type"
  | "status"
  | "human_review_status"
  | "reviewed_by_person"
  | "risk_level"
  | "language"
  | "jurisdiction_guess"
  | "page_count"
  | "classification_level"
  | "classification_confidence"
  | "applicable_triggers_count"
  | "created_at"
  | "updated_at"
  | "id"
  | "deal_id"
  | "classification_requires_review";  

export interface DocumentColumnDef {
  /** Уникальный ID колонки (используем в настройках/экспорте) */
  id: DocumentColumnId;
  /** Человеко-понятный заголовок для UI */
  label: string;
  /** Краткое объяснение, что это за колонка (подсказки, настройки) */
  description: string;
  /** Имя поля в объекте Document или спец. псевдоним (например, count) */
  field:
    | keyof Document
    | "applicable_triggers_count";
  /** По умолчанию показывать в таблице или нет */
  defaultVisible: boolean;
}

/**
 * Полный список всех возможных колонок по документу.
 * Используем:
 * - в табличном режиме DocumentsTab;
 * - в UI выбора колонок;
 * - как основу для экспорта (Excel/Word/PDF).
 */
export const ALL_DOCUMENT_COLUMNS: DocumentColumnDef[] = [
  {
    id: "filename",
    label: "Название документа",
    description: "Имя файла документа в Data Room.",
    field: "filename",
    defaultVisible: true,
  },
  {
    id: "folder_path",
    label: "Папка",
    description: "Путь к документу в структуре Data Room.",
    field: "folder_path",
    defaultVisible: true,
  },
  {
    id: "doc_type",
    label: "Тип документа",
    description: "Классифицированный тип документа (SPA, NDA и т.п.).",
    field: "doc_type",
    defaultVisible: true,
  },
  {
    id: "status",
    label: "Статус обработки",
    description: "Текущий статус обработки документа в пайплайне.",
    field: "status",
    defaultVisible: true,
  },
  {
    id: "human_review_status",
    label: "Проверка юриста",
    description: "Человекочитаемый статус проверки юристом.",
    field: "human_review_status",
    defaultVisible: true,
  },
  {
    id: "reviewed_by_person",
    label: "Флаг проверки",
    description: "Логический флаг: документ проверен юристом.",
    field: "reviewed_by_person",
    defaultVisible: false,
  },
  {
    id: "classification_requires_review",
    label: "Нужна проверка",
    description:
      "Флаг, что классификатор пометил документ как требующий ручной проверки (низкая уверенность).",
    field: "classification_requires_review",
    defaultVisible: false,
  },
  {
    id: "risk_level",
    label: "Риск",
    description: "Уровень риска документа: low/medium/high/critical.",
    field: "risk_level",
    defaultVisible: true,
  },
  {
    id: "language",
    label: "Язык",
    description: "Основной язык документа (RU, EN и т.п.).",
    field: "language",
    defaultVisible: false,
  },
  {
    id: "jurisdiction_guess",
    label: "Юрисдикция",
    description: "Предполагаемая юрисдикция документа.",
    field: "jurisdiction_guess",
    defaultVisible: false,
  },
  {
    id: "page_count",
    label: "Страницы",
    description: "Количество страниц в документе.",
    field: "page_count",
    defaultVisible: false,
  },
  {
    id: "classification_level",
    label: "Уровень классификации",
    description: "Уровень, на котором был определён тип документа (L0–L4, L_manual).",
    field: "classification_level",
    defaultVisible: false,
  },
  {
    id: "classification_confidence",
    label: "Уверенность классификации",
    description: "Число 0–1, показывающее уверенность в типе документа.",
    field: "classification_confidence",
    defaultVisible: false,
  },
  {
    id: "applicable_triggers_count",
    label: "Триггеры",
    description: "Количество сработавших триггеров проверок для документа.",
    field: "applicable_triggers_count",
    defaultVisible: false,
  },
  {
    id: "created_at",
    label: "Создан",
    description: "Дата и время добавления документа в сделку.",
    field: "created_at",
    defaultVisible: false,
  },
  {
    id: "updated_at",
    label: "Обновлён",
    description: "Дата и время последнего обновления документа.",
    field: "updated_at",
    defaultVisible: true,
  },
  {
    id: "id",
    label: "ID документа",
    description: "Технический идентификатор документа (UUID).",
    field: "id",
    defaultVisible: false,
  },
  {
    id: "deal_id",
    label: "ID сделки",
    description: "Идентификатор сделки, к которой относится документ.",
    field: "deal_id",
    defaultVisible: false,
  },
];

// -------------------------------------------------------------
// PLAYBOOKS (PLAYBOOK / PLAYBOOK VERSION)
// -------------------------------------------------------------

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
  /** ID ModelConfig (опционально, может быть null / не задан). */
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

// Линия (шаблон) для списков / выбора
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

// Элемент линии (то, что мы редактируем в конструкторе)
export interface PlaybookLineItemPayload {
  kind: "topic" | "check";
  topic_code?: string | null;
  check_code?: string | null;
  order_index: number;
}

// Детали линии = данные линии + список элементов
export interface PlaybookLineDetail extends PlaybookLineShort {
  items: PlaybookLineItemPayload[];
}


