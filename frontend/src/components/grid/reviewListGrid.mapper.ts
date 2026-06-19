// =============================================================
// src/components/grid/reviewListGrid.mapper.ts
// Review list row mapper.
//
// Transforms run-scoped review matrix data
// (document x check with nested cellsByCheckId)
// into a flat AG Grid row model where one row = one review finding.
//
// Why this file exists:
// - DDMatrixGrid renders a two-dimensional matrix.
// - DDReviewListGrid needs the same domain data in flat list form.
// - Keeping flattening logic here avoids duplicating normalization
//   in UI components and preserves a single source of truth.
//
// Production notes:
// - rowId is stable and suitable for AG Grid getRowId.
//   Format: `${matrixRowId}::${checkId}`
// - matrixRowId preserves linkage to the original matrix row.
// - sourceRow/sourceColumn/source cell provenance is preserved
//   so the list view can open the same details drawer as matrix view.
// - Default behaviour: all findings are included (pass, unclear, fail).
// - allowedCellKeys: when provided, only findings whose rowId is in the
//   set are included. This is the primary filtering mechanism so that
//   list mode respects the same quick-filters as matrix mode.
// - includePass: secondary gate, applied after allowedCellKeys.
//   Defaults to true.
// =============================================================

import type {
  ReviewGridRow,
  ReviewCheckColumn,
} from "../../pages/tabs/grid/reviewGrid.types";
import type { FindingListRow } from "./reviewListGrid.types";

export interface BuildReviewListRowsOptions {
  /**
   * When provided, only flat rows whose rowId is present in this set
   * will be included. The set should contain keys in the format
   * `${matrixRowId}::${checkId}` — matching FindingListRow.rowId.
   *
   * Use this to apply the same finding-level filters as matrix mode,
   * so that quick filters (critical, unclear, etc.) work correctly
   * in list mode.
   *
   * When omitted, all cells from the provided rows are included
   * (subject to includePass).
   */
  allowedCellKeys?: ReadonlySet<string>;

  /**
   * Whether rows with result === "pass" should be included.
   * Default: true.
   *
   * Set to false to show only non-pass findings.
   */
  includePass?: boolean;
}

/**
 * Builds flat list rows from normalized review matrix rows.
 *
 * Input:
 * - rows: normalized document-level review rows
 * - columns: normalized review check metadata
 *
 * Output:
 * - one flat row per visible review cell
 *
 * Filtering order:
 * 1. Skip cells with missing check metadata
 * 2. Skip cells not in allowedCellKeys (when provided)
 * 3. Skip pass cells when includePass === false
 */
export function buildReviewListRows(
  rows: ReviewGridRow[],
  columns: ReviewCheckColumn[],
  options: BuildReviewListRowsOptions = {},
): FindingListRow[] {
  const { includePass = true, allowedCellKeys } = options;

  const columnById = new Map<string, ReviewCheckColumn>(
    columns.map((col) => [col.checkId, col]),
  );

  return rows.flatMap((row) =>
    Object.entries(row.cellsByCheckId).flatMap(([checkId, cell]) => {
      if (!checkId || !cell) {
        return [];
      }

      const meta = columnById.get(checkId);
      if (!meta) {
        return [];
      }

      const flatRowId = `${row.rowId}::${checkId}`;

      // Gate 1: exact finding filter (applied by GridTabPage via filteredReviewFindings)
      if (allowedCellKeys !== undefined && !allowedCellKeys.has(flatRowId)) {
        return [];
      }

      // Gate 2: pass visibility toggle
      if (!includePass && cell.result === "pass") {
        return [];
      }

      return [
        {
          rowId: flatRowId,
          matrixRowId: row.rowId,

          documentId: row.documentId,
          documentName: row.documentName ?? null,

          checkId,
          checkName: meta.checkName ?? checkId,
          origin: meta.origin ?? null,
          baselineSeverity: meta.severity ?? null,

          docType: row.docType ?? null,
          classificationLevel: row.classificationLevel ?? null,
          classificationConfidence: row.classificationConfidence ?? null,

          segmentId: cell.segment_id ?? row.segmentId ?? null,
          segmentTitle: cell.segment_title ?? row.segmentTitle ?? null,
          segmentType: cell.segment_type ?? row.segmentType ?? null,
          segmentOrder: cell.segment_order ?? row.segmentOrder ?? null,
          isPrimarySegment: cell.is_primary_segment ?? row.isPrimarySegment ?? null,

          cell,
          sourceRow: row,
          sourceColumn: meta,
        },
      ];
    }),
  );
}


