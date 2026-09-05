// =============================================================
// src/api/documents.state.ts
// Normalized state objects for document data.
//
// These types and factories are utilized by adapters and containers
// to ensure the UI correctly understands the current state of documents:
// - loading in progress
// - document found / not found
// - structured data available / missing
// - error occurred
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
 * Normalized state for the right-hand document details panel.
 *
 * Invariants:
 * - When isLoading === true, other flags (notFound, error) must be false/null
 * - When notFound === true, doc === null and error === null
 * - When error !== null, notFound === false
 */
export interface DocumentDetailsState {
  // Main data for the view
  doc: Document | null;
  classification: DocumentDetailsViewClassification | null;
  family: DocumentFamilyView | null;

  // Technical flags
  isLoading: boolean;
  notFound: boolean;      // 404 on /documents/{id}
  error: string | null;   // network/server issues and other errors

  // Result of the last reclassification (if needed in the view)
  lastReclassifyResult?: ReclassifyResult;
}

/**
 * Initial state: nothing is loaded yet, loading is in progress.
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
 * Success state: document was found and data retrieved.
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
 * "Document not found" state (404).
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
 * "Load error" state (500, network issues, etc.).
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
 * Helper to set the reclassification result on top of the existing state.
 * Usually invoked by the container after a successful mutation.
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
 * Normalized state for the document structured data block.
 *
 * Invariants:
 * - When isLoading === true, other flags (notAvailable, error) must be false/null
 * - When notAvailable === true, items === [] and error === null
 * - When error !== null, notAvailable === false
 */
export interface StructuredDataState {
  // Main data
  items: StructuredDataView["extracted_values"];
  total: number;

  // Technical flags
  isLoading: boolean;
  notAvailable: boolean;  // 404 on /structured-data => no structured data exists for this document
  error: string | null;
}

/**
 * Initial state for structured data.
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
 * Success state: structured data retrieved.
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
 * "Data not available" state (404).
 * This is not treated as a network error, but as a normal state:
 * there is simply no structured data extracted for this document.
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
 * "Load error" state (500, network issues, etc.).
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


