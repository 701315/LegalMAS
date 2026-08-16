// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.qc.ts
// QC-помощники для DD Grid V1 (прямое чтение из drawer_contents).
//
// Backend контракт:
//   POST /api/v1/qc/review        — single finding QC update
//   POST /api/v1/qc/review/bulk   — bulk findings QC update
//
// В отличие от legacy reviewGrid.qc.ts:
// - читает QC статусы напрямую из DDGridV1DrawerDTO.qc_status
// - не использует адаптер или синтетические MatrixCellDTO
// - работает с segment-aware ключами (doc_id, segment_id, check_id)
// =============================================================

import type {
  ReviewFindingKey,
  ReviewQCBulkUpdateRequest,
} from "../../../api/qc";
import type { ReviewQcStatus } from "../../../types/dealReview";
import type {
  DDGridV1DerivedModel,
} from "./ddGridV1.types";
import type { ReviewSelectionItem } from "./ddGridV1.types";

/**
 * Причины, по которым текущая selection не может быть отправлена в QC.
 */
export type DDGridV1QcUnsupportedReason =
  | "empty_selection"
  | "no_drawers_in_selection"
  | "mixed_run_ids";

/**
 * Итог проверки возможности QC по текущей selection.
 */
export interface DDGridV1QcCapability {
  supported: boolean;
  reason: DDGridV1QcUnsupportedReason | null;
  message: string | null;
  selectedRowsCount: number;
  selectedFindingsCount: number;
}

/**
 * Один target QC-операции для V1.
 * Соответствует backend ReviewFindingKey + метаданные для UI.
 */
export interface DDGridV1QcTarget {
  findingId: string;
  rowId: string;

  runId: string;
  documentId: string;
  documentName: string;
  segmentId: string | null;

  checkId: string;
  checkName: string;

  currentQcStatus: string | null;
}

/**
 * Возвращает drawer contents для выбранных элементов selection.
 *
 * Поддерживает два режима:
 *
 * Matrix mode:
 *   ReviewSelectionItem содержит только rowId (=== documentId).
 *   Возвращаются ВСЕ drawers для этого документа.
 *
 * List mode:
 *   ReviewSelectionItem содержит rowId, matrixRowId и checkId.
 *   Возвращается только точный drawer с matching (documentId + checkId).
 *
 * Результат дедуплицирован по findingId.
 */
export function getSelectedV1Drawers(
  model: DDGridV1DerivedModel,
  selection: ReviewSelectionItem[],
): Array<{
  findingId: string;
  rowId: string;
  documentId: string;
  documentName: string;
  segmentId: string | null;
  checkId: string;
  checkName: string;
  qcStatus: string | null;
}> {
  if (!selection.length) {
    return [];
  }

  // Разбиваем selection на два типа:
  // exact — list mode (есть checkId)
  // coarse — matrix mode (только rowId = documentId)
  const exactKeys = new Set<string>();
  const coarseDocIds = new Set<string>();

  for (const item of selection) {
    if (item.matrixRowId && item.checkId) {
      // List mode: точный ключ documentId + checkId
      exactKeys.add(`${item.matrixRowId}::${item.checkId}`);
    } else {
      // Matrix mode: только documentId
      coarseDocIds.add(item.rowId);
    }
  }

  const seen = new Set<string>();
  const result: Array<{
    findingId: string;
    rowId: string;
    documentId: string;
    documentName: string;
    segmentId: string | null;
    checkId: string;
    checkName: string;
    qcStatus: string | null;
  }> = [];

  // Проходим по всем документам в модели
  for (const row of model.rows) {
    const docId = row.documentId;
    const docName = row.filename;
    // 3-уровневый lookup: segment_id из row
    const segmentId = row.segmentId ?? "_default";

    // Проверяем все checks для этого документа
    const perDocDrawers = model.drawerContents[docId] ?? {};
    const perSegmentDrawers = perDocDrawers[segmentId] ?? {};

    for (const [checkId, drawer] of Object.entries(perSegmentDrawers)) {
      const exactKey = `${docId}::${checkId}`;
      const matchedExact = exactKeys.has(exactKey);
      const matchedCoarse = coarseDocIds.has(docId);

      if ((matchedExact || matchedCoarse) && drawer) {
        const findingId = `v1:${docId}__${segmentId}__${checkId}`;

        if (!seen.has(findingId)) {
          seen.add(findingId);
          result.push({
            findingId,
            rowId: docId,
            documentId: docId,
            documentName: docName,
            segmentId,
            checkId,
            checkName: drawer.check_name,
            qcStatus: drawer.qc_status ?? null,
          });
        }
      }
    }
  }

  return result;
}

/**
 * Проверяет, можно ли текущую selection отправить в QC.
 */
export function getV1QcCapability(
  selection: ReviewSelectionItem[],
  selectedDrawers: ReturnType<typeof getSelectedV1Drawers>,
  runId: string | null | undefined,
): DDGridV1QcCapability {
  if (!selection.length) {
    return {
      supported: false,
      reason: "empty_selection",
      message: null,
      selectedRowsCount: 0,
      selectedFindingsCount: 0,
    };
  }

  if (!selectedDrawers.length) {
    return {
      supported: false,
      reason: "no_drawers_in_selection",
      message:
        "В выбранных строках нет проверок, к которым можно применить QC-действие.",
      selectedRowsCount: selection.length,
      selectedFindingsCount: 0,
    };
  }

  if (!runId) {
    return {
      supported: false,
      reason: "mixed_run_ids",
      message: "Не определён run для QC-действия.",
      selectedRowsCount: selection.length,
      selectedFindingsCount: selectedDrawers.length,
    };
  }

  return {
    supported: true,
    reason: null,
    message: null,
    selectedRowsCount: selection.length,
    selectedFindingsCount: selectedDrawers.length,
  };
}

/**
 * Сообщение-плейсхолдер для UI, когда QC недоступен.
 */
export function getV1QcDisabledNote(
  capability: DDGridV1QcCapability,
): string | null {
  if (capability.supported) return null;
  if (capability.reason === "empty_selection") return null;
  return capability.message;
}

/**
 * Собирает payload для POST /api/v1/qc/review/bulk.
 *
 * Использует segment-aware ключи для V1 контракта.
 */
export function buildV1QcBulkPayload(
  drawers: ReturnType<typeof getSelectedV1Drawers>,
  runId: string | null | undefined,
  qcStatus: ReviewQcStatus,
  comment?: string | null,
): ReviewQCBulkUpdateRequest | null {
  if (!runId || !drawers.length) return null;

  // Дедупликация по (run_id, document_id, check_id, segment_id)
  const seen = new Set<string>();
  const keys: ReviewFindingKey[] = [];

  for (const drawer of drawers) {
    const dedupKey = [
      runId,
      drawer.documentId,
      drawer.checkId,
      drawer.segmentId ?? "",
    ].join("|");

    if (!seen.has(dedupKey)) {
      seen.add(dedupKey);
      keys.push({
        run_id: runId,
        document_id: drawer.documentId,
        check_id: drawer.checkId,
        segment_id: drawer.segmentId,
      });
    }
  }

  if (!keys.length) return null;

  const normalizedComment =
    typeof comment === "string" && comment.trim().length > 0
      ? comment.trim()
      : null;

  return {
    findings: keys,
    qc_status: qcStatus,
    comment: normalizedComment,
  };
}
