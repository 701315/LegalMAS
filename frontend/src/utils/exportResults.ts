// =============================================================
// src/utils/exportResults.ts
// Утилиты экспорта CheckResult[] в Excel / PDF / Word.
// =============================================================

import type { CheckResult } from "../types";
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

interface ExportOptions {
  dealName?: string;
  runId?: string;
}

/** Преобразуем CheckResult в плоский объект для табличного экспорта. */
function mapResultToRow(r: CheckResult) {
  const flagsArray =
    Array.isArray(r.quality_flags) ? r.quality_flags : [];
  return {
    Risk: r.severity,
    Summary: r.value_text ?? "",
    Check: r.check_name ?? "",
    Document: r.document_name ?? "",
    "Doc Type": r.doc_type ?? "",
    "Doc Class": r.doc_classification_level ?? "",
    "Doc Class Conf": r.doc_classification_confidence ?? "",
    Result: r.result ?? "",
    Confidence:
      r.confidence != null ? Math.round(r.confidence * 100) + "%" : "",
    QC: r.qc_status ?? "",
    Flags: flagsArray.join(", "),
    Conditional: r.conditional_check_triggered ? "Yes" : "No",
    Trigger: r.trigger_name ?? "",
    Detector: r.detector_used ?? "",
    Created: r.created_at ?? "",
  };
}

// ------------------------ Excel ------------------------

export function exportResultsToExcel(
  results: CheckResult[],
  opts?: ExportOptions,
) {
  const rows = results.map(mapResultToRow);
  const worksheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Results");

  const deal = opts?.dealName ? `_${sanitizeFilePart(opts.dealName)}` : "";
  const run = opts?.runId ? `_run_${sanitizeFilePart(opts.runId)}` : "";
  const filename = `dd_results${deal}${run}.xlsx`;

  XLSX.writeFile(workbook, filename);
}

// ------------------------ PDF ------------------------

export function exportResultsToPdf(
  results: CheckResult[],
  opts?: ExportOptions,
) {
  const doc = new jsPDF({ orientation: "landscape" });

  const title = "Due Diligence Results";
  const subtitleParts: string[] = [];
  if (opts?.dealName) subtitleParts.push(`Deal: ${opts.dealName}`);
  if (opts?.runId) subtitleParts.push(`Run: ${opts.runId}`);
  const subtitle = subtitleParts.join(" | ");

  doc.setFontSize(16);
  doc.text(title, 14, 14);
  if (subtitle) {
    doc.setFontSize(11);
    doc.text(subtitle, 14, 22);
  }

  const head = [
    [
      "Risk",
      "Summary",
      "Check",
      "Document",
      "Doc Type",
      "Doc Class",
      "Result",
      "Conf",
      "QC",
      "Flags",
      "Cond",
      "Trigger",
      "Detector",
      "Created",
    ],
  ];

  const body = results.map((r) => {
    const flagsArray =
      Array.isArray(r.quality_flags) ? (r.quality_flags as string[]) : [];

    return [
      r.severity ?? "",
      (r.value_text ?? "").slice(0, 120),
      r.check_name ?? "",
      r.document_name ?? "",
      r.doc_type ?? "",
      r.doc_classification_level ?? "",
      r.result ?? "",
      r.confidence != null ? Math.round(r.confidence * 100) + "%" : "",
      r.qc_status ?? "",
      flagsArray.join(", "),
      r.conditional_check_triggered ? "Yes" : "No",
      r.trigger_name ?? "",
      r.detector_used ?? "",
      r.created_at ?? "",
    ];
  });

  // ✅ ИСПРАВЛЕНИЕ: вызываем autoTable как функцию, передав doc первым аргументом
  autoTable(doc, {
    head,
    body,
    startY: subtitle ? 28 : 20,
    styles: { fontSize: 7, cellWidth: "wrap" },
    headStyles: { fillColor: [40, 40, 40] },
  });

  const deal = opts?.dealName ? `_${sanitizeFilePart(opts.dealName)}` : "";
  const run = opts?.runId ? `_run_${sanitizeFilePart(opts.runId)}` : "";
  const filename = `dd_results${deal}${run}.pdf`;

  doc.save(filename);
}

// ------------------------ Word (docx) ------------------------

export async function exportResultsToWord(
  results: CheckResult[],
  opts?: ExportOptions,
) {
  const subtitleParts: string[] = [];
  if (opts?.dealName) subtitleParts.push(`Deal: ${opts.dealName}`);
  if (opts?.runId) subtitleParts.push(`Run: ${opts.runId}`);
  const subtitleText = subtitleParts.join(" | ");

  const docParagraphs: Paragraph[] = [
    new Paragraph({
      text: "Due Diligence Results",
      heading: HeadingLevel.TITLE,
    }),
  ];

  if (subtitleText) {
    docParagraphs.push(
      new Paragraph({
        text: subtitleText,
      }),
    );
  }

  docParagraphs.push(
    new Paragraph({
      text: `Total results: ${results.length}`,
    }),
  );

  // Таблица с результатами (основные поля, чтобы Word не раздувался)
  const tableHeader = new TableRow({
    children: [
      cell("Risk", true),
      cell("Summary", true),
      cell("Check", true),
      cell("Document", true),
      cell("Result", true),
      cell("Conf", true),
      cell("QC", true),
      cell("Conditional", true),
    ],
  });

  const tableRows = results.map(
    (r) =>
      new TableRow({
        children: [
          cell(r.severity ?? ""),
          cell((r.value_text ?? "").slice(0, 200)),
          cell(r.check_name ?? ""),
          cell(r.document_name ?? ""),
          cell(r.result ?? ""),
          cell(
            r.confidence != null
              ? Math.round(r.confidence * 100) + "%"
              : "",
          ),
          cell(r.qc_status ?? ""),
          cell(r.conditional_check_triggered ? "Yes" : "No"),
        ],
      }),
  );

  const table = new Table({
    rows: [tableHeader, ...tableRows],
    width: { size: 100, type: "pct" },
  });

  docParagraphs.push(new Paragraph("")); // небольшой отступ
  const document = new Document({
    sections: [
      {
        children: [...docParagraphs, table],
      },
    ],
  });

  const blob = await Packer.toBlob(document);

  const deal = opts?.dealName ? `_${sanitizeFilePart(opts.dealName)}` : "";
  const run = opts?.runId ? `_run_${sanitizeFilePart(opts.runId)}` : "";
  const filename = `dd_results${deal}${run}.docx`;

  saveAs(blob, filename);
}

// ------------------------ Helpers ------------------------

function cell(text: string, bold = false) {
  return new TableCell({
    children: [
      new Paragraph({
        children: [new TextRun({ text, bold })],
      }),
    ],
  });
}

function sanitizeFilePart(s: string) {
  return s.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 50);
}
