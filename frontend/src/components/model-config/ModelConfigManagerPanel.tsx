// =============================================================
// src/components/model-config/ModelConfigManagerPanel.tsx
// =============================================================

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

import type {
  ApiError,
  Deal,
  ModelConfig,
  ModelConfigCreateInput,
  ModelConfigUpdateInput,
} from "../../types";

import Button from "../ui/Button";

type ModelConfigUsage = {
  model_config_id: string;
  playbook_versions: {
    id: string;
    name: string;
    semver: string;
    status: string;
  }[];
  deals: { id: string; name: string; status: string }[];
};

interface ModelConfigManagerPanelState {
  items: ModelConfig[];
  isLoading: boolean;
  error: string | null;
  usage: Record<string, ModelConfigUsage | undefined>;
}

type Mode = "create" | "edit" | null;

export interface ModelConfigManagerPanelProps {
  mode?: "page" | "embedded";
  dealId?: string | null;
  currentDeal?: Deal | null;
  onFinished?: () => void;
  onCancel?: () => void;
  onDealPatched?: (patch: Partial<Deal>) => void;
  onOpenPlaybookVersions?: (modelConfigId: string) => void;
}

const defaultCreateValues: ModelConfigCreateInput = {
  name: "",
  embeddings_primary: "intfloat/multilingual-e5-large",
  embeddings_fallback: "cointegrated/LaBSE",
  candidate_n: 50,
  llm_context_k: 5,
  dense_weight: 0.6,
  sparse_weight: 0.3,
  metadata_boost: 0.1,
};

const cardClass =
  "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4";

const alertErrorClass =
  "rounded-2xl border border-red-500/40 bg-red-950/40 px-4 py-3 text-xs text-red-100";

const inputClass = "input-base h-8 text-xs";

const ModelConfigManagerPanel: React.FC<ModelConfigManagerPanelProps> = ({
  mode = "page",
  dealId = null,
  currentDeal = null,
  onFinished,
  onCancel,
  onDealPatched,
  onOpenPlaybookVersions,
}) => {
  const navigate = useNavigate();

  const [state, setState] = useState<ModelConfigManagerPanelState>({
    items: [],
    isLoading: false,
    error: null,
    usage: {},
  });

  const [editorMode, setEditorMode] = useState<Mode>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [formValues, setFormValues] = useState<ModelConfigCreateInput>(
    defaultCreateValues,
  );

  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [selectError, setSelectError] = useState<string | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [successText, setSuccessText] = useState<string | null>(null);

  const isEmbedded = mode === "embedded";

  const selectedConfig = useMemo(
    () => state.items.find((item) => item.id === selectedId) ?? null,
    [state.items, selectedId],
  );

  const clearTransientMessages = useCallback(() => {
    setFormError(null);
    setDeleteError(null);
    setSelectError(null);
    setSuccessText(null);
  }, []);

  const loadUsageForConfigs = useCallback(async (configs: ModelConfig[]) => {
    const usageMap: Record<string, ModelConfigUsage> = {};

    await Promise.all(
      configs.map(async (cfg) => {
        try {
          const res = await client.get<ModelConfigUsage>(
            `/api/v1/model-configs/${cfg.id}/usage`,
          );
          usageMap[cfg.id] = res.data;
        } catch {
          // Не заваливаем всю страницу, если usage одной записи не загрузился.
        }
      }),
    );

    setState((prev) => ({
      ...prev,
      usage: usageMap,
    }));
  }, []);

  const loadConfigs = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
      const items = res.data || [];

      setState({
        items,
        isLoading: false,
        error: null,
        usage: {},
      });

      await loadUsageForConfigs(items);
    } catch (err) {
      const apiErr = err as ApiError;
      setState({
        items: [],
        isLoading: false,
        error:
          apiErr.detail ||
          "Не удалось загрузить список профилей моделей. Попробуйте позже.",
        usage: {},
      });
    }
  }, [loadUsageForConfigs]);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  const handleBack = useCallback(() => {
    if (onCancel) {
      onCancel();
      return;
    }

    navigate("/admin");
  }, [navigate, onCancel]);

  const startCreate = useCallback(() => {
    clearTransientMessages();
    setEditorMode("create");
    setSelectedId(null);
    setFormValues(defaultCreateValues);
  }, [clearTransientMessages]);

  const startEdit = useCallback(
    (config: ModelConfig) => {
      clearTransientMessages();
      setEditorMode("edit");
      setSelectedId(config.id);

      setFormValues({
        name: config.name,
        embeddings_primary: "intfloat/multilingual-e5-large",
        embeddings_fallback: "cointegrated/LaBSE",
        candidate_n: 50,
        llm_context_k: 5,
        dense_weight: 0.6,
        sparse_weight: 0.3,
        metadata_boost: 0.1,
      });
    },
    [clearTransientMessages],
  );

  const resetForm = useCallback(() => {
    clearTransientMessages();
    setEditorMode(null);
    setSelectedId(null);
    setFormValues(defaultCreateValues);
  }, [clearTransientMessages]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>, numeric: boolean = false) => {
      const { name, value } = e.target;

      setFormValues((prev) => {
        if (numeric) {
          const parsed = value === "" ? NaN : Number(value);
          return {
            ...prev,
            [name]: Number.isNaN(parsed) ? ("" as unknown as number) : parsed,
          };
        }

        return {
          ...prev,
          [name]: value,
        };
      });
    },
    [],
  );

  const validateForm = useCallback((): boolean => {
    if (!formValues.name.trim()) {
      setFormError("Имя профиля обязательно.");
      return false;
    }

    if (
      typeof formValues.candidate_n !== "number" ||
      formValues.candidate_n <= 0
    ) {
      setFormError("candidate_n должен быть положительным числом.");
      return false;
    }

    if (
      typeof formValues.llm_context_k !== "number" ||
      formValues.llm_context_k <= 0
    ) {
      setFormError("llm_context_k должен быть положительным числом.");
      return false;
    }

    if (
      typeof formValues.dense_weight !== "number" ||
      typeof formValues.sparse_weight !== "number" ||
      typeof formValues.metadata_boost !== "number"
    ) {
      setFormError(
        "dense_weight, sparse_weight, metadata_boost должны быть числами.",
      );
      return false;
    }

    const sum =
      (formValues.dense_weight || 0) +
      (formValues.sparse_weight || 0) +
      (formValues.metadata_boost || 0);

    if (sum <= 0) {
      setFormError(
        "Сумма весов (dense_weight + sparse_weight + metadata_boost) должна быть больше нуля.",
      );
      return false;
    }

    setFormError(null);
    return true;
  }, [formValues]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!editorMode) return;

      if (!validateForm()) {
        return;
      }

      setIsSubmitting(true);
      setSuccessText(null);

      try {
        if (editorMode === "create") {
          const payload: ModelConfigCreateInput = {
            name: formValues.name.trim(),
            embeddings_primary:
              formValues.embeddings_primary ||
              "intfloat/multilingual-e5-large",
            embeddings_fallback:
              formValues.embeddings_fallback === ""
                ? null
                : formValues.embeddings_fallback ?? null,
            candidate_n: Number(formValues.candidate_n),
            llm_context_k: Number(formValues.llm_context_k),
            dense_weight: Number(formValues.dense_weight),
            sparse_weight: Number(formValues.sparse_weight),
            metadata_boost: Number(formValues.metadata_boost),
          };

          await client.post<ModelConfig>("/api/v1/model-configs", payload);
          setSuccessText("Профиль модели успешно создан.");
        } else if (editorMode === "edit" && selectedId) {
          const payload: ModelConfigUpdateInput = {
            name: formValues.name.trim(),
            embeddings_primary:
              formValues.embeddings_primary ||
              "intfloat/multilingual-e5-large",
            embeddings_fallback:
              formValues.embeddings_fallback === ""
                ? null
                : formValues.embeddings_fallback ?? null,
            candidate_n: Number(formValues.candidate_n),
            llm_context_k: Number(formValues.llm_context_k),
            dense_weight: Number(formValues.dense_weight),
            sparse_weight: Number(formValues.sparse_weight),
            metadata_boost: Number(formValues.metadata_boost),
          };

          await client.patch<ModelConfig>(
            `/api/v1/model-configs/${selectedId}`,
            payload,
          );
          setSuccessText("Профиль модели успешно обновлён.");
        }

        await loadConfigs();
        resetForm();
      } catch (err) {
        const apiErr = err as ApiError;
        setFormError(
          apiErr.detail ||
            "Не удалось сохранить профиль модели. Проверьте данные и попробуйте ещё раз.",
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [editorMode, formValues, loadConfigs, resetForm, selectedId, validateForm],
  );

  const handleDelete = useCallback(
    async (config: ModelConfig) => {
      const usage = state.usage[config.id];
      const isUsed =
        !!usage &&
        ((usage.playbook_versions && usage.playbook_versions.length > 0) ||
          (usage.deals && usage.deals.length > 0));

      if (isUsed) {
        setDeleteError(
          "Нельзя удалить профиль, который используется в плейбуках или проектах. Сначала переназначьте их на другой профиль.",
        );
        return;
      }

      const ok = window.confirm(
        `Удалить профиль модели "${config.name}"?\n\n` +
          "Если профиль не используется, его можно безопасно удалить.",
      );
      if (!ok) return;

      setIsDeleting(true);
      setDeleteError(null);
      setSuccessText(null);

      try {
        await client.delete(`/api/v1/model-configs/${config.id}`);
        await loadConfigs();

        if (selectedId === config.id) {
          resetForm();
        }

        setSuccessText(`Профиль "${config.name}" удалён.`);
      } catch (err) {
        const apiErr = err as ApiError;
        setDeleteError(
          apiErr.detail ||
            "Не удалось удалить профиль модели. Попробуйте позже.",
        );
      } finally {
        setIsDeleting(false);
      }
    },
    [loadConfigs, resetForm, selectedId, state.usage],
  );

  const handleSelectForDeal = useCallback(
    async (config: ModelConfig) => {
      if (!dealId) {
        return;
      }

      const ok = window.confirm(
        `Выбрать профиль модели "${config.name}" для текущего проекта?\n\n` +
          "Этот профиль будет использован при запуске анализа по сделке.",
      );
      if (!ok) return;

      setIsSelecting(true);
      setSelectError(null);
      setSuccessText(null);

      try {
        await client.patch(`/api/v1/deals/${dealId}/model-config`, {
          model_config_id: config.id,
        });

        onDealPatched?.({
          model_config_id: config.id,
          model_config_name: config.name,
        });

        setSuccessText(`Для проекта выбран профиль "${config.name}".`);

        if (onFinished) {
          onFinished();
        }
      } catch (err) {
        const apiErr = err as ApiError;
        setSelectError(
          apiErr.detail ||
            "Не удалось сохранить профиль модели для сделки. Попробуйте позже.",
        );
      } finally {
        setIsSelecting(false);
      }
    },
    [dealId, onDealPatched, onFinished],
  );

  const openPlaybookVersions = useCallback(
    (modelConfigId: string) => {
      if (onOpenPlaybookVersions) {
        onOpenPlaybookVersions(modelConfigId);
        return;
      }

      navigate(
        `/admin/playbook-versions?modelConfigId=${encodeURIComponent(
          modelConfigId,
        )}`,
      );
    },
    [navigate, onOpenPlaybookVersions],
  );

  const rootClassName = isEmbedded
    ? "h-full min-h-0 text-[var(--text-primary)]"
    : "min-h-screen bg-[var(--bg-base)] px-4 py-6 text-[var(--text-primary)]";

  const containerClassName = isEmbedded
    ? "h-full min-h-0 space-y-4"
    : "mx-auto max-w-5xl space-y-4";

  return (
    <div className={rootClassName}>
      <div className={containerClassName}>
        {!isEmbedded && (
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
                Профили моделей (ModelConfig)
              </h1>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Управление конфигурациями моделей, которые используют плейбуки и
                проекты.
              </p>
              {dealId && (
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  Страница открыта из конкретного проекта — можно выбрать профиль
                  модели для этой сделки.
                </p>
              )}
            </div>

            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={handleBack}
            >
              ← Назад
            </Button>
          </div>
        )}

        {isEmbedded && currentDeal?.model_config_name && (
          <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-muted)]">
            Текущий профиль сделки:{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {currentDeal.model_config_name}
            </span>
          </div>
        )}

        {state.error && <div className={alertErrorClass}>{state.error}</div>}
        {deleteError && <div className={alertErrorClass}>{deleteError}</div>}
        {selectError && <div className={alertErrorClass}>{selectError}</div>}
        {successText && (
          <div className="rounded-2xl border border-emerald-500/40 bg-emerald-950/30 px-4 py-3 text-xs text-emerald-100">
            {successText}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className={cardClass}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Список профилей
              </h2>

              <Button size="sm" variant="secondary" onClick={startCreate}>
                + Новый профиль
              </Button>
            </div>

            {state.isLoading ? (
              <p className="text-[11px] text-[var(--text-muted)]">
                Загружаем профили…
              </p>
            ) : state.items.length === 0 ? (
              <p className="text-[11px] text-[var(--text-muted)]">
                Пока нет ни одного профиля модели. Создайте первый.
              </p>
            ) : (
              <ul className="max-h-96 space-y-2 overflow-y-auto">
                {state.items.map((cfg) => {
                  const usage = state.usage[cfg.id];
                  const isUsed =
                    !!usage &&
                    ((usage.playbook_versions &&
                      usage.playbook_versions.length > 0) ||
                      (usage.deals && usage.deals.length > 0));

                  const isCurrentDealConfig =
                    currentDeal?.model_config_id === cfg.id;

                  return (
                    <li
                      key={cfg.id}
                      className={[
                        "flex items-start justify-between gap-3 rounded-xl border px-3 py-2 text-xs transition-colors",
                        selectedId === cfg.id
                          ? "border-[var(--border-strong)] bg-[var(--bg-card-hover)]"
                          : isCurrentDealConfig
                            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                            : "border-[var(--border)] bg-[var(--bg-card)] hover:bg-[var(--bg-card-hover)]",
                      ].join(" ")}
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-xs font-semibold text-[var(--text-primary)]">
                            {cfg.name}
                          </div>

                          {isCurrentDealConfig && (
                            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                              Текущий для сделки
                            </span>
                          )}
                        </div>

                        <div className="break-all text-[11px] text-[var(--text-muted)]">
                          ID: {cfg.id}
                        </div>

                        <div className="mt-0.5 text-[11px] leading-5 text-[var(--text-muted)]">
                          {usage ? (
                            isUsed ? (
                              <>
                                Используется в плейбуках:
                                {usage.playbook_versions.length > 0 ? " " : " нет"}
                                {usage.playbook_versions.slice(0, 3).map((pv) => (
                                  <span key={pv.id}>
                                    {` "${pv.name}" (${pv.semver})`}
                                  </span>
                                ))}
                                {usage.playbook_versions.length > 3 && " …"}
                                <button
                                  type="button"
                                  onClick={() => openPlaybookVersions(cfg.id)}
                                  className="ml-1 text-[11px] text-indigo-300 underline"
                                >
                                  открыть версии
                                </button>
                                <br />
                                Проекты:
                                {usage.deals.length > 0 ? " " : " нет"}
                                {usage.deals.slice(0, 3).map((d) => (
                                  <span key={d.id}>{` "${d.name}"`}</span>
                                ))}
                                {usage.deals.length > 3 && " …"}
                              </>
                            ) : (
                              <span className="text-emerald-300">
                                Не используется (можно безопасно удалить)
                              </span>
                            )
                          ) : (
                            <span>Загружаем информацию об использовании…</span>
                          )}
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setSelectedId(cfg.id);
                            startEdit(cfg);
                          }}
                        >
                          Редактировать
                        </Button>

                        {dealId && (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="text-indigo-300 hover:bg-indigo-500/10 hover:text-indigo-200"
                            onClick={() => handleSelectForDeal(cfg)}
                            isLoading={isSelecting}
                            disabled={isSelecting}
                          >
                            Выбрать для проекта
                          </Button>
                        )}

                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="text-red-300 hover:bg-red-500/10 hover:text-red-200"
                          onClick={() => handleDelete(cfg)}
                          isLoading={isDeleting}
                          disabled={isDeleting}
                        >
                          Удалить
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className={cardClass}>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {editorMode === "create"
                ? "Создание нового профиля"
                : editorMode === "edit"
                  ? "Редактирование профиля"
                  : "Выбор / создание профиля"}
            </h2>

            {editorMode ? (
              <form onSubmit={handleSubmit} className="space-y-3">
                {formError && (
                  <div className="rounded border border-red-500/50 bg-red-950/60 px-3 py-2 text-[11px] text-red-100">
                    {formError}
                  </div>
                )}

                {editorMode === "edit" && selectedConfig && (
                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-muted)]">
                    Редактируется профиль:{" "}
                    <span className="font-semibold text-[var(--text-primary)]">
                      {selectedConfig.name}
                    </span>
                  </div>
                )}

                <div>
                  <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                    Имя профиля
                  </label>
                  <input
                    type="text"
                    name="name"
                    value={formValues.name}
                    onChange={(e) => handleInputChange(e, false)}
                    className={inputClass}
                    placeholder="например, default-v1, fast-v1, quality-v1"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                    Embeddings primary
                  </label>
                  <input
                    type="text"
                    name="embeddings_primary"
                    value={formValues.embeddings_primary}
                    onChange={(e) => handleInputChange(e, false)}
                    className={inputClass}
                  />
                  <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    Основная модель эмбеддингов (ретривер и классификация).
                  </p>
                </div>

                <div>
                  <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                    Embeddings fallback (опционально)
                  </label>
                  <input
                    type="text"
                    name="embeddings_fallback"
                    value={formValues.embeddings_fallback ?? ""}
                    onChange={(e) => handleInputChange(e, false)}
                    className={inputClass}
                  />
                  <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    Запасная модель эмбеддингов или оставьте пустым.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                      candidate_n
                    </label>
                    <input
                      type="number"
                      name="candidate_n"
                      value={formValues.candidate_n}
                      onChange={(e) => handleInputChange(e, true)}
                      className={inputClass}
                    />
                    <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                      Сколько кандидатов рассматривать при поиске.
                    </p>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                      llm_context_k
                    </label>
                    <input
                      type="number"
                      name="llm_context_k"
                      value={formValues.llm_context_k}
                      onChange={(e) => handleInputChange(e, true)}
                      className={inputClass}
                    />
                    <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                      Сколько контекста отдавать LLM (баланс скорость/качество).
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                      dense_weight
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      name="dense_weight"
                      value={formValues.dense_weight}
                      onChange={(e) => handleInputChange(e, true)}
                      className={inputClass}
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                      sparse_weight
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      name="sparse_weight"
                      value={formValues.sparse_weight}
                      onChange={(e) => handleInputChange(e, true)}
                      className={inputClass}
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-[var(--text-secondary)]">
                      metadata_boost
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      name="metadata_boost"
                      value={formValues.metadata_boost}
                      onChange={(e) => handleInputChange(e, true)}
                      className={inputClass}
                    />
                  </div>
                </div>

                <p className="text-[11px] text-[var(--text-muted)]">
                  Веса управляют балансом между dense, sparse и метаданными.
                  Сумма должна быть больше нуля.
                </p>

                <div className="mt-3 flex items-center justify-end gap-2 border-t border-[var(--border)] pt-3">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={resetForm}
                  >
                    Отмена
                  </Button>

                  <Button
                    type="submit"
                    size="sm"
                    variant="secondary"
                    isLoading={isSubmitting}
                  >
                    {editorMode === "create"
                      ? "Создать профиль"
                      : "Сохранить изменения"}
                  </Button>
                </div>
              </form>
            ) : (
              <p className="text-[11px] text-[var(--text-muted)]">
                Выберите профиль слева или нажмите{" "}
                <span className="font-semibold">«Новый профиль»</span>, чтобы
                создать конфигурацию модели.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelConfigManagerPanel;

