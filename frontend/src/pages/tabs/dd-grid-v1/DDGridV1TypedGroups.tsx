// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1TypedGroups.tsx
// Orchestration-компонент для multi-table view DD Grid V1.
//
// Что делает:
// - читает checksScope и docGrouping из zustand store;
// - строит группы таблиц через pure helpers по комбинации параметров:
//
//   docGrouping = "by_type":
//     - buildDDGridV1TypedGroups()  — по одной таблице на doc_type
//   docGrouping = "all_docs":
//     - buildDDGridV1AllDocumentsGroup() — одна таблица со всеми
//
//   Затем накладываем фильтр checksScope на visibleCheckIds:
//     - "all"            → без фильтра
//     - "global_only"    → только globalCheckIds
//     - "doc_type_only"  → только docTypeCheckIds
//
// - пересекает эти группы с уже отфильтрованными legacy rows,
//   чтобы matrix view уважал текущие Filters;
// - агрегирует selection из нескольких DDGridV1Matrix,
//   не позволяя одной таблице затирать selection другой;
// - пробрасывает глобальное collapsed-state checks во все таблицы.
//
// i18n: все UI-строки локализованы через namespace "ddGrid".
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";

import type { OpenViewerAtFn } from "../../../types";

import type {
  DDGridV1MatrixRow,
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
} from "./ddGridV1.types";
import type { ReviewSelectionItem } from "./ddGridV1.types";
import {
  buildDDGridV1AllDocumentsGroup,
  buildDDGridV1TypedGroups,
  type DDGridV1DocTypeGroupView,
} from "./ddGridV1.docTypeGroups";
import {
  useDDGridV1UIStore,
  type DDGridV1ChecksScope,
  type DDGridV1DocGrouping,
} from "./ddGridV1.collapseStore";
import DDGridV1Matrix, {
  DD_GRID_V1_TOP_LEVEL_KEYS,
} from "./DDGridV1Matrix";

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------

interface RenderableGroup extends DDGridV1DocTypeGroupView {
  reviewRows: DDGridV1MatrixRow[];
}

/**
 * Строит базовые группы по параметру docGrouping.
 * Фильтрация по checksScope применяется отдельным шагом.
 */
function buildBaseGroups(
  model: DDGridV1DerivedModel,
  docGrouping: DDGridV1DocGrouping,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
): DDGridV1DocTypeGroupView[] {
  switch (docGrouping) {
    case "all_docs":
      return [buildDDGridV1AllDocumentsGroup(model, tFn)];
    case "by_type":
    default:
      return buildDDGridV1TypedGroups(model, tFn);
  }
}

/**
 * Применяет фильтр по checksScope: возвращает подмножество check_ids
 * из group.visibleCheckIds согласно выбранному режиму.
 */
function filterCheckIdsByScope(
  group: DDGridV1DocTypeGroupView,
  scope: DDGridV1ChecksScope,
): string[] {
  switch (scope) {
    case "global_only":
      return group.globalCheckIds;
    case "doc_type_only":
      return group.docTypeCheckIds;
    case "all":
    default:
      return group.visibleCheckIds;
  }
}

function buildReviewRowsByDocumentId(
  rows: DDGridV1MatrixRow[],
): Map<string, DDGridV1MatrixRow[]> {
  const map = new Map<string, DDGridV1MatrixRow[]>();

  for (const row of rows) {
    const arr = map.get(row.documentId);
    if (arr) {
      arr.push(row);
    } else {
      map.set(row.documentId, [row]);
    }
  }

  return map;
}

function estimateGroupMatrixHeightPx(rowsCount: number): number {
  const min = 320;
  const max = 560;
  const estimated = 180 + rowsCount * 52;
  return Math.max(min, Math.min(max, estimated));
}

function areSelectionItemsEqual(
  a: ReviewSelectionItem[],
  b: ReviewSelectionItem[],
): boolean {
  if (a.length !== b.length) return false;

  for (let i = 0; i < a.length; i += 1) {
    if (
      a[i].rowId !== b[i].rowId ||
      a[i].matrixRowId !== b[i].matrixRowId ||
      a[i].checkId !== b[i].checkId
    ) {
      return false;
    }
  }

  return true;
}

function areSelectionMapsEqual(
  a: Record<string, ReviewSelectionItem[]>,
  b: Record<string, ReviewSelectionItem[]>,
): boolean {
  const aKeys = Object.keys(a).sort();
  const bKeys = Object.keys(b).sort();

  if (aKeys.length !== bKeys.length) return false;

  for (let i = 0; i < aKeys.length; i += 1) {
    if (aKeys[i] !== bKeys[i]) return false;
    if (!areSelectionItemsEqual(a[aKeys[i]] ?? [], b[bKeys[i]] ?? [])) {
      return false;
    }
  }

  return true;
}

function pruneSelectionMap(
  prev: Record<string, ReviewSelectionItem[]>,
  groups: RenderableGroup[],
): Record<string, ReviewSelectionItem[]> {
  const next: Record<string, ReviewSelectionItem[]> = {};

  for (const group of groups) {
    const allowedRowIds = new Set(group.reviewRows.map((row) => row.rowId));
    const current = prev[group.groupKey] ?? [];
    const kept = current.filter((item) => allowedRowIds.has(item.rowId));

    if (kept.length > 0) {
      next[group.groupKey] = kept;
    }
  }

  return next;
}

function flattenSelectionMap(
  selectionByGroup: Record<string, ReviewSelectionItem[]>,
  groups: RenderableGroup[],
): ReviewSelectionItem[] {
  const out: ReviewSelectionItem[] = [];

  for (const group of groups) {
    const items = selectionByGroup[group.groupKey] ?? [];
    out.push(...items);
  }

  return out;
}

// -------------------------------------------------------------
// Props
// -------------------------------------------------------------

export interface DDGridV1TypedGroupsProps {
  runId: string;
  model: DDGridV1DerivedModel;
  rows: DDGridV1MatrixRow[];
  columns: DDGridV1CheckNode[];
  onOpenAtLocation?: OpenViewerAtFn;
  onSelectionChange?: (selection: ReviewSelectionItem[]) => void;
  clearSelectionToken?: number;
}

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGridV1TypedGroups: React.FC<DDGridV1TypedGroupsProps> = ({
  runId,
  model,
  rows,
  columns,
  onOpenAtLocation,
  onSelectionChange,
  clearSelectionToken,
}) => {
  const { t } = useTranslation("ddGrid");

  const checksScope = useDDGridV1UIStore((state) => state.checksScope);
  const docGrouping = useDDGridV1UIStore((state) => state.docGrouping);

  const collapsedCheckIdsRecord = useDDGridV1UIStore(
    (state) => state.collapsedCheckIds,
  );
  const collapsedGroupKeysRecord = useDDGridV1UIStore(
    (state) => state.collapsedGroupKeys,
  );
  const toggleCheckCollapsed = useDDGridV1UIStore(
    (state) => state.toggleCheckCollapsed,
  );
  const toggleGroupCollapsed = useDDGridV1UIStore(
    (state) => state.toggleGroupCollapsed,
  );

  const collapsedCheckIds = React.useMemo(
    () => new Set(Object.keys(collapsedCheckIdsRecord)),
    [collapsedCheckIdsRecord],
  );

  const collapsedGroupKeys = React.useMemo(
    () => new Set(Object.keys(collapsedGroupKeysRecord)),
    [collapsedGroupKeysRecord],
  );

  // Референс на top-level keys оставляем для будущего toolbar;
  // сейчас не используется, но нужен для типизации.
  void DD_GRID_V1_TOP_LEVEL_KEYS;

  const reviewRowsByDocumentId = React.useMemo(
    () => buildReviewRowsByDocumentId(rows),
    [rows],
  );

  const baseGroups = React.useMemo(
    () => buildBaseGroups(model, docGrouping, t),
    [model, docGrouping, t],
  );

  const renderGroups = React.useMemo<RenderableGroup[]>(() => {
    return baseGroups
      .map<RenderableGroup>((group) => {
        const reviewRows = group.rows.flatMap(
          (v1Row) => reviewRowsByDocumentId.get(v1Row.documentId) ?? [],
        );

        // Применяем фильтр checksScope
        const filteredVisibleCheckIds = filterCheckIdsByScope(
          group,
          checksScope,
        );

        return {
          ...group,
          visibleCheckIds: filteredVisibleCheckIds,
          reviewRows,
        };
      })
      // Убираем пустые группы:
      // - без строк
      // - без видимых check_ids (например, doc_type_only + группа без doc-type checks)
      .filter(
        (group) =>
          group.reviewRows.length > 0 && group.visibleCheckIds.length > 0,
      );
  }, [baseGroups, checksScope, reviewRowsByDocumentId]);

  const [selectionByGroup, setSelectionByGroup] = React.useState<
    Record<string, ReviewSelectionItem[]>
  >({});

  // При смене режимов checksScope/docGrouping сбрасываем selection
  const didInitRef = React.useRef(false);
  React.useEffect(() => {
    if (!didInitRef.current) {
      didInitRef.current = true;
      return;
    }
    setSelectionByGroup({});
  }, [checksScope, docGrouping]);

  const lastClearTokenRef = React.useRef<number | undefined>(clearSelectionToken);
  React.useEffect(() => {
    if (clearSelectionToken === lastClearTokenRef.current) return;
    lastClearTokenRef.current = clearSelectionToken;
    setSelectionByGroup({});
  }, [clearSelectionToken]);

  // Пруним selection при изменении rows/групп
  React.useEffect(() => {
    setSelectionByGroup((prev) => {
      const next = pruneSelectionMap(prev, renderGroups);
      return areSelectionMapsEqual(prev, next) ? prev : next;
    });
  }, [renderGroups]);

  // Наружу — агрегированное selection
  React.useEffect(() => {
    if (!onSelectionChange) return;
    onSelectionChange(flattenSelectionMap(selectionByGroup, renderGroups));
  }, [selectionByGroup, renderGroups, onSelectionChange]);

  const handleGroupSelectionChange = React.useCallback(
    (groupKey: string, selection: ReviewSelectionItem[]) => {
      setSelectionByGroup((prev) => {
        const next = { ...prev };
        if (selection.length > 0) {
          next[groupKey] = selection;
        } else {
          delete next[groupKey];
        }
        return areSelectionMapsEqual(prev, next) ? prev : next;
      });
    },
    [],
  );

  if (!renderGroups.length) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center text-sm text-[var(--text-secondary)] shadow-sm">
        {t("emptyState")}
      </div>
    );
  }

  const modeKey = `${docGrouping}:${checksScope}`;

  if (renderGroups.length === 1) {
    const group = renderGroups[0];

    return (
      <div className="h-full min-h-0">
        <DDGridV1Matrix
          key={`${modeKey}:${group.groupKey}`}
          runId={runId}
          model={model}
          title={group.title}
          rows={group.reviewRows}
          columns={columns}
          visibleCheckIds={group.visibleCheckIds}
          collapsedCheckIds={collapsedCheckIds}
          onToggleCollapseCheck={toggleCheckCollapsed}
          collapsedGroupKeys={collapsedGroupKeys}
          onToggleCollapseGroup={toggleGroupCollapsed}
          onOpenAtLocation={onOpenAtLocation}
          onSelectionChange={(selection) =>
            handleGroupSelectionChange(group.groupKey, selection)
          }
          clearSelectionToken={clearSelectionToken}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto pr-1">
      {renderGroups.map((group) => (
        <div
          key={`${modeKey}:${group.groupKey}`}
          className="min-h-0 shrink-0"
          style={{ height: estimateGroupMatrixHeightPx(group.reviewRows.length) }}
        >
          <DDGridV1Matrix
            runId={runId}
            model={model}
            title={group.title}
            rows={group.reviewRows}
            columns={columns}
            visibleCheckIds={group.visibleCheckIds}
            collapsedCheckIds={collapsedCheckIds}
            onToggleCollapseCheck={toggleCheckCollapsed}
            collapsedGroupKeys={collapsedGroupKeys}
            onToggleCollapseGroup={toggleGroupCollapsed}
            onOpenAtLocation={onOpenAtLocation}
            onSelectionChange={(selection) =>
              handleGroupSelectionChange(group.groupKey, selection)
            }
            clearSelectionToken={clearSelectionToken}
          />
        </div>
      ))}
    </div>
  );
};

export default DDGridV1TypedGroups;


