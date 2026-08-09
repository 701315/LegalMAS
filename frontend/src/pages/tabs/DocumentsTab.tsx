// =============================================================
// src/pages/tabs/DocumentsTab.tsx
// =============================================================

import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
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

import DocumentDetailsContainer from "../../components/documents/DocumentDetailsContainer";
import PipelineStagePreviewPane from "../../components/documents/pipeline/PipelineStagePreviewPane";
import {
  getDocumentsCountLabel,
  resolveDocumentCellValue,
  resolveDocumentCellTitle,
} from "./documents/utils";
import Button from "../../components/ui/Button";
import ClassificationWarningBanner from "./documents/components/ClassificationWarningBanner";
import ColumnSelectorInlinePanel from "./documents/components/ColumnSelectorInlinePanel";
import ExportMenu from "./documents/components/ExportMenu";

interface DocumentsTabProps {
  deal: Deal;
  openViewerAt?: OpenViewerAtPayload | null;
  onViewerLocationConsumed?: () => void;
}

interface PipelinePreviewState {
  stage: PipelineStageViewDTO;
  stages: PipelineStageViewDTO[];
}

// -------------------------------------------------------------
// DocumentsTab
// -------------------------------------------------------------

const DocumentsTab: React.FC<DocumentsTabProps> = ({
  deal,
  openViewerAt,
  onViewerLocationConsumed,
}) => {
  const navigate = useNavigate();

  // ── Data fetching ──────────────────────────────────────────
  const [page] = useState(1);
  const { data, isLoading, error } = useDocuments(deal.id, page);
  const { data: classifiedPage } = useDocumentsWithClassification(deal.id);

  // ── UI state ───────────────────────────────────────────────
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [pipelinePreview, setPipelinePreview] = useState<PipelinePreviewState | null>(null);
  const [isBannerExpanded, setIsBannerExpanded] = useState(false);
  const [isColumnSelectorOpen, setIsColumnSelectorOpen] = useState(false);
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);

  // ── Computed values ────────────────────────────────────────
  const documents = useMemo<DocumentListItem[]>(
    () => data?.items ?? [],
    [data?.items],
  );

  const totalDocumentsCount = data?.total ?? documents.length;

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

  const [visibleColumnIds, setVisibleColumnIds] = useState<DocumentColumnId[]>(defaultVisibleIds);
  const [tempSelectedIds, setTempSelectedIds] = useState<DocumentColumnId[]>(defaultVisibleIds);

  const visibleColumns = useMemo<DocumentColumnDef[]>(
    () => ALL_DOCUMENT_COLUMNS.filter((col) => visibleColumnIds.includes(col.id)),
    [visibleColumnIds],
  );

  const hasColumnSelectionChanges = useMemo(() => {
    if (tempSelectedIds.length !== visibleColumnIds.length) return true;
    const current = new Set(visibleColumnIds);
    return tempSelectedIds.some((id) => !current.has(id));
  }, [tempSelectedIds, visibleColumnIds]);

  const reviewDocs = useMemo(
    () => classifiedDocs.filter((doc) => doc.classification_requires_review === true),
    [classifiedDocs],
  );

  const isDetailsPanelOpen = isPanelOpen && selectedDocId !== null;
  const isPipelinePreviewOpen = pipelinePreview !== null;

  // ── Effects ────────────────────────────────────────────────
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
    setIsPanelOpen(true);
    onViewerLocationConsumed?.();
  }, [openViewerAt, onViewerLocationConsumed]);

  React.useEffect(() => {
    if (!isDetailsPanelOpen) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [isDetailsPanelOpen]);

  // ── Event handlers ─────────────────────────────────────────
  const handleToggleColumnSelection = (colId: DocumentColumnId) => {
    setTempSelectedIds((prev) =>
      prev.includes(colId) ? prev.filter((id) => id !== colId) : [...prev, colId],
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
    setIsPanelOpen(true);
  };

  const handleCloseDetails = () => {
    setPipelinePreview(null);
    setIsPanelOpen(false);
    // НЕ сбрасываем selectedDocId — строка остаётся активной
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
    showReviewFlag: boolean,
  ): React.ReactNode => {
    if (isPrimaryCell && showReviewFlag) {
      return (
        <span className="flex items-center gap-1.5">
          <span className="truncate">{String(value ?? "")}</span>
          <span
            className="shrink-0 rounded-full bg-[var(--color-warning-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-warning-text)]"
            title="Требует проверки классификации"
          >
            !
          </span>
        </span>
      );
    }
    if (typeof value === "boolean") return value ? "Да" : "Нет";
    if (value === null || value === undefined) return "";
    if (typeof value === "number" || typeof value === "string") return value;
    return String(value);
  };

  // ── Render ─────────────────────────────────────────────────
  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-labelledby="documents-tab-title"
    >
      <div className="relative flex min-h-0 flex-1 flex-col text-[var(--text-primary)]">
        <div
          className={`grid min-h-0 flex-1 gap-4 ${
            isDetailsPanelOpen
              ? "lg:grid-cols-[minmax(0,2fr)_minmax(360px,1fr)]"
              : "grid-cols-1"
          }`}
        >
          {/* ── Основная секция ─────────────────────────────── */}
          <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            {!isPipelinePreviewOpen && (
              <div className="px-5">
                {/* Заголовок — выровнен с PageSection */}
                <div className="py-3">
                  <h2
                    id="documents-tab-title"
                    className="text-sm font-semibold text-[var(--text-primary)]"
                  >
                    Документы
                  </h2>
                  <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    {totalDocumentsCount > 0
                      ? `В проекте анализируется ${totalDocumentsCount} ${getDocumentsCountLabel(totalDocumentsCount)}`
                      : "В проекте пока нет загруженных документов"}
                  </p>
                </div>

                <div className="border-t border-[var(--border-subtle)]" />

                {/* Тулбар */}
                <div className="flex min-h-10 flex-wrap items-center gap-2 py-3">
                  <Button
                    type="button"
                    size="sm"
                    variant={isColumnSelectorOpen ? "outline" : "secondary"}
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

                  <ExportMenu
                    isOpen={isExportMenuOpen}
                    onToggle={() => setIsExportMenuOpen((prev) => !prev)}
                    onClose={() => setIsExportMenuOpen(false)}
                    onExportExcel={handleExportExcel}
                    onExportWord={handleExportWord}
                    onExportPDF={handleExportPDF}
                  />
                </div>

                <div className="border-t border-[var(--border-subtle)]" />
              </div>
            )}

            {!isPipelinePreviewOpen && reviewDocs.length > 0 && (
              <div className="shrink-0">
                <ClassificationWarningBanner
                  count={reviewDocs.length}
                  docs={reviewDocs}
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
              <div className="shrink-0 px-5 py-3 text-sm text-[var(--color-error-text)]">
                Не удалось загрузить документы.
              </div>
            )}

            {!isLoading && !error && (
              <div className="flex min-h-0 flex-1 overflow-hidden">
                {isPipelinePreviewOpen ? (
                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[var(--bg-card)]">
                    <PipelineStagePreviewPane
                      stage={pipelinePreview.stage}
                      stages={pipelinePreview.stages}
                      documentId={selectedDocId ?? ""}
                      onOpenAtLocation={undefined}
                      onClose={() => setPipelinePreview(null)}
                    />
                  </div>
                ) : (
                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
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

                    <div className="flex-1 overflow-hidden bg-[var(--bg-card)] px-5 pb-5 pt-4">
                      <div className="h-full overflow-auto rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
                        <table className="w-full border-collapse">
                          <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
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
                              const showReviewFlag = doc.classification_requires_review === true;
                              const isSelected = selectedDocId === doc.id;

                              return (
                                <tr
                                  key={doc.id}
                                  className={`cursor-pointer border-b border-[var(--border-subtle)] transition-colors ${
                                    isSelected
                                      ? "bg-[var(--bg-elevated-soft)] shadow-[inset_3px_0_0_var(--accent-primary)]"
                                      : "hover:bg-[var(--bg-elevated-soft)]"
                                  }`}
                                  onClick={() => handleSelectDocument(doc.id)}
                                >
                                  {visibleColumns.map((col) => {
                                    const value = resolveDocumentCellValue(
                                      col.id,
                                      col.field,
                                      doc,
                                    );

                                    const title = resolveDocumentCellTitle(
                                      col.field,
                                      value,
                                      doc,
                                    );

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
                                          showReviewFlag,
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
              </div>
            )}
          </section>

          {/* ── Панель деталей документа ────────────────────── */}
          {isDetailsPanelOpen && (
            <>
              {/* Mobile backdrop */}
              <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden" />

              <aside
                className="
                  fixed inset-0 z-50
                  flex min-h-0 flex-col
                  bg-[var(--bg-card)]
                  lg:relative lg:inset-auto
                  lg:rounded-2xl lg:border lg:border-[var(--border)] lg:shadow-sm
                  overflow-hidden
                "
              >
                <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-[3px] bg-[var(--accent-primary)]" />

                <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Детали документа
                    </span>
                    <span className="text-[var(--text-faint)]">·</span>
                    <span
                      className="truncate text-sm font-medium text-[var(--text-primary)]"
                      title={selectedDocument?.filename ?? selectedDocId ?? ""}
                    >
                      {selectedDocument?.filename ?? selectedDocId}
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={handleCloseDetails}
                    className="
                      shrink-0 rounded-lg p-2
                      text-[var(--text-muted)]
                      transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]
                    "
                    aria-label="Закрыть панель деталей документа"
                  >
                    <span className="lg:hidden">← Назад</span>
                    <span className="hidden lg:inline">✕</span>
                  </button>
                </div>

                <div className="min-h-0 flex-1 overflow-hidden bg-[var(--bg-elevated-soft)]">
                  <DocumentDetailsContainer
                    docId={selectedDocId!}
                    dealId={deal.id}
                    onNavigateToGrid={(dealId, docName) => {
                      navigate(
                        `/projects/${dealId}?tab=dd_grid&document=${encodeURIComponent(docName)}`,
                      );
                    }}
                    onOpenPipelineStagePreview={handleOpenPipelineStagePreview}
                  />
                </div>
              </aside>
            </>
          )}
        </div>
      </div>
    </section>
  );
};

export default DocumentsTab;

