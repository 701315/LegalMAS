// =============================================================
// src/api/documents.stateHooks.ts
// Хуки-обёртки над DTO-хуками:
// - useDocumentDetailsState
// - useStructuredDataState
//
// Они не меняют существующий API (useDocumentDetail/useStructuredData),
// а поверх него строят нормализованный доменный стейт.
// =============================================================

import { useDocumentDetail, useStructuredData } from "./documents";
import {
  createInitialDocumentDetailsState,
  createDocumentDetailsSuccessState,
  createDocumentDetailsErrorState,
  createInitialStructuredDataState,
  createStructuredDataSuccessState,
  createStructuredDataErrorState,
  createDocumentDetailsNotFoundState,
  createStructuredDataNotAvailableState,
  type DocumentDetailsState,
  type StructuredDataState,
} from "./documents.state";

import type { DocumentDetail, StructuredDataResult, ApiError } from "../types";

/**
 * Хук для получения нормализованного стейта деталей документа.
 *
 * Внутри использует useDocumentDetail (DTO) и добавляет:
 * - isLoading
 * - error (как строку)
 * - notFound (true при 404 или отсутствии данных)
 */
export function useDocumentDetailsState(
  docId: string | null,
): DocumentDetailsState {
  const { data, isLoading, error } = useDocumentDetail(docId);

  // Начальное состояние

  if (isLoading) {
    // Пока грузится — возвращаем initialState с isLoading=true
    return createInitialDocumentDetailsState();
  }

  if (error) {
    const apiError = error as Partial<ApiError>;

    // 404: документ не найден
    if (apiError.status === 404) {
      return createDocumentDetailsNotFoundState();
    }

    // Другие ошибки: сервер/сеть и т.п.
    const message = getErrorMessage(error);
    return createDocumentDetailsErrorState(message);
  }

  // Успешный ответ: data — это DocumentDetail | undefined
  const detail = data as DocumentDetail | undefined;
  if (!detail) {
    // Нет данных и нет ошибки — считаем, что документ не найден
    return createDocumentDetailsNotFoundState();
  }

  const classification = adaptClassification(detail);
  const family = null; // family сейчас грузится отдельным хуком в контейнере

  return createDocumentDetailsSuccessState({
    doc: detail.document,
    classification,
    family,
  });
}

/**
 * Хук для нормализованного стейта структурированных данных.
 *
 * Внутри использует useStructuredData (DTO) и добавляет:
 * - isLoading
 * - error
 * - notAvailable (true при 404 или отсутствии данных)
 */
export function useStructuredDataState(
  docId: string | null,
): StructuredDataState {
  const { data, isLoading, error } = useStructuredData(docId);


  if (isLoading) {
    return createInitialStructuredDataState();
  }

  if (error) {
    const apiError = error as Partial<ApiError>;

    // 404: для этого документа нет структурированных данных
    if (apiError.status === 404) {
      return createStructuredDataNotAvailableState();
    }

    const message = getErrorMessage(error);
    return createStructuredDataErrorState(message);
  }

  const structured = data as StructuredDataResult | undefined;
  if (!structured) {
    // Нет данных и нет ошибки — считаем, что данных нет (notAvailable)
    return createStructuredDataNotAvailableState();
  }

  return createStructuredDataSuccessState(structured);
}

// -------------------------------------------------------------
// Вспомогательные функции
// -------------------------------------------------------------

function getErrorMessage(error: unknown): string {
  const err = error as Partial<ApiError> & { message?: string };
  if (err.detail) return String(err.detail);
  if (err.message) return String(err.message);
  return "Ошибка при загрузке данных";
}

function adaptClassification(detail: DocumentDetail) {
  if (!detail.classification) return null;

  const c = detail.classification;
  return {
    doc_type: c.doc_type,
    classification_level: c.classification_level,
    classification_confidence: c.classification_confidence,
    applicable_triggers: c.applicable_triggers ?? [],
    yaml_instruction_available: c.yaml_instruction_available,
    low_confidence: c.low_confidence,
  };
}
