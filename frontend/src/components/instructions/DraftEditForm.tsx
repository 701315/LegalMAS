// src/components/instructions/DraftEditForm.tsx
// Форма редактирования draft instruction version.
//
// Поддерживает оба типа инструкций: doc-type и global.
// Для global инструкций доступен визуальный редактор (таб "Редактор").
// Для doc-type — только YAML.
//
// Autosave на blur каждого поля.

import React, { useCallback, useEffect, useMemo, useState } from "react";
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
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

const textareaClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs font-mono text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60 resize-y";

// ── Types ──────────────────────────────────────────────────────

type AnyVersionDetailItem =
  | InstructionVersionDetailItem
  | GlobalInstructionVersionDetailItem;

export type DraftEditFormInstructionType = "doc-type" | "global";

interface DraftEditFormProps {
  versionId: string;
  initialData: AnyVersionDetailItem;
  onSaveSuccess?: () => void;
  instructionType?: DraftEditFormInstructionType;
}

// ── Component ──────────────────────────────────────────────────

const DraftEditForm: React.FC<DraftEditFormProps> = ({
  versionId,
  initialData,
  onSaveSuccess,
  instructionType = "doc-type",
}) => {
  const queryClient = useQueryClient();

  // ── Edit mode tabs (только для global) ────────────────────────
  // "editor" — визуальный редактор
  // "yaml"   — raw YAML textarea
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

  useEffect(() => {
    setName(initialData.name ?? "");
    setSourceYaml(initialData.source_yaml ?? "");
    setSemver(initialData.semver ?? "");
    setChangeSummary(initialData.change_summary ?? "");
  }, [initialData]);

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

  // При изменении YAML через визуальный редактор — автосохранение
  const handleEditorYamlChange = useCallback(
    (newYaml: string) => {
      setSourceYaml(newYaml);
    },
    [],
  );

  // При переключении с editor → yaml: yaml уже актуален (синхронизирован)
  // При переключении с yaml → editor: editor сам реагирует на sourceYaml
  const handleEditModeChange = useCallback(
    (mode: string) => {
      setEditMode(mode as "editor" | "yaml");
    },
    [],
  );

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
          <div className="rounded-xl border border-[#dc2626]/30 bg-[#fef2f2] px-4 py-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#b91c1c]">
              Свежие данные с сервера
            </div>
            <div className="space-y-1 text-[11px] text-[#b91c1c]">
              <div>
                Имя:{" "}
                <span className="font-semibold">
                  {concurrencyState.conflictData.name}
                </span>
              </div>
              {concurrencyState.conflictData.change_summary && (
                <div>
                  Описание изменений:{" "}
                  {concurrencyState.conflictData.change_summary}
                </div>
              )}
              <div>
                Обновлено:{" "}
                {concurrencyState.conflictData.updated_at
                  ? new Date(
                      concurrencyState.conflictData.updated_at,
                    ).toLocaleString("ru-RU")
                  : "—"}
              </div>
            </div>
            <p className="mt-2 text-[11px] text-[#b91c1c]">
              Обновите форму вручную с учётом свежих данных, затем нажмите
              «Сохранить».
            </p>
          </div>
        )}

      {/* Metadata fields (общие для обоих типов) */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Название версии" required>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={handleBlurSave}
            disabled={isBusy}
            className={inputClassName}
            placeholder="Например: Initial draft, Updated checks..."
          />
        </Field>

        <Field label="Semver">
          <input
            type="text"
            value={semver}
            onChange={(e) => setSemver(e.target.value)}
            onBlur={handleBlurSave}
            disabled={isBusy}
            className={inputClassName}
            placeholder="1.0.0"
          />
        </Field>

        <div className="sm:col-span-2">
          <Field label="Описание изменений (change summary)">
            <input
              type="text"
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
              onBlur={handleBlurSave}
              disabled={isBusy}
              className={inputClassName}
              placeholder="Что изменено в этой версии..."
            />
          </Field>
        </div>
      </div>

      {/* Source YAML / Visual Editor */}
      {instructionType === "global" ? (
        // Global: tabs Редактор / YAML
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--text-secondary)]">
              Содержимое инструкции
            </span>
            <Tabs value={editMode} onChange={handleEditModeChange}>
              <TabsList aria-label="Режим редактирования">
                <TabsTrigger value="editor">Редактор</TabsTrigger>
                <TabsTrigger value="yaml">YAML</TabsTrigger>
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
            <Field label="Source YAML" required>
              <textarea
                value={sourceYaml}
                onChange={(e) => setSourceYaml(e.target.value)}
                onBlur={handleBlurSave}
                disabled={isBusy}
                className={textareaClassName}
                rows={24}
                placeholder="# Вставьте YAML-конфигурацию инструкции..."
                spellCheck={false}
              />
            </Field>
          )}
        </div>
      ) : (
        // Doc-type: только YAML
        <Field label="Source YAML" required>
          <textarea
            value={sourceYaml}
            onChange={(e) => setSourceYaml(e.target.value)}
            onBlur={handleBlurSave}
            disabled={isBusy}
            className={textareaClassName}
            rows={16}
            placeholder="# Вставьте YAML-конфигурацию инструкции..."
            spellCheck={false}
          />
        </Field>
      )}

      {/* Save button */}
      <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          {instructionType === "global" && editMode === "editor"
            ? "Изменения в редакторе применяются сразу. Сохраните черновик вручную."
            : "Черновик сохраняется автоматически при переходе между полями."}
        </p>
        <Button
          variant="secondary"
          size="sm"
          type="button"
          onClick={() => void handleSave()}
          disabled={!canSave}
          isLoading={concurrencyState.status === "saving"}
        >
          Сохранить черновик
        </Button>
      </div>
    </div>
  );
};

export default DraftEditForm;


