// =============================================================
// src/components/documents/DocumentTree.tsx
// Левое дерево документов (иерархия папок Data Room).
// Для юриста даёт:
// - быстрое понимание структуры дата-рума;
// - статус обработки документа;
// - уровень классификации (L0–L4 / manual) в компактном виде.
// =============================================================

import React, { useState, useMemo } from "react";
import type { Document, ClassificationLevel } from "../../types";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FileText,
  Search,
} from "lucide-react";
import { cn } from "../../utils";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { DOCUMENT_STATUS_CONFIG } from "../../utils/statusConfig";

/* ---------- Публичные пропсы ---------- */

interface Props {
  documents: Document[];
  selectedDocId: string | null;
  onSelectDoc: (doc: Document) => void;
  /** Показывать ли компактный бейдж классификации. */
  showClassification?: boolean;
  /** Можно ли удалять документы (admin/editor). */
  canDelete?: boolean;
  /** Колбэк для удаления документа. */
  onDeleteDoc?: (doc: Document) => void;
}

/* ---------- Внутренние типы ---------- */

/** Узел дерева: папка с дочерними папками и файлами. */
interface TreeNode {
  name: string; // Имя папки
  fullPath: string; // Полный путь от корня
  children: TreeNode[]; // Дочерние папки
  docs: Document[]; // Файлы в этой папке
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
  // По умолчанию раскрыт корень
  const [expanded, setExpanded] = useState<Set<string>>(new Set([""]));

  /* --- Построение дерева --- */
  const rootNode = useMemo(() => buildTree(documents), [documents]);

  /* --- Фильтрация по поиску --- */
  const displayTree = useMemo(() => {
    if (!searchText.trim()) return rootNode;
    return filterTree(rootNode, searchText.toLowerCase());
  }, [rootNode, searchText]);

  /* --- Клик по папке: развернуть / свернуть --- */
  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  /* --- Подсчёт документов --- */
  const totalShown = countDocs(displayTree);

  return (
    <div className="flex flex-col h-full bg-white">
      {/* ---------- Поиск ---------- */}
      <div className="p-3 border-b">
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
            className="w-full pl-8 pr-3 py-1.5 text-sm border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <p className="text-[11px] text-gray-400 mt-1.5">
          Показано: {totalShown} из {documents.length} документов
        </p>
      </div>

      {/* ---------- Дерево ---------- */}
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {totalShown === 0 ? (
          <p className="text-center text-gray-400 text-sm py-10">
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
  onSelectDoc: (doc: Document) => void;
  depth: number;
  showClassification: boolean;
  canDelete: boolean;
  onDeleteDoc?: (doc: Document) => void;
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
      {/* ---- Строка папки (пропускаем для корня) ---- */}
      {node.name && (
        <div
          className="flex items-center gap-1.5 py-1 px-2 rounded hover:bg-gray-50 cursor-pointer select-none"
          style={{ paddingLeft }}
          onClick={() => hasContent && onToggle(node.fullPath)}
        >
          {/* Стрелка */}
          {hasContent ? (
            isOpen ? (
              <ChevronDown size={14} className="text-gray-400 shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-gray-400 shrink-0" />
            )
          ) : (
            <span className="w-3.5 shrink-0" />
          )}

          {/* Иконка папки */}
          <Folder size={14} className="text-blue-500 shrink-0" />

          {/* Имя */}
          <span className="flex-1 text-sm text-gray-700 truncate">
            {node.name}
          </span>

          {/* Счётчик документов в поддереве */}
          <span className="text-[11px] text-gray-400 shrink-0">
            {countDocs(node)}
          </span>
        </div>
      )}

      {/* ---- Содержимое (дочерние папки + файлы) ---- */}
      {isOpen && (
        <>
          {/* Дочерние папки */}
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

          {/* Файлы в текущей папке */}
          {node.docs.map((doc) => {
            const config = DOCUMENT_STATUS_CONFIG[doc.status];

            return (
              <div
                key={doc.id}
                className={cn(
                  "flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer text-sm",
                  selectedDocId === doc.id
                    ? "bg-blue-50 text-blue-800 ring-1 ring-blue-300"
                    : "hover:bg-gray-50 text-gray-700",
                )}
                style={{ paddingLeft: (depth + 1) * 14 + 8 }}
                onClick={() => onSelectDoc(doc)}
              >
                <FileText size={13} className="text-gray-400 shrink-0" />

                <span className="flex-1 truncate">{doc.filename}</span>

                {/* Бейдж классификации (компактный) */}
                {showClassification && doc.classification_level && (
                  <ClassificationBadge
                    level={doc.classification_level as ClassificationLevel}
                    confidence={doc.classification_confidence}
                    showConfidence={false}
                    className="shrink-0 ml-1"
                  />
                )}

                {/* Явный статус документа */}
                <span
                  className={cn(
                    "shrink-0 ml-2 text-[11px] uppercase",
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

                {/* Кнопка удаления (если разрешено) */}
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

/** Построить дерево из плоского списка документов. */
function buildTree(documents: Document[]): TreeNode {
  const root: TreeNode = { name: "", fullPath: "", children: [], docs: [] };

  for (const doc of documents) {
    const parts = (doc.folder_path || "")
      .split("/")
      .filter((p) => p.length > 0);

    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const path = parts.slice(0, i + 1).join("/");
      let child = current.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, fullPath: path, children: [], docs: [] };
        current.children.push(child);
      }
      current = child;
    }

    current.docs.push(doc);
  }

  sortTree(root);
  return root;
}

/** Рекурсивная сортировка: папки по имени, файлы по имени. */
function sortTree(node: TreeNode) {
  node.children.sort((a, b) => a.name.localeCompare(b.name, "ru"));
  node.docs.sort((a, b) => a.filename.localeCompare(b.filename, "ru"));
  node.children.forEach(sortTree);
}

/** Фильтрация дерева: оставить только совпадающие файлы и их родительские папки. */
function filterTree(node: TreeNode, searchLower: string): TreeNode {
  const matchingDocs = node.docs.filter((d) =>
    d.filename.toLowerCase().includes(searchLower),
  );

  const matchingChildren = node.children
    .map((c) => filterTree(c, searchLower))
    .filter((c) => c.children.length > 0 || c.docs.length > 0);

  return { ...node, docs: matchingDocs, children: matchingChildren };
}

/** Рекурсивный подсчёт документов во всём поддереве. */
function countDocs(node: TreeNode): number {
  return (
    node.docs.length + node.children.reduce((sum, c) => sum + countDocs(c), 0)
  );
}

export default DocumentTree;
