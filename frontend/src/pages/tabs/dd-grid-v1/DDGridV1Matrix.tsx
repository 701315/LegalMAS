// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1Matrix.tsx
// V1-specific матрица DD Grid.
//
// Иерархия column groups (сверху вниз):
//
//   TOP-LEVEL SCOPE
//     "Глобальные проверки"     (top:global)
//       SCOPE GROUP             (global:<groupId>, например "CONFIDENTIALITY")
//         CHECK GROUP           (check|<checkNodeKey>)
//           runtime columns / summary column
//     "Проверки по типу"        (top:docType)
//       SCOPE GROUP             (docType:<classId>:<typeCode>)
//         CHECK GROUP
//           runtime columns / summary column
//
// Иконки collapse:
// - "+"  когда элемент свёрнут
// - "-"  когда элемент раскрыт
//
// Правила collapse:
// - Q16 = A: групповой collapse НЕ трогает индивидуальное состояние check-ов;
// - Q17 = C: collapsed group / top-level полностью скрывает свои дочерние
//   колонки — от группы остаётся только header с "+", клик разворачивает;
// - Q18 = A: состояние групп персистится в store симметрично checks.
//
// Правила общего характера:
// - никаких хардкодов check_id / column_id / doc_type;
// - для runtime columns source of truth — V1 model/runtimeKey;
// - для details drawer source of truth — legacy-adapted MatrixCellDTO
//   из ReviewGridRow.cellsByCheckId[checkId];
// - для instruction snapshot source of truth — DDGridV1MatrixRow.instructionSnapshot
//   (per doc_type, приходит батчем в DDGridV1ResponseDTO, без отдельного fetch).
// =============================================================


import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Minus, Plus } from "lucide-react";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  ColGroupDef,
  GridApi,
  GridReadyEvent,
  ICellRendererParams,
  SelectionChangedEvent,
  ValueFormatterParams,
  ValueGetterParams,
} from "ag-grid-community";


import type { OpenViewerAtFn } from "../../../types";
import type {
  DDGridV1CellState,
  DDGridV1DrawerContentDTO,
  DDGridV1InstructionSnapshotDTO,
  MatrixCellDTO,
  ReviewQcStatus,
} from "../../../types/dealReview";


import DDGridV1Drawer from "./DDGridV1Drawer";
import DDGridV1InstructionDrawer from "./DDGridV1InstructionDrawer";


import type {
  ReviewGridRow,
  ReviewCheckColumn,
  ReviewSelectionItem,
} from "../grid/reviewGrid.types";


import type {
  DDGridV1CellView,
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
  DDGridV1RuntimeColumn,
} from "./ddGridV1.types";
import { resolveDDGridV1CellView } from "./ddGridV1.selectors";
import { useDDGridV1UIStore } from "./ddGridV1.collapseStore";


import "ag-grid-community/styles/ag-grid.css";
import "../../../styles/ag-theme-legalmas.css";


// -------------------------------------------------------------
// Public constants
// -------------------------------------------------------------


/**
 * Стабильные ключи top-level scope buckets.
 * Экспортируются, чтобы другие компоненты (например, будущий toolbar
 * "Свернуть все глобальные") могли переиспользовать одни и те же ключи.
 */
export const DD_GRID_V1_TOP_LEVEL_KEYS = {
  global: "top:global",
  docType: "top:docType",
} as const;


// -------------------------------------------------------------
// Internal constants
// -------------------------------------------------------------


const MATRIX_MIN_HEIGHT_PX = 240;
const MATRIX_MIN_WIDTH_PX = 1200;
const RUNTIME_COLUMN_MIN_WIDTH_PX = 220;


const NO_COLLAPSED_KEYS: ReadonlySet<string> = new Set<string>();


// -------------------------------------------------------------
// Row model
// -------------------------------------------------------------


type V1MatrixGridRow = ReviewGridRow & {
  [key: `check_${string}`]: MatrixCellDTO | undefined;
};


function toV1MatrixGridRow(row: ReviewGridRow): V1MatrixGridRow {
  const checkCells = Object.entries(row.cellsByCheckId).reduce<
    Record<`check_${string}`, MatrixCellDTO | undefined>
  >((acc, [checkId, cell]) => {
    acc[`check_${checkId}`] = cell;
    return acc;
  }, {} as Record<`check_${string}`, MatrixCellDTO | undefined>);


  return {
    ...row,
    ...checkCells,
  };
}


// -------------------------------------------------------------
// Column-group planning
// -------------------------------------------------------------


interface V1ScopeGroupPlan {
  groupKey: string;
  groupLabel: string;
  scope: "global" | "docType";
  checks: DDGridV1CheckNode[];
}


interface V1TopLevelPlan {
  topKey: string;
  topLabel: string;
  scope: "global" | "docType";
  groups: V1ScopeGroupPlan[];
}


/**
 * Строит top-level buckets:
 *   "Глобальные проверки"      (global groups внутри)
 *   "Проверки по типу"         (doc-type groups внутри)
 *
 * Учитывает visibleCheckIds и удаляет пустые группы.
 */
function planV1TopLevelBuckets(
  model: DDGridV1DerivedModel,
  visibleCheckIds?: readonly string[],
): V1TopLevelPlan[] {
  const visibleSet = visibleCheckIds ? new Set(visibleCheckIds) : null;
  const seenCheckIds = new Set<string>();


  const globalGroups: V1ScopeGroupPlan[] = [];
  for (const group of model.globalGroups) {
    const plan: V1ScopeGroupPlan = {
      groupKey: `global:${group.groupId}`,
      groupLabel: group.label,
      scope: "global",
      checks: [],
    };


    for (const check of group.checks) {
      if (visibleSet && !visibleSet.has(check.checkId)) continue;
      if (seenCheckIds.has(check.checkId)) continue;
      seenCheckIds.add(check.checkId);
      plan.checks.push(check);
    }


    if (plan.checks.length > 0) {
      globalGroups.push(plan);
    }
  }


  const docTypeGroups: V1ScopeGroupPlan[] = [];
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      const plan: V1ScopeGroupPlan = {
        groupKey: `docType:${cls.groupId}:${t.typeCode}`,
        groupLabel: `${cls.label} · ${t.name}`,
        scope: "docType",
        checks: [],
      };


      for (const check of t.checks) {
        if (visibleSet && !visibleSet.has(check.checkId)) continue;
        if (seenCheckIds.has(check.checkId)) continue;
        seenCheckIds.add(check.checkId);
        plan.checks.push(check);
      }


      if (plan.checks.length > 0) {
        docTypeGroups.push(plan);
      }
    }
  }


  const buckets: V1TopLevelPlan[] = [];


  if (globalGroups.length > 0) {
    buckets.push({
      topKey: DD_GRID_V1_TOP_LEVEL_KEYS.global,
      topLabel: "Глобальные проверки",
      scope: "global",
      groups: globalGroups,
    });
  }


  if (docTypeGroups.length > 0) {
    buckets.push({
      topKey: DD_GRID_V1_TOP_LEVEL_KEYS.docType,
      topLabel: "Проверки по типу документа",
      scope: "docType",
      groups: docTypeGroups,
    });
  }


  return buckets;
}


// -------------------------------------------------------------
// Sorting helpers
// -------------------------------------------------------------


function compareDisplayText(a: string, b: string): number {
  return a.localeCompare(b, "ru", {
    numeric: true,
    sensitivity: "base",
  });
}


function cellStateSortRank(state: DDGridV1CellState | null | undefined): number {
  switch (state) {
    case "defined":
      return 0;
    case "not_defined":
      return 1;
    case "not_executed":
      return 2;
    case "not_applicable":
      return 3;
    case "error":
      return 4;
    default:
      return 5;
  }
}


function compareRuntimeCellViews(
  a: DDGridV1CellView | null,
  b: DDGridV1CellView | null,
): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;


  const rankDiff =
    cellStateSortRank(a.cellState) - cellStateSortRank(b.cellState);
  if (rankDiff !== 0) return rankDiff;


  return compareDisplayText(a.displayText, b.displayText);
}


// -------------------------------------------------------------
// Cell state -> visual tone
// -------------------------------------------------------------


function cellStateToneClass(state: DDGridV1CellState): string {
  switch (state) {
    case "defined":
      return "text-[var(--text-primary)]";
    case "not_applicable":
      return "text-[var(--text-muted)] italic";
    case "error":
      return "text-[var(--color-error)]";
    case "not_defined":
    case "not_executed":
    default:
      return "text-[var(--text-muted)]";
  }
}


// -------------------------------------------------------------
// Selection
// -------------------------------------------------------------


function buildSelectionItems(
  event: SelectionChangedEvent<V1MatrixGridRow>,
): ReviewSelectionItem[] {
  return event.api
    .getSelectedNodes()
    .flatMap((node) => {
      const data = node.data;
      if (!data?.rowId) return [];
      return [{ rowId: data.rowId }];
    });
}


// -------------------------------------------------------------
// Props
// -------------------------------------------------------------


export interface DDGridV1MatrixProps {
  runId: string;
  model: DDGridV1DerivedModel;
  rows: ReviewGridRow[];
  columns: ReviewCheckColumn[];


  /** Optional title для локальной таблицы (например, конкретного doc_type). */
  title?: string;


  /**
   * Optional whitelist check-ов, которые должны быть показаны в этой таблице.
   * Если не задан — показываем все check-ids, доступные в модели.
   */
  visibleCheckIds?: readonly string[];


  /**
   * Глобальное множество свернутых check-ов.
   */
  collapsedCheckIds?: ReadonlySet<string>;
  onToggleCollapseCheck?: (checkId: string) => void;


  /**
   * Глобальное множество свернутых group keys.
   * Сюда попадают top-level ключи (DD_GRID_V1_TOP_LEVEL_KEYS.*) и
   * scope group ключи ("global:<groupId>", "docType:<classId>:<typeCode>").
   */
  collapsedGroupKeys?: ReadonlySet<string>;
  onToggleCollapseGroup?: (groupKey: string) => void;


  onOpenAtLocation?: OpenViewerAtFn;
  onSelectionChange?: (selection: ReviewSelectionItem[]) => void;
  clearSelectionToken?: number;
}


interface SelectedCellState {
  open: boolean;
  rowId: string | null;
  documentId: string | null;
  documentName: string | null;
  checkId: string | null;
  drawerContent: DDGridV1DrawerContentDTO | null;
  currentQcStatus: ReviewQcStatus | null;
  currentQcComment: string | null;
}


interface SelectedInstructionState {
  open: boolean;
  documentName: string | null;
  snapshot: DDGridV1InstructionSnapshotDTO | null;
}


// -------------------------------------------------------------
// Shared header components
// -------------------------------------------------------------


type GroupCollapseButtonProps = {
  collapsed: boolean;
  onClick: () => void;
  title?: string;
  variant?: "default" | "strong";
};


const GroupCollapseButton: React.FC<GroupCollapseButtonProps> = ({
  collapsed,
  onClick,
  title,
  variant = "default",
}) => {
  const sizeClass =
    variant === "strong"
      ? "h-5 w-5"
      : "h-5 w-5";
  const iconSizeClass = variant === "strong" ? "h-3.5 w-3.5" : "h-3.5 w-3.5";


  return (
    <button
      type="button"
      className={`inline-flex ${sizeClass} shrink-0 items-center justify-center rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-muted)] hover:text-[var(--text-primary)]`}
      title={title}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      }}
    >
      {collapsed ? (
        <Plus className={iconSizeClass} aria-hidden />
      ) : (
        <Minus className={iconSizeClass} aria-hidden />
      )}
    </button>
  );
};


// Top-level scope header (например, "Глобальные проверки")
type V1TopLevelHeaderGroupProps = {
  displayName?: string;
  topKey?: string;
  collapsed?: boolean;
  onToggleCollapseGroup?: (groupKey: string) => void;
};


const V1TopLevelHeaderGroup: React.FC<V1TopLevelHeaderGroupProps> = ({
  displayName,
  topKey,
  collapsed = false,
  onToggleCollapseGroup,
}) => {
  const canToggle =
    typeof topKey === "string" &&
    topKey.length > 0 &&
    typeof onToggleCollapseGroup === "function";


  return (
    <div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">
      <span
        className="truncate text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-primary)]"
        title={displayName || ""}
      >
        {displayName || "—"}
      </span>


      {canToggle ? (
        <GroupCollapseButton
          collapsed={collapsed}
          onClick={() => onToggleCollapseGroup?.(topKey!)}
          title={
            collapsed
              ? "Развернуть блок проверок"
              : "Свернуть блок проверок"
          }
          variant="strong"
        />
      ) : null}
    </div>
  );
};


// Scope group header (например, "CONFIDENTIALITY")
type V1ScopeHeaderGroupProps = {
  displayName?: string;
  groupKey?: string;
  collapsed?: boolean;
  onToggleCollapseGroup?: (groupKey: string) => void;
};


const V1ScopeHeaderGroup: React.FC<V1ScopeHeaderGroupProps> = ({
  displayName,
  groupKey,
  collapsed = false,
  onToggleCollapseGroup,
}) => {
  const canToggle =
    typeof groupKey === "string" &&
    groupKey.length > 0 &&
    typeof onToggleCollapseGroup === "function";


  return (
    <div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">
      <span
        className="truncate text-[11px] font-semibold text-[var(--text-primary)]"
        title={displayName || ""}
      >
        {displayName || "—"}
      </span>


      {canToggle ? (
        <GroupCollapseButton
          collapsed={collapsed}
          onClick={() => onToggleCollapseGroup?.(groupKey!)}
          title={
            collapsed
              ? "Развернуть группу проверок"
              : "Свернуть группу проверок"
          }
        />
      ) : null}
    </div>
  );
};


// Check header (например, "Конфиденциальность и коммерческая тайна")
type V1CheckHeaderGroupProps = {
  displayName?: string;
  checkId?: string;
  collapsed?: boolean;
  onToggleCollapseCheck?: (checkId: string) => void;
};


const V1CheckHeaderGroup: React.FC<V1CheckHeaderGroupProps> = ({
  displayName,
  checkId,
  collapsed = false,
  onToggleCollapseCheck,
}) => {
  const canToggle =
    typeof checkId === "string" &&
    checkId.length > 0 &&
    typeof onToggleCollapseCheck === "function";


  return (
    <div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">
      <span
        className="truncate text-[11px] font-semibold text-[var(--text-primary)]"
        title={displayName || ""}
      >
        {displayName || "—"}
      </span>


      {canToggle ? (
        <GroupCollapseButton
          collapsed={collapsed}
          onClick={() => onToggleCollapseCheck?.(checkId!)}
          title={
            collapsed
              ? "Развернуть параметры проверки"
              : "Свернуть параметры проверки"
          }
        />
      ) : null}
    </div>
  );
};


// Header для свёрнутой колонки (показывает название и кнопку "+")
type V1CollapsedHeaderProps = {
  displayName?: string;
  onExpand?: () => void;
  uppercase?: boolean;
};


const V1CollapsedHeader: React.FC<V1CollapsedHeaderProps> = ({
  displayName,
  onExpand,
  uppercase = false,
}) => {
  return (
    <div className="flex h-full min-w-0 items-center justify-between gap-2 px-2">
      <span
        className={`truncate text-[11px] font-semibold text-[var(--text-primary)] ${uppercase ? "uppercase tracking-[0.06em]" : ""}`}
        title={displayName || ""}
      >
        {displayName || "—"}
      </span>


      {onExpand ? (
        <button
          type="button"
          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          title="Развернуть"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onExpand();
          }}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
        </button>
      ) : null}
    </div>
  );
};


// -------------------------------------------------------------
// Cell tooltip / export formatting
// -------------------------------------------------------------


function buildRuntimeCellTooltip(
  checkName: string,
  label: string,
  cellView: DDGridV1CellView | null,
): string {
  if (!cellView) return checkName;
  return [checkName, `${label}: ${cellView.displayText}`].join("\n");
}


function formatRuntimeCellForExport(cellView: DDGridV1CellView | null): string {
  if (!cellView) return "";
  return cellView.displayText;
}


// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------


export const DDGridV1Matrix: React.FC<DDGridV1MatrixProps> = ({
  runId,
  model,
  rows,
  columns,
  title,
  visibleCheckIds,
  collapsedCheckIds,
  onToggleCollapseCheck,
  collapsedGroupKeys,
  onToggleCollapseGroup,
  onOpenAtLocation,
  onSelectionChange,
  clearSelectionToken,
}) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rootWidth, setRootWidth] = useState<number>(0);
  const [gridApi, setGridApi] = useState<GridApi<V1MatrixGridRow> | null>(null);


  const [selectedCell, setSelectedCell] = useState<SelectedCellState>({
    open: false,
    rowId: null,
    documentId: null,
    documentName: null,
    checkId: null,
    drawerContent: null,
    currentQcStatus: null,
    currentQcComment: null,
  });


  // Instruction snapshot drawer state.
  // Отдельный state от selectedCell: разная семантика (per doc_type,
  // не per check), разный drawer-компонент, разные данные (уже в модели,
  // без обращения к drawerContents).
  const [selectedInstruction, setSelectedInstruction] =
    useState<SelectedInstructionState>({
      open: false,
      documentName: null,
      snapshot: null,
    });


  const rowData = useMemo<V1MatrixGridRow[]>(
    () => rows.map(toV1MatrixGridRow),
    [rows],
  );

  const topLevelPlans = useMemo(
    () => planV1TopLevelBuckets(model, visibleCheckIds),
    [model, visibleCheckIds],
  );


  const visibleChecksCount = useMemo(
    () =>
      topLevelPlans.reduce(
        (acc, top) =>
          acc + top.groups.reduce((a, g) => a + g.checks.length, 0),
        0,
      ),
    [topLevelPlans],
  );


  const collapsedCheckSet = collapsedCheckIds ?? NO_COLLAPSED_KEYS;
  const collapsedGroupSet = collapsedGroupKeys ?? NO_COLLAPSED_KEYS;


  const columnLookup = useMemo(() => {
    const map = new Map<string, ReviewCheckColumn>();
    for (const c of columns) map.set(c.checkId, c);
    return map;
  }, [columns]);


  useEffect(() => {
    const node = rootRef.current;
    if (!node) return;


    const update = () => {
      setRootWidth(Math.round(node.getBoundingClientRect().width));
    };


    update();


    const ro = new ResizeObserver(() => update());
    ro.observe(node);
    const raf = requestAnimationFrame(update);


    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);


  // Глобальное состояние для синхронизации drawer'ов между таблицами
  const activeDrawerMatrixTitle = useDDGridV1UIStore(
    (state) => state.activeDrawerMatrixTitle
  );
  const setActiveDrawerMatrixTitle = useDDGridV1UIStore(
    (state) => state.setActiveDrawerMatrixTitle
  );
  const currentMatrixTitle = title ?? "default_matrix";

  // Эта таблица показывает drawer ТОЛЬКО если она им владеет
  const isThisMatrixActive = activeDrawerMatrixTitle === currentMatrixTitle;

  const isCellDrawerOpen =
    selectedCell.open && selectedCell.drawerContent !== null && isThisMatrixActive;
  const isInstructionDrawerOpen = selectedInstruction.open && isThisMatrixActive;
  const isDrawerPanelOpen = isCellDrawerOpen || isInstructionDrawerOpen;

  // Если другая таблица открыла drawer, принудительно закрываем локальное состояние этой
  useEffect(() => {
    if (
      activeDrawerMatrixTitle !== null &&
      activeDrawerMatrixTitle !== currentMatrixTitle
    ) {
      if (selectedCell.open || selectedInstruction.open) {
        setSelectedCell({
          open: false,
          rowId: null,
          documentId: null,
          documentName: null,
          checkId: null,
          drawerContent: null,
          currentQcStatus: null,
          currentQcComment: null,
        });
        setSelectedInstruction({ open: false, documentName: null, snapshot: null });
      }
    }
  }, [activeDrawerMatrixTitle, currentMatrixTitle, selectedCell.open, selectedInstruction.open]);

  const closeDetails = useCallback(() => {
    setSelectedCell({
      open: false,
      rowId: null,
      documentId: null,
      documentName: null,
      checkId: null,
      drawerContent: null,
      currentQcStatus: null,
      currentQcComment: null,
    });
    // Освобождаем право на drawer, только если он принадлежал нам
    if (activeDrawerMatrixTitle === currentMatrixTitle) {
      setActiveDrawerMatrixTitle(null);
    }
  }, [activeDrawerMatrixTitle, currentMatrixTitle, setActiveDrawerMatrixTitle]);

  const openDetailsForCell = useCallback(
    (params: {
      row: ReviewGridRow;
      checkId: string;
      cell?: MatrixCellDTO;
    }) => {
      const drawerContent =
        model.drawerContents[params.row.documentId]?.[params.checkId] ?? null;

      if (!drawerContent) return;

      const legacyCell = params.cell;

      setSelectedInstruction({ open: false, documentName: null, snapshot: null });

      setSelectedCell({
        open: true,
        rowId: params.row.rowId,
        documentId: params.row.documentId,
        documentName: params.row.documentName ?? null,
        checkId: params.checkId,
        drawerContent,
        currentQcStatus: legacyCell?.qc_status ?? null,
        currentQcComment: legacyCell?.qc_comment ?? null,
      });

      // Захватываем право на drawer для этой таблицы
      setActiveDrawerMatrixTitle(currentMatrixTitle);
    },
    [model.drawerContents, currentMatrixTitle, setActiveDrawerMatrixTitle]
  );

  const closeInstructionDrawer = useCallback(() => {
    setSelectedInstruction({ open: false, documentName: null, snapshot: null });
    if (activeDrawerMatrixTitle === currentMatrixTitle) {
      setActiveDrawerMatrixTitle(null);
    }
  }, [activeDrawerMatrixTitle, currentMatrixTitle, setActiveDrawerMatrixTitle]);


  const getV1RowForReviewRow = useCallback(
    (row: ReviewGridRow | V1MatrixGridRow | null | undefined) => {
      if (!row) return null;
      return model.rowsByDocumentId[row.documentId] ?? null;
    },
    [model.rowsByDocumentId],
  );


  const openInstructionDrawerForRow = useCallback(
    (row: V1MatrixGridRow | null | undefined) => {
      if (!row) return;
      const v1Row = getV1RowForReviewRow(row);

      setSelectedCell({
        open: false,
        rowId: null,
        documentId: null,
        documentName: null,
        checkId: null,
        drawerContent: null,
        currentQcStatus: null,
        currentQcComment: null,
      });

      setSelectedInstruction({
        open: true,
        documentName: row.documentName ?? null,
        snapshot: v1Row?.instructionSnapshot ?? null,
      });

      // Захватываем право на drawer для этой таблицы
      setActiveDrawerMatrixTitle(currentMatrixTitle);
    },
    [getV1RowForReviewRow, currentMatrixTitle, setActiveDrawerMatrixTitle],
  );


  const defaultColDef = useMemo<ColDef<V1MatrixGridRow>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      suppressHeaderMenuButton: false,
      wrapHeaderText: true,
      autoHeaderHeight: true,
    }),
    [],
  );


  const rowSelection = useMemo(
    () => ({
      mode: "multiRow" as const,
      enableSelectionWithoutKeys: true,
      checkboxes: true,
      headerCheckbox: true,
      enableClickSelection: false,
    }),
    [],
  );


  // -----------------------------------------------------------
  // Base columns
  // -----------------------------------------------------------


  const baseColumns = useMemo<ColDef<V1MatrixGridRow>[]>(
    () => [
      {
        headerName: "#",
        width: 64,
        minWidth: 64,
        maxWidth: 64,
        pinned: "left",
        sortable: false,
        filter: false,
        resizable: false,
        headerTooltip: "Выберите строки для массового QC действия",
        valueGetter: (params: ValueGetterParams<V1MatrixGridRow>) =>
          params.node?.rowIndex != null ? params.node.rowIndex + 1 : "",
      },
      {
        headerName: "Документ",
        field: "documentName",
        width: 320,
        minWidth: 260,
        maxWidth: 400,
        pinned: "left",
        headerClass: "ag-center-header",
        cellRenderer: (params: ICellRendererParams<V1MatrixGridRow>) => {
          const name = params.data?.documentName || "[no name]";
          return (
            <span className="text-xs text-[var(--text-primary)]">{name}</span>
          );
        },
      },
      {
        headerName: "Тип документа",
        field: "docType",
        width: 220,
        minWidth: 180,
        maxWidth: 260,
        pinned: "left",
        headerClass: "ag-center-header",
        valueFormatter: (
          params: ValueFormatterParams<V1MatrixGridRow>,
        ): string =>
          (params.value as string | null | undefined) || "—",
      },
      {
        headerName: "Инструкция",
        colId: "instructionSnapshot",
        minWidth: 130,
        maxWidth: 160,
        pinned: "left",
        sortable: false,
        filter: false,
        headerClass: "ag-center-header",
        valueGetter: (params: ValueGetterParams<V1MatrixGridRow>) => {
          const v1Row = getV1RowForReviewRow(params.data);
          return v1Row?.instructionSnapshot?.version_id ?? null;
        },
        tooltipValueGetter: (params) => {
          const v1Row = getV1RowForReviewRow(
            params.data as V1MatrixGridRow | undefined,
          );
          const snap = v1Row?.instructionSnapshot;
          if (!snap) return "Тип документа не классифицирован";
          return snap.is_persisted_snapshot
            ? `Зафиксированная версия инструкции: ${snap.version_id}`
            : "Legacy run: версия инструкции не зафиксирована (fallback на файловую систему)";
        },
        cellRenderer: (params: ICellRendererParams<V1MatrixGridRow>) => {
          const row = params.data;
          const v1Row = getV1RowForReviewRow(row);
          const snap = v1Row?.instructionSnapshot;
          if (!snap) {
            return (
              <span className="text-xs text-[var(--text-faint)]">—</span>
            );
          }
          const linkTone = snap.is_persisted_snapshot
            ? "text-[var(--accent-primary)] hover:text-[var(--accent-primary-hover)]"
            : "text-amber-700 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-300";
          return (
            <button
              type="button"
              className={`text-xs underline decoration-dotted underline-offset-2 ${linkTone}`}
              onClick={(e) => {
                e.stopPropagation();
                openInstructionDrawerForRow(row);
              }}
            >
              {snap.is_persisted_snapshot ? "Зафиксирована" : "Legacy"}
            </button>
          );
        },
      },
    ],
    [getV1RowForReviewRow, openInstructionDrawerForRow],
  );


  // -----------------------------------------------------------
  // Leaf columns: expanded runtime column
  // -----------------------------------------------------------


  const buildRuntimeLeafColumnDef = useCallback(
    (
      check: DDGridV1CheckNode,
      runtimeColumn: DDGridV1RuntimeColumn,
    ): ColDef<V1MatrixGridRow> => {
      const meta = columnLookup.get(check.checkId);
      const label = runtimeColumn.column.label;


      return {
        colId: `runtime|${runtimeColumn.runtimeKey}`,
        headerName: label,
        headerTooltip: label,
        headerClass: "ag-center-header",
        minWidth: RUNTIME_COLUMN_MIN_WIDTH_PX,
        autoHeight: true,
        wrapText: true,
        cellDataType: false,


        valueGetter: (params: ValueGetterParams<V1MatrixGridRow>) => {
          const row = params.data;
          const v1Row = getV1RowForReviewRow(row);
          if (!v1Row) return null;


          return resolveDDGridV1CellView(v1Row, runtimeColumn, model.cellValues);
        },


        filterValueGetter: (params) => {
          const row = params.data as V1MatrixGridRow | undefined;
          const v1Row = getV1RowForReviewRow(row);
          if (!v1Row) return "";


          const cellView = resolveDDGridV1CellView(
            v1Row,
            runtimeColumn,
            model.cellValues,
          );
          return formatRuntimeCellForExport(cellView);
        },


        valueFormatter: (
          params: ValueFormatterParams<V1MatrixGridRow>,
        ): string =>
          formatRuntimeCellForExport(
            params.value as DDGridV1CellView | null,
          ),


        tooltipValueGetter: (params) =>
          buildRuntimeCellTooltip(
            check.checkName,
            label,
            params.value as DDGridV1CellView | null,
          ),


        comparator: (a, b) =>
          compareRuntimeCellViews(
            a as DDGridV1CellView | null,
            b as DDGridV1CellView | null,
          ),


        cellRenderer: (params: ICellRendererParams<V1MatrixGridRow>) => {
          const row = params.data;
          const cellView = params.value as DDGridV1CellView | null;


          if (!row || !cellView) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }


          const cellForDrawer = row.cellsByCheckId[check.checkId];
          const canOpen = Boolean(meta && cellForDrawer);
          const wrapperTone =
            cellView.cellState === "not_applicable" ? "opacity-70" : "";


          const content = (
            <div
              className="py-0"
              style={{
                lineHeight: 1.2,
              }}
            >
              <span
                className={`whitespace-normal break-words text-[11px] ${cellStateToneClass(cellView.cellState)}`}
                style={{
                  lineHeight: 1.2,
                  display: "block",
                }}
              >
                {cellView.displayText}
              </span>
            </div>
          );


          if (!canOpen || !cellForDrawer) {
            return <div className={wrapperTone}>{content}</div>;
          }


          return (
            <button
              type="button"
              className={`w-full text-left ${wrapperTone}`.trim()}
              onClick={(e) => {
                e.stopPropagation();
                openDetailsForCell({
                  row,
                  checkId: check.checkId,
                  cell: cellForDrawer,
                });
              }}
            >
              {content}
            </button>
          );
        },
      };
    },
    [columnLookup, getV1RowForReviewRow, model.cellValues, openDetailsForCell],
  );


  // -----------------------------------------------------------
  // Check group: expanded or collapsed
  // -----------------------------------------------------------


  const buildCheckGroupDef = useCallback(
    (check: DDGridV1CheckNode): ColDef<V1MatrixGridRow> | ColGroupDef<V1MatrixGridRow> => {
      const meta = columnLookup.get(check.checkId);
      const headerName = meta?.checkName ?? check.checkName ?? check.checkId;
      const collapsed = collapsedCheckSet.has(check.checkId);


      if (collapsed) {
        // При сворачивании возвращаем обычную колонку с кастомным header.
        // Клик по ячейке открывает V1 drawer для этого check-а.
        return {
          colId: `collapsed-check|${check.nodeKey}`,
          headerName: headerName,
          headerTooltip: `Нажмите + чтобы развернуть ${headerName}`,
          headerClass: "ag-center-header",
          width: 200,
          minWidth: 140,
          maxWidth: 350,
          resizable: true,
          sortable: false,
          filter: false,
          suppressMovable: false,
          valueGetter: () => "",
          headerComponent: V1CollapsedHeader,
          headerComponentParams: {
            displayName: headerName,
            onExpand: () => onToggleCollapseCheck?.(check.checkId),
            uppercase: false,
          },
          cellRenderer: (params: ICellRendererParams<V1MatrixGridRow>) => {
            const row = params.data;
            if (!row) return null;


            const cellForDrawer = row.cellsByCheckId[check.checkId];
            const hasDrawer =
              model.drawerContents[row.documentId]?.[check.checkId] != null;


            if (!hasDrawer) {
              return (
                <span className="text-[11px] italic text-[var(--text-faint)]">
                  Открыть проверку
                </span>
              );
            }


            return (
              <button
                type="button"
                className="w-full text-left"
                onClick={(e) => {
                  e.stopPropagation();
                  openDetailsForCell({
                    row,
                    checkId: check.checkId,
                    cell: cellForDrawer,
                  });
                }}
              >
                <span className="text-[11px] text-[var(--accent-primary)] hover:underline">
                  Открыть проверку →
                </span>
              </button>
            );
          },
        };
      }


      return {
        groupId: `check|${check.nodeKey}`,
        headerName,
        headerTooltip: headerName,
        marryChildren: true,
        headerGroupComponent: V1CheckHeaderGroup,
        headerGroupComponentParams: {
          displayName: headerName,
          checkId: check.checkId,
          collapsed,
          onToggleCollapseCheck,
        },
        children: check.columns.map((runtimeColumn) =>
          buildRuntimeLeafColumnDef(check, runtimeColumn),
        ),
      };
    },
    [
      buildRuntimeLeafColumnDef,
      collapsedCheckSet,
      columnLookup,
      model.drawerContents,
      onToggleCollapseCheck,
      openDetailsForCell,
    ],
  );


  // -----------------------------------------------------------
  // Scope group: expanded or collapsed
  // -----------------------------------------------------------


  const buildScopeGroupDef = useCallback(
    (plan: V1ScopeGroupPlan): ColDef<V1MatrixGridRow> | ColGroupDef<V1MatrixGridRow> => {
      const collapsed = collapsedGroupSet.has(plan.groupKey);


      if (collapsed) {
        // При сворачивании возвращаем обычную колонку с кастомным header
        return {
          colId: `collapsed-scope|${plan.groupKey}`,
          headerName: plan.groupLabel,
          headerTooltip: `Нажмите + чтобы развернуть ${plan.groupLabel}`,
          headerClass: "ag-center-header",
          width: 180,
          minWidth: 120,
          maxWidth: 300,
          resizable: true,
          sortable: false,
          filter: false,
          suppressMovable: false,
          valueGetter: () => "",
          headerComponent: V1CollapsedHeader,
          headerComponentParams: {
            displayName: plan.groupLabel,
            onExpand: () => onToggleCollapseGroup?.(plan.groupKey),
            uppercase: false,
          },
        };
      }


      return {
        groupId: plan.groupKey,
        headerName: plan.groupLabel,
        headerTooltip: plan.groupLabel,
        marryChildren: true,
        headerGroupComponent: V1ScopeHeaderGroup,
        headerGroupComponentParams: {
          displayName: plan.groupLabel,
          groupKey: plan.groupKey,
          collapsed,
          onToggleCollapseGroup,
        },
        children: plan.checks.map((check) => buildCheckGroupDef(check)),
      };
    },
    [
      buildCheckGroupDef,
      collapsedGroupSet,
      onToggleCollapseGroup,
    ],
  );


  // -----------------------------------------------------------
  // Top-level bucket: expanded or collapsed
  // -----------------------------------------------------------


  const buildTopLevelGroupDef = useCallback(
    (plan: V1TopLevelPlan): ColDef<V1MatrixGridRow> | ColGroupDef<V1MatrixGridRow> => {
      const collapsed = collapsedGroupSet.has(plan.topKey);


      if (collapsed) {
        // При сворачивании возвращаем обычную колонку с кастомным header
        return {
          colId: `collapsed-top|${plan.topKey}`,
          headerName: plan.topLabel,
          headerTooltip: `Нажмите + чтобы развернуть ${plan.topLabel}`,
          headerClass: "ag-center-header",
          width: 220,
          minWidth: 160,
          maxWidth: 400,
          resizable: true,
          sortable: false,
          filter: false,
          suppressMovable: false,
          valueGetter: () => "",
          headerComponent: V1CollapsedHeader,
          headerComponentParams: {
            displayName: plan.topLabel,
            onExpand: () => onToggleCollapseGroup?.(plan.topKey),
            uppercase: true,
          },
        };
      }


      return {
        groupId: plan.topKey,
        headerName: plan.topLabel,
        headerTooltip: plan.topLabel,
        marryChildren: true,
        headerGroupComponent: V1TopLevelHeaderGroup,
        headerGroupComponentParams: {
          displayName: plan.topLabel,
          topKey: plan.topKey,
          collapsed,
          onToggleCollapseGroup,
        },
        children: plan.groups.map((group) => buildScopeGroupDef(group)),
      };
    },
    [
      buildScopeGroupDef,
      collapsedGroupSet,
      onToggleCollapseGroup,
    ],
  );


  // -----------------------------------------------------------
  // Full columnDefs
  // -----------------------------------------------------------


  const groupedCheckColumns = useMemo<
    (ColDef<V1MatrixGridRow> | ColGroupDef<V1MatrixGridRow>)[]
  >(() => {
    return topLevelPlans.map((plan) => buildTopLevelGroupDef(plan));
  }, [topLevelPlans, buildTopLevelGroupDef]);


  const columnDefs = useMemo<
    (ColDef<V1MatrixGridRow> | ColGroupDef<V1MatrixGridRow>)[]
  >(
    () => [...baseColumns, ...groupedCheckColumns],
    [baseColumns, groupedCheckColumns],
  );


  // -----------------------------------------------------------
  // Selection propagation
  // -----------------------------------------------------------


  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<V1MatrixGridRow>) => {
      if (!onSelectionChange) return;
      onSelectionChange(buildSelectionItems(event));
    },
    [onSelectionChange],
  );


  const handleGridReady = useCallback(
    (event: GridReadyEvent<V1MatrixGridRow>) => {
      setGridApi(event.api);
      requestAnimationFrame(() => {
        try {
          event.api.sizeColumnsToFit();
        } catch {
          /* noop */
        }
      });
    },
    [],
  );


  useLayoutEffect(() => {
    if (!gridApi) return;
    const id = requestAnimationFrame(() => {
      try {
        gridApi.sizeColumnsToFit();
      } catch {
        /* noop */
      }
    });
    return () => cancelAnimationFrame(id);
  }, [gridApi, rootWidth, rowData.length, columnDefs]);


  const lastClearTokenRef = useRef<number | undefined>(clearSelectionToken);


  useEffect(() => {
    if (!gridApi) return;
    if (clearSelectionToken === lastClearTokenRef.current) return;
    lastClearTokenRef.current = clearSelectionToken;
    try {
      gridApi.deselectAll();
    } catch {
      /* noop */
    }
  }, [gridApi, clearSelectionToken]);


  if (!rowData.length) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center text-sm text-[var(--text-secondary)] shadow-sm">
        По выбранным фильтрам в DD Grid ничего не найдено.
      </div>
    );
  }

  return (
    <>
      {/* Активная таблица сжимается до 2/3, освобождая 1/3 для drawer */}
      <div
        className={`flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm transition-all duration-300 ${
          isDrawerPanelOpen ? "w-2/3" : "w-full"
        }`}
      >
        {title ? (
          <div className="shrink-0 border-b border-[var(--border-subtle)] px-5 py-4">
            <div className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </div>
            <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
              Документы: {rowData.length} · Проверки: {visibleChecksCount}
            </div>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-hidden">
          <div
            className="ag-theme-legalmas h-full w-full"
            style={{
              minHeight: MATRIX_MIN_HEIGHT_PX,
              minWidth: MATRIX_MIN_WIDTH_PX,
            }}
          >
            <AgGridReact<V1MatrixGridRow>
              theme="legacy"
              rowData={rowData}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              rowSelection={rowSelection}
              suppressCellFocus={false}
              tooltipShowDelay={200}
              onSelectionChanged={handleSelectionChanged}
              onGridReady={handleGridReady}
              getRowId={(params) => params.data.rowId}
              domLayout="normal"
            />
          </div>
        </div>
      </div>

      {/* Drawer с position: absolute — занимает ровно 1/3 ширины */}
      {isDrawerPanelOpen && (
        <div className="absolute top-0 right-0 h-full w-1/3 z-50">
          <div className="flex h-full flex-col overflow-hidden border-l border-[var(--border)] bg-[var(--bg-card)] rounded-l-2xl shadow-2xl">
            {isCellDrawerOpen && (
              <DDGridV1Drawer
                open={true}
                onClose={closeDetails}
                runId={runId}
                documentId={selectedCell.documentId}
                documentName={selectedCell.documentName}
                drawerContent={selectedCell.drawerContent}
                currentQcStatus={selectedCell.currentQcStatus}
                currentQcComment={selectedCell.currentQcComment}
                onOpenInViewer={
                  onOpenAtLocation
                    ? (payload) =>
                        onOpenAtLocation({
                          documentId: payload.documentId,
                          page: payload.page ?? undefined,
                          clauseUid: payload.clauseUid ?? undefined,
                          elementId: undefined,
                          segmentId: payload.segmentId ?? undefined,
                          chunkId: payload.chunkId ?? undefined,
                          chunkIndex: payload.chunkIndex ?? undefined,
                        })
                    : undefined
                }
              />
            )}

            {isInstructionDrawerOpen && (
              <DDGridV1InstructionDrawer
                open={true}
                onClose={closeInstructionDrawer}
                documentName={selectedInstruction.documentName}
                snapshot={selectedInstruction.snapshot}
              />
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default DDGridV1Matrix;


