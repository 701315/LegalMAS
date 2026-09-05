// =============================================================
// src/api/documents.stateHooks.ts
// Wrapper hooks around DTO queries:
// - useDocumentDetailsState
// - useStructuredDataState
//
// These wrap existing data queries without breaking contracts,
// producing normalized domain state models.
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
 * Hook for retrieving the normalized state of document details.
 *
 * Utilizes useDocumentDetail (DTO) internally and adds:
 * - isLoading
 * - error (as string)
 * - notFound (true on 404 or missing payload)
 */
export function useDocumentDetailsState(
  docId: string | null,
): DocumentDetailsState {
  const { data, isLoading, error } = useDocumentDetail(docId);

  if (isLoading) {
    return createInitialDocumentDetailsState();
  }

  if (error) {
    const apiError = error as Partial<ApiError>;

    // 404: document not found
    if (apiError.status === 404) {
      return createDocumentDetailsNotFoundState();
    }

    // Other errors: server/network etc.
    const message = getErrorMessage(error);
    return createDocumentDetailsErrorState(message);
  }

  const detail = data as DocumentDetail | undefined;
  if (!detail) {
    return createDocumentDetailsNotFoundState();
  }

  const classification = adaptClassification(detail);
  const family = null; // family is loaded by a dedicated hook in the container

  return createDocumentDetailsSuccessState({
    doc: detail.document,
    classification,
    family,
  });
}

/**
 * Hook for normalized structured data state.
 *
 * Utilizes useStructuredData (DTO) internally and adds:
 * - isLoading
 * - error
 * - notAvailable (true on 404 or missing payload)
 */
export function useStructuredDataState(
  docId: string | null,
): StructuredDataState {
  const { data, isLoading, error } = useStructuredData(docId);

  if (isLoading) {
    return createInitialStructuredDataState();
  }

  if (error) {
    const apiError = error as Partial<ApiError> & { detail?: unknown };

    // 404: no structured data available for this document
    if (apiError.status === 404) {
      const detail = apiError.detail;

      const code =
        detail && typeof detail === "object"
          ? (detail as { code?: string }).code
          : undefined;

      if (
        code === "STRUCTURED_NOT_READY" ||
        code === "STRUCTURED_MISSING" ||
        code === undefined
      ) {
        return createStructuredDataNotAvailableState();
      }

      return createStructuredDataNotAvailableState();
    }

    const message = getErrorMessage(error);
    return createStructuredDataErrorState(message);
  }

  const structured = data as StructuredDataResult | undefined;
  if (!structured) {
    return createStructuredDataNotAvailableState();
  }

  return createStructuredDataSuccessState(structured);
}

// -------------------------------------------------------------
// Helper functions
// -------------------------------------------------------------

function getErrorMessage(error: unknown): string {
  const err = error as Partial<ApiError> & { message?: string };
  if (err.detail) return String(err.detail);
  if (err.message) return String(err.message);
  return "Failed to load data.";
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



