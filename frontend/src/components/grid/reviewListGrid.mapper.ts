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
// - sourceRow/sourceColumn/source cell provenance is preserved
//   so the list view can open the same details drawer as matrix view.
// - includePass allows the caller to choose between:
//   * full audit list
//   * findings-only list (recommended default for review UX)
// =============================================================

import type {
  ReviewGridRow,
  ReviewCheckColumn,
} from "../../pages/tabs/grid/reviewGrid.types";
import type { FindingListRow } from "./reviewListGrid.types";

export interface BuildReviewListRowsOptions {
  /**
   * Whether rows with result === "pass" should be included.
   * Default: true.
   *
   * Use includePass: false for a cleaner findings-focused review list.
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
 * - one flat row per existing review cell
 *
 * Behavior:
 * - skips empty cells
 * - skips cells whose check metadata is missing
 * - optionally skips pass results
 */
export function buildReviewListRows(
  rows: ReviewGridRow[],
  columns: ReviewCheckColumn[],
  options: BuildReviewListRowsOptions = {},
): FindingListRow[] {
  const { includePass = true } = options;

  const columnById = new Map<string, ReviewCheckColumn>(
    columns.map((col) => [col.checkId, col]),
  );

  return rows.flatMap((row) =>
    Object.entries(row.cellsByCheckId).flatMap(([checkId, cell]) => {
      if (!checkId || !cell) {
        return [];
      }

      if (!includePass && cell.result === "pass") {
        return [];
      }

      const meta = columnById.get(checkId);
      if (!meta) {
        return [];
      }

      return [
        {
          rowId: `${row.rowId}::${checkId}`,
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


