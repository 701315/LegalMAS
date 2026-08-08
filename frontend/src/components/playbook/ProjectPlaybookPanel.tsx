// =============================================================
// src/components/playbook/ProjectPlaybookPanel.tsx
// =============================================================

import React, { useEffect, useState } from "react";
import client from "../../api/client";
import { useDealPermissions } from "../../hooks/usePermissions";
import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";
import type { ApiError } from "../../types";

interface PlaybookResponse {
  yaml: string;
}

interface ProjectPlaybookPanelProps {
  dealId: string;
  mode?: "page" | "embedded";
  onFinished?: () => void;
  onCancel?: () => void;
}

const ProjectPlaybookPanel: React.FC<ProjectPlaybookPanelProps> = ({
  dealId,
  mode = "page",
  onFinished,
  onCancel,
}) => {
  const [yamlText, setYamlText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [infoText, setInfoText] = useState<string | null>(null);

  const { canViewOverview } = useDealPermissions(dealId);
  const canEditPlaybook = canViewOverview;

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
      onFinished?.();
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

  if (!canEditPlaybook) {
    return (
      <div
        className={
          mode === "page" ? "min-h-screen bg-[var(--bg-base)] px-4" : "h-full"
        }
      >
        <div
          className={
            mode === "page"
              ? "flex min-h-screen items-center justify-center"
              : "flex h-full items-center justify-center p-5"
          }
        >
          <div className="w-full max-w-md rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center shadow-sm">
            <p className="mb-4 text-sm text-[var(--text-secondary)]">
              У вас нет прав для редактирования playbook этого проекта.
            </p>

            {onCancel && (
              <Button variant="secondary" size="sm" onClick={onCancel}>
                Вернуться назад
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const containerClass =
    mode === "page"
      ? "min-h-screen bg-[var(--bg-base)] px-4 py-6 text-[var(--text-primary)]"
      : "h-full min-h-0 bg-[var(--bg-elevated-soft)] px-5 py-4 text-[var(--text-primary)]";

  const contentClass =
    mode === "page"
      ? "mx-auto max-w-5xl space-y-5"
      : "flex h-full min-h-0 flex-col space-y-4";

  return (
    <div className={containerClass}>
      <div className={contentClass}>
        {mode === "page" && (
          <header className="flex flex-wrap items-center justify-between gap-4">
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
                Этот редактор предназначен для прямого редактирования
                YAML-конфигурации playbook для конкретного проекта. Используйте
                его только если понимаете структуру схемы.
              </p>
            </div>

            {onCancel && (
              <Button variant="secondary" size="sm" onClick={onCancel}>
                ← Назад к проекту
              </Button>
            )}
          </header>
        )}

        {errorText && <InlineAlert tone="error" message={errorText} />}
        {!errorText && infoText && <InlineAlert tone="success" message={infoText} />}

        <section
          className={[
            "rounded-[28px] border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",
            mode === "page" ? "p-5" : "flex min-h-0 flex-1 flex-col p-5",
          ].join(" ")}
        >
          <div className="flex flex-col gap-3 border-b border-[var(--border-soft)] pb-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Редактор YAML-playbook
              </p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                Отредактируйте текст вручную или загрузите готовый YAML-файл.
                При сохранении конфигурация применится только к этому проекту.
              </p>
            </div>

            <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--accent-primary)]">
              <span className="rounded-2xl border border-[var(--accent-primary)] px-3 py-1.5 text-[var(--accent-primary)] transition hover:bg-[var(--accent-muted)]">
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

          <div
            className={
              mode === "page"
                ? "mt-4 space-y-3"
                : "mt-4 flex min-h-0 flex-1 flex-col space-y-3"
            }
          >
            {isLoading ? (
              <p className="text-sm text-[var(--text-secondary)]">
                Загружаем текущий playbook…
              </p>
            ) : (
              <textarea
                value={yamlText}
                onChange={(e) => setYamlText(e.target.value)}
                className={[
                  "w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-3 py-2 font-mono text-xs text-[var(--text-primary)] outline-none transition",
                  "focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)]",
                  mode === "page" ? "h-80" : "min-h-[320px] flex-1 resize-none",
                ].join(" ")}
                spellCheck={false}
              />
            )}

            <div className="mt-3 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--border-soft)] pt-3">
              {onCancel && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onCancel}
                  disabled={isSaving}
                >
                  Отмена
                </Button>
              )}

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

export default ProjectPlaybookPanel;


