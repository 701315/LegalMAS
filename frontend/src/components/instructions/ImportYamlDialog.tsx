// src/components/instructions/ImportYamlDialog.tsx
// Универсальная модалка импорта YAML-файла как нового draft.
// Работает для двух режимов: global instruction и doc-type instruction.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, FileUp, X } from "lucide-react";
import * as yaml from "js-yaml";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export type ImportYamlKind = "global" | "doc-type";

export interface ImportYamlSubmitPayload {
  /** Извлечённый из YAML код: `id` для global, `type` для doc-type */
  code: string;
  /** Полное содержимое YAML файла как строка */
  sourceYaml: string;
  /** Опционально — извлечённое `name` из YAML, если есть */
  name: string | null;
}

interface ImportYamlDialogProps {
  open: boolean;
  kind: ImportYamlKind;
  /** Индикатор что запрос отправляется */
  isSubmitting?: boolean;
  /** Ошибка от backend после submit */
  submitError?: string | null;
  onCancel: () => void;
  onSubmit: (payload: ImportYamlSubmitPayload) => void;
}

// ─────────────────────────────────────────────────────────────
// YAML validation helpers
// ─────────────────────────────────────────────────────────────

interface ParsedInfo {
  code: string;
  name: string | null;
}

/**
 * Парсит YAML и извлекает обязательный код + опциональное имя.
 * Для global: обязательное поле `id`.
 * Для doc-type: обязательное поле `type`.
 */
function parseYamlAndExtract(
  text: string,
  kind: ImportYamlKind,
): { ok: true; info: ParsedInfo } | { ok: false; error: string } {
  if (!text.trim()) {
    return { ok: false, error: "Файл пуст." };
  }

  let parsed: unknown;
  try {
    parsed = yaml.load(text);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `Ошибка парсинга YAML: ${message}` };
  }

  if (!parsed || typeof parsed !== "object") {
    return {
      ok: false,
      error: "YAML должен быть объектом с полями верхнего уровня.",
    };
  }

  const record = parsed as Record<string, unknown>;

  const codeFieldName = kind === "global" ? "id" : "type";
  const rawCode = record[codeFieldName];

  if (typeof rawCode !== "string" || !rawCode.trim()) {
    return {
      ok: false,
      error: `В YAML отсутствует обязательное поле «${codeFieldName}» (строка).`,
    };
  }

  const nameRaw = record["name"];
  const name = typeof nameRaw === "string" && nameRaw.trim() ? nameRaw : null;

  return {
    ok: true,
    info: { code: rawCode.trim(), name },
  };
}

// ─────────────────────────────────────────────────────────────
// Dialog
// ─────────────────────────────────────────────────────────────

const ImportYamlDialog: React.FC<ImportYamlDialogProps> = ({
  open,
  kind,
  isSubmitting = false,
  submitError = null,
  onCancel,
  onSubmit,
}) => {
  const [fileName, setFileName] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsedInfo, setParsedInfo] = useState<ParsedInfo | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Сброс состояния при закрытии
  useEffect(() => {
    if (!open) {
      setFileName(null);
      setContent("");
      setParseError(null);
      setParsedInfo(null);
    }
  }, [open]);

  // Валидация при каждом изменении content
  useEffect(() => {
    if (!content.trim()) {
      setParseError(null);
      setParsedInfo(null);
      return;
    }
    const result = parseYamlAndExtract(content, kind);
    if (result.ok) {
      setParseError(null);
      setParsedInfo(result.info);
    } else {
      setParseError(result.error);
      setParsedInfo(null);
    }
  }, [content, kind]);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setFileName(file.name);
      try {
        const text = await file.text();
        setContent(text);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setParseError(`Не удалось прочитать файл: ${message}`);
      }
    },
    [],
  );

  const handleContentChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setContent(e.target.value);
    },
    [],
  );

  const handleClearFile = useCallback(() => {
    setFileName(null);
    setContent("");
    setParseError(null);
    setParsedInfo(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleSubmit = useCallback(() => {
    if (!parsedInfo) return;
    onSubmit({
      code: parsedInfo.code,
      sourceYaml: content,
      name: parsedInfo.name,
    });
  }, [content, parsedInfo, onSubmit]);

  if (!open) return null;

  const canSubmit = parsedInfo !== null && !isSubmitting;
  const codeFieldLabel = kind === "global" ? "id" : "type";
  const kindLabel =
    kind === "global" ? "global instruction" : "doc-type instruction";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-yaml-dialog-title"
    >
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border-soft)] p-5">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
              Импорт
            </div>
            <h2
              id="import-yaml-dialog-title"
              className="mt-0.5 text-base font-semibold text-[var(--text-primary)]"
            >
              Загрузить {kindLabel} из YAML
            </h2>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              Файл будет сохранён как <strong>черновик</strong>. После импорта
              вы сможете валидировать и опубликовать его.
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Закрыть"
            disabled={isSubmitting}
            className="shrink-0 rounded-md p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] disabled:opacity-40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="space-y-4">
            {/* File picker */}
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                YAML файл
              </label>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".yaml,.yml,text/yaml,application/x-yaml"
                  onChange={handleFileSelect}
                  disabled={isSubmitting}
                  className="hidden"
                  id="import-yaml-file-input"
                />
                <label
                  htmlFor="import-yaml-file-input"
                  className={[
                    "inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] transition-colors",
                    isSubmitting
                      ? "cursor-not-allowed opacity-60"
                      : "hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]",
                  ].join(" ")}
                >
                  <FileUp className="h-3.5 w-3.5" />
                  Выбрать файл
                </label>

                {fileName && (
                  <>
                    <span className="truncate text-xs text-[var(--text-muted)]">
                      {fileName}
                    </span>
                    <button
                      type="button"
                      onClick={handleClearFile}
                      disabled={isSubmitting}
                      className="ml-auto text-[11px] text-[var(--text-muted)] transition-colors hover:text-rose-500 disabled:opacity-40"
                    >
                      Очистить
                    </button>
                  </>
                )}
              </div>
              <p className="mt-1.5 text-[10px] text-[var(--text-muted)]">
                Формат: .yaml, .yml. Или вставьте содержимое в поле ниже
                вручную.
              </p>
            </div>

            {/* YAML content preview / paste */}
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Содержимое YAML
              </label>
              <textarea
                value={content}
                onChange={handleContentChange}
                disabled={isSubmitting}
                rows={12}
                spellCheck={false}
                placeholder={
                  kind === "global"
                    ? "id: my_new_check\nname: Моя новая проверка\ngroup: ...\n..."
                    : "type: contract_9.2_franchise\nparent: class_9_franchising\nname: ...\n..."
                }
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] p-3 font-mono text-[11px] leading-relaxed text-[var(--text-primary)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>

            {/* Parse feedback */}
            {parseError && (
              <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{parseError}</span>
              </div>
            )}

            {parsedInfo && (
              <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  Обнаружено
                </div>
                <div className="mt-1 space-y-0.5 text-xs">
                  <div>
                    <span className="text-[var(--text-muted)]">
                      {codeFieldLabel}:
                    </span>{" "}
                    <span className="font-mono font-semibold text-[var(--text-primary)]">
                      {parsedInfo.code}
                    </span>
                  </div>
                  {parsedInfo.name && (
                    <div>
                      <span className="text-[var(--text-muted)]">name:</span>{" "}
                      <span className="text-[var(--text-primary)]">
                        {parsedInfo.name}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Submit error */}
            {submitError && (
              <InlineAlert tone="error" message={submitError} />
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-[var(--border-soft)] p-5">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Отмена
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={!canSubmit}
            isLoading={isSubmitting}
          >
            Создать черновик
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ImportYamlDialog;



