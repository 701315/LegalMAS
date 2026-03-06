// =============================================================
// src/pages/tabs/DocumentsTab.tsx
// Вкладка "Документы":
// - слева: дерево документов + вкладка "Классификация" 
// - справа: панель DocumentDetails
// =============================================================

import React, { useMemo, useState } from "react";
import {
  useDocuments,
  useDocumentsWithClassification,
} from "../../api/documents";
import type { Deal, Document } from "../../types";
import DocumentDetails from "../../components/documents/DocumentDetails";
import { DocumentTree } from "../../components/documents/DocumentTree";
import { ClassificationBadge } from "../../components/ui/ClassificationBadge";

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

const DocumentsTab: React.FC<DocumentsTabProps> = ({ deal }) => {
  const [page] = useState(1);
  const { data, isLoading, error } = useDocuments(deal.id, page);
  const { data: classifiedPage } = useDocumentsWithClassification(deal.id);

  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<"tree" | "classification">("tree");

  const documents = data?.items ?? [];
  const classifiedDocs = classifiedPage?.items ?? [];

  // Статистика по классификации + список low-confidence документов
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

    const lows: Document[] = [];

    for (const doc of classifiedDocs) {
      const level = doc.classification_level || "L0";
      stats[level] = (stats[level] || 0) + 1;

      if (
        doc.classification_confidence !== undefined &&
        doc.classification_confidence < LOW_CONFIDENCE_THRESHOLD
      ) {
        lows.push(doc);
        stats.low_confidence++;
      }
    }

    return {
      classificationStats: stats,
      lowConfidenceDocs: lows,
    };
  }, [classifiedDocs]);

  return (
    <div className="flex h-full">
      {/* Левая колонка: дерево / панель классификации */}
      <div className="w-[45%] border-r border-gray-200 flex flex-col">
        {/* Заголовок + табы */}
        <div className="border-b">
          <div className="px-4 pt-2 text-xs font-semibold text-gray-500 uppercase">
            Документы ({documents.length})
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
          </div>
        </div>

        {/* Состояния загрузки/ошибки для дерева */}
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

                {/* Предупреждение о low-confidence */}
                {classificationStats.low_confidence > 0 && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded p-2 text-xs text-yellow-800">
                    <p className="font-semibold mb-1">
                      Документы с низкой уверенностью классификации
                    </p>
                    <p>
                      Уровень уверенности ниже{" "}
                      {Math.round(LOW_CONFIDENCE_THRESHOLD * 100)}% —
                      рекомендуется проверить тип документа.
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
              </div>
            )}
          </div>
        )}
      </div>

      {/* Правая колонка: детали документа */}
      <div className="flex-1">
        {selectedDocId ? (
          <DocumentDetails
            docId={selectedDocId}
            dealId={deal.id}
            onNavigateToGrid={(dealId, docName) => {
              window.location.href = `/deals/${dealId}/grid?document=${encodeURIComponent(
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
