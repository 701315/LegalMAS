// =============================================================
// frontend/src/components/upload/ProjectUploadPanel.tsx
// =============================================================

import React, { useMemo, useRef, useState } from "react";
import axios from "axios";
import { useDocuments, useUploadDocuments } from "../../api/documents";
import { useDealPermissions } from "../../hooks/usePermissions";
import { formatDate } from "../../utils";
import Button from "../ui/Button";
import UploadDropzoneCard from "./UploadDropzoneCard";
import UploadWorkflowCard from "./UploadWorkflowCard";
import PreparedFilesTable, {
  type PreparedFileRow,
} from "./PreparedFilesTable";

type FileWithRelativePath = File & {
  webkitRelativePath?: string;
};

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size >= 100 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${
    units[unitIndex]
  }`;
}

function getFileExtension(filename: string): string {
  const trimmed = filename.trim();
  const idx = trimmed.lastIndexOf(".");
  if (idx <= 0 || idx === trimmed.length - 1) return "—";
  return trimmed.slice(idx + 1).toUpperCase();
}

function getRelativePath(file: FileWithRelativePath): string {
  return file.webkitRelativePath?.trim() || "—";
}

interface ProjectUploadPanelProps {
  dealId: string;
  onFinished: () => void;
  mode?: "page" | "embedded";
  showWorkflow?: boolean;
}

const ProjectUploadPanel: React.FC<ProjectUploadPanelProps> = ({
  dealId,
  onFinished,
  mode = "page",
  showWorkflow = true,
}) => {
  const filesInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  const { canUploadDocuments } = useDealPermissions(dealId);

  const {
    data: docsPage,
    isLoading: docsLoading,
    error: docsError,
  } = useDocuments(dealId, 1);

  const uploadMutation = useUploadDocuments(dealId);

  const [selectedFiles, setSelectedFiles] = useState<FileWithRelativePath[]>([]);
  const [selectedPreparedRowIds, setSelectedPreparedRowIds] = useState<string[]>(
    [],
  );
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const documents = docsPage?.items ?? [];
  const isSubmitting = uploadMutation.isPending;
  const canSubmit = !isSubmitting && selectedFiles.length > 0;

  const docsErrorText = useMemo(() => {
    if (!docsError) return null;

    if (axios.isAxiosError<{ detail?: string }>(docsError)) {
      return (
        docsError.response?.data?.detail ??
        docsError.message ??
        "Ошибка загрузки документов."
      );
    }

    if (docsError instanceof Error) {
      return docsError.message || "Ошибка загрузки документов.";
    }

    return "Ошибка загрузки документов.";
  }, [docsError]);

  const preparedRows = useMemo<PreparedFileRow[]>(() => {
    return selectedFiles.map((file, index) => ({
      id: `${file.name}-${file.size}-${index}`,
      name: file.name,
      extension: getFileExtension(file.name),
      sizeLabel: formatFileSize(file.size),
      pathLabel: getRelativePath(file),
    }));
  }, [selectedFiles]);

  const resetInputs = () => {
    if (filesInputRef.current) {
      filesInputRef.current.value = "";
    }
    if (folderInputRef.current) {
      folderInputRef.current.value = "";
    }
  };

  const resetSelection = () => {
    setSelectedFiles([]);
    setSelectedPreparedRowIds([]);
    setErrorText(null);
    resetInputs();
  };

  const applySelectedFiles = (files: FileWithRelativePath[]) => {
    setErrorText(null);
    setSelectedPreparedRowIds([]);
    setSelectedFiles(files);
  };

  const handleFilesPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []) as FileWithRelativePath[];
    applySelectedFiles(files);
  };

  const handleFolderPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []) as FileWithRelativePath[];
    applySelectedFiles(files);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    const files = Array.from(e.dataTransfer.files ?? []) as FileWithRelativePath[];
    if (files.length === 0) return;

    applySelectedFiles(files);
  };

  const togglePreparedRow = (rowId: string) => {
    setSelectedPreparedRowIds((prev) =>
      prev.includes(rowId)
        ? prev.filter((id) => id !== rowId)
        : [...prev, rowId],
    );
  };

  const toggleAllPreparedRows = () => {
    setSelectedPreparedRowIds((prev) =>
      prev.length === preparedRows.length ? [] : preparedRows.map((row) => row.id),
    );
  };

  const removePreparedRows = (rowIds: string[]) => {
    const rowIdSet = new Set(rowIds);

    setSelectedFiles((prev) =>
      prev.filter((file, index) => {
        const rowId = `${file.name}-${file.size}-${index}`;
        return !rowIdSet.has(rowId);
      }),
    );

    setSelectedPreparedRowIds((prev) => prev.filter((id) => !rowIdSet.has(id)));
  };

  const handleRemovePreparedSelected = () => {
    if (selectedPreparedRowIds.length === 0) return;
    removePreparedRows(selectedPreparedRowIds);
  };

  const handleRemovePreparedSingle = (rowId: string) => {
    removePreparedRows([rowId]);
  };

  const handleUpload = async () => {
    setErrorText(null);

    if (selectedFiles.length === 0) {
      setErrorText("Сначала выберите файлы или папку для загрузки.");
      return;
    }

    try {
      await uploadMutation.mutateAsync({
        files: selectedFiles,
      });

      resetSelection();
      onFinished();
    } catch (err: unknown) {
      if (axios.isAxiosError<{ detail?: string }>(err)) {
        setErrorText(
          err.response?.data?.detail ??
            err.message ??
            "Не удалось загрузить документы.",
        );
        return;
      }

      if (err instanceof Error) {
        setErrorText(err.message || "Не удалось загрузить документы.");
        return;
      }

      setErrorText("Не удалось загрузить документы.");
    }
  };

  if (!canUploadDocuments) {
    if (mode === "page") {
      return (
        <div className="mx-auto max-w-md">
          <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
            <p className="text-sm text-[var(--text-secondary)]">
              У вас нет прав на загрузку документов в этот проект.
            </p>
          </div>
        </div>
      );
    }

    return (
      <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
        <p className="text-sm text-[var(--text-secondary)]">
          У вас нет прав на загрузку документов в этот проект.
        </p>
      </div>
    );
  }

  const gridClass = showWorkflow ? "grid gap-4 lg:grid-cols-2" : "grid gap-4";

  const content = (
    <div
      className={
        mode === "page"
          ? "mx-auto max-w-6xl space-y-6"
          : "flex min-h-0 flex-col space-y-4"
      }
    >
      {mode === "page" && (
        <header className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-[26px] font-semibold tracking-tight">
              Загрузка документов
            </h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Подготовьте набор файлов и загрузите его в проект.
            </p>
          </div>
        </header>
      )}

      <input
        ref={filesInputRef}
        type="file"
        multiple
        onChange={handleFilesPicked}
        className="hidden"
      />

      <input
        ref={(node) => {
          folderInputRef.current = node;

          if (node) {
            node.setAttribute("webkitdirectory", "");
            node.setAttribute("directory", "");
          }
        }}
        type="file"
        multiple
        onChange={handleFolderPicked}
        className="hidden"
      />

      <div className={gridClass}>
        <UploadDropzoneCard
          isDragActive={isDragActive}
          isSubmitting={isSubmitting}
          selectedCount={selectedFiles.length}
          onDragOver={handleDragOver}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onPickFiles={() => filesInputRef.current?.click()}
          onPickFolder={() => folderInputRef.current?.click()}
        />

        {showWorkflow && <UploadWorkflowCard />}
      </div>

      {errorText && (
        <div className="rounded-[18px] border border-[color:rgba(161,53,68,0.22)] bg-[color:rgba(161,53,68,0.08)] px-4 py-3 text-sm text-[color:rgb(120,35,46)]">
          {errorText}
        </div>
      )}

      <PreparedFilesTable
        rows={preparedRows}
        selectedRowIds={selectedPreparedRowIds}
        isUploading={isSubmitting}
        canUpload={canSubmit}
        onUpload={handleUpload}
        onToggleRow={togglePreparedRow}
        onToggleAll={toggleAllPreparedRows}
        onRemoveSelected={handleRemovePreparedSelected}
        onRemoveSingle={handleRemovePreparedSingle}
      />

      <section className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Уже загруженные документы
            </h2>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Документы, которые уже присутствуют в проекте.
            </p>
          </div>

          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => window.location.reload()}
          >
            Обновить
          </Button>
        </div>

        <div className="px-5 py-4">
          {docsLoading ? (
            <div className="text-sm text-[var(--text-muted)]">Загрузка…</div>
          ) : docsErrorText ? (
            <div className="text-sm text-[color:rgb(120,35,46)]">
              {docsErrorText}
            </div>
          ) : documents.length === 0 ? (
            <div className="text-sm text-[var(--text-muted)]">
              В проекте пока нет загруженных документов.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--bg-base)]">
                    <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Имя файла
                    </th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Статус
                    </th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Загружен
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr
                      key={doc.id}
                      className="border-b border-[var(--border-soft)] last:border-b-0"
                    >
                      <td className="px-4 py-3 text-sm text-[var(--text-primary)]">
                        {doc.filename}
                      </td>
                      <td className="px-4 py-3 text-xs text-[var(--text-secondary)]">
                        {doc.status}
                      </td>
                      <td className="px-4 py-3 text-xs text-[var(--text-secondary)]">
                        {doc.created_at ? formatDate(doc.created_at) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );

  return mode === "page" ? (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6 text-[var(--text-primary)]">
      {content}
    </div>
  ) : (
    <div className="min-w-0 text-[var(--text-primary)]">{content}</div>
  );
};

export default ProjectUploadPanel;




