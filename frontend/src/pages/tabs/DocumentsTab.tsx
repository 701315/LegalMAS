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
import type { Deal, Document } from "../../types";
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

interface DocumentsTabProps {
  deal: Deal;
}

const LOW_CONFIDENCE_THRESHOLD = 0.6;

// Типизация для статистики классификации
interface ClassificationStats {
  L0: number;
  L1: number;
  L2: number;
  L3: number;
  L4: number;
  L_manual: number;
  low_confidence: number;
}

// Вспомогательное форматирование риска
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

// Вспомогательное форматирование дат
function formatDateTime(value: string | undefined | null): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

// Явный флаг наличия ошибки обработки по backend-полю
function hasProcessingError(doc: Document): boolean {
  if (doc.status === "failed" || doc.status === "quarantine") {
    return true;
  }
  const details = doc.processing_error_details;
  if (!details) return false;
  // В новой модели мы опираемся на type/message, а не на code.
  return Boolean(details.message || details.type);
}

const DocumentsTab: React.FC<DocumentsTabProps> = ({ deal }) => {
  const [page] = useState(1);
  const { data, isLoading, error } = useDocuments(deal.id, page);
  const { data: classifiedPage } = useDocumentsWithClassification(deal.id);

  const { canDeleteDocuments } = useDealPermissions(deal.id);

  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [modalDoc, setModalDoc] = useState<Document | null>(null);
  const [isOpenModal, setIsOpenModal] = useState(false);

  const [leftTab, setLeftTab] = useState<"tree" | "classification" | "table">(
    "tree",
  );

  const softDeleteMutation = useSoftDeleteDocument(deal.id);

  const documents = data?.items ?? [];

  const classifiedDocs = useMemo(
    () => classifiedPage?.items ?? [],
    [classifiedPage],
  );

  // === НОВОЕ: состояние видимых колонок и режима выбора ===

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
    () => ALL_DOCUMENT_COLUMNS.filter((col) => visibleColumnIds.includes(col.id)),
    [visibleColumnIds],
  );

  // Статистика по классификации + список low-confidence документов + L4-count
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

  const lowsByThreshold: Document[] = [];
  const lowsByFlag: Document[] = [];

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

  // Если backend уже шлёт явный флаг manual review, используем его.
  // Для старых данных (без флага) — fallback по порогу confidence.
  const lowDocs =
    lowsByFlag.length > 0 ? lowsByFlag : lowsByThreshold;

  return {
    classificationStats: stats,
    lowConfidenceDocs: lowDocs,
    l4Count,
  };
}, [classifiedDocs]);

  const handleDeleteDocument = (doc: Document) => {
    if (!canDeleteDocuments) return;

    const confirmed = window.confirm(
      `Удалить документ "${doc.filename}" из проекта? Документ будет помечен как удалённым.`,
    );
    if (!confirmed) return;

    softDeleteMutation.mutate(doc.id);
  };

  // === НОВОЕ: обработчики выбора колонок ===

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
    <div className="flex h-full">
      {/* Левая колонка: дерево / панель классификации / таблица */}
      <div className="w-[55%] border-r border-gray-200 flex flex-col">
        {/* Заголовок + табы */}
        <div className="border-b">
          <div className="px-4 pt-2 text-xs font-semibold text-gray-500 uppercase flex justify-between items-center">
            <span>Документы ({documents.length})</span>
          </div>
          <div className="mt-2 flex text-xs font-medium px-2">
            <button
              type="button"
              onClick={() => setLeftTab("tree")}
              className={`flex-1 px-2 py-1 rounded-t border-b-2 ${
                leftTab === "tree"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              📁 Дерево
            </button>
            <button
              type="button"
              onClick={() => setLeftTab("classification")}
              className={`flex-1 px-2 py-1 rounded-t border-b-2 flex items-center justify-center gap-1 ${
                leftTab === "classification"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              🏷️ Классификация
              {classificationStats.low_confidence > 0 && (
                <span className="ml-1 inline-flex items-center justify-center rounded-full bg-yellow-100 text-yellow-800 text-[10px] px-1.5 py-0.5">
                  {classificationStats.low_confidence}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setLeftTab("table")}
              className={`flex-1 px-2 py-1 rounded-t border-b-2 ${
                leftTab === "table"
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              📄 Таблица
            </button>
          </div>
        </div>

        {/* Состояния загрузки/ошибки */}
        {isLoading && (
          <div className="p-4 text-sm text-gray-500">Загружаем документы…</div>
        )}
        {error && (
          <div className="p-4 text-sm text-red-600">
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
              <div className="flex-1 overflow-y-auto p-3 space-y-4">
                {/* Мини-статистика по уровням */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                    Статистика по уровням
                  </h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {(["L0", "L1", "L2", "L3", "L4", "L_manual"] as const).map(
                      (lvl) => (
                        <div
                          key={lvl}
                          className="flex items-center justify-between bg-gray-50 rounded px-2 py-1"
                        >
                          <span className="text-gray-500">{lvl}</span>
                          <span className="font-semibold text-gray-800">
                            {classificationStats[lvl]}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                </div>

                {/* Явный индикатор использования L4 LLM */}
                {l4Count > 0 && (
                  <p className="text-xs text-green-700">
                    {l4Count} документ(ов) классифицировано с помощью L4 LLM.
                  </p>
                )}

                {/* Предупреждение о low-confidence */}
                {classificationStats.low_confidence > 0 && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded p-2 text-xs text-yellow-800">
                    <p className="font-semibold mb-1">
                      Документы с низкой уверенностью классификации
                    </p>
                    <p>
                      Уровень уверенности ниже{" "}
                      {Math.round(LOW_CONFIDENCE_THRESHOLD * 100)}% — рекомендуется
                      проверить тип документа.
                    </p>
                  </div>
                )}

                {/* Список low-confidence документов */}
                {lowConfidenceDocs.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Требуют внимания ({lowConfidenceDocs.length})
                    </h4>
                    <div className="space-y-1 max-h-64 overflow-y-auto">
                      {lowConfidenceDocs.map((doc) => (
                        <button
                          key={doc.id}
                          type="button"
                          onClick={() => {
                            setSelectedDocId(doc.id);
                            setLeftTab("tree");
                          }}
                          className="w-full text-left text-xs px-2 py-1.5 rounded hover:bg-gray-50 flex items-center gap-2"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-gray-800 truncate">
                              {doc.filename}
                            </p>
                            <p className="text-[11px] text-gray-400 truncate">
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
                  <p className="text-xs text-gray-400">
                    Документов с низкой уверенностью классификации нет.
                  </p>
                )}

                {/* Мини-таблица всех классифицированных документов */}
                {classifiedDocs.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Список классифицированных документов ({classifiedDocs.length})
                    </h4>
                    <div className="border border-gray-100 rounded bg-white max-h-64 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-2 py-1 text-left text-gray-500 font-semibold">
                              Имя файла
                            </th>
                            <th className="px-2 py-1 text-left text-gray-500 font-semibold">
                              Тип
                            </th>
                            <th className="px-2 py-1 text-left text-gray-500 font-semibold">
                              Уровень
                            </th>
                            <th className="px-2 py-1 text-right text-gray-500 font-semibold">
                              Уверенность
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {classifiedDocs.map((doc) => (
                            <tr
                              key={doc.id}
                              className="hover:bg-gray-50 cursor-pointer"
                              onClick={() => {
                                setSelectedDocId(doc.id);
                                setLeftTab("tree");
                              }}
                            >
                              <td className="px-2 py-1 truncate text-gray-800">
                                {doc.filename}
                              </td>
                              <td className="px-2 py-1 text-gray-500">
                                {doc.doc_type || "—"}
                              </td>
                              <td className="px-2 py-1">
                                <ClassificationBadge
                                  level={doc.classification_level}
                                  confidence={doc.classification_confidence}
                                  showConfidence={false}
                                />
                              </td>
                              <td className="px-2 py-1 text-right text-gray-500">
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
              <div className="flex-1 overflow-auto p-2">
                {/* Панель управления колонками и экспортом */}
                <div className="mb-2 flex items-center justify-between text-xs gap-2">
                  <div className="flex items-center gap-2">
                    {!isSelectingColumns ? (
                      <>
                        <button
                          type="button"
                          onClick={handleStartSelectingColumns}
                          className="px-2 py-1 bg-white border border-gray-300 rounded hover:bg-gray-100"
                        >
                          Выбрать колонки
                        </button>
                        <button
                          type="button"
                          onClick={handleResetColumns}
                          className="px-2 py-1 bg-white border border-gray-300 rounded hover:bg-gray-100"
                        >
                          Сбросить по умолчанию
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={handleApplyColumns}
                          className="px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                          Применить
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsSelectingColumns(false)}
                          className="px-2 py-1 bg-white border border-gray-300 rounded hover:bg-gray-100"
                        >
                          Отмена
                        </button>
                      </>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleExportExcel}
                      className="px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                      title="Экспорт в Excel"
                    >
                      📊 Excel
                    </button>
                    <button
                      type="button"
                      onClick={handleExportWord}
                      className="px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                      title="Экспорт в Word"
                    >
                      📝 Word
                    </button>
                    <button
                      type="button"
                      onClick={handleExportPDF}
                      className="px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700"
                      title="Экспорт в PDF"
                    >
                      📄 PDF
                    </button>
                  </div>
                </div>

                {/* Панель чекбоксов (только в режиме выбора) */}
                {isSelectingColumns && (
                  <div className="mb-3 p-2 bg-blue-50 border border-blue-200 rounded text-xs">
                    <p className="font-semibold mb-2 text-blue-800">
                      Выберите колонки для отображения:
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {ALL_DOCUMENT_COLUMNS.map((col) => (
                        <label
                          key={col.id}
                          className="flex items-center gap-2 cursor-pointer hover:bg-blue-100 p-1 rounded"
                        >
                          <input
                            type="checkbox"
                            checked={tempSelectedIds.includes(col.id)}
                            onChange={() => handleToggleColumnSelection(col.id)}
                            className="cursor-pointer"
                          />
                          <span className="text-gray-700">{col.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                <table className="min-w-full text-xs border-collapse">
                  <thead className="bg-gray-50">
                    <tr>
                      {visibleColumns.map((col) => (
                        <th
                          key={col.id}
                          className="px-2 py-1 text-left font-semibold text-gray-600 border-b border-gray-200"
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
                        className={`cursor-pointer hover:bg-gray-50 ${
                          selectedDocId === doc.id ? "bg-blue-50" : ""
                        }`}
                        onClick={() => {
                          setSelectedDocId(doc.id);
                          setModalDoc(doc);
                          setIsOpenModal(true);
                        }}
                      >
                        {visibleColumns.map((col) => {
                          let value: unknown;

                          switch (col.field) {
                            case "applicable_triggers_count":
                              value = doc.applicable_triggers?.length ?? 0;
                              break;
                            case "status": {
                              // Берём человекочитаемый текст статуса из единого конфига.
                              const baseLabel =
                                doc.status && DOCUMENT_STATUS_CONFIG[doc.status]
                                  ? DOCUMENT_STATUS_CONFIG[doc.status].label
                                  : doc.status || "";

                              if (hasProcessingError(doc)) {
                                // Добавляем небольшой индикатор ошибки.
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
                              // col.field совпадает с ключами Document, поэтому используем
                              // индексный доступ без any.
                              type DocumentKey = keyof Document;
                              const fieldName = col.field as DocumentKey;
                              value = doc[fieldName];
                              break;
                            }
                          }
                          let title: string | undefined;

                          if (col.field === "status" && hasProcessingError(doc)) {
                            const details = doc.processing_error_details;
                            const stageLabel = getErrorStageLabel(details);
                            const message = details?.message;

                            if (message && stageLabel !== "Неизвестная стадия") {
                              title = `${stageLabel}: ${message}`;
                            } else if (message) {
                              title = message;
                            } else {
                              title = typeof value === "string" ? value : undefined;
                            }
                          } else if (typeof value === "string") {
                            title = value;
                          }

                          return (
                            <td
                              key={col.id}
                              className="px-2 py-1 border-b border-gray-100 text-gray-800 max-w-xs truncate"
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
                          className="px-2 py-4 text-center text-xs text-gray-400"
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

      {/* Правая колонка: детали документа */}
      <div className="flex-1">
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
          <div className="h-full flex items-center justify-center text-sm text-gray-400">
            Выберите документ слева
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentsTab;
