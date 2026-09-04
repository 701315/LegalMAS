// =============================================================
// frontend/src/components/upload/ProjectUploadPanel.tsx
// =============================================================

import React, { useMemo, useRef, useState } from "react";
import axios from "axios";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { useDocuments, useUploadDocuments } from "../../api/documents";
import { useDealPermissions } from "../../hooks/usePermissions";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../hooks/useAuth";
import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";
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

function getErrorText(err: unknown, fallback: string): string {
  if (typeof err !== "object" || err === null) return fallback;

  const maybeApiError = err as Record<string, unknown>;
  if (
    typeof maybeApiError["detail"] === "string" &&
    maybeApiError["detail"]
  ) {
    return maybeApiError["detail"];
  }

  if (axios.isAxiosError<{ detail?: string }>(err)) {
    return err.response?.data?.detail ?? err.message ?? fallback;
  }

  if (err instanceof Error && err.message) {
    return err.message;
  }

  return fallback;
}

function formatDocDate(value: string, locale: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
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
  const { t, i18n } = useTranslation("documents");
  const filesInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const qc = useQueryClient();
  const { userId } = useAuth();

  const { canUploadDocuments } = useDealPermissions(dealId);

  const {
    data: docsPage,
    isLoading: docsLoading,
    error: docsError,
    refetch: refetchDocuments,
    isRefetching: isRefetchingDocuments,
  } = useDocuments(dealId, 1);

  const uploadMutation = useUploadDocuments(dealId);

  const [selectedFiles, setSelectedFiles] = useState<FileWithRelativePath[]>(
    [],
  );
  const [selectedPreparedRowIds, setSelectedPreparedRowIds] = useState<
    string[]
  >([]);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const documents = docsPage?.items ?? [];
  const isSubmitting = uploadMutation.isPending;
  const canSubmit = !isSubmitting && selectedFiles.length > 0;

  const docsErrorText = useMemo(() => {
    if (!docsError) return null;
    return getErrorText(docsError, t("upload.errors.loadDocsFailed"));
  }, [docsError, t]);

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
    if (filesInputRef.current) filesInputRef.current.value = "";
    if (folderInputRef.current) folderInputRef.current.value = "";
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

    const files = Array.from(
      e.dataTransfer.files ?? [],
    ) as FileWithRelativePath[];
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
      prev.length === preparedRows.length
        ? []
        : preparedRows.map((row) => row.id),
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

    setSelectedPreparedRowIds((prev) =>
      prev.filter((id) => !rowIdSet.has(id)),
    );
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
      setErrorText(t("upload.errors.selectFilesFirst"));
      return;
    }

    try {
      await uploadMutation.mutateAsync({ files: selectedFiles });
      await qc.invalidateQueries({
        queryKey: queryKeys.userProjects(userId ?? ""),
      });
      resetSelection();
      onFinished();
    } catch (err: unknown) {
      setErrorText(getErrorText(err, t("upload.errors.uploadFailed")));
    }
  };

  const handleRefreshDocuments = async () => {
    setErrorText(null);

    try {
      await refetchDocuments();
    } catch (err: unknown) {
      setErrorText(
        getErrorText(err, t("upload.errors.refreshFailed")),
      );
    }
  };

  if (!canUploadDocuments) {
    return (
      <div className="mx-auto max-w-md">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
          <p className="text-sm text-[var(--text-secondary)]">
            {t("upload.restricted")}
          </p>
        </div>
      </div>
    );
  }

  const gridClass = showWorkflow ? "grid gap-4 lg:grid-cols-2" : "grid gap-4";

  const content = (
    <div
      className={
        mode === "page"
          ? "space-y-4"
          : "flex min-h-0 flex-col space-y-4"
      }
    >
      {mode === "page" && (
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {t("upload.header.title")}
            </h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              {t("upload.header.subtitle")}
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

      {errorText && <InlineAlert tone="error" message={errorText} />}

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

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              {t("upload.existing.title")}
            </h2>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {t("upload.existing.subtitle")}
            </p>
          </div>

          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={handleRefreshDocuments}
            isLoading={isRefetchingDocuments}
          >
            {t("actions.refresh", { ns: "common" })}
          </Button>
        </div>

        <div className="px-5 py-4">
          {docsLoading ? (
            <div className="text-sm text-[var(--text-muted)]">
              {t("upload.existing.loading")}
            </div>
          ) : docsErrorText ? (
            <div className="text-sm text-[var(--color-error-text)]">
              {docsErrorText}
            </div>
          ) : documents.length === 0 ? (
            <div className="text-sm text-[var(--text-muted)]">
              {t("upload.existing.empty")}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--bg-base)]">
                    <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      {t("upload.existing.table.filename")}
                    </th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      {t("upload.existing.table.status")}
                    </th>
                    <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      {t("upload.existing.table.uploaded")}
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
                        {doc.created_at ? formatDocDate(doc.created_at, i18n.language) : "—"}
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
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein px-4 py-5 md:px-6">{content}</div>
    </div>
  ) : (
    <div className="min-w-0 text-[var(--text-primary)]">{content}</div>
  );
};

export default ProjectUploadPanel;


