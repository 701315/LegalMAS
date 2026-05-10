// =============================================================
// src/components/grid/reviewListGrid.types.ts
// Shared row types for the review list grid.
//
// This file defines the flat row model used by DDReviewListGrid.
// One list row represents one review cell / one check result
// extracted from the normalized review matrix.
//
// Why this exists:
// - DDMatrixGrid renders review data as a 2D matrix.
// - DDReviewListGrid renders the same data as a flat findings list.
// - A dedicated flat row type keeps AG Grid column definitions clean,
//   strongly typed, and easy to evolve.
//
// Production notes:
// - rowId must remain stable and unique for AG Grid getRowId.
// - matrixRowId preserves linkage to the original matrix row.
// - sourceRow/sourceColumn preserve domain provenance so the list view
//   can open the same details drawer and viewer navigation as matrix view.
// =============================================================

import type { SeverityLevel } from "../../types";
import type {
  ReviewGridRow,
  ReviewCheckColumn,
} from "../../pages/tabs/grid/reviewGrid.types";
import type { MatrixCellDTO } from "../../types/dealReview";

/**
 * Flat AG Grid row model for review findings list.
 *
 * One FindingListRow corresponds to one non-empty review cell
 * from the original matrix representation.
 */
export interface FindingListRow {
  /**
   * Stable unique row ID for AG Grid getRowId.
   * Format recommendation: `${matrixRowId}::${checkId}`
   */
  rowId: string;

  /**
   * Original matrix row identifier.
   * Useful for linking back to matrix view state if needed.
   */
  matrixRowId: string;

  documentId: string;
  documentName: string | null;

  checkId: string;
  checkName: string | null;

  origin: string | null;

  /**
   * Baseline severity from check metadata, not necessarily the final
   * interpreted cell severity.
   */
  baselineSeverity: SeverityLevel | string | null;

  docType: string | null;
  classificationLevel: string | null;
  classificationConfidence: number | null;

  segmentId: string | null;
  segmentTitle: string | null;
  segmentType: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;

  /**
   * Raw review cell payload used for rendering, tooltip formatting,
   * and opening the details drawer.
   */
  cell: MatrixCellDTO;

  /**
   * Original normalized review row from domain layer.
   * Preserved for shared details mapping and viewer navigation.
   */
  sourceRow: ReviewGridRow;

  /**
   * Original review check metadata for this finding.
   * Preserved for shared details mapping and list presentation.
   */
  sourceColumn: ReviewCheckColumn;
}



