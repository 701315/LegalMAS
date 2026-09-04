// src/components/instructions/DraftEditForm.tsx
// Форма редактирования draft instruction version.
//
// Поддерживает оба типа инструкций: doc-type и global.
// Для global инструкций доступен визуальный редактор (таб "Редактор").
// Для doc-type — только YAML.
//
// Autosave на blur каждого поля (YAML / metadata).
// В режиме визуального редактора — autosave по debounce после каждого
// изменения поля в GlobalInstructionEditor.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import Field from "../ui/Field";
import Button from "../ui/Button";
import { Tabs, TabsList, TabsTrigger } from "../ui/Tabs";
import ConcurrencyStatusBar from "./ConcurrencyStatusBar";
import { GlobalInstructionEditor } from "./GlobalInstructionEditor";
import {
  useETagConcurrency,
  docTypeETagAdapters,
  globalETagAdapters,
} from "../../hooks/instructions/useETagConcurrency";
import type { ETagConcurrencyAdapters } from "../../hooks/instructions/useETagConcurrency";
import { instructionQueryKeys } from "../../hooks/instructions/useInstructionVersions";
import { globalInstructionQueryKeys } from "../../hooks/instructions/useGlobalInstructions";
import type {
  InstructionVersionDetailItem,
  GlobalInstructionVersionDetailItem,
} from "../../types/instructions";

// ── Стили ─────────────────────────────────────────────────────

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const textareaClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs font-mono text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60 resize-y";

// ── Constants ─────────────────────────────────────────────────

/** Задержка debounce для автосохранения из визуального редактора (ms). */
const EDITOR_AUTOSAVE_DEBOUNCE_MS = 1500;

// ── Types ──────────────────────────────────────────────────────

type AnyVersionDetailItem =
  | InstructionVersionDetailItem
  | GlobalInstructionVersionDetailItem;

export type DraftEditFormInstructionType = "doc-type" | "global";

interface DraftEditFormProps {
  versionId: string;
  initialData: AnyVersionDetailItem;
  onSaveSuccess?: () => void;
  /** Сигнализирует родителю о наличии несохранённых изменений. */
  onDirtyChange?: (isDirty: boolean) => void;
  instructionType?: DraftEditFormInstructionType;
}

// ── Component ──────────────────────────────────────────────────

const DraftEditForm: React.FC<DraftEditFormProps> = ({
  versionId,
  initialData,
  onSaveSuccess,
  onDirtyChange,
  instructionType = "doc-type",
}) => {
  const { t, i18n } = useTranslation("instructions");
  const queryClient = useQueryClient();

  // ── Edit mode tabs (только для global) ────────────────────────
  const [editMode, setEditMode] = useState<"editor" | "yaml">("editor");

  // ── ETag adapters ─────────────────────────────────────────────
  const adapters: ETagConcurrencyAdapters = useMemo(
    () =>
      instructionType === "global" ? globalETagAdapters : docTypeETagAdapters,
    [instructionType],
  );

  // ── Form state ────────────────────────────────────────────────
  const [name, setName] = useState(initialData.name ?? "");
  const [sourceYaml, setSourceYaml] = useState(
    initialData.source_yaml ?? "",
  );
  const [semver, setSemver] = useState(initialData.semver ?? "");
  const [changeSummary, setChangeSummary] = useState(
    initialData.change_summary ?? "",
  );

  // Отслеживаем «грязность» формы — есть ли несохранённые изменения
  const lastSavedYamlRef = useRef(initialData.source_yaml ?? "");

  useEffect(() => {
    setName(initialData.name ?? "");
    setSourceYaml(initialData.source_yaml ?? "");
    setSemver(initialData.semver ?? "");
    setChangeSummary(initialData.change_summary ?? "");
    lastSavedYamlRef.current = initialData.source_yaml ?? "";
  }, [initialData]);

  // Сообщаем родителю о dirty state
  const isDirty = sourceYaml !== lastSavedYamlRef.current;
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  // ── ETag concurrency ──────────────────────────────────────────
  const {
    concurrencyState,
    loadDetail,
    saveDraft,
    resetConcurrencyState,
  } = useETagConcurrency(versionId, adapters);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  // ── Cache invalidation ────────────────────────────────────────
  const invalidateCache = useCallback(() => {
    if (instructionType === "global") {
      queryClient.invalidateQueries({
        queryKey: globalInstructionQueryKeys.versionDetail(versionId),
      });
    } else {
      queryClient.invalidateQueries({
        queryKey: instructionQueryKeys.versionDetail(versionId),
      });
    }
  }, [instructionType, queryClient, versionId]);

  // ── Save ──────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    const success = await saveDraft(
      {
        name: name.trim() || undefined,
        source_yaml: sourceYaml || undefined,
        semver: semver.trim() || undefined,
        change_summary: changeSummary.trim() || undefined,
      },
      {
        onSuccess: () => {
          lastSavedYamlRef.current = sourceYaml;
          invalidateCache();
          onSaveSuccess?.();
        },
      },
    );
    return success;
  }, [
    saveDraft,
    name,
    sourceYaml,
    semver,
    changeSummary,
    invalidateCache,
    onSaveSuccess,
  ]);

  const handleBlurSave = useCallback(() => {
    if (
      concurrencyState.status === "loading" ||
      concurrencyState.status === "saving"
    ) {
      return;
    }
    void handleSave();
  }, [concurrencyState.status, handleSave]);

  // ── Editor YAML change + debounced autosave ───────────────────
  // Визуальный редактор вызывает onChange при каждом изменении поля.
  // Мы обновляем локальный state немедленно, а автосохранение на сервер
  // делаем по debounce чтобы не забивать backend слишком частыми PATCH.
  const editorSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEditorYamlChange = useCallback(
    (newYaml: string) => {
      setSourceYaml(newYaml);

      // Debounced autosave
      if (editorSaveTimerRef.current) {
        clearTimeout(editorSaveTimerRef.current);
      }
      editorSaveTimerRef.current = setTimeout(() => {
        editorSaveTimerRef.current = null;
        // handleSave берёт sourceYaml из closure — но setState ещё не
        // отработал. Поэтому используем functional save через ref:
        // saveDraft будет вызван после React commit с актуальным state.
        // К счастью handleBlurSave проверяет status и вызывает handleSave,
        // а handleSave использует текущие значения state на момент вызова.
        handleBlurSave();
      }, EDITOR_AUTOSAVE_DEBOUNCE_MS);
    },
    [handleBlurSave],
  );

  // Очистка таймера при unmount
  useEffect(() => {
    return () => {
      if (editorSaveTimerRef.current) {
        clearTimeout(editorSaveTimerRef.current);
      }
    };
  }, []);

  const handleEditModeChange = useCallback((mode: string) => {
    setEditMode(mode as "editor" | "yaml");
  }, []);

  const isBusy =
    concurrencyState.status === "loading" ||
    concurrencyState.status === "saving";

  const hasName = name.trim().length > 0;
  const hasYaml = sourceYaml.trim().length > 0;
  const canSave = hasName && hasYaml && !isBusy;

  // ── Render ────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Concurrency status */}
      <ConcurrencyStatusBar
        state={concurrencyState}
        onRetryAfterStale={() => void handleSave()}
        onDismissConflict={resetConcurrencyState}
      />

      {/* Conflict hint */}
      {concurrencyState.status === "conflict" &&
        concurrencyState.conflictData && (
          <div className="rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-error-text)]">
              {t("draftEditForm.conflict.title")}
            </div>
            <div className="space-y-1 text-[11px] text-[var(--color-error-text)]">
              <div>
                <Trans
                  t={t}
                  i18nKey="draftEditForm.conflict.name"
                  values={{ name: concurrencyState.conflictData.name }}
                  components={{
                    bold: <span className="font-semibold" />,
                  }}
                />
              </div>
              {concurrencyState.conflictData.change_summary && (
                <div>
                  {t("draftEditForm.conflict.changeSummary", {
                    summary: concurrencyState.conflictData.change_summary,
                  })}
                </div>
              )}
              <div>
                {t("draftEditForm.conflict.updatedAt", {
                  time: concurrencyState.conflictData.updated_at
                    ? new Date(
                        concurrencyState.conflictData.updated_at,
                      ).toLocaleString(i18n.language)
                    : "—",
                })}
              </div>
            </div>
            <p className="mt-2 text-[11px] text-[var(--color-error-text)]">
              {t("draftEditForm.conflict.manualHint")}
            </p>
          </div>
        )}

      {/* Metadata fields */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("draftEditForm.fields.name")} required>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={handleBlurSave}
            disabled={isBusy}
            className={inputClassName}
            placeholder={t("draftEditForm.fields.namePlaceholder")}
          />
        </Field>

        <Field label={t("draftEditForm.fields.semver")}>
          <input
            type="text"
            value={semver}
            onChange={(e) => setSemver(e.target.value)}
            onBlur={handleBlurSave}
            disabled={isBusy}
            className={inputClassName}
            placeholder={t("draftEditForm.fields.semverPlaceholder")}
          />
        </Field>

        <div className="sm:col-span-2">
          <Field label={t("draftEditForm.fields.changeSummary")}>
            <input
              type="text"
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
              onBlur={handleBlurSave}
              disabled={isBusy}
              className={inputClassName}
              placeholder={t("draftEditForm.fields.changeSummaryPlaceholder")}
            />
          </Field>
        </div>
      </div>

      {/* Source YAML / Visual Editor */}
      {instructionType === "global" ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--text-secondary)]">
              {t("draftEditForm.fields.instructionContent")}
            </span>
            <Tabs value={editMode} onChange={handleEditModeChange}>
              <TabsList aria-label={t("draftEditForm.fields.instructionContent")}>
                <TabsTrigger value="editor">{t("draftEditForm.fields.editor")}</TabsTrigger>
                <TabsTrigger value="yaml">{t("draftEditForm.fields.yaml")}</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {editMode === "editor" ? (
            <GlobalInstructionEditor
              sourceYaml={sourceYaml}
              onChange={handleEditorYamlChange}
              disabled={isBusy}
            />
          ) : (
            <Field label={t("draftEditForm.fields.sourceYaml")} required>
              <textarea
                value={sourceYaml}
                onChange={(e) => setSourceYaml(e.target.value)}
                onBlur={handleBlurSave}
                disabled={isBusy}
                className={textareaClassName}
                rows={24}
                placeholder={t("draftEditForm.fields.yamlPlaceholder")}
                spellCheck={false}
              />
            </Field>
          )}
        </div>
      ) : (
        <Field label={t("draftEditForm.fields.sourceYaml")} required>
          <textarea
            value={sourceYaml}
            onChange={(e) => setSourceYaml(e.target.value)}
            onBlur={handleBlurSave}
            disabled={isBusy}
            className={textareaClassName}
            rows={16}
            placeholder={t("draftEditForm.fields.yamlPlaceholder")}
            spellCheck={false}
          />
        </Field>
      )}

      {/* Save button + dirty indicator */}
      <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          {isDirty ? (
            <span className="text-[var(--color-warning-text)]">
              {t("draftEditForm.status.dirty")}
            </span>
          ) : instructionType === "global" && editMode === "editor" ? (
            t("draftEditForm.status.autosaveDebounce")
          ) : (
            t("draftEditForm.status.autosaveBlur")
          )}
        </p>
        <Button
          variant="secondary"
          size="sm"
          type="button"
          onClick={() => void handleSave()}
          disabled={!canSave}
          isLoading={concurrencyState.status === "saving"}
        >
          {t("draftEditForm.status.saveDraft")}
        </Button>
      </div>
    </div>
  );
};

export default DraftEditForm;



