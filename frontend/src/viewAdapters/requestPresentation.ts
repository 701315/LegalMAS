// =============================================================
// src/viewAdapters/requestPresentation.ts
// Адаптеры для преобразования legacy DDRequest и review DDRequestDTO
// в единую UI read-model для переиспользуемых presentation components.
//
// Цель:
// - Изолировать различия между legacy и review API-контрактами
// - Предоставить стабильный интерфейс для UI-компонентов
// - Упростить добавление новых полей без изменения UI-логики
//
// Для непрофессионального программиста:
// Этот файл — "переводчик" между двумя разными форматами данных с бэкенда
// (legacy requests и review requests) в один общий формат, понятный UI.
// Так UI-компоненты могут работать с обоими источниками данных без изменений.
// =============================================================

import type { DDRequest, StructuredValue } from "../types/ddRequests";
import type { DDRequestDTO } from "../types/dealReview";
import { normalizeStructuredValue } from "../types/ddRequests";

// =============================================================
// UI Read-Model типы (view-слой)
// =============================================================

/**
 * Провenance-информация о сегменте и chunk для навигации в viewer.
 * Все поля опциональны, потому что в legacy requests этих данных нет.
 */
export interface SegmentProvenanceView {
  segmentId: string | null;
  segmentTitle: string | null;
  segmentType: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;
  chunkId: string | null;
  chunkIndex: number | null;
}

/**
 * Документ в UI-представлении.
 * id — опционален, потому что в legacy это UUID, а в review его нет.
 * name — всегда есть (в legacy это UUID, в review — человекочитаемое имя).
 */
export interface DocumentView {
  id: string | null;
  name: string;
  rawId?: string | null; // для tooltip с UUID в review mode
}

/**
 * Извлечённое значение (structured value) в UI-представлении.
 */
export interface StructuredValueView {
  key: string;
  value: string;
  format: string | null;
}

/**
 * Источник запроса (source badge).
 */
export interface SourceView {
  code: string;
  label: string;
  colorClass: string;
  helperText?: string | null;
}

/**
 * Статус запроса (для legacy CRUD-режима).
 */
export interface StatusView {
  code: string;
  label: string;
}

/**
 * UI read-model для строки таблицы DD-запросов.
 * Используется в RequestsTable и ReviewRequestsTable.
 */
export interface RequestTableRowView {
  id: string;
  priority: "critical" | "high" | "medium";
  text: string;
  checkLabel: string | null;
  addressee: string | null;

  // Документы
  documentsLabel: string | null; // "3 док." или "Договор.pdf +2"
  documentCount: number;

  // Segment context (только для review)
  segmentTitle: string | null;
  chunkIndex: number | null;
  hasSegmentContext: boolean;

  // Legacy-only поля
  statusLabel: string | null;
  sourceLabel: string | null;
  sourceColorClass: string | null;

  mode: "legacy" | "review";
}

/**
 * UI read-model для side panel деталей DD-запроса.
 * Используется в RequestSidePanel и ReviewRequestSidePanel.
 */
export interface RequestPanelView {
  id: string;
  title: string; // check_name или fallback "Запрос #..."
  priority: "critical" | "high" | "medium";
  text: string;
  addressee: string | null;

  checkId: string | null;
  checkLabel: string | null;

  documents: DocumentView[];
  docTypes: string[];

  structuredValues: StructuredValueView[];

  source: SourceView | null;
  status: StatusView | null;

  evidenceRefs: string[];

  segment: SegmentProvenanceView | null;

  canEdit: boolean;
  canDelete: boolean;
  isReadOnly: boolean;
  mode: "legacy" | "review";
}

/**
 * Viewer navigation target для review request.
 *
 * Для непрофессионального программиста:
 * Это набор данных, необходимых чтобы открыть PDF-viewer на конкретном
 * документе и прокрутить его до нужного сегмента/чанка.
 *
 * Если documentId === null, значит backend не передал идентификатор документа
 * и навигация в viewer невозможна.
 */
export interface RequestViewerTargetView {
  documentId: string;
  segmentId: string | null;
  chunkId: string | null;
  chunkIndex: number | null;
}

// =============================================================
// Константы для UI-маппинга
// =============================================================

const STATUS_LABELS: Record<string, string> = {
  open: "Открыт",
  in_progress: "В работе",
  resolved: "Закрыт",
};

const SOURCE_CONFIG: Record<
  string,
  { label: string; color: string; helper?: string }
> = {
  yaml_template: {
    label: "YAML-шаблон",
    color: "bg-purple-100 text-purple-700",
    helper:
      "Текст и адресат сгенерированы автоматически из YAML-инструкции типа документа.",
  },
  manual: {
    label: "Вручную",
    color: "bg-blue-100 text-blue-700",
  },
  aggregator: {
    label: "Агрегатор",
    color: "bg-green-100 text-green-700",
  },
};

// =============================================================
// Helper-функции
// =============================================================

/**
 * Формирует короткий label для списка документов в таблице.
 * Примеры: "3 док.", "Договор.pdf", "Договор.pdf +2"
 */
function getDocumentsLabel(
  documents: DocumentView[],
  maxVisible: number = 1,
): string | null {
  if (documents.length === 0) return null;
  if (documents.length === 1) return documents[0].name;

  const first = documents[0].name;
  const rest = documents.length - maxVisible;
  return rest > 0 ? `${first} +${rest}` : first;
}

/**
 * Формирует segment label для таблицы.
 * Приоритет: segment_title > segment_type > null
 */
function getSegmentLabel(segment: SegmentProvenanceView | null): string | null {
  if (!segment) return null;
  if (segment.segmentTitle) return segment.segmentTitle;
  if (segment.segmentType) return segment.segmentType;
  return null;
}

/**
 * Проверяет, есть ли реальные segment-данные (хотя бы одно поле не null).
 */
function hasSegmentContext(segment: SegmentProvenanceView | null): boolean {
  if (!segment) return false;
  return !!(
    segment.segmentId ||
    segment.segmentTitle ||
    segment.chunkId ||
    segment.chunkIndex != null
  );
}

// =============================================================
// Адаптеры для Table Row View
// =============================================================

/**
 * Преобразует legacy DDRequest в UI read-model для строки таблицы.
 * Legacy requests НЕ ИМЕЮТ segment context — возвращаем null.
 */
export function toRequestTableRowFromLegacy(
  req: DDRequest,
): RequestTableRowView {
  const documents: DocumentView[] = (req.document_refs || []).map((docId) => ({
    id: docId,
    name: docId, // в legacy нет имён, только UUID
    rawId: docId,
  }));

  const sourceConfig = req.source ? SOURCE_CONFIG[req.source] : null;

  return {
    id: req.id,
    priority: req.priority,
    text: req.text,
    checkLabel: req.check_id || null,
    addressee: req.addressee || null,

    documentsLabel: getDocumentsLabel(documents),
    documentCount: documents.length,

    // Legacy НЕ имеет segment context
    segmentTitle: null,
    chunkIndex: null,
    hasSegmentContext: false,

    statusLabel: req.status ? STATUS_LABELS[req.status] || req.status : null,
    sourceLabel: sourceConfig?.label || null,
    sourceColorClass: sourceConfig?.color || null,

    mode: "legacy",
  };
}

/**
 * Преобразует review DDRequestDTO в UI read-model для строки таблицы.
 * Review requests УЖЕ ИМЕЮТ segment context через extends SegmentProvenanceDTO.
 *
 * Для непрофессионального программиста:
 * Backend отдаёт два массива: document_names (имена файлов) и document_ids (UUID).
 * Они синхронизированы по индексу: первое имя соответствует первому id, и так далее.
 * Мы создаём объекты DocumentView, где id берётся из document_ids по тому же индексу.
 */
export function toRequestTableRowFromReview(
  req: DDRequestDTO,
): RequestTableRowView {
  // document_ids может быть пустым, если backend ещё не обновлён
  const documentIds = req.document_ids || [];

  // Создаём DocumentView для каждого документа, беря id из document_ids по индексу
  const documents: DocumentView[] = (req.document_names || []).map(
    (name, index) => ({
      id: documentIds[index] ?? null,
      name,
      rawId: documentIds[index] ?? null,
    }),
  );

  const segment: SegmentProvenanceView = {
    segmentId: req.segment_id ?? null,
    segmentTitle: req.segment_title ?? null,
    segmentType: req.segment_type ?? null,
    segmentOrder: req.segment_order ?? null,
    isPrimarySegment: req.is_primary_segment ?? null,
    chunkId: req.chunk_id ?? null,
    chunkIndex: req.chunk_index ?? null,
  };

  return {
    id: req.request_id,
    priority: req.priority as "critical" | "high" | "medium",
    text: req.text,
    checkLabel: req.check_name || null,
    addressee: req.addressee || null,

    documentsLabel: getDocumentsLabel(documents),
    documentCount: documents.length,

    segmentTitle: getSegmentLabel(segment),
    chunkIndex: segment.chunkIndex,
    hasSegmentContext: hasSegmentContext(segment),

    // Review не имеет status/source
    statusLabel: null,
    sourceLabel: null,
    sourceColorClass: null,

    mode: "review",
  };
}

// =============================================================
// Адаптеры для Panel View
// =============================================================

/**
 * Преобразует legacy DDRequest в UI read-model для side panel.
 */
export function toRequestPanelViewFromLegacy(
  req: DDRequest,
  canManageRequests: boolean = false,
): RequestPanelView {
  const documents: DocumentView[] = (req.document_refs || []).map((docId) => ({
    id: docId,
    name: docId, // в legacy нет имён, показываем UUID
    rawId: docId,
  }));

  const structuredValues: StructuredValueView[] = (
    req.structured_values || []
  ).map((sv: StructuredValue) => normalizeStructuredValue(sv));

  const sourceConfig = req.source ? SOURCE_CONFIG[req.source] : null;
  const source: SourceView | null = sourceConfig
    ? {
        code: req.source!,
        label: sourceConfig.label,
        colorClass: sourceConfig.color,
        helperText: sourceConfig.helper || null,
      }
    : null;

  const status: StatusView | null = req.status
    ? {
        code: req.status,
        label: STATUS_LABELS[req.status] || req.status,
      }
    : null;

  return {
    id: req.id,
    title: req.check_id || `Запрос #${req.id.slice(-6)}`,
    priority: req.priority,
    text: req.text,
    addressee: req.addressee || null,

    checkId: req.check_id || null,
    checkLabel: req.check_id || null,

    documents,
    docTypes: [],

    structuredValues,

    source,
    status,

    evidenceRefs: req.evidence_refs || [],

    // Legacy НЕ имеет segment provenance
    segment: null,

    canEdit: canManageRequests,
    canDelete: canManageRequests,
    isReadOnly: false,
    mode: "legacy",
  };
}

/**
 * Преобразует review DDRequestDTO в UI read-model для side panel.
 *
 * Для непрофессионального программиста:
 * Берём данные из backend DTO и создаём удобный для UI формат.
 * Документы формируем как пары (id, name), где id берётся из document_ids.
 * Если document_ids пустой — id будет null, и viewer jump будет недоступен.
 */
export function toRequestPanelViewFromReview(
  req: DDRequestDTO,
): RequestPanelView {
  // document_ids может быть пустым, если backend ещё не обновлён
  const documentIds = req.document_ids || [];

  // Создаём DocumentView для каждого документа, беря id из document_ids по индексу
  const documents: DocumentView[] = (req.document_names || []).map(
    (name, index) => ({
      id: documentIds[index] ?? null,
      name,
      rawId: documentIds[index] ?? null,
    }),
  );

  const structuredValues: StructuredValueView[] = (
    req.structured_values || []
  ).map((sv) => {
    // DDRequestDTO.structured_values теперь поддерживает оба формата
    // после исправления типа в dealReview.ts
    return normalizeStructuredValue(sv as StructuredValue);
  });

  const segment: SegmentProvenanceView = {
    segmentId: req.segment_id ?? null,
    segmentTitle: req.segment_title ?? null,
    segmentType: req.segment_type ?? null,
    segmentOrder: req.segment_order ?? null,
    isPrimarySegment: req.is_primary_segment ?? null,
    chunkId: req.chunk_id ?? null,
    chunkIndex: req.chunk_index ?? null,
  };

  return {
    id: req.request_id,
    title: req.check_name || `Запрос`,
    priority: req.priority as "critical" | "high" | "medium",
    text: req.text,
    addressee: req.addressee || null,

    checkId: req.check_id || null,
    checkLabel: req.check_name || null,

    documents,
    docTypes: req.doc_types || [],

    structuredValues,

    // Review не имеет source/status (read-only режим)
    source: null,
    status: null,

    evidenceRefs: [],

    segment: hasSegmentContext(segment) ? segment : null,

    // Review mode — read-only
    canEdit: false,
    canDelete: false,
    isReadOnly: true,
    mode: "review",
  };
}

// =============================================================
// Helper для viewer navigation (MR4)
// =============================================================

/**
 * Определяет target для viewer navigation из review request panel view.
 *
 * Для непрофессионального программиста:
 * Эта функция проверяет, можно ли открыть viewer для данного запроса.
 * Для этого нужен хотя бы один документ с непустым id.
 *
 * Возвращает:
 * - null, если нет документов с id (viewer jump невозможен)
 * - объект RequestViewerTargetView с document_id + segment/chunk данными
 *
 * Логика выбора документа:
 * - Берём первый документ, у которого есть id
 * - Если все documents имеют id === null, возвращаем null
 */
export function getRequestViewerTarget(
  view: RequestPanelView,
): RequestViewerTargetView | null {
  // Ищем первый документ с непустым id
  const firstDocumentWithId = view.documents.find((doc) => !!doc.id);

  if (!firstDocumentWithId?.id) {
    // Нет ни одного документа с id — viewer jump невозможен
    return null;
  }

  // Формируем viewer target из первого документа + segment provenance
  return {
    documentId: firstDocumentWithId.id,
    segmentId: view.segment?.segmentId ?? null,
    chunkId: view.segment?.chunkId ?? null,
    chunkIndex: view.segment?.chunkIndex ?? null,
  };
}





