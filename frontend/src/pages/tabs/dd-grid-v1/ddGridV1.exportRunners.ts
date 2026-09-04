// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.exportRunners.ts
// Все runner-функции для экспорта DD Grid V1.
// Отделены от UI (кнопок и picker'ов) для чистой separation of concerns.
//
// Экспортирует:
// - exportListToExcel / exportListToPdf / exportListToWord (list mode)
// - exportMatrixToExcel (matrix mode, single только для Excel)
// - exportMatrixSingleToPdf / exportMatrixSingleToWord (matrix Layout 1)
// - exportSectionedToPdf / exportSectionedToWord (matrix Layout 2 & 3)
//
// Все тяжёлые библиотеки (xlsx, jspdf, docx) грузятся динамически,
// только при первом вызове export-функции.
// =============================================================

import type {
  DDGridV1MatrixExportTable,
  DDGridV1SectionedExportTable,
} from "./ddGridV1.exportBuilder";

// -------------------------------------------------------------
// Type-only imports (не попадают в runtime bundle)
// -------------------------------------------------------------

import type { jsPDF as JsPDFType } from "jspdf";
import type * as XLSXType from "xlsx";
import type {
  Document as DocumentType,
  HeadingLevel as HeadingLevelType,
  Packer as PackerType,
  PageOrientation as PageOrientationType,
  Paragraph as ParagraphType,
  Table as TableType,
  TableCell as TableCellType,
  TableRow as TableRowType,
  TextRun as TextRunType,
  WidthType as WidthTypeType,
} from "docx";

// -------------------------------------------------------------
// I18n contract
// -------------------------------------------------------------

export interface DDGridV1ExportI18n {
  t: (key: string, options?: Record<string, unknown>) => string;
  locale: string;
}

// -------------------------------------------------------------
// Common types
// -------------------------------------------------------------

export interface DDGridV1ExportFileOpts {
  dealName?: string;
  runId?: string;
  i18n?: DDGridV1ExportI18n;
}

// -------------------------------------------------------------
// Lazy module loaders (singleton cache per module)
// -------------------------------------------------------------

let _xlsxModule: typeof XLSXType | null = null;
async function loadXLSX(): Promise<typeof XLSXType> {
  if (!_xlsxModule) {
    _xlsxModule = await import("xlsx");
  }
  return _xlsxModule;
}

let _jspdfModule: { jsPDF: typeof JsPDFType } | null = null;
async function loadJsPDF(): Promise<{ jsPDF: typeof JsPDFType }> {
  if (!_jspdfModule) {
    const mod = await import("jspdf");
    _jspdfModule = { jsPDF: mod.jsPDF };
  }
  return _jspdfModule;
}

let _autoTableFn: ((doc: JsPDFType, options: unknown) => void) | null = null;
async function loadAutoTable(): Promise<
  (doc: JsPDFType, options: unknown) => void
> {
  if (!_autoTableFn) {
    const mod = await import("jspdf-autotable");
    _autoTableFn = mod.default as (doc: JsPDFType, options: unknown) => void;
  }
  return _autoTableFn;
}

interface DocxModule {
  Document: typeof DocumentType;
  HeadingLevel: typeof HeadingLevelType;
  Packer: typeof PackerType;
  PageOrientation: typeof PageOrientationType;
  Paragraph: typeof ParagraphType;
  Table: typeof TableType;
  TableCell: typeof TableCellType;
  TableRow: typeof TableRowType;
  TextRun: typeof TextRunType;
  WidthType: typeof WidthTypeType;
}

let _docxModule: DocxModule | null = null;
async function loadDocx(): Promise<DocxModule> {
  if (!_docxModule) {
    const mod = await import("docx");
    _docxModule = {
      Document: mod.Document,
      HeadingLevel: mod.HeadingLevel,
      Packer: mod.Packer,
      PageOrientation: mod.PageOrientation,
      Paragraph: mod.Paragraph,
      Table: mod.Table,
      TableCell: mod.TableCell,
      TableRow: mod.TableRow,
      TextRun: mod.TextRun,
      WidthType: mod.WidthType,
    };
  }
  return _docxModule;
}

let _saveAsFn: ((blob: Blob, filename: string) => void) | null = null;
async function loadSaveAs(): Promise<(blob: Blob, filename: string) => void> {
  if (!_saveAsFn) {
    const mod = await import("file-saver");
    _saveAsFn = mod.saveAs;
  }
  return _saveAsFn;
}

// -------------------------------------------------------------
// File name helpers
// -------------------------------------------------------------

function sanitizeFilePart(s: string): string {
  return s.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 50);
}

function buildFilename(
  suffix: "xlsx" | "pdf" | "docx",
  opts: DDGridV1ExportFileOpts & { layoutSuffix?: string },
): string {
  const deal = opts.dealName ? `_${sanitizeFilePart(opts.dealName)}` : "";
  const run = opts.runId ? `_run_${sanitizeFilePart(opts.runId)}` : "";
  const layout = opts.layoutSuffix ? `_${opts.layoutSuffix}` : "";
  return `dd_grid_v1${deal}${run}${layout}.${suffix}`;
}

function formatExportTimestamp(locale: string, date: Date = new Date()): string {
  return date.toLocaleString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function buildExportMetadata(
  opts: {
    dealName?: string;
    runId?: string;
    rowCount: number;
    columnCount: number;
  },
  t?: DDGridV1ExportI18n["t"],
  locale?: string,
): Array<[string, string]> {
  const meta: Array<[string, string]> = [];
  if (opts.dealName) {
    meta.push([t?.("exports:ddGridExport.meta.project") ?? "Project", opts.dealName]);
  }
  if (opts.runId) {
    meta.push([t?.("exports:ddGridExport.meta.runId") ?? "Run ID", opts.runId]);
  }
  meta.push([
    t?.("exports:ddGridExport.meta.date") ?? "Generated",
    formatExportTimestamp(locale ?? "en-US"),
  ]);
  meta.push([
    t?.("exports:ddGridExport.meta.rows") ?? "Records",
    String(opts.rowCount),
  ]);
  meta.push([
    t?.("exports:ddGridExport.meta.columns") ?? "Columns",
    String(opts.columnCount),
  ]);
  return meta;
}

// -------------------------------------------------------------
// Column width helpers
// -------------------------------------------------------------

function computeColumnWidths(
  headers: string[],
  rows: string[][],
): Array<{ wch: number }> {
  const MIN_WIDTH = 10;
  const MAX_WIDTH = 80;
  const PADDING = 2;

  return headers.map((header, colIndex) => {
    let maxLen = header.length;
    for (const row of rows) {
      const cell = row[colIndex] ?? "";
      const cellMax = cell
        .split("\n")
        .reduce((acc, line) => Math.max(acc, line.length), 0);
      if (cellMax > maxLen) maxLen = cellMax;
    }
    const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, maxLen + PADDING));
    return { wch: width };
  });
}

function computePdfColumnWidths(
  headers: string[],
  rows: string[][],
  availableWidth: number,
): number[] {
  const MIN_WIDTH_MM = 15;
  const CHAR_TO_MM_RATIO = 1.5;

  const rawWeights = headers.map((header, colIndex) => {
    let maxLen = header.length;
    for (const row of rows) {
      const cell = row[colIndex] ?? "";
      const lines = cell.split("\n");
      for (const line of lines) {
        if (line.length > maxLen) maxLen = line.length;
      }
    }
    return maxLen;
  });

  const idealWidths = rawWeights.map((w) => w * CHAR_TO_MM_RATIO);
  const idealTotal = idealWidths.reduce((acc, w) => acc + w, 0);

  if (idealTotal <= availableWidth) {
    return idealWidths.map((w) => Math.max(MIN_WIDTH_MM, w));
  }

  const minTotal = MIN_WIDTH_MM * headers.length;
  const flexAvailable = Math.max(0, availableWidth - minTotal);
  const excessWeights = idealWidths.map((w) => Math.max(0, w - MIN_WIDTH_MM));
  const excessTotal = excessWeights.reduce((acc, w) => acc + w, 0);

  if (excessTotal === 0) {
    return headers.map(() => availableWidth / headers.length);
  }

  return excessWeights.map(
    (w) => MIN_WIDTH_MM + (w / excessTotal) * flexAvailable,
  );
}

function computeWordColumnWidths(
  headers: string[],
  rows: string[][],
): number[] {
  const AVAILABLE_WIDTH_DXA = 15488;
  const MIN_WIDTH_DXA = 850;
  const CHAR_TO_DXA_RATIO = 85;

  const rawWeights = headers.map((header, colIndex) => {
    let maxLen = header.length;
    for (const row of rows) {
      const cell = row[colIndex] ?? "";
      const lines = cell.split("\n");
      for (const line of lines) {
        if (line.length > maxLen) maxLen = line.length;
      }
    }
    return maxLen;
  });

  const idealWidths = rawWeights.map((w) => w * CHAR_TO_DXA_RATIO);
  const idealTotal = idealWidths.reduce((acc, w) => acc + w, 0);

  if (idealTotal <= AVAILABLE_WIDTH_DXA) {
    return idealWidths.map((w) => Math.max(MIN_WIDTH_DXA, w));
  }

  const minTotal = MIN_WIDTH_DXA * headers.length;
  const flexAvailable = Math.max(0, AVAILABLE_WIDTH_DXA - minTotal);
  const excessWeights = idealWidths.map((w) =>
    Math.max(0, w * CHAR_TO_DXA_RATIO - MIN_WIDTH_DXA),
  );
  const excessTotal = excessWeights.reduce((acc, w) => acc + w, 0);

  if (excessTotal === 0) {
    return headers.map(() => AVAILABLE_WIDTH_DXA / headers.length);
  }

  return excessWeights.map(
    (w) => MIN_WIDTH_DXA + (w / excessTotal) * flexAvailable,
  );
}

// -------------------------------------------------------------
// Cyrillic font loader for jsPDF
// -------------------------------------------------------------

let cachedRegularFontBase64: string | null = null;
let cachedBoldFontBase64: string | null = null;

async function fetchFontAsBase64(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load font: ${url} (${response.status})`);
  }
  const arrayBuffer = await response.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, Array.from(chunk));
  }
  return btoa(binary);
}

async function applyCyrillicFontToPdf(doc: JsPDFType): Promise<boolean> {
  try {
    if (cachedRegularFontBase64 === null) {
      cachedRegularFontBase64 = await fetchFontAsBase64(
        "/fonts/LiberationSans-Regular.ttf",
      );
    }
    if (cachedBoldFontBase64 === null) {
      cachedBoldFontBase64 = await fetchFontAsBase64(
        "/fonts/LiberationSans-Bold.ttf",
      );
    }
    doc.addFileToVFS("LiberationSans-Regular.ttf", cachedRegularFontBase64);
    doc.addFont("LiberationSans-Regular.ttf", "LiberationSans", "normal");
    doc.addFileToVFS("LiberationSans-Bold.ttf", cachedBoldFontBase64);
    doc.addFont("LiberationSans-Bold.ttf", "LiberationSans", "bold");
    doc.setFont("LiberationSans", "normal");
    return true;
  } catch (error) {
    // eslint-disable-next-line no-console
    console.error("Failed to load Cyrillic font for PDF export:", error);
    return false;
  }
}

// -------------------------------------------------------------
// Shared PDF page footer helper
// -------------------------------------------------------------

function drawPdfPageFooter(
  doc: JsPDFType,
  fontName: string,
  t?: DDGridV1ExportI18n["t"],
): void {
  const pageCount = doc.getNumberOfPages();
  if (pageCount <= 1) return;
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFont(fontName, "normal");
    doc.setFontSize(8);
    doc.setTextColor(120);
    const text =
      t?.("exports:ddGridExport.pageFooter", { current: i, total: pageCount }) ??
      `Page ${i} of ${pageCount}`;
    doc.text(text, pageWidth / 2, pageHeight - 5, { align: "center" });
  }
}

// =============================================================
// LIST export — flat table
// =============================================================

export async function exportListToExcel(
  headers: string[],
  rows: string[][],
  opts: DDGridV1ExportFileOpts,
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const XLSX = await loadXLSX();
  const workbook = XLSX.utils.book_new();

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: rows.length, columnCount: headers.length },
    t,
    locale,
  );

  const title = t?.("exports:ddGridExport.title") ?? "DD Grid V1 — Export";
  const metadataSheetLabel = t?.("exports:ddGridExport.metadataSheet") ?? "Metadata";

  const metadataSheetData: (string | number)[][] = [
    [title],
    [],
    ...metadata.map(([label, value]) => [label, value]),
  ];
  const metadataSheet = XLSX.utils.aoa_to_sheet(metadataSheetData);
  metadataSheet["!cols"] = [{ wch: 25 }, { wch: 60 }];
  XLSX.utils.book_append_sheet(workbook, metadataSheet, metadataSheetLabel);

  const worksheetData: string[][] = [headers, ...rows];
  const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
  worksheet["!cols"] = computeColumnWidths(headers, rows);
  worksheet["!rows"] = [{ hpt: 22 }];
  worksheet["!freeze"] = { xSplit: 0, ySplit: 1 };
  XLSX.utils.book_append_sheet(workbook, worksheet, "DD Grid V1");

  XLSX.writeFile(workbook, buildFilename("xlsx", opts));
}

export async function exportListToPdf(
  headers: string[],
  rows: string[][],
  opts: DDGridV1ExportFileOpts,
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const { jsPDF } = await loadJsPDF();
  const autoTable = await loadAutoTable();

  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const fontApplied = await applyCyrillicFontToPdf(doc);
  const fontName = fontApplied ? "LiberationSans" : "helvetica";

  const title = t?.("exports:ddGridExport.title") ?? "DD Grid V1 — Export";
  doc.setFont(fontName, "bold");
  doc.setFontSize(16);
  doc.text(title, 14, 14);

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: rows.length, columnCount: headers.length },
    t,
    locale,
  );

  doc.setFont(fontName, "normal");
  doc.setFontSize(9);
  let currentY = 22;
  for (const [label, value] of metadata) {
    doc.text(`${label}: ${value}`, 14, currentY);
    currentY += 5;
  }
  currentY += 2;

  const pageWidth = doc.internal.pageSize.getWidth();
  const marginLeftRight = 8;
  const availableWidth = pageWidth - marginLeftRight * 2;

  const columnWidths = computePdfColumnWidths(headers, rows, availableWidth);
  const columnStyles: Record<number, { cellWidth: number }> = {};
  columnWidths.forEach((width, index) => {
    columnStyles[index] = { cellWidth: width };
  });

  autoTable(doc, {
    head: [headers],
    body: rows,
    startY: currentY,
    margin: { left: marginLeftRight, right: marginLeftRight },
    tableWidth: "wrap",
    styles: {
      font: fontName,
      fontStyle: "normal",
      fontSize: 7,
      cellPadding: 1.5,
      overflow: "linebreak",
      valign: "top",
      lineColor: [200, 200, 200],
      lineWidth: 0.1,
    },
    headStyles: {
      font: fontName,
      fontStyle: "bold",
      fontSize: 7,
      fillColor: [40, 40, 40],
      textColor: [255, 255, 255],
      halign: "left",
    },
    bodyStyles: { textColor: [30, 30, 30] },
    alternateRowStyles: { fillColor: [248, 248, 248] },
    columnStyles,
  });

  drawPdfPageFooter(doc, fontName, t);
  doc.save(buildFilename("pdf", opts));
}

export async function exportListToWord(
  headers: string[],
  rows: string[][],
  opts: DDGridV1ExportFileOpts,
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const docx = await loadDocx();
  const saveAs = await loadSaveAs();

  const {
    Document,
    HeadingLevel,
    Packer,
    PageOrientation,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextRun,
    WidthType,
  } = docx;

  const title = t?.("exports:ddGridExport.title") ?? "DD Grid V1 — Export";

  const paragraphs: ParagraphType[] = [
    new Paragraph({
      text: title,
      heading: HeadingLevel.TITLE,
    }),
  ];

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: rows.length, columnCount: headers.length },
    t,
    locale,
  );

  for (const [label, value] of metadata) {
    paragraphs.push(
      new Paragraph({
        children: [
          new TextRun({ text: `${label}: `, bold: true }),
          new TextRun({ text: value }),
        ],
      }),
    );
  }

  const columnWidthsDxa = computeWordColumnWidths(headers, rows);

  const wordCell = (
    text: string,
    widthDxa: number,
    bold = false,
  ): TableCellType =>
    new TableCell({
      width: { size: Math.round(widthDxa), type: WidthType.DXA },
      children: [
        new Paragraph({
          children: [new TextRun({ text, bold, size: 18 })],
        }),
      ],
    });

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => wordCell(h, columnWidthsDxa[i], true)),
  });

  const bodyRows = rows.map(
    (row) =>
      new TableRow({
        children: row.map((cell, i) =>
          wordCell(cell, columnWidthsDxa[i], false),
        ),
      }),
  );

  const table = new Table({
    rows: [headerRow, ...bodyRows],
    width: {
      size: columnWidthsDxa.reduce((acc, w) => acc + w, 0),
      type: WidthType.DXA,
    },
    layout: "fixed" as never,
  });

  const document = new Document({
    sections: [
      {
        properties: {
          page: {
            size: { orientation: PageOrientation.LANDSCAPE },
            margin: { top: 720, right: 720, bottom: 720, left: 720 },
          },
        },
        children: [...paragraphs, new Paragraph(""), table],
      },
    ],
  });

  const blob = await Packer.toBlob(document);
  saveAs(blob, buildFilename("docx", opts));
}

// =============================================================
// MATRIX export — Excel (единая таблица с merged headers)
// =============================================================

export async function exportMatrixToExcel(
  table: DDGridV1MatrixExportTable,
  opts: DDGridV1ExportFileOpts,
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const XLSX = await loadXLSX();
  const workbook = XLSX.utils.book_new();

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: table.rowCount, columnCount: table.leafHeaders.length },
    t,
    locale,
  );

  const title = t?.("exports:ddGridExport.titleMatrix") ?? "DD Grid V1 — Export (matrix)";
  const metadataSheetLabel = t?.("exports:ddGridExport.metadataSheet") ?? "Metadata";

  const metadataSheetData: (string | number)[][] = [
    [title],
    [],
    ...metadata.map(([label, value]) => [label, value]),
  ];
  const metadataSheet = XLSX.utils.aoa_to_sheet(metadataSheetData);
  metadataSheet["!cols"] = [{ wch: 25 }, { wch: 60 }];
  XLSX.utils.book_append_sheet(workbook, metadataSheet, metadataSheetLabel);

  const pinnedCount = table.pinnedColumnCount;
  const totalCols = pinnedCount + table.headerRows[2].length;
  const sheetData: string[][] = [];

  const headerRow0: string[] = new Array(totalCols).fill("");
  table.pinnedHeaders.forEach((label, i) => {
    headerRow0[i] = label;
  });
  let cIdx = pinnedCount;
  for (const cell of table.headerRows[0]) {
    headerRow0[cIdx] = cell.label;
    cIdx += cell.colSpan;
  }

  const headerRow1: string[] = new Array(totalCols).fill("");
  cIdx = pinnedCount;
  for (const cell of table.headerRows[1]) {
    headerRow1[cIdx] = cell.label;
    cIdx += cell.colSpan;
  }

  const headerRow2: string[] = new Array(totalCols).fill("");
  cIdx = pinnedCount;
  for (const cell of table.headerRows[2]) {
    headerRow2[cIdx] = cell.label;
    cIdx += cell.colSpan;
  }

  sheetData.push(headerRow0, headerRow1, headerRow2, ...table.rows);
  const worksheet = XLSX.utils.aoa_to_sheet(sheetData);

  const merges: XLSXType.Range[] = [];
  for (let i = 0; i < pinnedCount; i++) {
    merges.push({ s: { r: 0, c: i }, e: { r: 2, c: i } });
  }
  let mergeStart = pinnedCount;
  for (const cell of table.headerRows[0]) {
    if (cell.colSpan > 1) {
      merges.push({
        s: { r: 0, c: mergeStart },
        e: { r: 0, c: mergeStart + cell.colSpan - 1 },
      });
    }
    mergeStart += cell.colSpan;
  }
  mergeStart = pinnedCount;
  for (const cell of table.headerRows[1]) {
    if (cell.colSpan > 1) {
      merges.push({
        s: { r: 1, c: mergeStart },
        e: { r: 1, c: mergeStart + cell.colSpan - 1 },
      });
    }
    mergeStart += cell.colSpan;
  }
  worksheet["!merges"] = merges;

  const combinedForWidth = [headerRow0, headerRow1, headerRow2, ...table.rows];
  worksheet["!cols"] = computeColumnWidths(
    new Array(totalCols).fill(""),
    combinedForWidth,
  );
  worksheet["!rows"] = [{ hpt: 20 }, { hpt: 20 }, { hpt: 22 }];
  worksheet["!freeze"] = { xSplit: pinnedCount, ySplit: 3 };

  XLSX.utils.book_append_sheet(workbook, worksheet, "DD Grid V1");
  XLSX.writeFile(workbook, buildFilename("xlsx", opts));
}

// =============================================================
// MATRIX export — Layout 1: PDF (single wide table)
// =============================================================

export async function exportMatrixSingleToPdf(
  table: DDGridV1MatrixExportTable,
  opts: DDGridV1ExportFileOpts,
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const { jsPDF } = await loadJsPDF();
  const autoTable = await loadAutoTable();

  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const fontApplied = await applyCyrillicFontToPdf(doc);
  const fontName = fontApplied ? "LiberationSans" : "helvetica";

  const title = t?.("exports:ddGridExport.titleSingle") ?? "DD Grid V1 — Export (single table)";
  doc.setFont(fontName, "bold");
  doc.setFontSize(16);
  doc.text(title, 14, 14);

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: table.rowCount, columnCount: table.leafHeaders.length },
    t,
    locale,
  );

  doc.setFont(fontName, "normal");
  doc.setFontSize(9);
  let currentY = 22;
  for (const [label, value] of metadata) {
    doc.text(`${label}: ${value}`, 14, currentY);
    currentY += 5;
  }
  currentY += 2;

  const pageWidth = doc.internal.pageSize.getWidth();
  const marginLeftRight = 8;
  const availableWidth = pageWidth - marginLeftRight * 2;

  const headRow0: Array<{
    content: string;
    colSpan?: number;
    rowSpan?: number;
  }> = [];
  for (const label of table.pinnedHeaders) {
    headRow0.push({ content: label, rowSpan: 3 });
  }
  for (const cell of table.headerRows[0]) {
    headRow0.push({ content: cell.label, colSpan: cell.colSpan });
  }
  const headRow1: Array<{ content: string; colSpan?: number }> = [];
  for (const cell of table.headerRows[1]) {
    headRow1.push({ content: cell.label, colSpan: cell.colSpan });
  }
  const headRow2 = table.headerRows[2].map((c) => c.label);

  const columnWidths = computePdfColumnWidths(
    table.leafHeaders,
    table.rows,
    availableWidth,
  );
  const columnStyles: Record<number, { cellWidth: number }> = {};
  columnWidths.forEach((width, index) => {
    columnStyles[index] = { cellWidth: width };
  });

  autoTable(doc, {
    head: [headRow0, headRow1, headRow2],
    body: table.rows,
    startY: currentY,
    margin: { left: marginLeftRight, right: marginLeftRight },
    tableWidth: "wrap",
    styles: {
      font: fontName,
      fontStyle: "normal",
      fontSize: 7,
      cellPadding: 1.5,
      overflow: "linebreak",
      valign: "top",
      lineColor: [200, 200, 200],
      lineWidth: 0.1,
    },
    headStyles: {
      font: fontName,
      fontStyle: "bold",
      fontSize: 7,
      fillColor: [40, 40, 40],
      textColor: [255, 255, 255],
      halign: "left",
    },
    bodyStyles: { textColor: [30, 30, 30] },
    alternateRowStyles: { fillColor: [248, 248, 248] },
    columnStyles,
  });

  drawPdfPageFooter(doc, fontName, t);
  doc.save(buildFilename("pdf", { ...opts, layoutSuffix: "single" }));
}

// =============================================================
// MATRIX export — Layout 1: Word (single wide table)
// =============================================================

export async function exportMatrixSingleToWord(
  table: DDGridV1MatrixExportTable,
  opts: DDGridV1ExportFileOpts,
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const docx = await loadDocx();
  const saveAs = await loadSaveAs();

  const {
    Document,
    HeadingLevel,
    Packer,
    PageOrientation,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextRun,
    WidthType,
  } = docx;

  const title = t?.("exports:ddGridExport.titleSingle") ?? "DD Grid V1 — Export (single table)";

  const paragraphs: ParagraphType[] = [
    new Paragraph({
      text: title,
      heading: HeadingLevel.TITLE,
    }),
  ];

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: table.rowCount, columnCount: table.leafHeaders.length },
    t,
    locale,
  );

  for (const [label, value] of metadata) {
    paragraphs.push(
      new Paragraph({
        children: [
          new TextRun({ text: `${label}: `, bold: true }),
          new TextRun({ text: value }),
        ],
      }),
    );
  }

  const columnWidthsDxa = computeWordColumnWidths(
    table.leafHeaders,
    table.rows,
  );
  const pinnedCount = table.pinnedColumnCount;

  const buildCell = (
    text: string,
    widthDxa: number,
    cellOpts?: {
      bold?: boolean;
      columnSpan?: number;
      rowSpan?: number;
      shading?: string;
    },
  ): TableCellType => {
    return new TableCell({
      width: { size: Math.round(widthDxa), type: WidthType.DXA },
      columnSpan: cellOpts?.columnSpan,
      rowSpan: cellOpts?.rowSpan,
      shading: cellOpts?.shading
        ? { fill: cellOpts.shading, type: "clear", color: "auto" }
        : undefined,
      children: [
        new Paragraph({
          children: [
            new TextRun({ text, bold: cellOpts?.bold, size: 18 }),
          ],
        }),
      ],
    });
  };

  const headerRow0Cells: TableCellType[] = [];
  for (let i = 0; i < pinnedCount; i++) {
    headerRow0Cells.push(
      buildCell(table.pinnedHeaders[i], columnWidthsDxa[i], {
        bold: true,
        rowSpan: 3,
        shading: "1F2937",
      }),
    );
  }
  let colIdx = pinnedCount;
  for (const cell of table.headerRows[0]) {
    let combinedWidth = 0;
    for (let k = 0; k < cell.colSpan; k++) {
      combinedWidth += columnWidthsDxa[colIdx + k];
    }
    headerRow0Cells.push(
      buildCell(cell.label, combinedWidth, {
        bold: true,
        columnSpan: cell.colSpan,
        shading: "374151",
      }),
    );
    colIdx += cell.colSpan;
  }

  const headerRow1Cells: TableCellType[] = [];
  colIdx = pinnedCount;
  for (const cell of table.headerRows[1]) {
    let combinedWidth = 0;
    for (let k = 0; k < cell.colSpan; k++) {
      combinedWidth += columnWidthsDxa[colIdx + k];
    }
    headerRow1Cells.push(
      buildCell(cell.label, combinedWidth, {
        bold: true,
        columnSpan: cell.colSpan,
        shading: "4B5563",
      }),
    );
    colIdx += cell.colSpan;
  }

  const headerRow2Cells: TableCellType[] = [];
  colIdx = pinnedCount;
  for (const cell of table.headerRows[2]) {
    headerRow2Cells.push(
      buildCell(cell.label, columnWidthsDxa[colIdx], {
        bold: true,
        shading: "6B7280",
      }),
    );
    colIdx += 1;
  }

  const bodyRows = table.rows.map(
    (row) =>
      new TableRow({
        children: row.map((cellText, i) =>
          buildCell(cellText, columnWidthsDxa[i], { bold: false }),
        ),
      }),
  );

  const wordTable = new Table({
    rows: [
      new TableRow({ tableHeader: true, children: headerRow0Cells }),
      new TableRow({ tableHeader: true, children: headerRow1Cells }),
      new TableRow({ tableHeader: true, children: headerRow2Cells }),
      ...bodyRows,
    ],
    width: {
      size: columnWidthsDxa.reduce((acc, w) => acc + w, 0),
      type: WidthType.DXA,
    },
    layout: "fixed" as never,
  });

  const document = new Document({
    sections: [
      {
        properties: {
          page: {
            size: { orientation: PageOrientation.LANDSCAPE },
            margin: { top: 720, right: 720, bottom: 720, left: 720 },
          },
        },
        children: [...paragraphs, new Paragraph(""), wordTable],
      },
    ],
  });

  const blob = await Packer.toBlob(document);
  saveAs(blob, buildFilename("docx", { ...opts, layoutSuffix: "single" }));
}

// =============================================================
// MATRIX export — Layout 2 & 3: sectioned PDF/Word
// =============================================================

export async function exportSectionedToPdf(
  sectionedTable: DDGridV1SectionedExportTable,
  opts: DDGridV1ExportFileOpts & {
    titleSuffix: string;
    layoutSuffix: string;
  },
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const { jsPDF } = await loadJsPDF();
  const autoTable = await loadAutoTable();

  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const fontApplied = await applyCyrillicFontToPdf(doc);
  const fontName = fontApplied ? "LiberationSans" : "helvetica";

  const title = t
    ? t("exports:ddGridExport.titleSectioned", { suffix: opts.titleSuffix })
    : `DD Grid V1 — Export (${opts.titleSuffix})`;

  doc.setFont(fontName, "bold");
  doc.setFontSize(16);
  doc.text(title, 14, 14);

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: sectionedTable.totalRowCount, columnCount: sectionedTable.maxColumnCount },
    t,
    locale,
  );

  doc.setFont(fontName, "normal");
  doc.setFontSize(9);
  let currentY = 22;
  for (const [label, value] of metadata) {
    doc.text(`${label}: ${value}`, 14, currentY);
    currentY += 5;
  }
  currentY += 4;

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const marginLeftRight = 8;
  const availableWidth = pageWidth - marginLeftRight * 2;

  for (const section of sectionedTable.sections) {
    if (currentY > pageHeight - 40) {
      doc.addPage();
      currentY = 14;
    }

    doc.setFont(fontName, "bold");
    doc.setFontSize(12);
    doc.text(section.title, 14, currentY);
    currentY += 5;

    if (section.subtitle) {
      doc.setFont(fontName, "normal");
      doc.setFontSize(9);
      doc.setTextColor(100);
      doc.text(section.subtitle, 14, currentY);
      currentY += 5;
      doc.setTextColor(0);
    }
    currentY += 1;

    const columnWidths = computePdfColumnWidths(
      section.headers,
      section.rows,
      availableWidth,
    );
    const columnStyles: Record<number, { cellWidth: number }> = {};
    columnWidths.forEach((width, index) => {
      columnStyles[index] = { cellWidth: width };
    });

    autoTable(doc, {
      head: [section.headers],
      body: section.rows,
      startY: currentY,
      margin: { left: marginLeftRight, right: marginLeftRight },
      tableWidth: "wrap",
      styles: {
        font: fontName,
        fontStyle: "normal",
        fontSize: 8,
        cellPadding: 1.8,
        overflow: "linebreak",
        valign: "top",
        lineColor: [200, 200, 200],
        lineWidth: 0.1,
      },
      headStyles: {
        font: fontName,
        fontStyle: "bold",
        fontSize: 8,
        fillColor: [40, 40, 40],
        textColor: [255, 255, 255],
        halign: "left",
      },
      bodyStyles: { textColor: [30, 30, 30] },
      alternateRowStyles: { fillColor: [248, 248, 248] },
      columnStyles,
    });

    const lastTable = (doc as unknown as { lastAutoTable?: { finalY: number } })
      .lastAutoTable;
    currentY = lastTable ? lastTable.finalY + 8 : currentY + 30;
  }

  drawPdfPageFooter(doc, fontName, t);
  doc.save(buildFilename("pdf", opts));
}

export async function exportSectionedToWord(
  sectionedTable: DDGridV1SectionedExportTable,
  opts: DDGridV1ExportFileOpts & {
    titleSuffix: string;
    layoutSuffix: string;
  },
): Promise<void> {
  const t = opts.i18n?.t;
  const locale = opts.i18n?.locale ?? "en-US";
  const docx = await loadDocx();
  const saveAs = await loadSaveAs();

  const {
    Document,
    HeadingLevel,
    Packer,
    PageOrientation,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextRun,
    WidthType,
  } = docx;

  const title = t
    ? t("exports:ddGridExport.titleSectioned", { suffix: opts.titleSuffix })
    : `DD Grid V1 — Export (${opts.titleSuffix})`;

  const paragraphs: ParagraphType[] = [
    new Paragraph({
      text: title,
      heading: HeadingLevel.TITLE,
    }),
  ];

  const metadata = buildExportMetadata(
    { dealName: opts.dealName, runId: opts.runId, rowCount: sectionedTable.totalRowCount, columnCount: sectionedTable.maxColumnCount },
    t,
    locale,
  );

  for (const [label, value] of metadata) {
    paragraphs.push(
      new Paragraph({
        children: [
          new TextRun({ text: `${label}: `, bold: true }),
          new TextRun({ text: value }),
        ],
      }),
    );
  }
  paragraphs.push(new Paragraph(""));

  const wordCell = (
    text: string,
    widthDxa: number,
    bold = false,
    shading?: string,
  ): TableCellType =>
    new TableCell({
      width: { size: Math.round(widthDxa), type: WidthType.DXA },
      shading: shading
        ? { fill: shading, type: "clear", color: "auto" }
        : undefined,
      children: [
        new Paragraph({
          children: [new TextRun({ text, bold, size: 18 })],
        }),
      ],
    });

  const sectionChildren: Array<ParagraphType | TableType> = [...paragraphs];

  for (const section of sectionedTable.sections) {
    sectionChildren.push(
      new Paragraph({
        text: section.title,
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 240, after: 60 },
      }),
    );

    if (section.subtitle) {
      sectionChildren.push(
        new Paragraph({
          children: [
            new TextRun({
              text: section.subtitle,
              italics: true,
              size: 20,
              color: "666666",
            }),
          ],
          spacing: { after: 120 },
        }),
      );
    }

    const columnWidthsDxa = computeWordColumnWidths(
      section.headers,
      section.rows,
    );

    const headerRow = new TableRow({
      tableHeader: true,
      children: section.headers.map((h, i) =>
        wordCell(h, columnWidthsDxa[i], true, "374151"),
      ),
    });

    const bodyRows = section.rows.map(
      (row) =>
        new TableRow({
          children: row.map((cell, i) =>
            wordCell(cell, columnWidthsDxa[i], false),
          ),
        }),
    );

    const table = new Table({
      rows: [headerRow, ...bodyRows],
      width: {
        size: columnWidthsDxa.reduce((acc, w) => acc + w, 0),
        type: WidthType.DXA,
      },
      layout: "fixed" as never,
    });

    sectionChildren.push(table);
    sectionChildren.push(new Paragraph(""));
  }

  const document = new Document({
    sections: [
      {
        properties: {
          page: {
            size: { orientation: PageOrientation.LANDSCAPE },
            margin: { top: 720, right: 720, bottom: 720, left: 720 },
          },
        },
        children: sectionChildren,
      },
    ],
  });

  const blob = await Packer.toBlob(document);
  saveAs(blob, buildFilename("docx", opts));
}


