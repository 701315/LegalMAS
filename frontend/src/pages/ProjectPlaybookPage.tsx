// =============================================================
// src/pages/ProjectPlaybookPage.tsx
// Редактирование YAML-playbook проекта (только admin).
// =============================================================

import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import client from "../api/client";

interface PlaybookResponse {
  yaml: string;
}

const ProjectPlaybookPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const { projectRoles } = useAuth();

  const [yamlText, setYamlText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [infoText, setInfoText] = useState<string | null>(null);

  if (!dealId) {
    return (
      <div className="p-6 text-center text-red-600">
        dealId не указан в маршруте.
      </div>
    );
  }

  const currentRole = projectRoles[dealId];
  const isAdmin = currentRole === "admin";

  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md bg-white rounded-lg border shadow p-6 text-center">
          <p className="text-sm text-gray-700 mb-4">
            У вас нет прав для редактирования playbook этого проекта.
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

  // Загрузка существующего playbook
  useEffect(() => {
    let cancelled = false;

    async function loadPlaybook() {
      setIsLoading(true);
      setErrorText(null);
      setInfoText(null);
      try {
        const res = await client.get<PlaybookResponse>(
          `/api/v1/projects/${dealId}/playbook`,
        );
        if (!cancelled) {
          setYamlText(res.data.yaml || "");
        }
      } catch (err: any) {
        // Если 404 — считаем, что playbook ещё не создан
        if (err?.code === "404" || err?.detail === "Not Found") {
          if (!cancelled) {
            setYamlText("");
            setInfoText("Playbook для этого проекта ещё не создан.");
          }
        } else if (!cancelled) {
          setErrorText(
            err?.detail ||
              "Не удалось загрузить playbook. Попробуйте позже.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadPlaybook();
    return () => {
      cancelled = true;
    };
  }, [dealId]);

  const handleFileUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      setYamlText(text);
      setInfoText(`Загружен файл: ${file.name}`);
      setErrorText(null);
    } catch {
      setErrorText("Не удалось прочитать файл YAML.");
    }
  };

  const handleSave = async () => {
    setErrorText(null);
    setInfoText(null);

    if (!yamlText.trim()) {
      setErrorText("Нельзя сохранить пустой playbook.");
      return;
    }

    setIsSaving(true);
    try {
      await client.put(`/api/v1/projects/${dealId}/playbook`, {
        yaml: yamlText,
      });
      setInfoText("Playbook успешно сохранён.");
    } catch (err: any) {
      setErrorText(
        err?.detail ||
          "Не удалось сохранить playbook. Проверьте YAML и попробуйте еще раз.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Заголовок */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Playbook проекта
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

        {/* Управление YAML-файлом */}
        <div className="bg-white rounded-lg border p-4 space-y-3">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-gray-800">
                YAML-playbook проекта
              </p>
              <p className="text-xs text-gray-500">
                Вы можете отредактировать текст вручную или загрузить готовый YAML-файл.
              </p>
            </div>

            <label className="inline-flex items-center gap-2 text-sm text-blue-700 cursor-pointer">
              <span className="px-3 py-1.5 rounded border border-blue-600 text-blue-600 hover:bg-blue-50">
                Загрузить YAML-файл
              </span>
              <input
                type="file"
                accept=".yaml,.yml,text/yaml"
                className="hidden"
                onChange={handleFileUpload}
              />
            </label>
          </div>

          {isLoading ? (
            <p className="text-sm text-gray-500">
              Загружаем текущий playbook…
            </p>
          ) : (
            <textarea
              value={yamlText}
              onChange={(e) => setYamlText(e.target.value)}
              className="w-full h-80 font-mono text-xs border rounded px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
              spellCheck={false}
            />
          )}

          {errorText && (
            <p className="text-sm text-red-600">
              {errorText}
            </p>
          )}

          {infoText && !errorText && (
            <p className="text-sm text-green-700">
              {infoText}
            </p>
          )}

          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleBack}
              className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving || isLoading}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {isSaving ? "Сохраняем..." : "Сохранить"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProjectPlaybookPage;
