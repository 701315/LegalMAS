// =============================================================
// src/components/documents/DocumentTree.tsx
// Левое дерево документов (иерархия папок Data Room).
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
import { getCompositionBadgeData } from "../../utils/compositionHelpers";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { DOCUMENT_STATUS_CONFIG } from "../../utils/statusConfig";

/* ---------- Публичные пропсы ---------- */

interface Props {
  documents: DocumentListItem[];
  selectedDocId: string | null;
  onSelectDoc: (doc: DocumentListItem) => void;
  showClassification?: boolean;
  canDelete?: boolean;
  onDeleteDoc?: (doc: DocumentListItem) => void;
}

/* ---------- Внутренние типы ---------- */

interface TreeNode {
  name: string;
  fullPath: string;
  children: TreeNode[];
  docs: DocumentListItem[];
}

/* ====================================================================
   Главный компонент
   ===================================================================== */

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
    <div className="flex h-full flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-surface)]">
      <div className="border-b border-[var(--border-subtle)] px-3 py-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]"
            size={14}
          />
          <input
            type="text"
            placeholder="Поиск по имени документа…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] py-2 pl-8 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-faint)] outline-none transition focus:border-[var(--accent-primary)]"
          />
        </div>

        <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">
          Показано: {totalShown} из {documents.length} документов
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-1.5 py-2">
        {totalShown === 0 ? (
          <p className="py-10 text-center text-sm text-[var(--text-muted)]">
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
   ===================================================================== */

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
        <button
          type="button"
          className="flex w-full items-center gap-1.5 rounded-xl px-2 py-1.5 text-left text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
          style={{ paddingLeft }}
          onClick={() => hasContent && onToggle(node.fullPath)}
        >
          {hasContent ? (
            isOpen ? (
              <ChevronDown
                size={14}
                className="shrink-0 text-[var(--text-faint)]"
              />
            ) : (
              <ChevronRight
                size={14}
                className="shrink-0 text-[var(--text-faint)]"
              />
            )
          ) : (
            <span className="w-3.5 shrink-0" />
          )}

          <Folder
            size={14}
            className="shrink-0 text-[var(--accent-primary)]"
          />

          <span className="min-w-0 flex-1 truncate">{node.name}</span>

          <span className="shrink-0 text-[11px] text-[var(--text-faint)]">
            {countDocs(node)}
          </span>
        </button>
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
            const compositionBadges = getCompositionBadgeData(doc);

            return (
              <button
                key={doc.id}
                type="button"
                className={cn(
                  "flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-sm transition-colors",
                  selectedDocId === doc.id
                    ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
                )}
                style={{ paddingLeft: (depth + 1) * 14 + 8 }}
                onClick={() => onSelectDoc(doc)}
              >
                <FileText
                  size={13}
                  className={cn(
                    "shrink-0",
                    selectedDocId === doc.id
                      ? "text-[var(--accent-primary)]"
                      : "text-[var(--text-faint)]",
                  )}
                />

                <span className="min-w-0 flex-1 truncate">{doc.filename}</span>

                {(compositionBadges.showMultiBadge ||
                  compositionBadges.showSegmentCount ||
                  compositionBadges.showPrimaryLabel ||
                  compositionBadges.showCompositeBadge) && (
                  <div
                    className="ml-1 flex shrink-0 items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {compositionBadges.showMultiBadge && (
                      <span
                        className="inline-flex items-center rounded-full border border-[var(--color-blue)]/20 bg-[var(--color-blue-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-blue)]"
                        title="Файл содержит несколько логических документов"
                      >
                        multi
                      </span>
                    )}

                    {compositionBadges.showSegmentCount && (
                      <span
                        className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
                        title="Количество сегментов / логических документов"
                      >
                        {compositionBadges.segmentCount} seg
                      </span>
                    )}

                    {compositionBadges.showPrimaryLabel && (
                      <span
                        className="inline-flex max-w-[120px] items-center truncate rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]"
                        title={`Основной сегмент: ${compositionBadges.primaryLabel}`}
                      >
                        {compositionBadges.primaryLabel}
                      </span>
                    )}

                    {compositionBadges.showCompositeBadge && (
                      <span
                        className="inline-flex items-center rounded-full border border-[var(--color-purple)]/20 bg-[var(--color-purple-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-purple)]"
                        title="Composite file: содержит несколько юридических документов"
                      >
                        composite
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
                    className="ml-1 shrink-0 rounded-full border border-[var(--color-gold)]/20 bg-[var(--color-gold-highlight)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-gold-text)]"
                    title="Классификатор не уверен, требуется ручной просмотр"
                  >
                    нужна проверка
                  </span>
                )}

                <span
                  className={cn(
                    "ml-2 shrink-0 text-[10px] uppercase tracking-wide",
                    config?.color === "success"
                      ? "text-[var(--color-success)]"
                      : config?.color === "warning"
                        ? "text-[var(--color-gold-text)]"
                        : config?.color === "error"
                          ? "text-[var(--color-error)]"
                          : "text-[var(--text-faint)]",
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
                    className="ml-1 shrink-0 rounded p-0.5 text-[var(--color-error)] transition-colors hover:bg-[var(--color-error-bg)] hover:text-[var(--color-error-text)]"
                    title="Удалить документ"
                    aria-label={`Удалить документ ${doc.filename}`}
                  >
                    ✕
                  </button>
                )}
              </button>
            );
          })}
        </>
      )}
    </>
  );
};

/* ====================================================================
   Утилиты: построение дерева, фильтрация, подсчёт
   ===================================================================== */

function buildTree(documents: DocumentListItem[]): TreeNode {
  const root: TreeNode = { name: "", fullPath: "", children: [], docs: [] };

  for (const doc of documents) {
    const parts = (doc.folder_path || "")
      .split("/")
      .filter((part) => part.length > 0);

    let current = root;

    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      const path = parts.slice(0, index + 1).join("/");

      let child = current.children.find((candidate) => candidate.name === part);
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
  const matchingDocs = node.docs.filter((doc) =>
    doc.filename.toLowerCase().includes(searchLower),
  );

  const matchingChildren = node.children
    .map((child) => filterTree(child, searchLower))
    .filter((child) => child.children.length > 0 || child.docs.length > 0);

  return {
    ...node,
    docs: matchingDocs,
    children: matchingChildren,
  };
}

function countDocs(node: TreeNode): number {
  return node.docs.length + node.children.reduce((sum, child) => sum + countDocs(child), 0);
}

export default DocumentTree;


