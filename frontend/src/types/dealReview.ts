// =============================================================
// src/types/dealReview.ts
// DTO-типы для UI deal review API.
// Базово повторяют backend-контракт из src/api/schemas/deal_review.py,
// но дополнены optional полями для canonical display semantics
// и segment-aware UX.
// =============================================================

export type ReviewResult = "fail" | "pass" | "unclear";

/**
 * В текущем backend severity местами семантически смешивается с результатом:
 * кроме "critical" / "high" / "medium" могут приходить "pass" / "unclear".
 * Оставляем это поведение как часть контракта, чтобы не ломать существующий UI.
 */
export type ReviewSeverity =
  | "critical"
  | "high"
  | "medium"
  | "pass"
  | "unclear";

export type ReviewQcStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_review";

/**
 * Canonical review workflow status из backend result semantics.
 * Фронт не интерпретирует бизнес-смысл заново — только рендерит.
 */
export type ReviewWorkflowStatus =
  | "needs_review"
  | "ok"
  | "not_applicable"
  | "unclear";

export type ReviewCheckOrigin =
  | "GLOBAL_PLAYBOOK"
  | "DOCUMENT_TYPE"
  | "CONDITIONAL";

export type ReviewFieldFormat = "money" | "date" | "entity_name" | "text";

/**
 * Denormalized semantic type чека из backend playbook/result semantics.
 * Нужен для правильного renderer / details UX.
 */
export type ReviewUiMode =
  | "clause_presence"
  | "extraction"
  | "field_extraction"
  | "risk_flag"
  | "comparison"
  | "summary";

/**
 * Общий provenance-блок для segment/chunk-aware navigation.
 * Все поля optional, чтобы контракт был совместим с текущим backend.
 */
export interface SegmentProvenanceDTO {
  segment_id?: string | null;
  segment_title?: string | null;
  segment_type?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  chunk_id?: string | null;
  chunk_index?: number | null;
}

/**
 * Сводка по документу для review-экранов.
 * Optional composition-поля добавлены заранее под будущие badges/filters.
 */
export interface DocumentSummaryDTO {
  document_id: string;
  name: string;
  doc_type: string;
  status: string;

  critical_count: number;
  high_count: number;
  medium_count: number;
  pass_count: number;
  unclear_count: number;

  has_degraded_structure: boolean;
  in_quarantine: boolean;

  classification_level: string;
  classification_confidence: number;

  // Optional composition fields for multi-document UX
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;
}

/**
 * Деталь конкретной проверки на document detail review page.
 */
export interface CheckItemDTO extends SegmentProvenanceDTO {
  check_id: string;
  check_name: string;

  result: ReviewResult | string;
  severity: ReviewSeverity | string;

  evidence_snippet: string | null;
  page: number | null;
  clause_uid: string | null;

  confidence: number | null;
  detector_used: string | null;
  quality_flags: Record<string, unknown> | null;

  conditional_check_triggered: boolean;
  trigger_name: string | null;

  structured_data: Record<string, unknown>;
  origin?: ReviewCheckOrigin | string | null;

  // Canonical display semantics (NEW)
  display_text?: string | null;
  review_status?: ReviewWorkflowStatus | string | null;
  review_message?: string | null;
  needs_manual_review?: boolean;
  ui_mode?: ReviewUiMode | string | null;
}

/**
 * Метаданные check-колонки в DD Matrix.
 */
export interface CheckMetaDTO {
  check_id: string;
  check_name: string;
  origin: ReviewCheckOrigin | string;
  severity: "critical" | "high" | "medium" | string;
  order_index: number;
  applicable_doc_types?: string[] | null;
}

/**
 * Извлечённое поле внутри matrix cell / document structured data.
 * Дополнено provenance-полями и местом в документе.
 */
export interface ExtractedFieldDTO extends SegmentProvenanceDTO {
  field_name: string;
  field_value: string;
  field_format: ReviewFieldFormat | string;

  page?: number | null;
  clause_uid?: string | null;
  snippet?: string | null;

  check_id?: string | null;
  check_name?: string | null;
}

/**
 * Ячейка новой DD Matrix.
 * Уже готова к segment-aware drill-down и viewer navigation.
 */
export interface MatrixCellDTO extends SegmentProvenanceDTO {
  result: ReviewResult | string;
  severity: ReviewSeverity | string;

  snippet: string;
  page: number | null;
  clause_uid: string | null;

  extracted: ExtractedFieldDTO[];

  confidence: number | null;
  qc_status: ReviewQcStatus | null;

  // QC audit trail
  qc_by: string | null;
  qc_comment: string | null;
  qc_at: string | null;

  conditional_check_triggered: boolean;
  trigger_name: string | null;

  // Canonical display semantics (NEW)
  display_text?: string | null;
  review_status?: ReviewWorkflowStatus | string | null;
  review_message?: string | null;
  needs_manual_review?: boolean;
  ui_mode?: ReviewUiMode | string | null;
}

/**
 * Строка матрицы = один документ + словарь результатов по check_id.
 */
export interface DocumentMatrixRowDTO {
  document_id: string;
  document_name: string;
  doc_type: string;
  folder_path: string;
  status: string;

  classification_level: string;
  classification_confidence: number;
  requires_manual_review?: boolean;

  // Optional composition fields
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;

  results: Record<string, MatrixCellDTO>;
}

/**
 * NEW:
 * Строка матрицы = один logical document / segment row.
 * Это целевой primary row model для review-only DD Grid.
 */
export interface SegmentMatrixRowDTO {
  document_id: string;
  document_name: string;
  doc_type: string;
  folder_path?: string | null;

  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  status: string;

  classification_level: string;
  classification_confidence: number;
  requires_manual_review?: boolean;

  results: Record<string, MatrixCellDTO>;
}

/**
 * Основной ответ backend dd-matrix endpoint.
 */
export interface DDMatrixResponseDTO {
  deal_id: string;
  run_id: string;
  deal_name: string;

  checks: CheckMetaDTO[];
  global_check_ids: string[];
  doc_type_check_ids: Record<string, string[]>;

  documents: DocumentMatrixRowDTO[];

  /**
   * NEW:
   * Segment-oriented rows returned by backend.
   * Это primary source для review matrix.
   * Optional до полного выравнивания frontend/backend контрактов.
   */
  segment_documents?: SegmentMatrixRowDTO[];

  total_documents: number;
  total_checks: number;
  severity_counts: Record<string, number>;
  quarantine_count: number;
  degraded_count: number;
  evidence_validity_rate: number;
}

/**
 * Детали review по конкретному документу в рамках run.
 */
export interface DocumentDetailDTO {
  document_id: string;
  name: string;
  doc_type: string;
  status: string;

  classification_level: string;
  classification_confidence: number;
  applicable_triggers: string[];

  // Optional composition fields
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;

  checks: CheckItemDTO[];
}

/**
 * DD Request / follow-up request в рамках review.
 *
 * Для непрофессионального программиста:
 * Это запрос юриста или автоматически сформированный follow-up вопрос
 * по результатам проверки документов. Содержит текст запроса, приоритет,
 * список документов и segment/chunk provenance для навигации в viewer.
 *
 * ВАЖНО для MR4:
 * - document_ids содержит UUID документов для прямой навигации в viewer
 * - document_names содержит человекочитаемые имена файлов для отображения
 * - Эти два массива синхронизированы по индексу: document_ids[0] относится
 *   к document_names[0], и так далее
 * - Segment provenance (segment_id, chunk_id, etc.) унаследованы от
 *   SegmentProvenanceDTO и указывают на конкретное место в документе
 */
export interface DDRequestDTO extends SegmentProvenanceDTO {
  request_id: string;
  priority: string;

  check_id: string | null;
  check_name: string | null;

  addressee: string;
  text: string;

  document_names: string[];

  /**
   * UUID документов, соответствующие document_names по индексу.
   * Если backend ещё не обновлён — может быть пустым массивом.
   * Если есть хотя бы один id — можно строить viewer navigation.
   */
  document_ids: string[];

  doc_types: string[];

  structured_values: Array<
    | { field_name: string; field_value: unknown; field_format?: string | null }
    | Record<string, unknown>
  >;
}

/**
 * Conditional checks в run-scoped review API.
 */
export interface ConditionalCheckDTO extends SegmentProvenanceDTO {
  document_name: string;
  doc_type: string;

  trigger_name: string;
  check_id: string;
  check_name: string;

  result: ReviewResult | string;
  severity: ReviewSeverity | string;

  evidence_snippet: string | null;
  page: number | null;
  clause_uid?: string | null;

  confidence: number | null;
  quality_flags: Record<string, unknown> | null;
}

/**
 * Плоское extracted-value представление для run-level / document-level structured data.
 * Расширено provenance-полями для segment-aware grouping.
 */
export interface ExtractedValueDTO extends SegmentProvenanceDTO {
  document_name: string;
  doc_type: string;

  check_name: string;
  field_name: string;
  field_value: string;
  field_format: ReviewFieldFormat | string;

  page: number | null;
  clause_uid: string | null;
}

/**
 * Structured data по конкретному документу внутри review run.
 * values сохранены в текущей форме backend-контракта,
 * но теперь каждая запись может нести segment/chunk provenance.
 */
export interface DocumentStructuredDataDTO {
  deal_id: string;
  run_id: string;

  document_id: string;
  document_name: string;
  doc_type: string;

  playbook_version_id?: string | null;
  playbook_name?: string | null;
  profile?: string | null;

  // Optional composition fields
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;

  total_values: number;
  values: ExtractedValueDTO[];
}

