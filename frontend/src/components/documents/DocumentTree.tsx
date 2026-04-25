// =============================================================
// src/components/documents/DocumentTree.tsx
// Левое дерево документов (иерархия папок Data Room).
// Для юриста даёт:
// - быстрое понимание структуры дата-рума;
// - статус обработки документа;
// - уровень классификации (L0–L4 / manual) в компактном виде;
// - признак composite-файла (single / multi) и число сегментов.
// =============================================================

import React, { useMemo, useState } from "react";
import type { ClassificationLevel, DocumentListItem } from "../../types";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  Search,
} from "lucide-react";
import { cn } from "../../utils";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { DOCUMENT_STATUS_CONFIG } from "../../utils/statusConfig";

/* ---------- Публичные пропсы ---------- */

interface Props {
  documents: DocumentListItem[];
  selectedDocId: string | null;
  onSelectDoc: (doc: DocumentListItem) => void;
  /** Показывать ли компактный бейдж классификации. */
  showClassification?: boolean;
  /** Можно ли удалять документы (admin/editor). */
  canDelete?: boolean;
  /** Колбэк для удаления документа. */
  onDeleteDoc?: (doc: DocumentListItem) => void;
}

/* ---------- Внутренние типы ---------- */

/** Узел дерева: папка с дочерними папками и файлами. */
interface TreeNode {
  name: string;
  fullPath: string;
  children: TreeNode[];
  docs: DocumentListItem[];
}

/* ====================================================================
   Главный компонент
   ==================================================================== */

export const DocumentTree: React.FC<Props> = ({
  documents,
  selectedDocId,
  onSelectDoc,
  showClassification = true,
  canDelete = false,
  onDeleteDoc,
}) => {
  const [searchText, setSearchText] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set([""]));

  const rootNode = useMemo(() => buildTree(documents), [documents]);

  const displayTree = useMemo(() => {
    if (!searchText.trim()) return rootNode;
    return filterTree(rootNode, searchText.toLowerCase());
  }, [rootNode, searchText]);

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const totalShown = countDocs(displayTree);

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="border-b p-3">
        <div className="relative">
          <Search
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400"
            size={14}
          />
          <input
            type="text"
            placeholder="Поиск по имени документа…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="w-full rounded border py-1.5 pl-8 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <p className="mt-1.5 text-[11px] text-gray-400">
          Показано: {totalShown} из {documents.length} документов
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-1 py-2">
        {totalShown === 0 ? (
          <p className="py-10 text-center text-sm text-gray-400">
            Документы не найдены
          </p>
        ) : (
          <NodeView
            node={displayTree}
            expanded={expanded}
            onToggle={toggle}
            selectedDocId={selectedDocId}
            onSelectDoc={onSelectDoc}
            depth={0}
            showClassification={showClassification}
            canDelete={canDelete}
            onDeleteDoc={onDeleteDoc}
          />
        )}
      </div>
    </div>
  );
};

/* ====================================================================
   Рекурсивный компонент «узел дерева»
   ==================================================================== */

interface NodeViewProps {
  node: TreeNode;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  selectedDocId: string | null;
  onSelectDoc: (doc: DocumentListItem) => void;
  depth: number;
  showClassification: boolean;
  canDelete: boolean;
  onDeleteDoc?: (doc: DocumentListItem) => void;
}

const NodeView: React.FC<NodeViewProps> = ({
  node,
  expanded,
  onToggle,
  selectedDocId,
  onSelectDoc,
  depth,
  showClassification,
  canDelete,
  onDeleteDoc,
}) => {
  const isOpen = expanded.has(node.fullPath);
  const hasContent = node.children.length > 0 || node.docs.length > 0;
  const paddingLeft = depth * 14 + 8;

  return (
    <>
      {node.name && (
        <div
          className="flex cursor-pointer select-none items-center gap-1.5 rounded px-2 py-1 hover:bg-gray-50"
          style={{ paddingLeft }}
          onClick={() => hasContent && onToggle(node.fullPath)}
        >
          {hasContent ? (
            isOpen ? (
              <ChevronDown size={14} className="shrink-0 text-gray-400" />
            ) : (
              <ChevronRight size={14} className="shrink-0 text-gray-400" />
            )
          ) : (
            <span className="w-3.5 shrink-0" />
          )}

          <Folder size={14} className="shrink-0 text-blue-500" />

          <span className="flex-1 truncate text-sm text-gray-700">
            {node.name}
          </span>

          <span className="shrink-0 text-[11px] text-gray-400">
            {countDocs(node)}
          </span>
        </div>
      )}

      {isOpen && (
        <>
          {node.children.map((child) => (
            <NodeView
              key={child.fullPath}
              node={child}
              expanded={expanded}
              onToggle={onToggle}
              selectedDocId={selectedDocId}
              onSelectDoc={onSelectDoc}
              depth={depth + 1}
              showClassification={showClassification}
              canDelete={canDelete}
              onDeleteDoc={onDeleteDoc}
            />
          ))}

          {node.docs.map((doc) => {
            const config = DOCUMENT_STATUS_CONFIG[doc.status];
            const needsReview = doc.classification_requires_review;
            const composition = doc.composition ?? null;

            return (
              <div
                key={doc.id}
                className={cn(
                  "flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-sm",
                  selectedDocId === doc.id
                    ? "bg-blue-50 text-blue-800 ring-1 ring-blue-300"
                    : "text-gray-700 hover:bg-gray-50",
                )}
                style={{ paddingLeft: (depth + 1) * 14 + 8 }}
                onClick={() => onSelectDoc(doc)}
              >
                <FileText size={13} className="shrink-0 text-gray-400" />

                <span className="min-w-0 flex-1 truncate">{doc.filename}</span>

                {composition && (
                  <div className="ml-1 flex shrink-0 items-center gap-1">
                    {composition.composition_type === "multi" && (
                      <span
                        className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700"
                        title="Файл содержит несколько логических документов"
                      >
                        multi
                      </span>
                    )}

                    {typeof composition.segment_count === "number" &&
                      composition.segment_count > 1 && (
                        <span
                          className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[10px] text-gray-600"
                          title="Количество сегментов / логических документов"
                        >
                          {composition.segment_count} seg
                        </span>
                      )}
                  </div>
                )}

                {showClassification && doc.classification_level && (
                  <ClassificationBadge
                    level={doc.classification_level as ClassificationLevel}
                    confidence={doc.classification_confidence}
                    showConfidence={false}
                    className="ml-1 shrink-0"
                  />
                )}

                {needsReview && (
                  <span
                    className="ml-1 shrink-0 rounded border border-yellow-200 bg-yellow-50 px-1.5 py-0.5 text-[11px] text-yellow-700"
                    title="Классификатор не уверен, требуется ручной просмотр"
                  >
                    нужна проверка
                  </span>
                )}

                <span
                  className={cn(
                    "ml-2 shrink-0 text-[11px] uppercase",
                    config?.color === "success"
                      ? "text-green-600"
                      : config?.color === "warning"
                      ? "text-yellow-700"
                      : config?.color === "error"
                      ? "text-red-600"
                      : "text-gray-500",
                  )}
                  title={config?.label || doc.status}
                >
                  {config?.label || doc.status}
                </span>

                {canDelete && onDeleteDoc && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteDoc(doc);
                    }}
                    className="ml-1 text-[11px] text-red-500 hover:text-red-700"
                    title="Удалить документ"
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })}
        </>
      )}
    </>
  );
};

/* ====================================================================
   Утилиты: построение дерева, фильтрация, подсчёт
   ==================================================================== */

function buildTree(documents: DocumentListItem[]): TreeNode {
  const root: TreeNode = { name: "", fullPath: "", children: [], docs: [] };

  for (const doc of documents) {
    const parts = (doc.folder_path || "").split("/").filter((p) => p.length > 0);

    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const path = parts.slice(0, i + 1).join("/");

      let child = current.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          fullPath: path,
          children: [],
          docs: [],
        };
        current.children.push(child);
      }

      current = child;
    }

    current.docs.push(doc);
  }

  sortTree(root);
  return root;
}

function sortTree(node: TreeNode) {
  node.children.sort((a, b) => a.name.localeCompare(b.name, "ru"));
  node.docs.sort((a, b) => a.filename.localeCompare(b.filename, "ru"));
  node.children.forEach(sortTree);
}

function filterTree(node: TreeNode, searchLower: string): TreeNode {
  const matchingDocs = node.docs.filter((d) =>
    d.filename.toLowerCase().includes(searchLower),
  );

  const matchingChildren = node.children
    .map((c) => filterTree(c, searchLower))
    .filter((c) => c.children.length > 0 || c.docs.length > 0);

  return {
    ...node,
    docs: matchingDocs,
    children: matchingChildren,
  };
}

function countDocs(node: TreeNode): number {
  return (
    node.docs.length +
    node.children.reduce((sum, c) => sum + countDocs(c), 0)
  );
}

export default DocumentTree;



