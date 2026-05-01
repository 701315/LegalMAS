// =============================================================
// src/pages/ProjectUploadPage.tsx
// Загрузка документов для проекта (admin + editor).
// Упрощённый и понятный UI выбора файлов / папки.
// =============================================================

import React, { useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import axios from "axios";

import { useDocuments, useUploadDocuments } from "../api/documents";
import { useDealPermissions } from "../hooks/usePermissions";
import { formatDate } from "../utils";

type FileWithRelativePath = File & {
  webkitRelativePath?: string;
};

const ProjectUploadPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const filesInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  const resolvedDealId = dealId ?? "";

  const { canUploadDocuments } = useDealPermissions(resolvedDealId);
  const {
    data: docsPage,
    isLoading: docsLoading,
    error: docsError,
  } = useDocuments(resolvedDealId, 1);
  const uploadMutation = useUploadDocuments(resolvedDealId);

  const [selectedFiles, setSelectedFiles] = useState<FileWithRelativePath[]>([]);
  const [selectionMode, setSelectionMode] = useState<"files" | "folder" | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const documents = docsPage?.items ?? [];
  const isSubmitting = uploadMutation.isPending;
  const hasDocuments = documents.length > 0;
  const canSubmit = !isSubmitting && selectedFiles.length > 0;

  const docsErrorText = useMemo(() => {
    if (!docsError) return null;

    if (axios.isAxiosError<{ detail?: string }>(docsError)) {
      return (
        docsError.response?.data?.detail ||
        docsError.message ||
        "Не удалось загрузить список документов."
      );
    }

    if (docsError instanceof Error) {
      return docsError.message || "Не удалось загрузить список документов.";
    }

    return "Не удалось загрузить список документов.";
  }, [docsError]);

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  if (!canUploadDocuments) {
    return (
      <div className="min-h-screen bg-gray-50 px-4 py-6">
        <div className="mx-auto flex min-h-[60vh] max-w-md items-center justify-center">
          <div className="w-full rounded-lg border bg-white p-6 text-center shadow-sm">
            <p className="mb-4 text-sm text-gray-700">
              У вас нет прав для загрузки документов в этот проект.
            </p>
            <button
              type="button"
              onClick={() => navigate(`/projects/${dealId}`)}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
            >
              Вернуться к проекту
            </button>
          </div>
        </div>
      </div>
    );
  }

  const goBackToProject = () => {
    navigate(`/projects/${dealId}`);
  };

  const resetSelection = () => {
    setSelectedFiles([]);
    setSelectionMode(null);
    setErrorText(null);

    if (filesInputRef.current) {
      filesInputRef.current.value = "";
    }

    if (folderInputRef.current) {
      folderInputRef.current.value = "";
    }
  };

  const applySelectedFiles = (
    files: FileWithRelativePath[],
    mode: "files" | "folder",
  ) => {
    setErrorText(null);
    setSelectionMode(mode);
    setSelectedFiles(files);
  };

  const handleFilesPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []) as FileWithRelativePath[];
    applySelectedFiles(files, "files");
  };

  const handleFolderPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []) as FileWithRelativePath[];
    applySelectedFiles(files, "folder");
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    const files = Array.from(e.dataTransfer.files ?? []) as FileWithRelativePath[];
    if (files.length === 0) return;

    applySelectedFiles(files, "files");
  };

  const handleUpload = async () => {
    setErrorText(null);

    if (selectedFiles.length === 0) {
      setErrorText("Выберите хотя бы один файл или папку для загрузки.");
      return;
    }

    try {
      await uploadMutation.mutateAsync({
        files: selectedFiles,
      });

      resetSelection();
      navigate(`/projects/${dealId}`);
    } catch (err: unknown) {
      if (axios.isAxiosError<{ detail?: string }>(err)) {
        setErrorText(
          err.response?.data?.detail ||
            err.message ||
            "Не удалось загрузить документы. Попробуйте позже.",
        );
        return;
      }

      if (err instanceof Error) {
        setErrorText(
          err.message || "Не удалось загрузить документы. Попробуйте позже.",
        );
        return;
      }

      setErrorText("Не удалось загрузить документы. Попробуйте позже.");
    }
  };

  const topVisibleFiles = selectedFiles.slice(0, 10);
  const hasMoreFiles = selectedFiles.length > topVisibleFiles.length;

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Загрузка документов
            </h1>
            <p className="text-sm text-gray-500">Проект: {dealId}</p>
          </div>

          <button
            type="button"
            onClick={goBackToProject}
            className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            ← Назад к проекту
          </button>
        </div>

        {errorText && (
          <div
            className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            role="alert"
          >
            {errorText}
          </div>
        )}

        {docsErrorText && (
          <div
            className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
            role="alert"
          >
            {docsErrorText}
          </div>
        )}

        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-gray-800">
            Уже загруженные документы
          </h2>

          {docsLoading && (
            <p className="text-sm text-gray-500">
              Загружаем список документов…
            </p>
          )}

          {!docsLoading && !docsErrorText && !hasDocuments && (
            <p className="text-sm text-gray-500">
              В этом проекте пока нет документов.
            </p>
          )}

          {!docsLoading && hasDocuments && (
            <ul className="divide-y divide-gray-100 text-sm">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center justify-between gap-4 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-gray-800">{doc.filename}</p>
                    <p className="text-xs text-gray-500">
                      Статус: {doc.status} · Создан: {formatDate(doc.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-gray-800">
            Добавить новые документы
          </h2>

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
              }
            }}
            type="file"
            multiple
            onChange={handleFolderPicked}
            className="hidden"
          />

          <div
            role="button"
            tabIndex={0}
            onClick={() => filesInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                filesInputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setIsDragActive(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setIsDragActive(false);
            }}
            onDrop={handleDrop}
            className={`rounded-xl border-2 border-dashed p-8 text-center transition ${
              isDragActive
                ? "border-blue-500 bg-blue-50"
                : "border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/40"
            }`}
            aria-label="Нажмите, чтобы выбрать файлы, или перетащите их сюда"
          >
            <div className="mx-auto max-w-xl space-y-3">
              <div className="text-base font-semibold text-gray-900">
                Перетащите файлы сюда или нажмите для выбора
              </div>
              <p className="text-sm text-gray-500">
                Самый простой способ — нажать на область и выбрать документы в
                проводнике.
              </p>

              <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    filesInputRef.current?.click();
                  }}
                  disabled={isSubmitting}
                  className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Выбрать файлы
                </button>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    folderInputRef.current?.click();
                  }}
                  disabled={isSubmitting}
                  className="rounded border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Выбрать папку
                </button>
              </div>

              <p className="text-xs text-gray-500">
                Если браузер поддерживает выбор папки, будут добавлены файлы из
                выбранной директории и вложенных подпапок. [web:1434][web:1437]
              </p>
            </div>
          </div>

          {selectedFiles.length > 0 && (
            <div className="mt-4 rounded border border-gray-200 bg-gray-50 p-4">
              <div className="mb-2 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-gray-800">
                    Готово к загрузке
                  </div>
                  <div className="text-xs text-gray-500">
                    Режим:{" "}
                    {selectionMode === "folder"
                      ? "выбрана папка"
                      : "выбраны файлы"}{" "}
                    · Всего элементов: {selectedFiles.length}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={resetSelection}
                  disabled={isSubmitting}
                  className="text-sm text-gray-500 hover:text-gray-700 disabled:opacity-60"
                >
                  Очистить
                </button>
              </div>

              <ul className="space-y-1 text-xs text-gray-600">
                {topVisibleFiles.map((file) => (
                  <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                    {file.webkitRelativePath || file.name}
                  </li>
                ))}
              </ul>

              {hasMoreFiles && (
                <div className="mt-2 text-xs text-gray-500">
                  И ещё {selectedFiles.length - topVisibleFiles.length} файлов…
                </div>
              )}
            </div>
          )}

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={handleUpload}
              disabled={!canSubmit}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Загружаем..." : "Загрузить"}
            </button>

            <button
              type="button"
              onClick={goBackToProject}
              disabled={isSubmitting}
              className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Отмена
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProjectUploadPage;
