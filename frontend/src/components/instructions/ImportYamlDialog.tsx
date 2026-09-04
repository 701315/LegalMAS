// =============================================================
// src/components/instructions/ImportYamlDialog.tsx
// =============================================================

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { AlertCircle, FileUp, X } from "lucide-react";
import * as yaml from "js-yaml";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export type ImportYamlKind = "global" | "doc-type";

export interface ImportYamlSubmitPayload {
  code: string;
  sourceYaml: string;
  name: string | null;
}

interface ImportYamlDialogProps {
  open: boolean;
  kind: ImportYamlKind;
  isSubmitting?: boolean;
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

function parseYamlAndExtract(
  text: string,
  kind: ImportYamlKind,
  tFn: (key: string, options?: any) => string,
): { ok: true; info: ParsedInfo } | { ok: false; error: string } {
  if (!text.trim()) {
    return { ok: false, error: tFn("importYaml.validation.empty") };
  }

  let parsed: unknown;
  try {
    parsed = yaml.load(text);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: tFn("importYaml.validation.parseError", { message }) };
  }

  if (!parsed || typeof parsed !== "object") {
    return {
      ok: false,
      error: tFn("importYaml.validation.invalidStructure"),
    };
  }

  const record = parsed as Record<string, unknown>;

  const codeFieldName = kind === "global" ? "id" : "type";
  const rawCode = record[codeFieldName];

  if (typeof rawCode !== "string" || !rawCode.trim()) {
    return {
      ok: false,
      error: tFn("importYaml.validation.missingField", { field: codeFieldName }),
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
  const { t } = useTranslation("instructions");
  const [fileName, setFileName] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsedInfo, setParsedInfo] = useState<ParsedInfo | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setFileName(null);
      setContent("");
      setParseError(null);
      setParsedInfo(null);
    }
  }, [open]);

  useEffect(() => {
    if (!content.trim()) {
      setParseError(null);
      setParsedInfo(null);
      return;
    }
    const result = parseYamlAndExtract(content, kind, t);
    if (result.ok) {
      setParseError(null);
      setParsedInfo(result.info);
    } else {
      setParseError(result.error);
      setParsedInfo(null);
    }
  }, [content, kind, t]);

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
        setParseError(t("importYaml.validation.readError", { message }));
      }
    },
    [t],
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
    kind === "global" ? t("importYaml.kinds.global") : t("importYaml.kinds.docType");

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
              {t("importYaml.header.import")}
            </div>
            <h2
              id="import-yaml-dialog-title"
              className="mt-0.5 text-base font-semibold text-[var(--text-primary)]"
            >
              {t("importYaml.header.title", { kind: kindLabel })}
            </h2>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              <Trans
                t={t}
                i18nKey="importYaml.header.description"
                components={{
                  bold: <strong />,
                }}
              />
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label={t("actions.close", { ns: "common" })}
            disabled={isSubmitting}
            className="shrink-0 rounded-md p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:opacity-40"
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
                {t("importYaml.file.label")}
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
                  {t("importYaml.file.select")}
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
                      className="ml-auto text-[11px] text-[var(--text-muted)] transition-colors hover:text-[var(--color-error-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:opacity-40"
                    >
                      {t("importYaml.file.clear")}
                    </button>
                  </>
                )}
              </div>
              <p className="mt-1.5 text-[10px] text-[var(--text-muted)]">
                {t("importYaml.file.tip")}
              </p>
            </div>

            {/* YAML content preview / paste */}
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {t("importYaml.textarea.label")}
              </label>
              <textarea
                value={content}
                onChange={handleContentChange}
                disabled={isSubmitting}
                rows={12}
                spellCheck={false}
                placeholder={
                  kind === "global"
                    ? t("importYaml.textarea.placeholderGlobal")
                    : t("importYaml.textarea.placeholderDocType")
                }
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] p-3 font-mono text-[11px] leading-relaxed text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>

            {/* Parse feedback */}
            {parseError && (
              <div className="flex items-start gap-2 rounded-lg border border-[var(--color-error-border)] bg-[var(--color-error-bg)] p-3 text-xs text-[var(--color-error-text)]">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{parseError}</span>
              </div>
            )}

            {parsedInfo && (
              <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("importYaml.detected.title")}
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
                      <span className="text-[var(--text-muted)]">
                        {t("importYaml.detected.name")}:
                      </span>{" "}
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
            {t("importYaml.buttons.cancel")}
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={!canSubmit}
            isLoading={isSubmitting}
          >
            {t("importYaml.buttons.createDraft")}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ImportYamlDialog;



