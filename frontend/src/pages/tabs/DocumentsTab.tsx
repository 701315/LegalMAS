// =============================================================
// src/pages/tabs/DocumentsTab.tsx
// Вкладка "Документы":
// - слева: дерево / классификация / таблица
// - справа: панель DocumentDetails (через контейнер)
// =============================================================

import React, { useMemo, useState } from "react";
import {
  useDocuments,
  useDocumentsWithClassification,
  useSoftDeleteDocument,
  exportDocumentsExcel,
  exportDocumentsWord,
  exportDocumentsPDF,
} from "../../api/documents";
import type { Deal, DocumentListItem, OpenViewerAtPayload } from "../../types";
import DocumentDetailsContainer from "../../components/documents/DocumentDetailsContainer";
import { DocumentTree } from "../../components/documents/DocumentTree";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";
import { ALL_DOCUMENT_COLUMNS } from "../../types";
import type { DocumentColumnDef, DocumentColumnId } from "../../types";
import { useDealPermissions } from "../../hooks/usePermissions";
import DocumentOpenModal from "../../components/documents/DocumentOpenModal";

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
  if (doc.status === "failed" || doc.status === "quarantine") {
    return true;
  }
  const details = doc.processing_error_details;
  if (!details) return false;
  return Boolean(details.message || details.type);
}

const DocumentsTab: React.FC<DocumentsTabProps> = ({
  deal,
  runId: _runId,
  openViewerAt,
  onViewerLocationConsumed,
}) => {
  const [page] = useState(1);
  const { data, isLoading, error } = useDocuments(deal.id, page);
  const { data: classifiedPage } = useDocumentsWithClassification(deal.id);

  const { canDeleteDocuments } = useDealPermissions(deal.id);

  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [modalDoc, setModalDoc] = useState<DocumentListItem | null>(null);
  const [isOpenModal, setIsOpenModal] = useState(false);

  const [leftTab, setLeftTab] = useState<"tree" | "classification" | "table">(
    "tree",
  );

  const softDeleteMutation = useSoftDeleteDocument(deal.id);

  const documents: DocumentListItem[] = data?.items ?? [];

  const classifiedDocs: DocumentListItem[] = useMemo(
    () => classifiedPage?.items ?? [],
    [classifiedPage],
  );

  const defaultVisibleIds = useMemo<DocumentColumnId[]>(
    () =>
      ALL_DOCUMENT_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.id),
    [],
  );

  const [visibleColumnIds, setVisibleColumnIds] =
    useState<DocumentColumnId[]>(defaultVisibleIds);

  const [isSelectingColumns, setIsSelectingColumns] = useState(false);
  const [tempSelectedIds, setTempSelectedIds] =
    useState<DocumentColumnId[]>(defaultVisibleIds);

  const visibleColumns = useMemo<DocumentColumnDef[]>(
    () =>
      ALL_DOCUMENT_COLUMNS.filter((col) => visibleColumnIds.includes(col.id)),
    [visibleColumnIds],
  );

  const { classificationStats, lowConfidenceDocs, l4Count } = useMemo(() => {
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

      if (doc.classification_requires_review) {
        lowsByFlag.push(doc);
      }
    }

    const l4Count = classifiedDocs.filter(
      (d) => d.classification_level === "L4",
    ).length;

    const lowDocs = lowsByFlag.length > 0 ? lowsByFlag : lowsByThreshold;

    return {
      classificationStats: stats,
      lowConfidenceDocs: lowDocs,
      l4Count,
    };
  }, [classifiedDocs]);

  React.useEffect(() => {
    if (!openViewerAt) return;

    const targetDocId = openViewerAt.documentId;
    setSelectedDocId(targetDocId);
    setLeftTab("tree");

    onViewerLocationConsumed?.();
  }, [openViewerAt, onViewerLocationConsumed]);

  const handleDeleteDocument = (doc: DocumentListItem) => {
    if (!canDeleteDocuments) return;

    const confirmed = window.confirm(
      `Удалить документ "${doc.filename}" из проекта? Документ будет помечен как удалённым.`,
    );
    if (!confirmed) return;

    softDeleteMutation.mutate(doc.id);
  };

  const handleToggleColumnSelection = (colId: DocumentColumnId) => {
    setTempSelectedIds((prev) =>
      prev.includes(colId)
        ? prev.filter((id) => id !== colId)
        : [...prev, colId],
    );
  };

  const handleApplyColumns = () => {
    setVisibleColumnIds(tempSelectedIds);
    setIsSelectingColumns(false);
  };

  const handleResetColumns = () => {
    setVisibleColumnIds(defaultVisibleIds);
    setTempSelectedIds(defaultVisibleIds);
    setIsSelectingColumns(false);
  };

  const handleStartSelectingColumns = () => {
    setTempSelectedIds(visibleColumnIds);
    setIsSelectingColumns(true);
  };

  const handleExportExcel = async () => {
    try {
      await exportDocumentsExcel(deal.id, visibleColumnIds);
    } catch (err) {
      console.error(err);
      alert("Не удалось экспортировать в Excel");
    }
  };

  const handleExportWord = async () => {
    try {
      await exportDocumentsWord(deal.id, visibleColumnIds);
    } catch (err) {
      console.error(err);
      alert("Не удалось экспортировать в Word");
    }
  };

  const handleExportPDF = async () => {
    try {
      await exportDocumentsPDF(deal.id, visibleColumnIds);
    } catch (err) {
      console.error(err);
      alert("Не удалось экспортировать в PDF");
    }
  };

  return (
    <div className="flex h-full bg-[var(--bg-base)] text-[var(--text-primary)]">
      <div className="flex w-[55%] flex-col border-r border-[var(--border)] bg-[var(--bg-surface)]">
        <div className="border-b border-[var(--border)]">
          <div className="flex items-center justify-between px-4 pt-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            <span>Документы ({documents.length})</span>
          </div>

          <div className="mt-2 flex px-2 text-xs font-medium">
            <button
              type="button"
              onClick={() => setLeftTab("tree")}
              className={`flex-1 rounded-t-md border-b-2 px-2 py-1 transition-colors duration-150 ${
                leftTab === "tree"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              📁 Дерево
            </button>

            <button
              type="button"
              onClick={() => setLeftTab("classification")}
              className={`flex flex-1 items-center justify-center gap-1 rounded-t-md border-b-2 px-2 py-1 transition-colors duration-150 ${
                leftTab === "classification"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              🏷️ Классификация
              {classificationStats.low_confidence > 0 && (
                <span className="ml-1 inline-flex items-center justify-center rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
                  {classificationStats.low_confidence}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setLeftTab("table")}
              className={`flex-1 rounded-t-md border-b-2 px-2 py-1 transition-colors duration-150 ${
                leftTab === "table"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              📄 Таблица
            </button>
          </div>
        </div>

        {isLoading && (
          <div className="p-4 text-sm text-[var(--text-secondary)]">
            Загружаем документы…
          </div>
        )}

        {error && (
          <div className="p-4 text-sm text-red-400">
            Не удалось загрузить документы.
          </div>
        )}

        {!isLoading && !error && (
          <div className="flex-1 overflow-hidden">
            {leftTab === "tree" && (
              <DocumentTree
                documents={documents}
                selectedDocId={selectedDocId}
                onSelectDoc={(doc) => setSelectedDocId(doc.id)}
                showClassification
                canDelete={canDeleteDocuments}
                onDeleteDoc={handleDeleteDocument}
              />
            )}

            {leftTab === "classification" && (
              <div className="flex-1 space-y-4 overflow-y-auto bg-[var(--bg-surface)] p-3">
                <div>
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                    Статистика по уровням
                  </h4>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {(["L0", "L1", "L2", "L3", "L4", "L_manual"] as const).map(
                      (lvl) => (
                        <div
                          key={lvl}
                          className="flex items-center justify-between rounded-lg bg-[var(--bg-card)] px-2 py-1"
                        >
                          <span className="text-[var(--text-secondary)]">
                            {lvl}
                          </span>
                          <span className="font-semibold text-[var(--text-primary)]">
                            {classificationStats[lvl]}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                </div>

                {l4Count > 0 && (
                  <p className="text-xs text-emerald-400">
                    {l4Count} документ(ов) классифицировано с помощью L4 LLM.
                  </p>
                )}

                {classificationStats.low_confidence > 0 && (
                  <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
                    <p className="mb-1 font-semibold">
                      Документы с низкой уверенностью классификации
                    </p>
                    <p>
                      Уровень уверенности ниже{" "}
                      {Math.round(LOW_CONFIDENCE_THRESHOLD * 100)}% —
                      рекомендуется проверить тип документа.
                    </p>
                  </div>
                )}

                {lowConfidenceDocs.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                      Требуют внимания ({lowConfidenceDocs.length})
                    </h4>

                    <div className="max-h-64 space-y-1 overflow-y-auto">
                      {lowConfidenceDocs.map((doc) => (
                        <button
                          key={doc.id}
                          type="button"
                          onClick={() => {
                            setSelectedDocId(doc.id);
                            setLeftTab("tree");
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-[var(--text-secondary)] transition-colors hover:bg-white/5"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-[var(--text-primary)]">
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

                {classificationStats.low_confidence === 0 && (
                  <p className="text-xs text-[var(--text-muted)]">
                    Документов с низкой уверенностью классификации нет.
                  </p>
                )}

                {classifiedDocs.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                      Список классифицированных документов ({classifiedDocs.length})
                    </h4>

                    <div className="max-h-64 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--bg-card)]">
                      <table className="w-full border-collapse">
                        <thead className="border-b border-[var(--border)]">
                          <tr>
                            <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                              Имя файла
                            </th>
                            <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                              Тип
                            </th>
                            <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                              Уровень
                            </th>
                            <th className="px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                              Уверенность
                            </th>
                          </tr>
                        </thead>

                        <tbody>
                          {classifiedDocs.map((doc) => (
                            <tr
                              key={doc.id}
                              className="cursor-pointer border-b border-[var(--border)] transition-colors hover:bg-white/5"
                              onClick={() => {
                                setSelectedDocId(doc.id);
                                setLeftTab("tree");
                              }}
                            >
                              <td className="px-3 py-2.5 text-sm text-[var(--text-primary)]">
                                {doc.filename}
                              </td>
                              <td className="px-3 py-2.5 text-sm text-[var(--text-secondary)]">
                                {doc.doc_type || "—"}
                              </td>
                              <td className="px-3 py-2.5 text-sm text-[var(--text-secondary)]">
                                <ClassificationBadge
                                  level={doc.classification_level}
                                  confidence={doc.classification_confidence}
                                  showConfidence={false}
                                />
                              </td>
                              <td className="px-3 py-2.5 text-right text-sm text-[var(--text-secondary)]">
                                {typeof doc.classification_confidence === "number"
                                  ? `${Math.round(
                                      doc.classification_confidence * 100,
                                    )}%`
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {leftTab === "table" && (
              <div className="flex-1 overflow-auto bg-[var(--bg-surface)] p-2">
                <div className="mb-3 flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    {!isSelectingColumns ? (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={handleStartSelectingColumns}
                        >
                          Выбрать колонки
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={handleResetColumns}
                        >
                          Сбросить по умолчанию
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          variant="primary"
                          onClick={handleApplyColumns}
                        >
                          Применить
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => setIsSelectingColumns(false)}
                        >
                          Отмена
                        </Button>
                      </>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={handleExportExcel}
                      title="Экспорт в Excel"
                    >
                      📊 Excel
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={handleExportWord}
                      title="Экспорт в Word"
                    >
                      📝 Word
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={handleExportPDF}
                      title="Экспорт в PDF"
                    >
                      📄 PDF
                    </Button>
                  </div>
                </div>

                {isSelectingColumns && (
                  <div className="mb-3 rounded-xl border border-indigo-500/40 bg-indigo-500/10 p-2 text-xs">
                    <p className="mb-2 font-semibold text-indigo-200">
                      Выберите колонки для отображения:
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {ALL_DOCUMENT_COLUMNS.map((col) => (
                        <label
                          key={col.id}
                          className="flex cursor-pointer items-center gap-2 rounded-lg px-1 py-1 hover:bg-white/5"
                        >
                          <input
                            type="checkbox"
                            checked={tempSelectedIds.includes(col.id)}
                            onChange={() => handleToggleColumnSelection(col.id)}
                            className="cursor-pointer"
                          />
                          <span className="text-[var(--text-secondary)]">
                            {col.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                <table className="w-full border-collapse">
                  <thead className="border-b border-[var(--border)]">
                    <tr>
                      {visibleColumns.map((col) => (
                        <th
                          key={col.id}
                          className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                          title={col.description}
                        >
                          {col.label}
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {documents.map((doc) => (
                      <tr
                        key={doc.id}
                        className={`cursor-pointer border-b border-[var(--border)] transition-colors ${
                          selectedDocId === doc.id
                            ? "border-indigo-500/20 bg-indigo-500/8"
                            : "hover:bg-white/3"
                        }`}
                        onClick={() => {
                          setSelectedDocId(doc.id);
                          setModalDoc(doc);
                          setIsOpenModal(true);
                        }}
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
                                value = doc.applicable_triggers?.length ?? 0;
                                break;

                              case "status": {
                                const baseLabel =
                                  doc.status &&
                                  DOCUMENT_STATUS_CONFIG[doc.status]
                                    ? DOCUMENT_STATUS_CONFIG[doc.status].label
                                    : doc.status || "";

                                if (hasProcessingError(doc)) {
                                  value = `${baseLabel} ⚠`;
                                } else {
                                  value = baseLabel;
                                }
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
                                type DocumentKey = keyof DocumentListItem;
                                const fieldName = col.field as DocumentKey;
                                value = doc[fieldName];
                                break;
                              }
                            }
                          }

                          let title: string | undefined;

                          if (
                            col.field === "status" &&
                            hasProcessingError(doc)
                          ) {
                            const details = doc.processing_error_details;
                            const stageLabel = getErrorStageLabel(details);
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
                                typeof value === "string" ? value : undefined;
                            }
                          } else if (col.field === "status" && doc.status) {
                            title =
                              DOCUMENT_STATUS_CONFIG[doc.status]?.tooltip ??
                              (typeof value === "string" ? value : undefined);
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
                              {(() => {
                                if (typeof value === "boolean") {
                                  return value ? "Да" : "Нет";
                                }
                                if (value === null || value === undefined) {
                                  return "";
                                }
                                if (
                                  typeof value === "number" ||
                                  typeof value === "string"
                                ) {
                                  return value as React.ReactNode;
                                }
                                return String(value);
                              })()}
                            </td>
                          );
                        })}
                      </tr>
                    ))}

                    {documents.length === 0 && (
                      <tr>
                        <td
                          colSpan={visibleColumns.length}
                          className="px-3 py-4 text-center text-xs text-[var(--text-muted)]"
                        >
                          Документов пока нет.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {modalDoc && isOpenModal && (
        <DocumentOpenModal
          doc={modalDoc}
          onClose={() => setIsOpenModal(false)}
        />
      )}

      <div className="flex-1 bg-[var(--bg-base)]">
        {selectedDocId ? (
          <DocumentDetailsContainer
            docId={selectedDocId}
            dealId={deal.id}
            onNavigateToGrid={(dealId, docName) => {
              window.location.href = `/projects/${dealId}?tab=grid&document=${encodeURIComponent(
                docName,
              )}`;
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
            Выберите документ слева
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentsTab;



