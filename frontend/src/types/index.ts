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
}


// -------------------------------------------------------------
// РОЛИ И ПРАВА ДОСТУПА
// -------------------------------------------------------------

/**
 * Роли пользователей в системе.
 * Уровни: viewer=1, editor=2, reviewer=3, admin=4
 */
export type UserRole = "viewer" | "editor" | "reviewer" | "admin";

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
  | "quarantine";

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

  // Проверка юристом и риск
  reviewed_by_person: boolean;
  human_review_status?: string | null;  // производное поле из backend
  risk_level?: string | null;           // "low" | "medium" | "high" | "critical" (по договорённости)

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
  rerun_checks?: boolean;
}

/** Ответ после переклассификации */
export interface ReclassifyResult {
  document_id: string;
  previous_doc_type?: string;
  new_doc_type: string;
  new_applicable_triggers: string[];
  yaml_instruction_found: boolean;
  checks_requeued: boolean;
}


// -------------------------------------------------------------
// СТРУКТУРИРОВАННЫЕ ДАННЫЕ (Этап 10)
// -------------------------------------------------------------

/**
 * Одно извлечённое поле из документа.
 * Поля соответствуют ответу GET /documents/{doc_id}/structured-data
 */
export interface StructuredValue {
  check_id: string;
  check_name: string;
  field_name: string;
  field_value: string;
  page?: number;
  clause_uid?: string;
}

/** Все структурированные данные по одному документу */
export interface StructuredDataResult {
  document_id: string;
  filename: string;
  doc_type?: string;
  extracted_values: StructuredValue[];
  total_extracted: number;
}


// -------------------------------------------------------------
// RUNS (ЗАПУСКИ АНАЛИЗА)
// -------------------------------------------------------------

export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

/**
 * Входные данные для старта нового анализа.
 *
 * Playbook и model_config берутся из настроек сделки (Deal.playbook_version_id),
 * поэтому их не нужно передавать в запросе.
 */
export interface RunCreateInput {
  profile?: string;
  /** Если true — HybridClassifier перезапустится для всех документов */
  force_reclassify?: boolean;
}

/** Информация о запуске анализа */
export interface Run {
  id: string;
  deal_id: string;
  status: RunStatus;
  profile: string;
  total_checks: number;
  completed_checks: number;
  started_at?: string;
  completed_at?: string;
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
  // Структурированные данные (Этап 10)
  structured_data?: Record<string, unknown>;
  // Условные проверки (Этап 10)
  conditional_check_triggered?: boolean;
  trigger_name?: string;
  // Денормализованная классификация документа (новое)
  doc_classification_level?: ClassificationLevel;
  doc_classification_confidence?: number;
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
  /** ID последнего запуска — используется для overview и classification report */
  last_run_id?: string;
  /** ID привязанной версии playbook (настройки сделки) */
  playbook_version_id?: string;
  created_at: string;
  updated_at: string;

  /** Произвольные метаданные сделки (в т.ч. контактное лицо и т.п.) */
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
  | "deal_id";

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



