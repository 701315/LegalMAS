// =============================================================
// src/pages/ProjectPlaybookPage.tsx
// Редактирование YAML-playbook проекта (по capability).
// Приведено к единому product-дизайну workspace.
// =============================================================

import React, { useEffect, useState } from "react";
import { useNavigate, useParams, Navigate } from "react-router-dom";
import client from "../api/client";
import { useDealPermissions } from "../hooks/usePermissions";
import Button from "../components/ui/Button";
import InlineAlert from "../components/InlineAlert";
import type { ApiError } from "../types";

interface PlaybookResponse {
  yaml: string;
}

const ProjectPlaybookPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const [yamlText, setYamlText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [infoText, setInfoText] = useState<string | null>(null);

  const { canViewOverview } = useDealPermissions(dealId as string);
  const canEditPlaybook = canViewOverview;

  useEffect(() => {
    if (!dealId) return;

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
      } catch (err) {
        const apiErr = err as ApiError;
        if (
          apiErr.code === "404" ||
          apiErr.detail === "Not Found" ||
          apiErr.detail === "PLAYBOOK_NOT_FOUND"
        ) {
          if (!cancelled) {
            setYamlText("");
            setInfoText("Playbook для этого проекта ещё не создан.");
          }
        } else if (!cancelled) {
          setErrorText(
            apiErr.detail ||
              "Не удалось загрузить playbook. Попробуйте позже.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadPlaybook();
    return () => {
      cancelled = true;
    };
  }, [dealId]);

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  if (!canEditPlaybook) {
    return (
      <div className="min-h-screen bg-[var(--bg-base)] px-4">
        <div className="flex min-h-screen items-center justify-center">
          <div className="w-full max-w-md rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center shadow-sm">
            <p className="mb-4 text-sm text-[var(--text-secondary)]">
              У вас нет прав для редактирования playbook этого проекта.
            </p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(`/projects/${dealId}`)}
            >
              Вернуться к проекту
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const handleBack = () => {
    navigate(`/projects/${dealId}`);
  };

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
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(
        apiErr.detail ||
          "Не удалось сохранить playbook. Проверьте YAML и попробуйте ещё раз.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6 text-[var(--text-primary)]">
      <div className="mx-auto max-w-5xl space-y-5">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
              Playbook YAML
            </div>
            <h1 className="mt-3 text-[24px] font-semibold tracking-tight text-[var(--text-primary)]">
              YAML-playbook проекта
            </h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Проект: {dealId}
            </p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Этот редактор предназначен для прямого редактирования YAML-конфигурации
              playbook для конкретного проекта. Используйте его только если понимаете структуру схемы.
            </p>
          </div>

          <Button variant="secondary" size="sm" onClick={handleBack}>
            ← Назад к проекту
          </Button>
        </div>

        <InlineAlert tone="error" message={errorText} />
        <InlineAlert tone="success" message={infoText} />

        {/* Main card */}
        <section className="rounded-[28px] border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="flex flex-col gap-3 border-b border-[var(--border-soft)] pb-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Редактор YAML-playbook
              </p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                Отредактируйте текст вручную или загрузите готовый YAML-файл. При сохранении
                конфигурация применится только к этому проекту.
              </p>
            </div>

            <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--accent-primary)]">
              <span className="rounded-2xl border border-[var(--accent-primary)] px-3 py-1.5 text-[var(--accent-primary)] hover:bg-[var(--accent-muted)]">
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

          <div className="mt-4 space-y-3">
            {isLoading ? (
              <p className="text-sm text-[var(--text-secondary)]">
                Загружаем текущий playbook…
              </p>
            ) : (
              <textarea
                value={yamlText}
                onChange={(e) => setYamlText(e.target.value)}
                className="h-80 w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-3 py-2 font-mono text-xs text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)]"
                spellCheck={false}
              />
            )}

            {errorText && (
              <p className="text-sm text-[color:rgb(120,35,46)]">{errorText}</p>
            )}

            {infoText && !errorText && (
              <p className="text-sm text-[var(--text-secondary)]">
                {infoText}
              </p>
            )}

            <div className="mt-3 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--border-soft)] pt-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleBack}
                disabled={isSaving}
              >
                Отмена
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleSave}
                disabled={isSaving || isLoading}
                isLoading={isSaving}
              >
                {isSaving ? "Сохраняем..." : "Сохранить"}
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default ProjectPlaybookPage;



