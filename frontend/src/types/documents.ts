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

// -------------------------------------------------------------
// COMPOSITION / SEGMENTATION VIEW
// -------------------------------------------------------------

/**
 * Тип композиции файла:
 * - "single" — файл содержит один логический документ;
 * - "multi" — файл содержит несколько логических документов / сегментов.
 */
export type DocumentCompositionType = "single" | "multi";

/**
 * View-модель композиции документа. Это не raw-поля из БД,
 * а агрегированная информация, рассчитанная по сегментам /
 * structured data / layouts (frontend- или backend-уровень).
 *
 * ВАЖНО: это специально вынесено в отдельный объект, чтобы
 * не смешивать API-модель Document и производные view-атрибуты.
 */
export interface DocumentCompositionMeta {
  /** Тип композиции: single vs multi */
  composition_type: DocumentCompositionType;

  /** Количество сегментов / логических документов внутри файла */
  segment_count: number;

  /** Метка основного сегмента (например, основной SPA) */
  primary_segment_label: string | null;

  /** ID основного сегмента, если известен */
  primary_segment_id: string | null;

  /** Флаг, что файл является “составным” (multi-structure / composite file) */
  is_composite_file: boolean;
}

/**
 * View-тип документа с информацией о композиции.
 * Может использоваться в списке документов, гриде и др. местах.
 */
export interface DocumentWithComposition extends Document {
  composition?: DocumentCompositionMeta | null;
}

export type DocumentListItem = DocumentWithComposition;

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

  field_format?: string | null;

  page?: number | null;
  clause_uid?: string | null;

  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

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
  page?: number;
  clauseUid?: string;
  elementId?: string;

  segmentId?: string;
  chunkId?: string;
  chunkIndex?: number;

  // ── B5: anchor-level highlight (populated as B3.6 lands) ───────────────
  // Когда непустой — viewer подсвечивает эти элементы напрямую.
  // Пока пусто — fallback на chunk-bbox (текущее поведение).
  layoutElementIds?: string[];
  bboxUnion?: [number, number, number, number];
  anchorMethod?: string;
  anchorConfidence?: number;
  anchorStale?: boolean;
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
  | "classification_requires_review"
  | "composition_type"
  | "segment_count"
  | "primary_segment_label"
  | "is_composite_file";

export interface DocumentColumnDef {
  id: DocumentColumnId;
  label: string;
  labelKey?: string;
  description: string;
  descriptionKey?: string;
  field: keyof Document | "applicable_triggers_count";
  defaultVisible: boolean;
}

export const ALL_DOCUMENT_COLUMNS: DocumentColumnDef[] = [
  {
    id: "filename",
    label: "Document Name",
    labelKey: "documents:columns.filename.label",
    description: "File name of the document in Data Room.",
    descriptionKey: "documents:columns.filename.description",
    field: "filename",
    defaultVisible: true,
  },
  {
    id: "folder_path",
    label: "Folder",
    labelKey: "documents:columns.folder_path.label",
    description: "Folder path in Data Room structure.",
    descriptionKey: "documents:columns.folder_path.description",
    field: "folder_path",
    defaultVisible: true,
  },
  {
    id: "doc_type",
    label: "Document Type",
    labelKey: "documents:columns.doc_type.label",
    description: "Classified document type (SPA, NDA, etc.).",
    descriptionKey: "documents:columns.doc_type.description",
    field: "doc_type",
    defaultVisible: true,
  },
  {
    id: "status",
    label: "Processing Status",
    labelKey: "documents:columns.status.label",
    description: "Current processing status of the document in the pipeline.",
    descriptionKey: "documents:columns.status.description",
    field: "status",
    defaultVisible: true,
  },
  {
    id: "human_review_status",
    label: "Lawyer Review",
    labelKey: "documents:columns.human_review_status.label",
    description: "Human-readable lawyer review status.",
    descriptionKey: "documents:columns.human_review_status.description",
    field: "human_review_status",
    defaultVisible: true,
  },
  {
    id: "reviewed_by_person",
    label: "Reviewed Flag",
    labelKey: "documents:columns.reviewed_by_person.label",
    description: "Boolean flag indicating whether the document was reviewed by a lawyer.",
    descriptionKey: "documents:columns.reviewed_by_person.description",
    field: "reviewed_by_person",
    defaultVisible: false,
  },
  {
    id: "classification_requires_review",
    label: "Needs Review",
    labelKey: "documents:columns.classification_requires_review.label",
    description: "Flag indicating classifier marked document as requiring manual review.",
    descriptionKey: "documents:columns.classification_requires_review.description",
    field: "classification_requires_review",
    defaultVisible: false,
  },
  {
    id: "risk_level",
    label: "Risk",
    labelKey: "documents:columns.risk_level.label",
    description: "Document risk level: low/medium/high/critical.",
    descriptionKey: "documents:columns.risk_level.description",
    field: "risk_level",
    defaultVisible: true,
  },
  {
    id: "language",
    label: "Language",
    labelKey: "documents:columns.language.label",
    description: "Primary document language (RU, EN, etc.).",
    descriptionKey: "documents:columns.language.description",
    field: "language",
    defaultVisible: false,
  },
  {
    id: "jurisdiction_guess",
    label: "Jurisdiction",
    labelKey: "documents:columns.jurisdiction_guess.label",
    description: "Estimated document jurisdiction.",
    descriptionKey: "documents:columns.jurisdiction_guess.description",
    field: "jurisdiction_guess",
    defaultVisible: false,
  },
  {
    id: "page_count",
    label: "Pages",
    labelKey: "documents:columns.page_count.label",
    description: "Number of pages in the document.",
    descriptionKey: "documents:columns.page_count.description",
    field: "page_count",
    defaultVisible: false,
  },
  {
    id: "classification_level",
    label: "Classification Level",
    labelKey: "documents:columns.classification_level.label",
    description: "Level at which document type was determined (L0–L4, L_manual).",
    descriptionKey: "documents:columns.classification_level.description",
    field: "classification_level",
    defaultVisible: false,
  },
  {
    id: "classification_confidence",
    label: "Classification Confidence",
    labelKey: "documents:columns.classification_confidence.label",
    description: "Score 0–1 indicating classification confidence.",
    descriptionKey: "documents:columns.classification_confidence.description",
    field: "classification_confidence",
    defaultVisible: false,
  },
  {
    id: "applicable_triggers_count",
    label: "Triggers",
    labelKey: "documents:columns.applicable_triggers_count.label",
    description: "Number of applicable check triggers for the document.",
    descriptionKey: "documents:columns.applicable_triggers_count.description",
    field: "applicable_triggers_count",
    defaultVisible: false,
  },
  {
    id: "created_at",
    label: "Created",
    labelKey: "documents:columns.created_at.label",
    description: "Date and time when the document was added.",
    descriptionKey: "documents:columns.created_at.description",
    field: "created_at",
    defaultVisible: false,
  },
  {
    id: "updated_at",
    label: "Updated",
    labelKey: "documents:columns.updated_at.label",
    description: "Date and time of last document update.",
    descriptionKey: "documents:columns.updated_at.description",
    field: "updated_at",
    defaultVisible: true,
  },
  {
    id: "id",
    label: "Document ID",
    labelKey: "documents:columns.id.label",
    description: "Technical document identifier (UUID).",
    descriptionKey: "documents:columns.id.description",
    field: "id",
    defaultVisible: false,
  },
  {
    id: "deal_id",
    label: "Deal ID",
    labelKey: "documents:columns.deal_id.label",
    description: "Identifier of the deal the document belongs to.",
    descriptionKey: "documents:columns.deal_id.description",
    field: "deal_id",
    defaultVisible: false,
  },
  {
    id: "composition_type",
    label: "Composition",
    labelKey: "documents:columns.composition_type.label",
    description: "Single or multi-document file (by segment structure).",
    descriptionKey: "documents:columns.composition_type.description",
    field: "id",
    defaultVisible: true,
  },
  {
    id: "segment_count",
    label: "Segments",
    labelKey: "documents:columns.segment_count.label",
    description: "Number of segments / logical documents in the file.",
    descriptionKey: "documents:columns.segment_count.description",
    field: "id",
    defaultVisible: true,
  },
  {
    id: "primary_segment_label",
    label: "Primary Segment",
    labelKey: "documents:columns.primary_segment_label.label",
    description: "Name of the primary segment (e.g. main SPA).",
    descriptionKey: "documents:columns.primary_segment_label.description",
    field: "id",
    defaultVisible: false,
  },
  {
    id: "is_composite_file",
    label: "Composite File",
    labelKey: "documents:columns.is_composite_file.label",
    description: "Flag indicating the file contains multiple logical documents.",
    descriptionKey: "documents:columns.is_composite_file.description",
    field: "id",
    defaultVisible: false,
  },
];


