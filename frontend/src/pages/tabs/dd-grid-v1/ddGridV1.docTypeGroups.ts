// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.docTypeGroups.ts
// Группировка документов и check-ов по doc-type для multi-table view.
//
// Правила:
// - никаких хардкодов конкретных check_id / column_id / doc_type;
// - резолвер doc_type = прямое строковое совпадение с type_code
//   (подтверждено фактическим response backend);
// - документ без известного doc_type попадает в отдельную группу
//   "other" (Q12 = A);
// - global checks собираются из model.globalGroups; они одинаковы
//   для всех групп;
// - doc-type checks собираются из соответствующего DDGridV1DocTypeNode.
// =============================================================

import type {
  DDGridV1DerivedModel,
  DDGridV1MatrixRow,
} from "./ddGridV1.types";

/**
 * Стабильный идентификатор группы doc-type для рендера.
 * "other" зарезервирован под группу документов без известного типа.
 */
export type DDGridV1DocTypeGroupKey = string;

export const DD_GRID_V1_OTHER_GROUP_KEY: DDGridV1DocTypeGroupKey = "other";
export const DD_GRID_V1_ALL_GROUP_KEY: DDGridV1DocTypeGroupKey = "__all__";

/**
 * View-модель одной таблицы в multi-table view.
 */
export interface DDGridV1DocTypeGroupView {
  /** Стабильный уникальный ключ группы. */
  groupKey: DDGridV1DocTypeGroupKey;

  /** Заголовок таблицы, показываемый пользователю. */
  title: string;

  /**
   * Строки документов, принадлежащих этой группе.
   * Для "other" — документы, чей doc_type не совпал ни с одним type_code.
   */
  rows: DDGridV1MatrixRow[];

  /**
   * check_ids, которые нужно показывать в этой таблице.
   * Порядок: сначала global checks, потом doc-type checks
   * (совпадает с исходным display_order в модели).
   *
   * Для группы "other" содержит только global check_ids.
   */
  visibleCheckIds: string[];

  /**
   * check_ids, относящиеся к global scope в этой таблице.
   * Используется, чтобы в UI различать global vs doc-type колонки
   * (например, для фильтра "Только глобальные проверки").
   */
  globalCheckIds: string[];

  /**
   * check_ids, относящиеся к doc-type scope в этой таблице.
   * Для "other" — пустой массив.
   */
  docTypeCheckIds: string[];
}

/**
 * Собирает уникальные check_ids из globalGroups в порядке появления.
 */
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

/**
 * Строит lookup type_code → { className, typeName, checkIds } из V1 модели.
 */
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
      // Один и тот же type_code теоретически мог бы встретиться дважды
      // (в разных классах). В контракте это не запрещено. Берём первый.
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

/**
 * Резолвит doc_type документа в канонический bucket key.
 *
 * Возвращает:
 * - trimmed doc_type, если он непустой и существует в lookup;
 * - null, если doc_type отсутствует, пустой или неизвестный.
 *
 * Важно:
 * - никаких хардкодов;
 * - match остаётся прямым строковым совпадением с type_code,
 *   как и зафиксировано в контракте backend.
 */
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

/**
 * Строит список групп для multi-table view (по одной таблице на doc-type
 * плюс опциональная "Прочие документы").
 *
 * Порядок групп:
 * 1. Doc-type группы в том порядке, в котором они появились в
 *    docTypeClasses × types (это отражает display_order из V1 модели).
 * 2. "Прочие документы" — только если есть документы без известного типа.
 *
 * Пустые группы (без документов) исключаются, чтобы UI не показывал
 * пустые заголовки таблиц.
 */
export function buildDDGridV1TypedGroups(
  model: DDGridV1DerivedModel,
): DDGridV1DocTypeGroupView[] {
  const globalCheckIds = collectGlobalCheckIds(model);
  const typeLookup = buildDocTypeInfoLookup(model);

  // Индексируем строки по резолвленному doc_type (или "other").
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

  // 1. Doc-type группы в порядке V1 модели.
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

  // 2. "Прочие документы" — если есть.
  const otherRows = rowsByBucket.get(DD_GRID_V1_OTHER_GROUP_KEY);
  if (otherRows && otherRows.length > 0) {
    result.push({
      groupKey: DD_GRID_V1_OTHER_GROUP_KEY,
      title: "Прочие документы",
      rows: otherRows,
      visibleCheckIds: globalCheckIds,
      globalCheckIds,
      docTypeCheckIds: [],
    });
  }

  return result;
}

/**
 * View-модель "Все документы" — используется в view mode "all_documents",
 * где мы показываем одну сводную таблицу без разбивки по типам, но со
 * всеми доступными в run check_ids.
 *
 * check_ids собираются в порядке: сначала все global, потом все doc-type
 * (в порядке появления в V1 модели, без дублей).
 */
export function buildDDGridV1AllDocumentsGroup(
  model: DDGridV1DerivedModel,
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
    title: "Все документы",
    rows: model.rows,
    visibleCheckIds: [...globalCheckIds, ...docTypeCheckIds],
    globalCheckIds,
    docTypeCheckIds,
  };
}

/**
 * View-модель "Только глобальные проверки" — используется в view mode
 * "global_only". Одна сводная таблица со всеми документами и только
 * global check_ids.
 */
export function buildDDGridV1GlobalOnlyGroup(
  model: DDGridV1DerivedModel,
): DDGridV1DocTypeGroupView {
  const globalCheckIds = collectGlobalCheckIds(model);

  return {
    groupKey: DD_GRID_V1_ALL_GROUP_KEY,
    title: "Все документы · только глобальные проверки",
    rows: model.rows,
    visibleCheckIds: globalCheckIds,
    globalCheckIds,
    docTypeCheckIds: [],
  };
}


