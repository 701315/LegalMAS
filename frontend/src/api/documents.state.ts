// =============================================================
// src/api/documents.state.ts
// Нормализованные стейт-объекты для данных по документам.
//
// Эти типы и фабрики используются адаптерами и контейнерами,
// чтобы UI всегда понимал, что происходит:
// - идёт загрузка
// - документ найден / не найден
// - структурированные данные есть / отсутствуют
// - произошла ошибка
// =============================================================

import type {
  Document,
  StructuredDataResult,
  ReclassifyResult,
} from "../types";
import type {
  DocumentDetailsViewClassification,
  DocumentFamilyView,
  StructuredDataView,
} from "../components/documents/DocumentDetails";

// -------------------------------------------------------------
// DocumentDetailsState
// -------------------------------------------------------------

/**
 * Нормализованный стейт для правой панели деталей документа.
 *
 * Инварианты:
 * - при isLoading === true остальные флаги (notFound, error) должны быть false/null
 * - при notFound === true doc === null и error === null
 * - при error !== null notFound === false
 */
export interface DocumentDetailsState {
  // Основные данные для view
  doc: Document | null;
  classification: DocumentDetailsViewClassification | null;
  family: DocumentFamilyView | null;

  // Технические флаги
  isLoading: boolean;
  notFound: boolean;      // 404 по /documents/{id}
  error: string | null;   // проблемы сервера/сети и прочие ошибки

  // Результат последней переклассификации (если нужен во view)
  lastReclassifyResult?: ReclassifyResult;
}

/**
 * Начальное состояние: пока ничего не знаем, идёт загрузка.
 */
export function createInitialDocumentDetailsState(): DocumentDetailsState {
  return {
    doc: null,
    classification: null,
    family: null,
    isLoading: true,
    notFound: false,
    error: null,
    lastReclassifyResult: undefined,
  };
}

/**
 * Состояние "успех": документ найден и данные получены.
 */
export function createDocumentDetailsSuccessState(params: {
  doc: Document;
  classification: DocumentDetailsViewClassification | null;
  family: DocumentFamilyView | null;
  lastReclassifyResult?: ReclassifyResult;
}): DocumentDetailsState {
  return {
    doc: params.doc,
    classification: params.classification,
    family: params.family,
    isLoading: false,
    notFound: false,
    error: null,
    lastReclassifyResult: params.lastReclassifyResult,
  };
}

/**
 * Состояние "документ не найден" (404).
 */
export function createDocumentDetailsNotFoundState(): DocumentDetailsState {
  return {
    doc: null,
    classification: null,
    family: null,
    isLoading: false,
    notFound: true,
    error: null,
    lastReclassifyResult: undefined,
  };
}

/**
 * Состояние "ошибка загрузки" (500, сеть и т.п.).
 */
export function createDocumentDetailsErrorState(message: string): DocumentDetailsState {
  return {
    doc: null,
    classification: null,
    family: null,
    isLoading: false,
    notFound: false,
    error: message,
    lastReclassifyResult: undefined,
  };
}

/**
 * Хелпер для установки результата переклассификации поверх существующего стейта.
 * Полезно вызывать из контейнера после успешной мутации.
 */
export function withReclassifyResult(
  state: DocumentDetailsState,
  result: ReclassifyResult | undefined,
): DocumentDetailsState {
  return {
    ...state,
    lastReclassifyResult: result,
  };
}

// -------------------------------------------------------------
// StructuredDataState
// -------------------------------------------------------------

/**
 * Нормализованный стейт для блока структурированных данных документа.
 *
 * Инварианты:
 * - при isLoading === true остальные флаги (notAvailable, error) должны быть false/null
 * - при notAvailable === true items === [] и error === null
 * - при error !== null notAvailable === false
 */
export interface StructuredDataState {
  // Основные данные
  items: StructuredDataView["extracted_values"];
  total: number;

  // Технические флаги
  isLoading: boolean;
  notAvailable: boolean;  // 404 по /structured-data => данных для этого документа нет
  error: string | null;
}

/**
 * Начальное состояние для структурированных данных.
 */
export function createInitialStructuredDataState(): StructuredDataState {
  return {
    items: [],
    total: 0,
    isLoading: true,
    notAvailable: false,
    error: null,
  };
}

/**
 * Состояние "успех": данные получены.
 */
export function createStructuredDataSuccessState(
  data: StructuredDataResult,
): StructuredDataState {
  return {
    items: data.extracted_values,
    total: data.total_extracted,
    isLoading: false,
    notAvailable: false,
    error: null,
  };
}

/**
 * Состояние "данные недоступны" (404).
 * Это не ошибка, а нормальная ситуация: для этого документа
 * просто нет структурированных данных.
 */
export function createStructuredDataNotAvailableState(): StructuredDataState {
  return {
    items: [],
    total: 0,
    isLoading: false,
    notAvailable: true,
    error: null,
  };
}

/**
 * Состояние "ошибка загрузки" (500, сеть).
 */
export function createStructuredDataErrorState(message: string): StructuredDataState {
  return {
    items: [],
    total: 0,
    isLoading: false,
    notAvailable: false,
    error: message,
  };
}
