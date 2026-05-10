// =============================================================
// src/pages/tabs/grid/reviewGrid.exportUtils.ts
// Review-native utilities для экспорта ReviewExportRow[] в Excel / PDF / Word.
// Без зависимости от legacy CheckResult[].
//
// Для непрофессионального программиста:
// Этот файл берёт готовые ReviewExportRow[] и генерирует из них
// конкретные файлы: XLSX, PDF, DOCX.
// =============================================================

import * as XLSX from "xlsx";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import { saveAs } from "file-saver";
import {
  Document,
  Packer,
  Paragraph,
  Table,
  TableRow,
  TableCell,
  HeadingLevel,
  TextRun,
} from "docx";

import type { ReviewExportRow } from "./reviewGrid.types";
import { buildReviewExportTableRows } from "./reviewGrid.export";

interface ReviewExportOptions {
  dealName?: string;
  runId?: string;
}

/**
 * Убирает небезопасные символы из имени файла.
 */
function sanitizeFilePart(s: string): string {
  return s.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 50);
}

/**
 * Строит базовое имя файла для export.
 */
function buildBaseFilename(
  suffix: "xlsx" | "pdf" | "docx",
  opts?: ReviewExportOptions,
): string {
  const deal = opts?.dealName ? `_${sanitizeFilePart(opts.dealName)}` : "";
  const run = opts?.runId ? `_run_${sanitizeFilePart(opts.runId)}` : "";
  return `dd_review_results${deal}${run}.${suffix}`;
}

/**
 * Строит подзаголовок для файла экспорта.
 */
function buildSubtitle(opts?: ReviewExportOptions): string {
  const parts: string[] = [];
  if (opts?.dealName) parts.push(`Deal: ${opts.dealName}`);
  if (opts?.runId) parts.push(`Run: ${opts.runId}`);
  return parts.join(" | ");
}

/**
 * Создаёт TableCell для Word export.
 */
function wordCell(text: string, bold = false): TableCell {
  return new TableCell({
    children: [
      new Paragraph({
        children: [new TextRun({ text, bold })],
      }),
    ],
  });
}

/**
 * Экспортирует review rows в Excel.
 *
 * Для непрофессионального программиста:
 * Использует готовый buildReviewExportTableRows(),
 * который уже привёл все значения к строковому виду.
 */
export function exportReviewRowsToExcel(
  rows: ReviewExportRow[],
  opts?: ReviewExportOptions,
): void {
  if (!rows.length) return;

  const tableRows = buildReviewExportTableRows(rows);
  const worksheet = XLSX.utils.json_to_sheet(tableRows);
  const workbook = XLSX.utils.book_new();

  XLSX.utils.book_append_sheet(workbook, worksheet, "Review Results");
  XLSX.writeFile(workbook, buildBaseFilename("xlsx", opts));
}

/**
 * Экспортирует review rows в PDF.
 *
 * Для непрофессионального программиста:
 * Использует jsPDF + autoTable для построения landscape-таблицы.
 * Теперь берёт готовые ReviewExportTableRow[] для единообразия форматирования.
 */
export function exportReviewRowsToPdf(
  rows: ReviewExportRow[],
  opts?: ReviewExportOptions,
): void {
  if (!rows.length) return;

  const doc = new jsPDF({ orientation: "landscape" });

  const title = "Due Diligence Review Results";
  const subtitle = buildSubtitle(opts);

  doc.setFontSize(16);
  doc.text(title, 14, 14);

  if (subtitle) {
    doc.setFontSize(11);
    doc.text(subtitle, 14, 22);
  }

  const tableRows = buildReviewExportTableRows(rows);

  const head = [[
    "Document",
    "Segment",
    "Check",
    "Origin",
    "Result",
    "Severity",
    "QC",
    "Conf",
    "Page",
    "Clause UID",
    "Conditional",
    "Snippet",
  ]];

  const body = tableRows.map((row) => [
    row["Document"],
    row["Segment Title"] || row["Segment ID"],
    row["Check"],
    row["Origin"],
    row["Result"],
    row["Severity"],
    row["QC"],
    row["Confidence"],
    row["Page"],
    row["Clause UID"],
    row["Conditional"],
    (row["Snippet"] || "").slice(0, 120),
  ]);

  autoTable(doc, {
    head,
    body,
    startY: subtitle ? 28 : 20,
    styles: {
      fontSize: 7,
      cellWidth: "wrap",
      overflow: "linebreak",
    },
    headStyles: {
      fillColor: [40, 40, 40],
    },
  });

  doc.save(buildBaseFilename("pdf", opts));
}

/**
 * Экспортирует review rows в Word.
 *
 * Для непрофессионального программиста:
 * Использует docx library для построения Word-документа с таблицей.
 * Теперь берёт готовые ReviewExportTableRow[] для единообразия форматирования.
 */
export async function exportReviewRowsToWord(
  rows: ReviewExportRow[],
  opts?: ReviewExportOptions,
): Promise<void> {
  if (!rows.length) return;

  const subtitle = buildSubtitle(opts);

  const paragraphs: Paragraph[] = [
    new Paragraph({
      text: "Due Diligence Review Results",
      heading: HeadingLevel.TITLE,
    }),
  ];

  if (subtitle) {
    paragraphs.push(
      new Paragraph({
        text: subtitle,
      }),
    );
  }

  paragraphs.push(
    new Paragraph({
      text: `Total findings: ${rows.length}`,
    }),
  );

  const tableRows = buildReviewExportTableRows(rows);

  const tableHeader = new TableRow({
    children: [
      wordCell("Document", true),
      wordCell("Segment", true),
      wordCell("Check", true),
      wordCell("Result", true),
      wordCell("Severity", true),
      wordCell("QC", true),
      wordCell("Confidence", true),
      wordCell("Conditional", true),
    ],
  });

  const docxTableRows = tableRows.map(
    (row) =>
      new TableRow({
        children: [
          wordCell(row["Document"]),
          wordCell(row["Segment Title"] || row["Segment ID"]),
          wordCell(row["Check"]),
          wordCell(row["Result"]),
          wordCell(row["Severity"]),
          wordCell(row["QC"]),
          wordCell(row["Confidence"]),
          wordCell(row["Conditional"]),
        ],
      }),
  );

  const table = new Table({
    rows: [tableHeader, ...docxTableRows],
    width: { size: 100, type: "pct" },
  });

  const document = new Document({
    sections: [
      {
        children: [...paragraphs, new Paragraph(""), table],
      },
    ],
  });

  const blob = await Packer.toBlob(document);
  saveAs(blob, buildBaseFilename("docx", opts));
}




