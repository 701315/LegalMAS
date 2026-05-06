// =============================================================
// src/pages/tabs/DocumentsTab.tsx
// Вкладка "Документы":
// - таблица на всю ширину по умолчанию
// - при выборе документа справа открывается панель деталей (1/3 ширины)
// - при открытии стадии pipeline таблица скрывается,
//   preview занимает 2/3, детали документа — 1/3
// - имя выбранного файла показывается в шапке панели деталей
// =============================================================

import React, { useMemo, useRef, useState } from "react";
import {
  useDocuments,
  useDocumentsWithClassification,
  exportDocumentsExcel,
  exportDocumentsWord,
  exportDocumentsPDF,
} from "../../api/documents";
import type {
  Deal,
  DocumentListItem,
  OpenViewerAtPayload,
  PipelineStageViewDTO,
} from "../../types";
import { ALL_DOCUMENT_COLUMNS } from "../../types";
import type { DocumentColumnDef, DocumentColumnId } from "../../types";
import { ChevronRight, Download } from "lucide-react";

import DocumentDetailsContainer from "../../components/documents/DocumentDetailsContainer";
import PipelineStagePreviewPane from "../../components/documents/pipeline/PipelineStagePreviewPane";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";
import {
  DOCUMENT_STATUS_CONFIG,
  getErrorStageLabel,
} from "../../utils/statusConfig";
import { getCompositionCellValue } from "../../utils/compositionHelpers";
import Button from "../../components/ui/Button";

interface DocumentsTabProps {
  deal: Deal;
  runId: string | null;
  openViewerAt?: OpenViewerAtPayload | null;
  onViewerLocationConsumed?: () => void;
}

const LOW_CONFIDENCE_THRESHOLD = 0.6;

interface ClassificationStats {
  L0: number;
  L1: number;
  L2: number;
  L3: number;
  L4: number;
  L_manual: number;
  low_confidence: number;
}

interface PipelinePreviewState {
  stage: PipelineStageViewDTO;
  stages: PipelineStageViewDTO[];
}

function formatRiskLevel(risk: string | null | undefined): string {
  if (!risk) return "";
  switch (risk) {
    case "low":
      return "Низкий";
    case "medium":
      return "Средний";
    case "high":
      return "Высокий";
    case "critical":
      return "Критический";
    default:
      return risk;
  }
}

function formatDateTime(value: string | undefined | null): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function hasProcessingError(doc: DocumentListItem): boolean {
  if (doc.status === "failed" || doc.status === "quarantine") return true;
  const details = doc.processing_error_details;
  if (!details) return false;
  return Boolean(details.message || details.type);
}

const ClassificationWarningBanner: React.FC<{
  count: number;
  docs: DocumentListItem[];
  isExpanded: boolean;
  onToggle: () => void;
  onSelectDoc: (id: string) => void;
}> = ({ count, docs, isExpanded, onToggle, onSelectDoc }) => (
  <div className="border-b border-[var(--border-subtle)]">
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-warning-subtle)] text-[10px] font-semibold text-[var(--color-warning)]">
          {count}
        </span>
        <span className="text-xs font-medium text-[var(--color-warning)]">
          Требуют проверки классификации
        </span>
      </div>
      <span className="text-[11px] text-[var(--text-muted)]">
        {isExpanded ? "Скрыть ▲" : "Показать ▼"}
      </span>
    </button>

    {isExpanded && (
      <div className="border-t border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] px-4 py-2">
        <div className="max-h-48 space-y-0.5 overflow-y-auto">
          {docs.map((doc) => (
            <button
              key={doc.id}
              type="button"
              onClick={() => onSelectDoc(doc.id)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-[var(--text-primary)]">
                  {doc.filename}
                </p>
                <p className="truncate text-[11px] text-[var(--text-muted)]">
                  {doc.doc_type || "Тип не определён"}
                </p>
              </div>
              <ClassificationBadge
                level={doc.classification_level}
                confidence={doc.classification_confidence}
                showConfidence={false}
                className="shrink-0"
              />
            </button>
          ))}
        </div>
      </div>
    )}
  </div>
);

const ColumnSelectorInlinePanel: React.FC<{
  tempSelectedIds: DocumentColumnId[];
  hasChanges: boolean;
  onToggle: (id: DocumentColumnId) => void;
  onApply: () => void;
  onReset: () => void;
  onCancel: () => void;
}> = ({
  tempSelectedIds,
  hasChanges,
  onToggle,
  onApply,
  onReset,
  onCancel,
}) => (
  <div
    id="documents-columns-panel"
    className="border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5 py-4"
  >
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          Отображаемые колонки
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          Нажмите на поле, чтобы показать или скрыть его в таблице
        </p>
      </div>

      <div className="px-4 py-4">
        <div className="flex flex-wrap gap-2">
          {ALL_DOCUMENT_COLUMNS.map((col) => {
            const isSelected = tempSelectedIds.includes(col.id);

            return (
              <Button
                key={col.id}
                type="button"
                size="sm"
                variant={isSelected ? "outline" : "secondary"}
                onClick={() => onToggle(col.id)}
                aria-pressed={isSelected}
                title={col.description}
                className={
                  isSelected
                    ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
                    : ""
                }
              >
                {col.label}
              </Button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
        <Button size="sm" variant="ghost" onClick={onReset}>
          По умолчанию
        </Button>

        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={onCancel}>
            Отмена
          </Button>

          <Button
            size="sm"
            variant="secondary"
            onClick={onApply}
            disabled={!hasChanges}
            title={
              hasChanges
                ? "Применить изменения отображаемых колонок"
                : "Сначала измените набор отображаемых колонок"
            }
            className={
              hasChanges
                ? ""
                : "disabled:opacity-100 disabled:border-[var(--border-subtle)] disabled:bg-[var(--bg-elevated-soft)] disabled:text-[var(--text-muted)] disabled:shadow-none disabled:ring-0"
            }
          >
            Применить
          </Button>
        </div>
      </div>
    </div>
  </div>
);

const ExportMenu: React.FC<{
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onExportExcel: () => void;
  onExportWord: () => void;
  onExportPDF: () => void;
}> = ({
  isOpen,
  onToggle,
  onClose,
  onExportExcel,
  onExportWord,
  onExportPDF,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  return (
    <div ref={containerRef} className="relative flex items-center">
      <Button
        type="button"
        size="sm"
        variant={isOpen ? "outline" : "secondary"}
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls="documents-export-slideout"
        leftIcon={<Download className="h-4 w-4" />}
        rightIcon={
          <ChevronRight
            className={`h-4 w-4 transition-transform duration-200 ${
              isOpen ? "rotate-90" : "rotate-0"
            }`}
          />
        }
        className={
          isOpen
            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
            : ""
        }
      >
        Сохранить список документов
      </Button>

      <div
        id="documents-export-slideout"
        className={`ml-2 flex origin-left items-center gap-2 overflow-hidden transition-all duration-300 ease-out ${
          isOpen
            ? "max-w-[340px] translate-x-0 opacity-100"
            : "pointer-events-none max-w-0 -translate-x-2 opacity-0"
        }`}
        aria-hidden={!isOpen}
      >
        <div className="flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-2 py-1.5 shadow-sm">
          <Button size="sm" variant="secondary" onClick={onExportExcel}>
            Excel
          </Button>
          <Button size="sm" variant="secondary" onClick={onExportWord}>
            Word
          </Button>
          <Button size="sm" variant="secondary" onClick={onExportPDF}>
            PDF
          </Button>
        </div>
      </div>
    </div>
  );
};

const DocumentsTab: React.FC<DocumentsTabProps> = ({
  deal,
  runId: _runId,
  openViewerAt,
  onViewerLocationConsumed,
}) => {
  const [page] = useState(1);
  const { data, isLoading, error } = useDocuments(deal.id, page);
  const { data: classifiedPage } = useDocumentsWithClassification(deal.id);

  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [pipelinePreview, setPipelinePreview] =
    useState<PipelinePreviewState | null>(null);
  const [isBannerExpanded, setIsBannerExpanded] = useState(false);
  const [isColumnSelectorOpen, setIsColumnSelectorOpen] = useState(false);
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);

  const documents: DocumentListItem[] = data?.items ?? [];

  const selectedDocument = useMemo(
    () => documents.find((doc) => doc.id === selectedDocId) ?? null,
    [documents, selectedDocId],
  );

  const classifiedDocs: DocumentListItem[] = useMemo(
    () => classifiedPage?.items ?? [],
    [classifiedPage],
  );

  const defaultVisibleIds = useMemo<DocumentColumnId[]>(
    () => ALL_DOCUMENT_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.id),
    [],
  );

  const [visibleColumnIds, setVisibleColumnIds] =
    useState<DocumentColumnId[]>(defaultVisibleIds);

  const [tempSelectedIds, setTempSelectedIds] =
    useState<DocumentColumnId[]>(defaultVisibleIds);

  const visibleColumns = useMemo<DocumentColumnDef[]>(
    () => ALL_DOCUMENT_COLUMNS.filter((col) => visibleColumnIds.includes(col.id)),
    [visibleColumnIds],
  );

  const hasColumnSelectionChanges = useMemo(() => {
    if (tempSelectedIds.length !== visibleColumnIds.length) return true;
    const current = new Set(visibleColumnIds);
    return tempSelectedIds.some((id) => !current.has(id));
  }, [tempSelectedIds, visibleColumnIds]);

  const { classificationStats, lowConfidenceDocs } = useMemo(() => {
    const stats: ClassificationStats = {
      L0: 0,
      L1: 0,
      L2: 0,
      L3: 0,
      L4: 0,
      L_manual: 0,
      low_confidence: 0,
    };
    const lowsByThreshold: DocumentListItem[] = [];
    const lowsByFlag: DocumentListItem[] = [];

    for (const doc of classifiedDocs) {
      const level =
        (doc.classification_level as keyof ClassificationStats) || "L0";
      stats[level] = (stats[level] || 0) + 1;

      const confidence =
        typeof doc.classification_confidence === "number"
          ? doc.classification_confidence
          : null;

      if (confidence !== null && confidence < LOW_CONFIDENCE_THRESHOLD) {
        lowsByThreshold.push(doc);
        stats.low_confidence++;
      }

      if (doc.classification_requires_review ?? false) {
        lowsByFlag.push(doc);
      }
    }

    const lowDocs = lowsByFlag.length > 0 ? lowsByFlag : lowsByThreshold;
    return { classificationStats: stats, lowConfidenceDocs: lowDocs };
  }, [classifiedDocs]);

  React.useEffect(() => {
    if (!selectedDocId) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (pipelinePreview) {
          setPipelinePreview(null);
          return;
        }
        setSelectedDocId(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedDocId, pipelinePreview]);

  React.useEffect(() => {
    setPipelinePreview(null);
  }, [selectedDocId]);

  React.useEffect(() => {
    if (!openViewerAt) return;
    setSelectedDocId(openViewerAt.documentId);
    onViewerLocationConsumed?.();
  }, [openViewerAt, onViewerLocationConsumed]);

  const handleToggleColumnSelection = (colId: DocumentColumnId) => {
    setTempSelectedIds((prev) =>
      prev.includes(colId)
        ? prev.filter((id) => id !== colId)
        : [...prev, colId],
    );
  };

  const handleApplyColumns = () => {
    setVisibleColumnIds(tempSelectedIds);
    setIsColumnSelectorOpen(false);
  };

  const handleResetColumns = () => {
    setVisibleColumnIds(defaultVisibleIds);
    setTempSelectedIds(defaultVisibleIds);
    setIsColumnSelectorOpen(false);
  };

  const handleOpenColumnSelector = () => {
    setTempSelectedIds(visibleColumnIds);
    setIsColumnSelectorOpen((prev) => !prev);
  };

  const handleExportExcel = async () => {
    try {
      await exportDocumentsExcel(deal.id, visibleColumnIds);
      setIsExportMenuOpen(false);
    } catch (err) {
      console.error(err);
      alert("Не удалось экспортировать в Excel");
    }
  };

  const handleExportWord = async () => {
    try {
      await exportDocumentsWord(deal.id, visibleColumnIds);
      setIsExportMenuOpen(false);
    } catch (err) {
      console.error(err);
      alert("Не удалось экспортировать в Word");
    }
  };

  const handleExportPDF = async () => {
    try {
      await exportDocumentsPDF(deal.id, visibleColumnIds);
      setIsExportMenuOpen(false);
    } catch (err) {
      console.error(err);
      alert("Не удалось экспортировать в PDF");
    }
  };

  const handleSelectDocument = (docId: string) => {
    setPipelinePreview(null);
    setSelectedDocId(docId);
  };

  const handleCloseDetails = () => {
    setPipelinePreview(null);
    setSelectedDocId(null);
  };

  const handleOpenPipelineStagePreview = (
    stage: PipelineStageViewDTO,
    stages: PipelineStageViewDTO[],
  ) => {
    setPipelinePreview({ stage, stages });
  };

  const renderCellValue = (
    value: unknown,
    isPrimaryCell: boolean,
    isLowConfidence: boolean,
  ): React.ReactNode => {
    if (isPrimaryCell && isLowConfidence) {
      return (
        <span className="flex items-center gap-1.5">
          <span className="truncate">{String(value ?? "")}</span>
          <span
            className="shrink-0 rounded-full bg-[var(--color-warning-subtle)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-warning)]"
            title="Требует проверки классификации"
          >
            !
          </span>
        </span>
      );
    }

    if (typeof value === "boolean") {
      return value ? "Да" : "Нет";
    }

    if (value === null || value === undefined) {
      return "";
    }

    if (typeof value === "number" || typeof value === "string") {
      return value;
    }

    return String(value);
  };

  const shouldShowTable = pipelinePreview === null;
  const isDetailsPanelOpen = selectedDocId !== null;

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden text-[var(--text-primary)]">
      <section className="flex min-h-0 flex-1 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <header className="shrink-0 border-b border-[var(--border-subtle)] px-5 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Документы
                  {documents.length > 0 && (
                    <span className="ml-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 font-semibold text-[var(--text-secondary)]">
                      {documents.length}
                    </span>
                  )}
                </span>

                <ExportMenu
                  isOpen={isExportMenuOpen}
                  onToggle={() => setIsExportMenuOpen((prev) => !prev)}
                  onClose={() => setIsExportMenuOpen(false)}
                  onExportExcel={handleExportExcel}
                  onExportWord={handleExportWord}
                  onExportPDF={handleExportPDF}
                />
              </div>
            </div>
          </header>

          {classificationStats.low_confidence > 0 && (
            <div className="shrink-0">
              <ClassificationWarningBanner
                count={classificationStats.low_confidence}
                docs={lowConfidenceDocs}
                isExpanded={isBannerExpanded}
                onToggle={() => setIsBannerExpanded((v) => !v)}
                onSelectDoc={handleSelectDocument}
              />
            </div>
          )}

          {isLoading && (
            <div className="shrink-0 px-5 py-3 text-sm text-[var(--text-secondary)]">
              Загружаем документы…
            </div>
          )}

          {error && (
            <div className="shrink-0 px-5 py-3 text-sm text-[var(--color-error)]">
              Не удалось загрузить документы.
            </div>
          )}

          {!isLoading && !error && (
            <div className="relative flex min-h-0 flex-1 overflow-hidden">
              {shouldShowTable && (
                <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
                  <div className="flex h-full flex-col overflow-hidden">
                    <div className="shrink-0 border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5">
                      <div className="flex min-h-12 items-center">
                        <Button
                          type="button"
                          size="sm"
                          variant={
                            isColumnSelectorOpen ? "outline" : "secondary"
                          }
                          onClick={handleOpenColumnSelector}
                          aria-expanded={isColumnSelectorOpen}
                          aria-controls="documents-columns-panel"
                          className={
                            isColumnSelectorOpen
                              ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
                              : ""
                          }
                        >
                          Настроить отображаемые колонки
                        </Button>
                      </div>
                    </div>

                    {isColumnSelectorOpen && (
                      <ColumnSelectorInlinePanel
                        tempSelectedIds={tempSelectedIds}
                        hasChanges={hasColumnSelectionChanges}
                        onToggle={handleToggleColumnSelection}
                        onApply={handleApplyColumns}
                        onReset={handleResetColumns}
                        onCancel={() => setIsColumnSelectorOpen(false)}
                      />
                    )}

                    <div className="flex-1 overflow-auto bg-[var(--bg-subtle)]">
                      <table className="w-full border-collapse">
                        <thead className="sticky top-0 z-10 bg-[var(--bg-card)]">
                          <tr className="border-b border-[var(--border-subtle)]">
                            {visibleColumns.map((col) => (
                              <th
                                key={col.id}
                                className="whitespace-nowrap px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                                title={col.description}
                              >
                                {col.label}
                              </th>
                            ))}
                          </tr>
                        </thead>

                        <tbody>
                          {documents.map((doc) => {
                            const isLowConfidence =
                              (typeof doc.classification_confidence ===
                                "number" &&
                                doc.classification_confidence <
                                  LOW_CONFIDENCE_THRESHOLD) ||
                              (doc.classification_requires_review ?? false);

                            const isSelected = selectedDocId === doc.id;

                            return (
                              <tr
                                key={doc.id}
                                className={`cursor-pointer border-b border-[var(--border-subtle)] transition-colors ${
                                  isSelected
                                    ? "bg-[var(--bg-elevated-soft)]"
                                    : "hover:bg-[var(--bg-elevated-soft)]"
                                }`}
                                onClick={() => handleSelectDocument(doc.id)}
                              >
                                {visibleColumns.map((col) => {
                                  let value: unknown;

                                  if (
                                    col.id === "composition_type" ||
                                    col.id === "segment_count" ||
                                    col.id === "primary_segment_label" ||
                                    col.id === "is_composite_file"
                                  ) {
                                    value = getCompositionCellValue(col.id, doc);
                                  } else {
                                    switch (col.field) {
                                      case "applicable_triggers_count":
                                        value =
                                          doc.applicable_triggers?.length ?? 0;
                                        break;
                                      case "status": {
                                        const baseLabel =
                                          doc.status &&
                                          DOCUMENT_STATUS_CONFIG[doc.status]
                                            ? DOCUMENT_STATUS_CONFIG[doc.status]
                                                .label
                                            : doc.status || "";
                                        value = hasProcessingError(doc)
                                          ? `${baseLabel} ⚠`
                                          : baseLabel;
                                        break;
                                      }
                                      case "risk_level":
                                        value = formatRiskLevel(doc.risk_level);
                                        break;
                                      case "created_at":
                                        value = formatDateTime(doc.created_at);
                                        break;
                                      case "updated_at":
                                        value = formatDateTime(doc.updated_at);
                                        break;
                                      default: {
                                        type DocumentKey =
                                          keyof DocumentListItem;
                                        value = doc[col.field as DocumentKey];
                                        break;
                                      }
                                    }
                                  }

                                  let title: string | undefined;

                                  if (
                                    col.field === "status" &&
                                    hasProcessingError(doc)
                                  ) {
                                    const details =
                                      doc.processing_error_details;
                                    const stageLabel =
                                      getErrorStageLabel(details);
                                    const message = details?.message;

                                    if (
                                      message &&
                                      stageLabel !== "Неизвестная стадия"
                                    ) {
                                      title = `${stageLabel}: ${message}`;
                                    } else if (message) {
                                      title = message;
                                    } else {
                                      title =
                                        typeof value === "string"
                                          ? value
                                          : undefined;
                                    }
                                  } else if (
                                    col.field === "status" &&
                                    doc.status
                                  ) {
                                    title =
                                      DOCUMENT_STATUS_CONFIG[doc.status]
                                        ?.tooltip ??
                                      (typeof value === "string"
                                        ? value
                                        : undefined);
                                  } else if (typeof value === "string") {
                                    title = value;
                                  }

                                  const isPrimaryCell = col.id === "filename";

                                  return (
                                    <td
                                      key={col.id}
                                      className={`px-3 py-2.5 text-sm ${
                                        isPrimaryCell
                                          ? "font-medium text-[var(--text-primary)]"
                                          : "text-[var(--text-secondary)]"
                                      }`}
                                      title={title}
                                    >
                                      {renderCellValue(
                                        value,
                                        isPrimaryCell,
                                        isLowConfidence,
                                      )}
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}

                          {documents.length === 0 && (
                            <tr>
                              <td
                                colSpan={visibleColumns.length}
                                className="px-4 py-12 text-center"
                              >
                                <p className="text-sm text-[var(--text-muted)]">
                                  Документов пока нет
                                </p>
                                <p className="mt-1 text-[11px] text-[var(--text-faint)]">
                                  Загрузите документы через вкладку «Обзор»
                                </p>
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {isDetailsPanelOpen && pipelinePreview && (
                <div className="flex w-[66.666%] min-w-0 flex-col overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--bg-card)]">
                  <PipelineStagePreviewPane
                    stage={pipelinePreview.stage}
                    stages={pipelinePreview.stages}
                    documentId={selectedDocId ?? ""}
                    onOpenAtLocation={undefined}
                    onClose={() => setPipelinePreview(null)}
                  />
                </div>
              )}

              <aside
                className={`flex shrink-0 flex-col overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] transition-all duration-300 ease-in-out ${
                  isDetailsPanelOpen ? "w-[33.333%]" : "w-0"
                }`}
                aria-hidden={!isDetailsPanelOpen}
              >
                {isDetailsPanelOpen && selectedDocId !== null && (
                  <>
                    <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                          Детали документа
                        </span>
                        <span className="text-[var(--text-faint)]">·</span>
                        <span
                          className="truncate text-sm font-medium text-[var(--text-primary)]"
                          title={selectedDocument?.filename ?? selectedDocId}
                        >
                          {selectedDocument?.filename ?? selectedDocId}
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={handleCloseDetails}
                        className="shrink-0 rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
                        aria-label="Закрыть панель деталей документа"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="min-h-0 flex-1 overflow-hidden bg-[var(--bg-elevated-soft)]">
                      <DocumentDetailsContainer
                        docId={selectedDocId}
                        dealId={deal.id}
                        onNavigateToGrid={(dealId, docName) => {
                          window.location.href = `/projects/${dealId}?tab=grid&document=${encodeURIComponent(
                            docName,
                          )}`;
                        }}
                        onOpenPipelineStagePreview={
                          handleOpenPipelineStagePreview
                        }
                      />
                    </div>
                  </>
                )}
              </aside>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default DocumentsTab;





