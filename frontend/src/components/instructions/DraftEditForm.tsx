// src/components/instructions/DraftEditForm.tsx
// Форма редактирования draft instruction version.
//
// Поддерживает оба типа инструкций: doc-type и global.
// Параметризуется через prop `adapters` (ETagConcurrencyAdapters).
//
// Поля: name, source_yaml (textarea), semver, change_summary.
// Autosave на blur каждого поля.
// Показывает ConcurrencyStatusBar для ETag flow.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import Field from "../ui/Field";
import Button from "../ui/Button";
import ConcurrencyStatusBar from "./ConcurrencyStatusBar";
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

// ── Props ─────────────────────────────────────────────────────

type AnyVersionDetailItem =
  | InstructionVersionDetailItem
  | GlobalInstructionVersionDetailItem;

/**
 * instructionType — определяет:
 * 1. Какие ETag adapters использовать (doc-type vs global endpoints).
 * 2. Какой query key инвалидировать после успешного сохранения.
 *
 * По умолчанию "doc-type" — backward compatible.
 */
export type DraftEditFormInstructionType = "doc-type" | "global";

interface DraftEditFormProps {
  versionId: string;
  initialData: AnyVersionDetailItem;
  onSaveSuccess?: () => void;
  /**
   * Тип инструкции. Определяет endpoint и query cache key.
   * "doc-type" (default) → /admin/instruction-versions/:id
   * "global"             → /admin/global-instruction-versions/:id
   */
  instructionType?: DraftEditFormInstructionType;
}

// ── Component ─────────────────────────────────────────────────

const DraftEditForm: React.FC<DraftEditFormProps> = ({
  versionId,
  initialData,
  onSaveSuccess,
  instructionType = "doc-type",
}) => {
  const queryClient = useQueryClient();

  // ── Adapters ─────────────────────────────────────────────────
  // Стабильная ссылка — не меняется между рендерами для одного типа.
  const adapters: ETagConcurrencyAdapters = useMemo(
    () =>
      instructionType === "global" ? globalETagAdapters : docTypeETagAdapters,
    [instructionType],
  );

  // ── Local form state ─────────────────────────────────────────
  const [name, setName] = useState(initialData.name ?? "");
  const [sourceYaml, setSourceYaml] = useState(
    initialData.source_yaml ?? "",
  );
  const [semver, setSemver] = useState(initialData.semver ?? "");
  const [changeSummary, setChangeSummary] = useState(
    initialData.change_summary ?? "",
  );

  // Синхронизируем форму если initialData изменился снаружи
  useEffect(() => {
    setName(initialData.name ?? "");
    setSourceYaml(initialData.source_yaml ?? "");
    setSemver(initialData.semver ?? "");
    setChangeSummary(initialData.change_summary ?? "");
  }, [initialData]);

  // ── ETag concurrency ─────────────────────────────────────────
  const {
    concurrencyState,
    loadDetail,
    saveDraft,
    resetConcurrencyState,
  } = useETagConcurrency(versionId, adapters);

  // Загружаем ETag при первом монтировании
  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  // ── Инвалидация кэша ─────────────────────────────────────────
  // После успешного сохранения инвалидируем нужный query key
  // в зависимости от типа инструкции.
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

  // ── Save ─────────────────────────────────────────────────────
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

  // Autosave on blur
  const handleBlurSave = useCallback(() => {
    if (
      concurrencyState.status === "loading" ||
      concurrencyState.status === "saving"
    ) {
      return;
    }
    void handleSave();
  }, [concurrencyState.status, handleSave]);

  const isBusy =
    concurrencyState.status === "loading" ||
    concurrencyState.status === "saving";

  const hasName = name.trim().length > 0;
  const hasYaml = sourceYaml.trim().length > 0;
  const canSave = hasName && hasYaml && !isBusy;

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Concurrency status */}
      <ConcurrencyStatusBar
        state={concurrencyState}
        onRetryAfterStale={() => void handleSave()}
        onDismissConflict={resetConcurrencyState}
      />

      {/* Conflict data hint */}
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
              Обновите форму вручную с учётом свежих данных, затем
              нажмите «Сохранить».
            </p>
          </div>
        )}

      {/* Form fields */}
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

        <div className="sm:col-span-2">
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
        </div>
      </div>

      {/* Manual save button */}
      <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          Черновик сохраняется автоматически при переходе между полями.
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


