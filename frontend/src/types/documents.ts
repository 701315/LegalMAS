// =============================================================
// src/types/documents.ts
// Типы домена документов, классификации и structured data.
// =============================================================

// -------------------------------------------------------------
// КЛАССИФИКАЦИЯ ДОКУМЕНТОВ
// -------------------------------------------------------------

/**
 * Уровни классификации HybridClassifier.
 * L0 — тип не определён, L4 — подтверждено LLM, L_manual — задан вручную.
 * Порог low_confidence = 0.6 (синхронизировано с бэкендом).
 */
export type ClassificationLevel =
  | "L0"
  | "L1"
  | "L2"
  | "L3"
  | "L4"
  | "L_manual";

/** Полные метаданные классификации одного документа */
export interface ClassificationMetadata {
  doc_type: string;
  classification_level: ClassificationLevel;
  classification_confidence: number;
  applicable_triggers: string[];
  yaml_instruction_available: boolean;
  low_confidence: boolean;
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
  trigger_coverage?: Record<string, number>;
}

// -------------------------------------------------------------
// ДОКУМЕНТЫ
// -------------------------------------------------------------

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

/** Детали ошибки обработки документа */
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
  id: string;
  deal_id: string;

  filename: string;
  folder_path?: string | null;

  status: DocumentStatus;
  doc_type?: string | null;

  language?: string | null;
  jurisdiction_guess?: string | null;

  page_count?: number | null;

  classification_level?: ClassificationLevel | null;
  classification_confidence?: number | null;
  applicable_triggers?: string[];

  classification_requires_review?: boolean;

  text_layout_raw_ref?: string | null;
  text_layout_sanitized_ref?: string | null;

  layout_primary_ref?: string | null;
  layout_primary_sanitized_ref?: string | null;

  reviewed_by_person: boolean;
  human_review_status?: string | null;
  risk_level?: string | null;

  processing_error_details?: ProcessingErrorDetails | null;

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

/** Детальная информация о документе */
export interface DocumentDetail {
  document: Document;
  latest_version?: DocumentVersion;
  family_id?: string;
  classification?: ClassificationMetadata;
}

/** DTO ответа GET /api/v1/documents/{doc_id}/family */
export interface DocumentFamilyDto {
  family_id: string;
  master_document: Document;
  related_documents: Document[];
  relations: Record<string, unknown>[];
}

/** View-модель семейства документов для правой панели */
export interface DocumentFamily {
  master: Document | null;
  appendices: Document[];
  amendments: Document[];
  versions: Document[];
}

/** Входные данные для ручной переклассификации документа */
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
  checks_requeued: boolean;
}

// -------------------------------------------------------------
// СТРУКТУРИРОВАННЫЕ ДАННЫЕ
// -------------------------------------------------------------

export interface ClauseNode {
  clause_uid: string;
  title: string;
  level: number;
  element_ids: string[];
  start_page: number;
  end_page: number;
  children: ClauseNode[];
}

export type StructuredClauseTree = ClauseNode[];

export interface ExtractedValue {
  check_id: string;
  check_name: string;

  field_name: string;
  field_value: string;

  // Формат и дополнительные атрибуты значения могут быть опциональными
  field_format?: string | null;

  page?: number | null;
  clause_uid?: string | null;

  // Новое: сегмент, к которому относится значение
  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  // Новое: привязка к чанку внутри сегмента/документа
  chunk_id?: string | null;
  chunk_index?: number | null;
}

export interface StructuredDataResult {
  document_id: string;
  filename: string;
  doc_type?: string | null;
  extracted_values: ExtractedValue[];
  total_extracted: number;
}

export type OpenViewerAtPayload = {
  documentId: string;
  page?: number | null;
  clauseUid?: string | null;
  elementId?: string | null;

  // v2: навигация по сегментам / чанкам
  segmentId?: string | null;
  chunkId?: string | null;
  chunkIndex?: number | null;
};

export type OpenViewerAtFn = (payload: OpenViewerAtPayload) => void;

// -------------------------------------------------------------
// DOCUMENT COLUMNS
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
  id: DocumentColumnId;
  label: string;
  description: string;
  field: keyof Document | "applicable_triggers_count";
  defaultVisible: boolean;
}

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
    description:
      "Уровень, на котором был определён тип документа (L0–L4, L_manual).",
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

