// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.collapseStore.ts
// Zustand store для persistent состояния DD Grid V1 UI:
// - настройки отображения матрицы (три независимых параметра)
// - collapsed checks / groups с persistence через localStorage
//
// Правила:
// - тот же стиль, что uiStore: ручной localStorage в setter,
//   без zustand/middleware persist;
// - never throws: safe read/write localStorage;
// - никаких хардкодов бизнес-семантики.
// =============================================================

import { create } from "zustand";

// -------------------------------------------------------------
// View settings — три независимых параметра
// -------------------------------------------------------------

/** Формат представления данных. */
export type DDGridV1GridFormat = "matrix" | "list";

/** Набор проверок, показываемых в таблице. */
export type DDGridV1ChecksScope = "all" | "global_only" | "doc_type_only";

/** Способ группировки документов. */
export type DDGridV1DocGrouping = "all_docs" | "by_type";

export const DD_GRID_V1_DEFAULT_FORMAT: DDGridV1GridFormat = "matrix";
export const DD_GRID_V1_DEFAULT_CHECKS_SCOPE: DDGridV1ChecksScope = "all";
export const DD_GRID_V1_DEFAULT_DOC_GROUPING: DDGridV1DocGrouping = "by_type";

const FORMAT_STORAGE_KEY = "mas_dd_v1_format";
const CHECKS_SCOPE_STORAGE_KEY = "mas_dd_v1_checks_scope";
const DOC_GROUPING_STORAGE_KEY = "mas_dd_v1_doc_grouping";
const COLLAPSED_CHECKS_STORAGE_KEY = "mas_dd_v1_collapsed_checks";
const COLLAPSED_GROUPS_STORAGE_KEY = "mas_dd_v1_collapsed_groups";

// -------------------------------------------------------------
// Safe localStorage helpers
// -------------------------------------------------------------

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* noop */
  }
}

function loadFormat(): DDGridV1GridFormat {
  const raw = safeGetItem(FORMAT_STORAGE_KEY);
  if (raw === "matrix" || raw === "list") return raw;
  return DD_GRID_V1_DEFAULT_FORMAT;
}

function loadChecksScope(): DDGridV1ChecksScope {
  const raw = safeGetItem(CHECKS_SCOPE_STORAGE_KEY);
  if (raw === "all" || raw === "global_only" || raw === "doc_type_only") {
    return raw;
  }
  return DD_GRID_V1_DEFAULT_CHECKS_SCOPE;
}

function loadDocGrouping(): DDGridV1DocGrouping {
  const raw = safeGetItem(DOC_GROUPING_STORAGE_KEY);
  if (raw === "all_docs" || raw === "by_type") return raw;
  return DD_GRID_V1_DEFAULT_DOC_GROUPING;
}

function loadKeyedRecord(storageKey: string): Record<string, true> {
  const raw = safeGetItem(storageKey);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const out: Record<string, true> = {};
    for (const key of Object.keys(parsed)) {
      if (typeof key === "string" && key.length > 0) {
        out[key] = true;
      }
    }
    return out;
  } catch {
    return {};
  }
}

function persistKeyedRecord(
  storageKey: string,
  next: Record<string, true>,
): void {
  safeSetItem(storageKey, JSON.stringify(next));
}

// -------------------------------------------------------------
// Store
// -------------------------------------------------------------

interface DDGridV1UIState {
  // View settings
  format: DDGridV1GridFormat;
  setFormat: (value: DDGridV1GridFormat) => void;

  checksScope: DDGridV1ChecksScope;
  setChecksScope: (value: DDGridV1ChecksScope) => void;

  docGrouping: DDGridV1DocGrouping;
  setDocGrouping: (value: DDGridV1DocGrouping) => void;

  // Collapsed checks
  collapsedCheckIds: Record<string, true>;
  isCheckCollapsed: (checkId: string) => boolean;
  toggleCheckCollapsed: (checkId: string) => void;
  setCheckCollapsed: (checkId: string, collapsed: boolean) => void;
  collapseAllChecks: (checkIds: readonly string[]) => void;
  expandAllChecks: (checkIds: readonly string[]) => void;

  // Collapsed groups (top-level и scope group)
  collapsedGroupKeys: Record<string, true>;
  isGroupCollapsed: (groupKey: string) => boolean;
  toggleGroupCollapsed: (groupKey: string) => void;
  setGroupCollapsed: (groupKey: string, collapsed: boolean) => void;
  collapseAllGroups: (groupKeys: readonly string[]) => void;
  expandAllGroups: (groupKeys: readonly string[]) => void;
}

function toggleInRecord(
  storageKey: string,
  record: Record<string, true>,
  key: string,
): Record<string, true> | null {
  if (typeof key !== "string" || key.length === 0) return null;
  const next = { ...record };
  if (next[key]) {
    delete next[key];
  } else {
    next[key] = true;
  }
  persistKeyedRecord(storageKey, next);
  return next;
}

function setInRecord(
  storageKey: string,
  record: Record<string, true>,
  key: string,
  collapsed: boolean,
): Record<string, true> | null {
  if (typeof key !== "string" || key.length === 0) return null;
  const already = Boolean(record[key]);
  if (already === collapsed) return null;
  const next = { ...record };
  if (collapsed) {
    next[key] = true;
  } else {
    delete next[key];
  }
  persistKeyedRecord(storageKey, next);
  return next;
}

function bulkSetInRecord(
  storageKey: string,
  record: Record<string, true>,
  keys: readonly string[],
  collapsed: boolean,
): Record<string, true> | null {
  if (!keys.length) return null;
  const next = { ...record };
  let changed = false;

  for (const key of keys) {
    if (typeof key !== "string" || key.length === 0) continue;
    const already = Boolean(next[key]);
    if (already === collapsed) continue;
    if (collapsed) {
      next[key] = true;
    } else {
      delete next[key];
    }
    changed = true;
  }

  if (!changed) return null;
  persistKeyedRecord(storageKey, next);
  return next;
}

export const useDDGridV1UIStore = create<DDGridV1UIState>((set, get) => ({
  // View settings
  format: loadFormat(),
  setFormat: (value) => {
    safeSetItem(FORMAT_STORAGE_KEY, value);
    set({ format: value });
  },

  checksScope: loadChecksScope(),
  setChecksScope: (value) => {
    safeSetItem(CHECKS_SCOPE_STORAGE_KEY, value);
    set({ checksScope: value });
  },

  docGrouping: loadDocGrouping(),
  setDocGrouping: (value) => {
    safeSetItem(DOC_GROUPING_STORAGE_KEY, value);
    set({ docGrouping: value });
  },

  // -----------------------------------------------------------
  // Checks
  // -----------------------------------------------------------

  collapsedCheckIds: loadKeyedRecord(COLLAPSED_CHECKS_STORAGE_KEY),

  isCheckCollapsed: (checkId) => {
    return Boolean(get().collapsedCheckIds[checkId]);
  },

  toggleCheckCollapsed: (checkId) => {
    set((state) => {
      const next = toggleInRecord(
        COLLAPSED_CHECKS_STORAGE_KEY,
        state.collapsedCheckIds,
        checkId,
      );
      return next ? { collapsedCheckIds: next } : state;
    });
  },

  setCheckCollapsed: (checkId, collapsed) => {
    set((state) => {
      const next = setInRecord(
        COLLAPSED_CHECKS_STORAGE_KEY,
        state.collapsedCheckIds,
        checkId,
        collapsed,
      );
      return next ? { collapsedCheckIds: next } : state;
    });
  },

  collapseAllChecks: (checkIds) => {
    set((state) => {
      const next = bulkSetInRecord(
        COLLAPSED_CHECKS_STORAGE_KEY,
        state.collapsedCheckIds,
        checkIds,
        true,
      );
      return next ? { collapsedCheckIds: next } : state;
    });
  },

  expandAllChecks: (checkIds) => {
    set((state) => {
      const next = bulkSetInRecord(
        COLLAPSED_CHECKS_STORAGE_KEY,
        state.collapsedCheckIds,
        checkIds,
        false,
      );
      return next ? { collapsedCheckIds: next } : state;
    });
  },

  // -----------------------------------------------------------
  // Groups
  // -----------------------------------------------------------

  collapsedGroupKeys: loadKeyedRecord(COLLAPSED_GROUPS_STORAGE_KEY),

  isGroupCollapsed: (groupKey) => {
    return Boolean(get().collapsedGroupKeys[groupKey]);
  },

  toggleGroupCollapsed: (groupKey) => {
    set((state) => {
      const next = toggleInRecord(
        COLLAPSED_GROUPS_STORAGE_KEY,
        state.collapsedGroupKeys,
        groupKey,
      );
      return next ? { collapsedGroupKeys: next } : state;
    });
  },

  setGroupCollapsed: (groupKey, collapsed) => {
    set((state) => {
      const next = setInRecord(
        COLLAPSED_GROUPS_STORAGE_KEY,
        state.collapsedGroupKeys,
        groupKey,
        collapsed,
      );
      return next ? { collapsedGroupKeys: next } : state;
    });
  },

  collapseAllGroups: (groupKeys) => {
    set((state) => {
      const next = bulkSetInRecord(
        COLLAPSED_GROUPS_STORAGE_KEY,
        state.collapsedGroupKeys,
        groupKeys,
        true,
      );
      return next ? { collapsedGroupKeys: next } : state;
    });
  },

  expandAllGroups: (groupKeys) => {
    set((state) => {
      const next = bulkSetInRecord(
        COLLAPSED_GROUPS_STORAGE_KEY,
        state.collapsedGroupKeys,
        groupKeys,
        false,
      );
      return next ? { collapsedGroupKeys: next } : state;
    });
  },
}));


