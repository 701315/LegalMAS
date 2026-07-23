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

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatFullTimestamp(): string {
  const d = new Date();
  return d.toLocaleString("ru-RU", {
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

/**
 * Порядок колонок для всех форматов. Меняется только здесь.
 */
const COLUMNS: Array<{ key: keyof ExportRow; label: string }> = [
  { key: "order", label: "№" },
  { key: "name", label: "Название клиента" },
  { key: "created_at", label: "Создан" },
  { key: "slug", label: "Slug" },
  { key: "id", label: "ID" },
  { key: "users_count", label: "Пользователей" },
  { key: "deals_count", label: "Проектов" },
  { key: "status", label: "Статус" },
];

function toRow(tenant: Tenant, index: number): ExportRow {
  return {
    order: index + 1,
    name: tenant.name,
    created_at: formatDate(tenant.created_at),
    slug: tenant.slug,
    id: tenant.id,
    users_count: tenant.users_count,
    deals_count: tenant.deals_count,
    status: tenant.is_active ? "Активен" : "Деактивирован",
  };
}

function assertNonEmpty(tenants: Tenant[]): void {
  if (tenants.length === 0) {
    throw new Error("Нет клиентов для экспорта");
  }
}

// ─────────────────────────────────────────────────────────────
// Excel (.xlsx)
// ─────────────────────────────────────────────────────────────

export async function exportTenantsExcel(tenants: Tenant[]): Promise<void> {
  assertNonEmpty(tenants);

  const XLSX = await import("xlsx");

  const rows = tenants.map(toRow);
  const headerRow = COLUMNS.map((c) => c.label);
  const dataRows = rows.map((r) => COLUMNS.map((c) => r[c.key]));

  const worksheet = XLSX.utils.aoa_to_sheet([headerRow, ...dataRows]);

  // Автоширина колонок по максимальной длине содержимого
  worksheet["!cols"] = COLUMNS.map((col, colIdx) => {
    const maxContent = Math.max(
      String(col.label).length,
      ...dataRows.map((row) => String(row[colIdx] ?? "").length),
    );
    return { wch: Math.min(maxContent + 2, 50) };
  });

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Клиенты");

  XLSX.writeFile(workbook, buildFileName("xlsx"));
}

// ─────────────────────────────────────────────────────────────
// Word (.docx)
// ─────────────────────────────────────────────────────────────

export async function exportTenantsWord(tenants: Tenant[]): Promise<void> {
  assertNonEmpty(tenants);

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

  const rows = tenants.map(toRow);

  const border = { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC" };
  const cellBorders = { top: border, bottom: border, left: border, right: border };

  const headerRow = new TableRow({
    tableHeader: true,
    children: COLUMNS.map(
      (col) =>
        new TableCell({
          borders: cellBorders,
          shading: { fill: "F3F3F3" },
          children: [
            new Paragraph({
              children: [new TextRun({ text: col.label, bold: true, size: 20 })],
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

  const doc = new Document({
    sections: [
      {
        properties: {},
        children: [
          new Paragraph({
            text: "Список клиентов",
            heading: HeadingLevel.HEADING_1,
            alignment: AlignmentType.LEFT,
          }),
          new Paragraph({
            children: [
              new TextRun({
                text: `Экспорт: ${formatFullTimestamp()}. Всего записей: ${rows.length}.`,
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
//
// ВНИМАНИЕ: jsPDF в стандартной поставке не поддерживает
// кириллицу через встроенные шрифты. Для корректного
// отображения русского текста в PDF нужно подключать custom
// TTF-шрифт (например, Roboto через jspdf.plugin.roboto).
//
// В данной версии PDF генерируется со встроенным шрифтом —
// латиница/цифры/ID отображаются корректно, кириллица может
// показываться некорректно.
//
// TODO: если критична кириллица в PDF, добавить подключение
// Roboto (см. https://github.com/parallax/jsPDF#use-of-utf-8--ttf).
// ─────────────────────────────────────────────────────────────

interface JsPDFWithAutoTable {
  autoTable: (options: Record<string, unknown>) => void;
  save: (filename: string) => void;
  setFontSize: (size: number) => void;
  setFont: (fontName: string, style?: string) => void;
  setTextColor: (r: number, g: number, b: number) => void;
  text: (text: string, x: number, y: number) => void;
}

export async function exportTenantsPDF(tenants: Tenant[]): Promise<void> {
  assertNonEmpty(tenants);

  const jsPDFModule = await import("jspdf");
  const JsPDF = jsPDFModule.default;
  // autoTable расширяет прототип jsPDF, важно импортировать после
  await import("jspdf-autotable");

  const rows = tenants.map(toRow);

  const doc = new JsPDF({
    orientation: "landscape",
    unit: "mm",
    format: "a4",
  }) as unknown as JsPDFWithAutoTable;

  // Заголовок
  doc.setFontSize(16);
  doc.setFont("helvetica", "bold");
  doc.text("Список клиентов", 14, 15);

  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(100, 100, 100);
  doc.text(
    `Экспорт: ${formatFullTimestamp()}. Всего записей: ${rows.length}.`,
    14,
    21,
  );

  doc.autoTable({
    startY: 26,
    head: [COLUMNS.map((c) => c.label)],
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



