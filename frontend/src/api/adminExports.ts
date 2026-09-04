// =============================================================
// src/api/adminExports.ts
// Экспорт списка клиентов в Excel / Word / PDF.
//
// Стратегия: клиентская генерация файлов.
// Причина: данных мало (десятки-сотни клиентов), backend
// endpoint не нужен, экспорт мгновенный.
//
// UI-контракт совпадает с documents.ts:
//   export{Excel,Word,PDF}(...) -> Promise<void>
// Внутри вызывается downloadBlob(blob, filename).
//
// Если в будущем понадобится серверная генерация —
// достаточно заменить тело трёх функций, вызывающие места
// (AdminPage / ExportMenu) не поменяются.
//
// Библиотеки xlsx / docx / jspdf / jspdf-autotable подгружаются
// динамически, чтобы не раздувать основной бандл.
// =============================================================

import type { Tenant } from "./admin";

// ─────────────────────────────────────────────────────────────
// Контракт интернационализации для экспорта
// ─────────────────────────────────────────────────────────────

export interface AdminExportI18n {
  t: (key: string, options?: Record<string, unknown>) => string;
  locale: string;
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

/**
 * Общий helper для скачивания Blob в браузере.
 * Совпадает по поведению с downloadBlob из src/api/documents.ts.
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

function formatDate(value: string, locale: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatFullTimestamp(locale: string): string {
  const d = new Date();
  return d.toLocaleString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Имя файла с временной меткой: tenants_2026-07-22_1435.{ext}
 */
function buildFileName(ext: "xlsx" | "docx" | "pdf"): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp =
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `_${pad(d.getHours())}${pad(d.getMinutes())}`;
  return `tenants_${stamp}.${ext}`;
}

// ─────────────────────────────────────────────────────────────
// Общая структура данных для экспорта
// ─────────────────────────────────────────────────────────────

interface ExportRow {
  order: number;
  name: string;
  created_at: string;
  slug: string;
  id: string;
  users_count: number;
  deals_count: number;
  status: string;
}

interface ColumnDef {
  key: keyof ExportRow;
  labelKey: string;
  fallback: string;
}

/**
 * Порядок колонок для всех форматов с поддержкой i18n-ключей.
 */
const COLUMNS: ColumnDef[] = [
  { key: "order", labelKey: "admin:tenantExport.columns.order", fallback: "#" },
  { key: "name", labelKey: "admin:tenantExport.columns.clientName", fallback: "Client name" },
  { key: "created_at", labelKey: "admin:tenantExport.columns.created", fallback: "Created" },
  { key: "slug", labelKey: "admin:tenantExport.columns.slug", fallback: "Slug" },
  { key: "id", labelKey: "admin:tenantExport.columns.id", fallback: "ID" },
  { key: "users_count", labelKey: "admin:tenantExport.columns.users", fallback: "Users" },
  { key: "deals_count", labelKey: "admin:tenantExport.columns.projects", fallback: "Projects" },
  { key: "status", labelKey: "admin:tenantExport.columns.status", fallback: "Status" },
];

function getColLabel(col: ColumnDef, t?: AdminExportI18n["t"]): string {
  return t?.(col.labelKey) ?? col.fallback;
}

function toRow(
  tenant: Tenant,
  index: number,
  t?: AdminExportI18n["t"],
  locale?: string,
): ExportRow {
  const activeLabel = t?.("admin:tenantExport.active") ?? "Active";
  const deactivatedLabel = t?.("admin:tenantExport.deactivated") ?? "Deactivated";

  return {
    order: index + 1,
    name: tenant.name,
    created_at: formatDate(tenant.created_at, locale ?? "en-US"),
    slug: tenant.slug,
    id: tenant.id,
    users_count: tenant.users_count,
    deals_count: tenant.deals_count,
    status: tenant.is_active ? activeLabel : deactivatedLabel,
  };
}

function assertNonEmpty(tenants: Tenant[], t?: AdminExportI18n["t"]): void {
  if (tenants.length === 0) {
    throw new Error(t?.("admin:tenantExport.noData") ?? "No clients to export");
  }
}

// ─────────────────────────────────────────────────────────────
// Excel (.xlsx)
// ─────────────────────────────────────────────────────────────

export async function exportTenantsExcel(
  tenants: Tenant[],
  i18n?: AdminExportI18n,
): Promise<void> {
  const t = i18n?.t;
  const locale = i18n?.locale ?? "en-US";
  assertNonEmpty(tenants, t);

  const XLSX = await import("xlsx");

  const rows = tenants.map((tn, idx) => toRow(tn, idx, t, locale));
  const headerRow = COLUMNS.map((c) => getColLabel(c, t));
  const dataRows = rows.map((r) => COLUMNS.map((c) => r[c.key]));

  const worksheet = XLSX.utils.aoa_to_sheet([headerRow, ...dataRows]);

  // Автоширина колонок по максимальной длине содержимого
  worksheet["!cols"] = COLUMNS.map((col, colIdx) => {
    const maxContent = Math.max(
      String(getColLabel(col, t)).length,
      ...dataRows.map((row) => String(row[colIdx] ?? "").length),
    );
    return { wch: Math.min(maxContent + 2, 50) };
  });

  const workbook = XLSX.utils.book_new();
  const sheetName = t?.("admin:tenantExport.sheetName") ?? "Clients";
  XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);

  XLSX.writeFile(workbook, buildFileName("xlsx"));
}

// ─────────────────────────────────────────────────────────────
// Word (.docx)
// ─────────────────────────────────────────────────────────────

export async function exportTenantsWord(
  tenants: Tenant[],
  i18n?: AdminExportI18n,
): Promise<void> {
  const t = i18n?.t;
  const locale = i18n?.locale ?? "en-US";
  assertNonEmpty(tenants, t);

  const {
    Document,
    Packer,
    Paragraph,
    Table,
    TableRow,
    TableCell,
    TextRun,
    HeadingLevel,
    AlignmentType,
    WidthType,
    BorderStyle,
  } = await import("docx");

  const rows = tenants.map((tn, idx) => toRow(tn, idx, t, locale));
  const headerLabels = COLUMNS.map((c) => getColLabel(c, t));

  const border = { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC" };
  const cellBorders = { top: border, bottom: border, left: border, right: border };

  const headerRow = new TableRow({
    tableHeader: true,
    children: headerLabels.map(
      (label) =>
        new TableCell({
          borders: cellBorders,
          shading: { fill: "F3F3F3" },
          children: [
            new Paragraph({
              children: [new TextRun({ text: label, bold: true, size: 20 })],
            }),
          ],
        }),
    ),
  });

  const dataRows = rows.map(
    (row) =>
      new TableRow({
        children: COLUMNS.map(
          (col) =>
            new TableCell({
              borders: cellBorders,
              children: [
                new Paragraph({
                  children: [
                    new TextRun({ text: String(row[col.key]), size: 18 }),
                  ],
                }),
              ],
            }),
        ),
      }),
  );

  const table = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [headerRow, ...dataRows],
  });

  const title = t?.("admin:tenantExport.title") ?? "Client list";
  const subtitle = t?.("admin:tenantExport.subtitle", {
    timestamp: formatFullTimestamp(locale),
    count: rows.length,
  }) ?? `Export: ${formatFullTimestamp(locale)}. Total records: ${rows.length}.`;

  const doc = new Document({
    sections: [
      {
        properties: {},
        children: [
          new Paragraph({
            text: title,
            heading: HeadingLevel.HEADING_1,
            alignment: AlignmentType.LEFT,
          }),
          new Paragraph({
            children: [
              new TextRun({
                text: subtitle,
                italics: true,
                size: 18,
                color: "666666",
              }),
            ],
          }),
          new Paragraph({ text: "" }),
          table,
        ],
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  downloadBlob(blob, buildFileName("docx"));
}

// ─────────────────────────────────────────────────────────────
// PDF (.pdf)
// ─────────────────────────────────────────────────────────────

interface JsPDFWithAutoTable {
  autoTable: (options: Record<string, unknown>) => void;
  save: (filename: string) => void;
  setFontSize: (size: number) => void;
  setFont: (fontName: string, style?: string) => void;
  setTextColor: (r: number, g: number, b: number) => void;
  text: (text: string, x: number, y: number) => void;
}

export async function exportTenantsPDF(
  tenants: Tenant[],
  i18n?: AdminExportI18n,
): Promise<void> {
  const t = i18n?.t;
  const locale = i18n?.locale ?? "en-US";
  assertNonEmpty(tenants, t);

  const jsPDFModule = await import("jspdf");
  const JsPDF = jsPDFModule.default;
  await import("jspdf-autotable");

  const rows = tenants.map((tn, idx) => toRow(tn, idx, t, locale));
  const headerLabels = COLUMNS.map((c) => getColLabel(c, t));

  const doc = new JsPDF({
    orientation: "landscape",
    unit: "mm",
    format: "a4",
  }) as unknown as JsPDFWithAutoTable;

  const title = t?.("admin:tenantExport.title") ?? "Client list";
  const subtitle = t?.("admin:tenantExport.subtitle", {
    timestamp: formatFullTimestamp(locale),
    count: rows.length,
  }) ?? `Export: ${formatFullTimestamp(locale)}. Total records: ${rows.length}.`;

  // Заголовок
  doc.setFontSize(16);
  doc.setFont("helvetica", "bold");
  doc.text(title, 14, 15);

  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(100, 100, 100);
  doc.text(subtitle, 14, 21);

  doc.autoTable({
    startY: 26,
    head: [headerLabels],
    body: rows.map((r) => COLUMNS.map((c) => String(r[c.key]))),
    styles: {
      fontSize: 8,
      cellPadding: 2,
    },
    headStyles: {
      fillColor: [243, 243, 243],
      textColor: [40, 40, 40],
      fontStyle: "bold",
    },
    alternateRowStyles: {
      fillColor: [250, 250, 250],
    },
    columnStyles: {
      0: { cellWidth: 10, halign: "center" }, // №
      4: { cellWidth: 60, fontSize: 7 }, // ID (UUID широкий)
      5: { halign: "center" },
      6: { halign: "center" },
    },
    margin: { left: 14, right: 14 },
  });

  doc.save(buildFileName("pdf"));
}


