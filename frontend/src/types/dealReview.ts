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

// =============================================================
// DD GRID V1 CONTRACT
// -------------------------------------------------------------
// Точное отражение backend-контракта GET
// /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
// Строго по DDGridV1ResponseDTO (Pydantic).
//
// Правила:
// - никаких хардкодов под конкретные check_id / column_id / doc_type;
// - все семантические состояния — closed unions;
// - execution_status оставлен как string, потому что закрытый список
//   его значений во frontend-контракте не зафиксирован; при появлении
//   закрытого enum — заменить на union без миграций UI-кода;
// - словари всегда строго типизированы через Record<string, X>;
// - fallback_display гарантированно строка (по контракту всегда задан).
// =============================================================

/**
 * Пять возможных состояний ячейки в DD Grid V1.
 *
 * defined         — значение найдено
 * not_defined     — check выполнен, значение не найдено
 * not_applicable  — check не применим к данному doc_type
 * not_executed    — check не выполнялся для данного документа
 * error           — техническая ошибка выполнения check-а
 */
export type DDGridV1CellState =
  | "defined"
  | "not_defined"
  | "not_applicable"
  | "not_executed"
  | "error";

/**
 * Формат runtime-колонки в DD Grid V1.
 *
 * text           — plain string (при наличии unit — string + " " + unit)
 * enum           — display строится через enum_labels[raw_value]
 * yes_no         — булево значение как "Да" / "Нет"
 * presence_only  — индикатор наличия ("Присутствует" / fallback)
 */
export type DDGridV1ColumnFormat =
  | "text"
  | "enum"
  | "yes_no"
  | "presence_only";

/**
 * Уверенность в location для одного поля / ячейки.
 *
 * high  — exact pinpoint (clause_ref / page точно определены)
 * low   — approximate (fallback), navigation допустима с caveat
 * null  — location недоступна для этой ячейки
 */
export type DDGridV1LocationConfidence = "high" | "low" | null;

/**
 * Runtime-колонка внутри check-а.
 *
 * ВАЖНО: column_id НЕ гарантирует уникальность в масштабе всего response,
 * потому что один и тот же column_id может встречаться несколько раз внутри
 * одного check-а (разные field_name с одинаковым column_id). Для стабильных
 * UI-ключей всегда строить runtime key на уровне (scope, path, index),
 * а не полагаться на column_id как на primary key.
 */
export interface DDGridV1ColumnDTO {
  column_id: string;
  check_id: string;
  label: string;
  format: DDGridV1ColumnFormat;
  fallback_display: string;
  display_order: number;
  enum_labels: Record<string, string>;
  unit: string | null;
}

/**
 * Метаданные одного check-а внутри группы (global) или типа документа.
 */
export interface DDGridV1CheckDTO {
  check_id: string;
  check_name: string;
  display_order: number;
  columns: DDGridV1ColumnDTO[];
  display_summary_field: string | null;
  metadata_fields: string[];
}

/**
 * Глобальная группа check-ов (не привязанная к типу документа).
 */
export interface DDGridV1GlobalGroupDTO {
  group_id: string;
  label: string;
  display_order: number;
  checks: DDGridV1CheckDTO[];
}

/**
 * Конкретный тип документа внутри doc-type класса.
 */
export interface DDGridV1DocTypeDTO {
  type_code: string;
  name: string;
  checks: DDGridV1CheckDTO[];
}

/**
 * Класс типов документов (например, "Передача права собственности"),
 * группирующий один или несколько типов документов.
 */
export interface DDGridV1DocTypeClassDTO {
  group_id: string;
  label: string;
  display_order: number;
  types: DDGridV1DocTypeDTO[];
}

/**
 * Одно значение ячейки для конкретного (document_id, column_id).
 *
 * Правила location:
 * - has_location_fallback = false + clause_ref/page заданы → exact
 * - has_location_fallback = true  + clause_ref/page заданы → approximate
 * - has_location_fallback = true  + clause_ref/page null    → navigation недоступна
 */
export interface DDGridV1CellValueDTO {
  cell_state: DDGridV1CellState;
  display_value: string;
  raw_value: string | null;
  location_clause_ref: string | null;
  location_page: number | null;
  location_confidence: DDGridV1LocationConfidence;
  has_location_fallback: boolean;
  location_fallback_reason: string | null;
}

/**
 * Одно извлечённое поле внутри drawer-content check-а.
 *
 * ВАЖНО: несколько field-ов внутри одного check-а могут ссылаться на
 * одинаковый column_id. Для стабильных ключей UI использовать индекс
 * внутри массива fields, а не column_id.
 */
export interface DDGridV1DrawerFieldDTO {
  column_id: string;
  field_name: string;
  label: string;
  cell_state: DDGridV1CellState;
  display_value: string;
  raw_value: string | null;
  location_clause_ref: string | null;
  location_page: number | null;
  location_confidence: DDGridV1LocationConfidence;
  has_location_fallback: boolean;
  location_fallback_reason: string | null;
}

/**
 * Полный контент drawer для одной пары (document_id, check_id).
 *
 * Reason precedence (реализуется в UI-слое):
 *   1. metadata field "reason"
 *   2. metadata field "explanation"
 *   3. metadata field "notes"
 *   4. review_message
 *   5. display_text
 *
/**
 * Уровень детекции.
 * L1 — Pattern/rules, L2 — LLM, L3 — RAG+LLM, L4 — Manual QC.
 */
export type DDGridV1DetectionLevel = "L1" | "L2" | "L3" | "L4";

/**
 * API QC статус для drawer.
 * pending — ещё не проверялось.
 * approved — одобрено.
 * rejected — отклонено.
 * needs_review — требует проверки.
 */
export type DDGridV1DrawerQcStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_review";

/**
 * Полный контракт drawer content из DDGridV1ResponseDTO (backend B3).
 *
 * execution_status: закрытый enum — SUCCESS | FAILED | TIMEOUT | SKIPPED | PARTIAL.
 * Оставлен строкой: новые значения backend добавляет без breaking change.
 *
 * detection_level / confidence / quality_flags — прозрачность результата (B3 P0).
 * qc_* — audit trail без отдельного round-trip (B3 P0).
 * agent_name / model_version / execution_time_ms / retry_attempts / input_tokens / output_tokens
 * — observability (B3 P1).
 */
export interface DDGridV1DrawerContentDTO {
  check_id: string;
  check_name: string;
  document_id: string;
  cell_state: DDGridV1CellState;
  reason: string | null;
  review_status: string | null;
  review_message: string | null;
  display_text: string | null;
  execution_status: string;

  // B3 P0 — Transparency
  detection_level: DDGridV1DetectionLevel | null;
  confidence: number | null;
  quality_flags: Record<string, true> | null;

  // B3 P0 — QC Audit Trail
  qc_status: DDGridV1DrawerQcStatus | null;
  qc_by: string | null;
  qc_at: string | null;
  qc_comment: string | null;

  // B3 P1 — Observability
  agent_name: string | null;
  model_version: string | null;
  execution_time_ms: number | null;
  retry_attempts: number | null;
  input_tokens: number | null;
  output_tokens: number | null;

  fields: DDGridV1DrawerFieldDTO[];
  evidence_items: string[];
}

/**
 * Метаданные документа, попавшего в ответ DD Grid V1.
 */
export interface DDGridV1DocumentMetaDTO {
  document_id: string;
  filename: string;
  doc_type: string;
  status: string;
  folder_path: string | null;
}

/**
 * Полный ответ backend endpoint GET
 * /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
 *
 * Источник правды для UI:
 * - строить runtime-колонки следует из global_groups + doc_type_classes,
 *   а НЕ из column_registry (registry не гарантирует уникальности
 *   пары column_id внутри одного check-а — там значения могут схлопнуться).
 * - column_registry рассматривать как индекс для быстрого lookup по column_id,
 *   но не как primary source of truth по составу колонок.
 */
export interface DDGridV1ResponseDTO {
  deal_id: string;
  run_id: string;

  global_groups: DDGridV1GlobalGroupDTO[];
  doc_type_classes: DDGridV1DocTypeClassDTO[];

  column_registry: Record<string, DDGridV1ColumnDTO>;
  cell_values: Record<string, Record<string, DDGridV1CellValueDTO>>;
  drawer_contents: Record<string, Record<string, DDGridV1DrawerContentDTO>>;

  documents_meta: DDGridV1DocumentMetaDTO[];
}

