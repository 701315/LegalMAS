// =============================================================
// src/pages/ProjectUploadPage.tsx
// Загрузка документов для проекта (admin + editor).
// =============================================================

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useDocuments, useUploadDocuments } from "../api/documents";
import { formatDate } from "../utils";
import { useDealPermissions } from "../hooks/usePermissions";

const ProjectUploadPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [folderPath, setFolderPath] = useState<string>("");
  const [errorText, setErrorText] = useState<string | null>(null);

  if (!dealId) {
    return (
      <div className="p-6 text-center text-red-600">
        dealId не указан в маршруте.
      </div>
    );
  }

  // Права на загрузку документов в конкретную сделку
  const { canUploadDocuments } = useDealPermissions(dealId);

  // Список уже загруженных документов по сделке (первая страница)
  const { data: docsPage, isLoading: docsLoading } = useDocuments(dealId, 1);
  const documents = docsPage?.items ?? [];

  // Мутация для загрузки файлов
  const uploadMutation = useUploadDocuments(dealId);
  const isSubmitting = uploadMutation.isPending;

  if (!canUploadDocuments) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md bg-white rounded-lg border shadow p-6 text-center">
          <p className="text-sm text-gray-700 mb-4">
            У вас нет прав для загрузки документов в этот проект.
          </p>
          <button
            type="button"
            onClick={() => navigate(`/projects/${dealId}`)}
            className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
          >
            Вернуться к проекту
          </button>
        </div>
      </div>
    );
  }

  const handleBack = () => {
    navigate(`/projects/${dealId}`);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorText(null);
    const files = Array.from(e.target.files ?? []);
    setSelectedFiles(files);
  };

  const handleUpload = async () => {
    setErrorText(null);

    if (!selectedFiles.length) {
      setErrorText("Выберите хотя бы один файл для загрузки.");
      return;
    }

    try {
      await uploadMutation.mutateAsync({
        files: selectedFiles,
        folderPath: folderPath.trim() || null,
      });

      setSelectedFiles([]);
      navigate(`/projects/${dealId}`);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.detail ||
        "Не удалось загрузить документы. Попробуйте позже.";
      setErrorText(detail);
    }
  };

  const handleCancel = () => {
    navigate(`/projects/${dealId}`);
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Заголовок */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Загрузка документов
            </h1>
            <p className="text-sm text-gray-500">
              Проект: {dealId}
            </p>
          </div>
          <button
            type="button"
            onClick={handleBack}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            ← Назад к проекту
          </button>
        </div>

        {/* Список уже загруженных документов */}
        <div className="bg-white rounded-lg border p-4">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">
            Уже загруженные документы
          </h2>

          {docsLoading && (
            <p className="text-sm text-gray-500">
              Загружаем список документов…
            </p>
          )}

          {!docsLoading && documents.length === 0 && (
            <p className="text-sm text-gray-500">
              В этом проекте пока нет документов.
            </p>
          )}

          {!docsLoading && documents.length > 0 && (
            <ul className="divide-y divide-gray-100 text-sm">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="py-2 flex items-center justify-between"
                >
                  <div>
                    <p className="text-gray-800">{doc.filename}</p>
                    <p className="text-xs text-gray-500">
                      Статус: {doc.status} · Создан: {formatDate(doc.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Выбор файлов и запуск загрузки */}
        <div className="bg-white rounded-lg border p-4 space-y-4">
          <h2 className="text-sm font-semibold text-gray-800">
            Добавить новые документы
          </h2>

          {/* Папка/путь в Data Room */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Папка в Data Room (необязательно)
            </label>
            <input
              type="text"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder='Например: 01. Corporate/Charter Docs'
            />
            <p className="mt-1 text-xs text-gray-500">
              Это значение попадёт в поле folder_path у новых документов.
            </p>
          </div>

          {/* Выбор файлов */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Файлы для загрузки
            </label>
            <input
              type="file"
              multiple
              onChange={handleFileChange}
              className="block text-sm"
            />
            {selectedFiles.length > 0 && (
              <div className="mt-1 text-xs text-gray-600">
                Выбрано файлов: {selectedFiles.length}
              </div>
            )}
          </div>

          {errorText && (
            <p className="text-sm text-red-600">
              {errorText}
            </p>
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleUpload}
              disabled={isSubmitting || selectedFiles.length === 0}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {isSubmitting ? "Загружаем..." : "Загрузить"}
            </button>

            <button
              type="button"
              onClick={handleCancel}
              className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
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
