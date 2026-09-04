// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.docTypeGroups.ts
// Группировка документов и check-ов по doc-type для multi-table view.
//
// i18n: канонический English fallback + динамический tFn.
// =============================================================

import type {
  DDGridV1DerivedModel,
  DDGridV1MatrixRow,
} from "./ddGridV1.types";

type TFunction = (key: string, options?: Record<string, unknown>) => string;

export type DDGridV1DocTypeGroupKey = string;

export const DD_GRID_V1_OTHER_GROUP_KEY: DDGridV1DocTypeGroupKey = "other";
export const DD_GRID_V1_ALL_GROUP_KEY: DDGridV1DocTypeGroupKey = "__all__";

export interface DDGridV1DocTypeGroupView {
  groupKey: DDGridV1DocTypeGroupKey;
  title: string;
  rows: DDGridV1MatrixRow[];
  visibleCheckIds: string[];
  globalCheckIds: string[];
  docTypeCheckIds: string[];
}

function collectGlobalCheckIds(model: DDGridV1DerivedModel): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (!seen.has(check.checkId)) {
        seen.add(check.checkId);
        out.push(check.checkId);
      }
    }
  }
  return out;
}

interface DocTypeInfo {
  className: string;
  typeName: string;
  checkIds: string[];
}

function buildDocTypeInfoLookup(
  model: DDGridV1DerivedModel,
): Map<string, DocTypeInfo> {
  const lookup = new Map<string, DocTypeInfo>();

  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      if (lookup.has(t.typeCode)) continue;

      const checkIds: string[] = [];
      const seen = new Set<string>();
      for (const check of t.checks) {
        if (!seen.has(check.checkId)) {
          seen.add(check.checkId);
          checkIds.push(check.checkId);
        }
      }

      lookup.set(t.typeCode, {
        className: cls.label,
        typeName: t.name,
        checkIds,
      });
    }
  }

  return lookup;
}

function resolveKnownDocTypeKey(
  row: DDGridV1MatrixRow,
  lookup: Map<string, DocTypeInfo>,
): string | null {
  const dt = row.docType;
  if (typeof dt !== "string") return null;

  const normalized = dt.trim();
  if (normalized.length === 0) return null;

  return lookup.has(normalized) ? normalized : null;
}

export function buildDDGridV1TypedGroups(
  model: DDGridV1DerivedModel,
  tFn?: TFunction,
): DDGridV1DocTypeGroupView[] {
  const globalCheckIds = collectGlobalCheckIds(model);
  const typeLookup = buildDocTypeInfoLookup(model);

  const rowsByBucket = new Map<string, DDGridV1MatrixRow[]>();
  for (const row of model.rows) {
    const resolvedDocTypeKey = resolveKnownDocTypeKey(row, typeLookup);
    const bucketKey = resolvedDocTypeKey ?? DD_GRID_V1_OTHER_GROUP_KEY;

    const arr = rowsByBucket.get(bucketKey);
    if (arr) {
      arr.push(row);
    } else {
      rowsByBucket.set(bucketKey, [row]);
    }
  }

  const result: DDGridV1DocTypeGroupView[] = [];

  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      const rows = rowsByBucket.get(t.typeCode);
      if (!rows || rows.length === 0) continue;

      const info = typeLookup.get(t.typeCode);
      if (!info) continue;

      const docTypeCheckIds = info.checkIds;
      const visibleCheckIds = [...globalCheckIds, ...docTypeCheckIds];

      result.push({
        groupKey: t.typeCode,
        title: `${info.className} · ${info.typeName}`,
        rows,
        visibleCheckIds,
        globalCheckIds,
        docTypeCheckIds,
      });
    }
  }

  const otherRows = rowsByBucket.get(DD_GRID_V1_OTHER_GROUP_KEY);
  if (otherRows && otherRows.length > 0) {
    result.push({
      groupKey: DD_GRID_V1_OTHER_GROUP_KEY,
      title: tFn ? tFn("docTypeGroups.otherDocuments") : "Other documents",
      rows: otherRows,
      visibleCheckIds: globalCheckIds,
      globalCheckIds,
      docTypeCheckIds: [],
    });
  }

  return result;
}

export function buildDDGridV1AllDocumentsGroup(
  model: DDGridV1DerivedModel,
  tFn?: TFunction,
): DDGridV1DocTypeGroupView {
  const globalCheckIds = collectGlobalCheckIds(model);

  const docTypeCheckIds: string[] = [];
  const seen = new Set<string>(globalCheckIds);
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        if (!seen.has(check.checkId)) {
          seen.add(check.checkId);
          docTypeCheckIds.push(check.checkId);
        }
      }
    }
  }

  return {
    groupKey: DD_GRID_V1_ALL_GROUP_KEY,
    title: tFn ? tFn("docTypeGroups.allDocuments") : "All documents",
    rows: model.rows,
    visibleCheckIds: [...globalCheckIds, ...docTypeCheckIds],
    globalCheckIds,
    docTypeCheckIds,
  };
}

export function buildDDGridV1GlobalOnlyGroup(
  model: DDGridV1DerivedModel,
  tFn?: TFunction,
): DDGridV1DocTypeGroupView {
  const globalCheckIds = collectGlobalCheckIds(model);

  return {
    groupKey: DD_GRID_V1_ALL_GROUP_KEY,
    title: tFn
      ? tFn("docTypeGroups.allDocumentsGlobalOnly")
      : "All documents · global checks only",
    rows: model.rows,
    visibleCheckIds: globalCheckIds,
    globalCheckIds,
    docTypeCheckIds: [],
  };
}


