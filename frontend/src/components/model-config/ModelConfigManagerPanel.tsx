// src/components/model-config/ModelConfigManagerPanel.tsx

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { Pencil, Plus } from "lucide-react";
import client from "../../api/client";

import type {
  ApiError,
  Deal,
  ModelConfig,
  ModelConfigCreateInput,
  ModelConfigUpdateInput,
} from "../../types";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

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

interface PanelState {
  items: ModelConfig[];
  isLoading: boolean;
  error: string | null;
  usage: Record<string, ModelConfigUsage | undefined>;
}

/** view = просмотр, edit = редактирование, create = новый */
type RightPanelMode = "view" | "edit" | "create" | null;

export interface ModelConfigManagerPanelProps {
  mode?: "page" | "embedded";
  dealId?: string | null;
  currentDeal?: Deal | null;
  onFinished?: () => void;
  onCancel?: () => void;
  onDealPatched?: (patch: Partial<Deal>) => void;
  onOpenPlaybookVersions?: (modelConfigId: string) => void;
}

// ─────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────

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

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const elevatedSoftInputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-60";

const numberInputClassName =
  "w-16 rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-2 py-1 text-right font-mono text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-60";

const weightInputClassName =
  "w-20 rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-2 py-1 text-right font-mono text-sm font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-60";

// ─────────────────────────────────────────────────────────────
// Panel
// ─────────────────────────────────────────────────────────────

const ModelConfigManagerPanel: React.FC<ModelConfigManagerPanelProps> = ({
  mode = "page",
  dealId = null,
  currentDeal = null,
  onFinished,
  onDealPatched,
}) => {
  const { t } = useTranslation("admin");

  const [state, setState] = useState<PanelState>({
    items: [],
    isLoading: false,
    error: null,
    usage: {},
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rightMode, setRightMode] = useState<RightPanelMode>(null);
  const [formValues, setFormValues] =
    useState<ModelConfigCreateInput>(defaultCreateValues);
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

  const clearMessages = useCallback(() => {
    setFormError(null);
    setDeleteError(null);
    setSelectError(null);
    setSuccessText(null);
  }, []);

  // ── Data loading ────────────────────────────────────────
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
          /* skip */
        }
      }),
    );
    setState((prev) => ({ ...prev, usage: usageMap }));
  }, []);

  const loadConfigs = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
      const items = res.data || [];
      setState({ items, isLoading: false, error: null, usage: {} });
      await loadUsageForConfigs(items);
    } catch (err) {
      const apiErr = err as ApiError;
      setState({
        items: [],
        isLoading: false,
        error: apiErr.detail || t("modelConfig.validation.loadFailed"),
        usage: {},
      });
    }
  }, [loadUsageForConfigs, t]);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  // ── Navigation handlers ─────────────────────────────────
  const handleSelectConfig = useCallback(
    (configId: string) => {
      clearMessages();
      setSelectedId(configId);
      setRightMode("view");
    },
    [clearMessages],
  );

  const handleStartCreate = useCallback(() => {
    clearMessages();
    setSelectedId(null);
    setRightMode("create");
    setFormValues(defaultCreateValues);
  }, [clearMessages]);

  const handleStartEdit = useCallback(() => {
    if (!selectedConfig) return;
    clearMessages();
    setRightMode("edit");
    setFormValues({
      name: selectedConfig.name,
      embeddings_primary: "intfloat/multilingual-e5-large",
      embeddings_fallback: "cointegrated/LaBSE",
      candidate_n: 50,
      llm_context_k: 5,
      dense_weight: 0.6,
      sparse_weight: 0.3,
      metadata_boost: 0.1,
    });
  }, [clearMessages, selectedConfig]);

  const handleCancelEdit = useCallback(() => {
    clearMessages();
    if (selectedId) {
      setRightMode("view");
    } else {
      setRightMode(null);
    }
  }, [clearMessages, selectedId]);

  // ── Form ────────────────────────────────────────────────
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>, numeric = false) => {
      const { name, value } = e.target;
      setFormValues((prev) => {
        if (numeric) {
          const parsed = value === "" ? NaN : Number(value);
          return {
            ...prev,
            [name]: Number.isNaN(parsed) ? ("" as unknown as number) : parsed,
          };
        }
        return { ...prev, [name]: value };
      });
    },
    [],
  );

  const validateForm = useCallback((): boolean => {
    if (!formValues.name.trim()) {
      setFormError(t("modelConfig.validation.nameRequired"));
      return false;
    }
    if (
      typeof formValues.candidate_n !== "number" ||
      formValues.candidate_n <= 0
    ) {
      setFormError(t("modelConfig.validation.candidateNPositive"));
      return false;
    }
    if (
      typeof formValues.llm_context_k !== "number" ||
      formValues.llm_context_k <= 0
    ) {
      setFormError(t("modelConfig.validation.contextKPositive"));
      return false;
    }
    if (
      typeof formValues.dense_weight !== "number" ||
      typeof formValues.sparse_weight !== "number" ||
      typeof formValues.metadata_boost !== "number"
    ) {
      setFormError(t("modelConfig.validation.weightsNumeric"));
      return false;
    }
    const sum =
      (formValues.dense_weight || 0) +
      (formValues.sparse_weight || 0) +
      (formValues.metadata_boost || 0);
    if (sum <= 0) {
      setFormError(t("modelConfig.validation.sumPositive"));
      return false;
    }
    setFormError(null);
    return true;
  }, [formValues, t]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!validateForm()) return;

      setIsSubmitting(true);
      setSuccessText(null);

      try {
        const payload = {
          name: formValues.name.trim(),
          embeddings_primary:
            formValues.embeddings_primary || "intfloat/multilingual-e5-large",
          embeddings_fallback:
            formValues.embeddings_fallback === ""
              ? null
              : (formValues.embeddings_fallback ?? null),
          candidate_n: Number(formValues.candidate_n),
          llm_context_k: Number(formValues.llm_context_k),
          dense_weight: Number(formValues.dense_weight),
          sparse_weight: Number(formValues.sparse_weight),
          metadata_boost: Number(formValues.metadata_boost),
        };

        if (rightMode === "create") {
          const res = await client.post<ModelConfig>(
            "/api/v1/model-configs",
            payload,
          );
          setSuccessText(t("modelConfig.validation.createSuccess"));
          await loadConfigs();
          setSelectedId(res.data.id);
          setRightMode("view");
        } else if (rightMode === "edit" && selectedId) {
          await client.patch<ModelConfig>(
            `/api/v1/model-configs/${selectedId}`,
            payload as ModelConfigUpdateInput,
          );
          setSuccessText(t("modelConfig.validation.updateSuccess"));
          await loadConfigs();
          setRightMode("view");
        }
      } catch (err) {
        const apiErr = err as ApiError;
        setFormError(apiErr.detail || t("modelConfig.validation.saveFailed"));
      } finally {
        setIsSubmitting(false);
      }
    },
    [formValues, loadConfigs, rightMode, selectedId, t, validateForm],
  );

  const handleDelete = useCallback(
    async (config: ModelConfig) => {
      const usage = state.usage[config.id];
      const isUsed =
        !!usage &&
        ((usage.playbook_versions?.length ?? 0) > 0 ||
          (usage.deals?.length ?? 0) > 0);

      if (isUsed) {
        setDeleteError(t("modelConfig.validation.deleteUsed"));
        return;
      }
      if (!window.confirm(t("modelConfig.confirm.delete", { name: config.name }))) return;

      setIsDeleting(true);
      setDeleteError(null);
      setSuccessText(null);

      try {
        await client.delete(`/api/v1/model-configs/${config.id}`);
        await loadConfigs();
        if (selectedId === config.id) {
          setSelectedId(null);
          setRightMode(null);
        }
        setSuccessText(t("modelConfig.validation.deleteSuccess", { name: config.name }));
      } catch (err) {
        const apiErr = err as ApiError;
        setDeleteError(apiErr.detail || t("modelConfig.validation.deleteFailed"));
      } finally {
        setIsDeleting(false);
      }
    },
    [loadConfigs, selectedId, state.usage, t],
  );

  const handleSelectForDeal = useCallback(
    async (config: ModelConfig) => {
      if (!dealId) return;
      if (!window.confirm(t("modelConfig.confirm.select", { name: config.name })))
        return;

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
        setSuccessText(t("modelConfig.validation.selectSuccess", { name: config.name }));
        onFinished?.();
      } catch (err) {
        const apiErr = err as ApiError;
        setSelectError(apiErr.detail || t("modelConfig.validation.selectFailed"));
      } finally {
        setIsSelecting(false);
      }
    },
    [dealId, onDealPatched, onFinished, t],
  );

  // ── Derived ─────────────────────────────────────────────
  const weightsSum =
    (Number(formValues.dense_weight) || 0) +
    (Number(formValues.sparse_weight) || 0) +
    (Number(formValues.metadata_boost) || 0);

  // ── Render: form (edit / create) ────────────────────────
  const renderForm = () => (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-5">
      {formError && <InlineAlert tone="error" message={formError} />}

      {/* Header: имя профиля + кнопки Отмена/Сохранить */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
            {t("modelConfig.form.profileName")}
          </label>
          <input
            type="text"
            name="name"
            value={formValues.name}
            onChange={(e) => handleInputChange(e, false)}
            className={inputClassName}
            placeholder={t("modelConfig.form.placeholder")}
          />
        </div>
        <div className="flex shrink-0 items-center gap-2 pt-5">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={handleCancelEdit}
          >
            {t("modelConfig.form.cancel")}
          </Button>
          <Button
            type="submit"
            size="sm"
            variant="primary"
            isLoading={isSubmitting}
          >
            {rightMode === "create" ? t("modelConfig.form.create") : t("modelConfig.form.save")}
          </Button>
        </div>
      </div>

      {/* ── Модели эмбеддингов ──────────────────────── */}
      <div className="space-y-3 border-t border-[var(--border-soft)] pt-4">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("modelConfig.form.embeddings.title")}
          </h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {t("modelConfig.form.embeddings.subtitle")}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {/* Primary */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.embeddings.primaryLabel")}
              </span>
              <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-0.5 text-[9px] font-semibold uppercase text-[var(--text-muted)]">
                {t("modelConfig.form.embeddings.primary")}
              </span>
            </div>
            <input
              type="text"
              name="embeddings_primary"
              value={formValues.embeddings_primary}
              onChange={(e) => handleInputChange(e, false)}
              className={`${elevatedSoftInputClassName} mt-1.5 font-mono`}
            />
            <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.embeddings.primaryDesc")}
            </p>
          </div>

          {/* Fallback */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.embeddings.fallbackLabel")}
              </span>
              <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-0.5 text-[9px] font-semibold uppercase text-[var(--text-muted)]">
                {t("modelConfig.form.embeddings.fallback")}
              </span>
            </div>
            <input
              type="text"
              name="embeddings_fallback"
              value={formValues.embeddings_fallback ?? ""}
              onChange={(e) => handleInputChange(e, false)}
              className={`${elevatedSoftInputClassName} mt-1.5 font-mono`}
              placeholder={t("modelConfig.form.embeddings.fallbackPlaceholder")}
            />
            <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.embeddings.fallbackDesc")}
            </p>
          </div>
        </div>
      </div>

      {/* ── Параметры поиска ─────────────────────────── */}
      <div className="space-y-3 border-t border-[var(--border-soft)] pt-4">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("modelConfig.form.searchParams.title")}
          </h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {t("modelConfig.form.searchParams.subtitle")}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {/* candidate_n */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.searchParams.candidateNLabel")}
              </span>
              <input
                type="number"
                name="candidate_n"
                value={formValues.candidate_n}
                onChange={(e) => handleInputChange(e, true)}
                className={numberInputClassName}
              />
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.searchParams.candidateNDesc")}
            </p>
            <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              <div className="font-semibold text-[var(--text-secondary)]">
                {t("modelConfig.form.searchParams.benchmarks.title")}
              </div>
              <div className="mt-0.5">
                {t("modelConfig.form.searchParams.benchmarks.fastShort")}
              </div>
              <div>
                <span className="font-semibold text-[var(--text-primary)]">
                  50
                </span>{" "}
                — {t("modelConfig.form.searchParams.benchmarks.balance")}
              </div>
              <div>{t("modelConfig.form.searchParams.benchmarks.complexMulti")}</div>
            </div>
          </div>

          {/* llm_context_k */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.searchParams.contextKLabel")}
              </span>
              <input
                type="number"
                name="llm_context_k"
                value={formValues.llm_context_k}
                onChange={(e) => handleInputChange(e, true)}
                className={numberInputClassName}
              />
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.searchParams.contextKDesc")}
            </p>
            <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              <div className="font-semibold text-[var(--text-secondary)]">
                {t("modelConfig.form.searchParams.benchmarks.title")}
              </div>
              <div className="mt-0.5">{t("modelConfig.form.searchParams.benchmarks.fastMode")}</div>
              <div>
                <span className="font-semibold text-[var(--text-primary)]">
                  5
                </span>{" "}
                — {t("modelConfig.form.searchParams.benchmarks.standard")}
              </div>
              <div>{t("modelConfig.form.searchParams.benchmarks.complexChecks")}</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Веса гибридного поиска ───────────────────── */}
      <div className="space-y-3 border-t border-[var(--border-soft)] pt-4">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("modelConfig.form.hybridWeights.title")}
          </h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
            {t("modelConfig.form.hybridWeights.subtitle")}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {/* dense_weight */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.hybridWeights.denseLabel")}
              </span>
              <input
                type="number"
                step="0.05"
                name="dense_weight"
                value={formValues.dense_weight}
                onChange={(e) => handleInputChange(e, true)}
                className={weightInputClassName}
              />
            </div>
            <div className="mt-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
              {t("modelConfig.form.hybridWeights.denseTitle")}
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.hybridWeights.denseDesc")}
            </p>
            <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] text-[var(--text-muted)]">
              <span className="font-semibold text-[var(--text-secondary)]">
                Увеличить:
              </span>{" "}
              {t("modelConfig.form.hybridWeights.denseIncrease")}
            </div>
          </div>

          {/* sparse_weight */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.hybridWeights.sparseLabel")}
              </span>
              <input
                type="number"
                step="0.05"
                name="sparse_weight"
                value={formValues.sparse_weight}
                onChange={(e) => handleInputChange(e, true)}
                className={weightInputClassName}
              />
            </div>
            <div className="mt-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
              {t("modelConfig.form.hybridWeights.sparseTitle")}
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.hybridWeights.sparseDesc")}
            </p>
            <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] text-[var(--text-muted)]">
              <span className="font-semibold text-[var(--text-secondary)]">
                Увеличить:
              </span>{" "}
              {t("modelConfig.form.hybridWeights.sparseIncrease")}
            </div>
          </div>

          {/* metadata_boost */}
          <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("modelConfig.form.hybridWeights.metaLabel")}
              </span>
              <input
                type="number"
                step="0.05"
                name="metadata_boost"
                value={formValues.metadata_boost}
                onChange={(e) => handleInputChange(e, true)}
                className={weightInputClassName}
              />
            </div>
            <div className="mt-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
              {t("modelConfig.form.hybridWeights.metaTitle")}
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.hybridWeights.metaDesc")}
            </p>
            <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] text-[var(--text-muted)]">
              <span className="font-semibold text-[var(--text-secondary)]">
                Увеличить:
              </span>{" "}
              {t("modelConfig.form.hybridWeights.metaIncrease")}
            </div>
          </div>

          {/* Сумма — live-расчёт */}
          <div
            className={[
              "rounded-lg border p-3",
              weightsSum > 0
                ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)]"
                : "border-[var(--color-error-border)] bg-[var(--color-error-bg)]",
            ].join(" ")}
          >
            <div className="flex items-center justify-between gap-2">
              <span
                className={[
                  "text-[10px] font-semibold uppercase tracking-[0.12em]",
                  weightsSum > 0
                    ? "text-[var(--color-success-text)]"
                    : "text-[var(--color-error-text)]",
                ].join(" ")}
              >
                {t("modelConfig.form.hybridWeights.sumLabel")}
              </span>
              <span
                className={[
                  "font-mono text-sm font-semibold",
                  weightsSum > 0
                    ? "text-[var(--color-success-text)]"
                    : "text-[var(--color-error-text)]",
                ].join(" ")}
              >
                {weightsSum.toFixed(2)}
              </span>
            </div>
            <p
              className={[
                "mt-1.5 text-[10px] leading-relaxed",
                weightsSum > 0
                  ? "text-[var(--color-success-text)]"
                  : "text-[var(--color-error-text)]",
              ].join(" ")}
            >
              {weightsSum > 0
                ? t("modelConfig.form.hybridWeights.sumValid")
                : t("modelConfig.form.hybridWeights.sumError")}
            </p>
          </div>
        </div>
      </div>
    </form>
  );

  // ── Render: view detail ─────────────────────────────────
  const renderViewDetail = () => {
    if (!selectedConfig) return null;

    const usage = state.usage[selectedConfig.id];
    const isUsed =
      !!usage &&
      ((usage.playbook_versions?.length ?? 0) > 0 ||
        (usage.deals?.length ?? 0) > 0);

    return (
      <div className="space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-[var(--text-primary)]">
              {selectedConfig.name}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">
              {selectedConfig.id}
            </div>
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleStartEdit}
            leftIcon={<Pencil className="h-3.5 w-3.5" />}
          >
            {t("modelConfig.form.edit")}
          </Button>
        </div>

        {/* ── Модели эмбеддингов ──────────────────────── */}
        <div className="space-y-3 border-t border-[var(--border-soft)] pt-4">
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("modelConfig.form.embeddings.title")}
            </h3>
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.embeddings.subtitle")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {/* Primary */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.embeddings.primaryLabel")}
                </span>
                <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-0.5 text-[9px] font-semibold uppercase text-[var(--text-muted)]">
                  {t("modelConfig.form.embeddings.primary")}
                </span>
              </div>
              <div className="mt-1.5 break-all font-mono text-xs font-semibold text-[var(--text-primary)]">
                intfloat/multilingual-e5-large
              </div>
              <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.embeddings.primaryDesc")}
              </p>
            </div>

            {/* Fallback */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.embeddings.fallbackLabel")}
                </span>
                <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-0.5 text-[9px] font-semibold uppercase text-[var(--text-muted)]">
                  {t("modelConfig.form.embeddings.fallback")}
                </span>
              </div>
              <div className="mt-1.5 break-all font-mono text-xs font-semibold text-[var(--text-primary)]">
                cointegrated/LaBSE
              </div>
              <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.embeddings.fallbackDesc")}
              </p>
            </div>
          </div>
        </div>

        {/* ── Параметры поиска ─────────────────────────── */}
        <div className="space-y-3 border-t border-[var(--border-soft)] pt-4">
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("modelConfig.form.searchParams.title")}
            </h3>
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.searchParams.subtitle")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {/* candidate_n */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.searchParams.candidateNLabel")}
                </span>
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                  50
                </span>
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.searchParams.candidateNDesc")}
              </p>
              <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                <div className="font-semibold text-[var(--text-secondary)]">
                  {t("modelConfig.form.searchParams.benchmarks.title")}
                </div>
                <div className="mt-0.5">
                  {t("modelConfig.form.searchParams.benchmarks.fastShort")}
                </div>
                <div>
                  <span className="font-semibold text-[var(--text-primary)]">
                    50
                  </span>{" "}
                  — {t("modelConfig.form.searchParams.benchmarks.balance")}
                </div>
                <div>{t("modelConfig.form.searchParams.benchmarks.complexMulti")}</div>
              </div>
            </div>

            {/* llm_context_k */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.searchParams.contextKLabel")}
                </span>
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                  5
                </span>
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.searchParams.contextKDesc")}
              </p>
              <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                <div className="font-semibold text-[var(--text-secondary)]">
                  {t("modelConfig.form.searchParams.benchmarks.title")}
                </div>
                <div className="mt-0.5">{t("modelConfig.form.searchParams.benchmarks.fastMode")}</div>
                <div>
                  <span className="font-semibold text-[var(--text-primary)]">
                    5
                  </span>{" "}
                  — {t("modelConfig.form.searchParams.benchmarks.standard")}
                </div>
                <div>{t("modelConfig.form.searchParams.benchmarks.complexChecks")}</div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Веса гибридного поиска ───────────────────── */}
        <div className="space-y-3 border-t border-[var(--border-soft)] pt-4">
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("modelConfig.form.hybridWeights.title")}
            </h3>
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {t("modelConfig.form.hybridWeights.subtitle")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {/* dense_weight */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.hybridWeights.denseLabel")}
                </span>
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                  0.6
                </span>
              </div>
              <div className="mt-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                {t("modelConfig.form.hybridWeights.denseTitle")}
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.hybridWeights.denseDesc")}
              </p>
              <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] text-[var(--text-muted)]">
                <span className="font-semibold text-[var(--text-secondary)]">
                  Увеличить:
                </span>{" "}
                {t("modelConfig.form.hybridWeights.denseIncrease")}
              </div>
            </div>

            {/* sparse_weight */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.hybridWeights.sparseLabel")}
                </span>
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                  0.3
                </span>
              </div>
              <div className="mt-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                {t("modelConfig.form.hybridWeights.sparseTitle")}
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.hybridWeights.sparseDesc")}
              </p>
              <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] text-[var(--text-muted)]">
                <span className="font-semibold text-[var(--text-secondary)]">
                  Увеличить:
                </span>{" "}
                {t("modelConfig.form.hybridWeights.sparseIncrease")}
              </div>
            </div>

            {/* metadata_boost */}
            <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("modelConfig.form.hybridWeights.metaLabel")}
                </span>
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                  0.1
                </span>
              </div>
              <div className="mt-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                {t("modelConfig.form.hybridWeights.metaTitle")}
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("modelConfig.form.hybridWeights.metaDesc")}
              </p>
              <div className="mt-2 rounded bg-[var(--bg-base)] px-2 py-1.5 text-[10px] text-[var(--text-muted)]">
                <span className="font-semibold text-[var(--text-secondary)]">
                  Увеличить:
                </span>{" "}
                {t("modelConfig.form.hybridWeights.metaIncrease")}
              </div>
            </div>

            {/* Сумма — как отдельная карточка для симметрии */}
            <div className="rounded-lg border border-[var(--color-success-border)] bg-[var(--color-success-bg)] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-success-text)]">
                  {t("modelConfig.form.hybridWeights.sumLabel")}
                </span>
                <span className="font-mono text-sm font-semibold text-[var(--color-success-text)]">
                  1.0
                </span>
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--color-success-text)]">
                {t("modelConfig.form.hybridWeights.sumFormula")}
              </p>
            </div>
          </div>
        </div>

        {/* ── Использование ───────────────────────────── */}
        <div className="space-y-2 border-t border-[var(--border-soft)] pt-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("modelConfig.form.usage.title")}
          </h3>

          {!usage ? (
            <p className="text-[11px] text-[var(--text-muted)]">{t("modelConfig.form.usage.loading")}</p>
          ) : !isUsed ? (
            <p className="text-[11px] text-[var(--color-success-text)]">
              {t("modelConfig.form.usage.notUsed")}
            </p>
          ) : (
            <div className="space-y-1.5 text-[11px] text-[var(--text-muted)]">
              {(usage.playbook_versions?.length ?? 0) > 0 && (
                <div>
                  <span className="font-semibold text-[var(--text-secondary)]">
                    {t("modelConfig.form.usage.playbooks")}
                  </span>{" "}
                  {usage.playbook_versions
                    .slice(0, 3)
                    .map((pv) => `${pv.name} (${pv.semver})`)
                    .join(", ")}
                  {usage.playbook_versions.length > 3 && " …"}
                </div>
              )}
              {(usage.deals?.length ?? 0) > 0 && (
                <div>
                  <span className="font-semibold text-[var(--text-secondary)]">
                    {t("modelConfig.form.usage.projects")}
                  </span>{" "}
                  {usage.deals
                    .slice(0, 3)
                    .map((d) => d.name)
                    .join(", ")}
                  {usage.deals.length > 3 && " …"}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Действия ────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border-soft)] pt-4">
          {dealId && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void handleSelectForDeal(selectedConfig)}
              isLoading={isSelecting}
              disabled={isSelecting}
            >
              {t("modelConfig.form.selectForProject")}
            </Button>
          )}

          <button
            type="button"
            onClick={() => void handleDelete(selectedConfig)}
            disabled={isDeleting || isUsed}
            className="ml-auto text-[10px] text-[var(--text-muted)] transition-colors hover:text-[var(--color-error-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {t("modelConfig.form.deleteProfile")}
          </button>
        </div>
      </div>
    );
  };

  // ── Main render ─────────────────────────────────────────
  return (
    <div className={isEmbedded ? "space-y-4" : "space-y-6"}>
      {/* Embedded: текущий профиль сделки */}
      {isEmbedded && currentDeal?.model_config_name && (
        <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-muted)]">
          <Trans
            t={t}
            i18nKey="modelConfig.currentDealProfile"
            values={{ name: currentDeal.model_config_name }}
            components={{
              bold: <span className="font-medium text-[var(--text-primary)]" />,
            }}
          />
        </div>
      )}

      {/* Alerts */}
      {state.error && <InlineAlert tone="error" message={state.error} />}
      {deleteError && <InlineAlert tone="error" message={deleteError} />}
      {selectError && <InlineAlert tone="error" message={selectError} />}
      {successText && <InlineAlert tone="success" message={successText} />}

      {/* Main grid: узкая левая колонка + широкая правая */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(260px,1fr)_3fr]">
        {/* ── Список профилей ──────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("modelConfig.list.title")}
            </h2>
            <Button
              size="sm"
              variant="secondary"
              onClick={handleStartCreate}
              leftIcon={<Plus className="h-3.5 w-3.5" />}
            >
              {t("modelConfig.list.newBtn")}
            </Button>
          </div>

          {state.isLoading ? (
            <p className="text-xs text-[var(--text-muted)]">
              {t("modelConfig.list.loading")}
            </p>
          ) : state.items.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-xs text-[var(--text-muted)]">
              {t("modelConfig.list.empty")}
            </p>
          ) : (
            <ul className="max-h-[36rem] space-y-1.5 overflow-y-auto">
              {state.items.map((cfg) => {
                const isSelected =
                  selectedId === cfg.id && rightMode === "view";
                const isEditing =
                  selectedId === cfg.id && rightMode === "edit";
                const isCurrentDealConfig =
                  currentDeal?.model_config_id === cfg.id;
                const usage = state.usage[cfg.id];
                const isUsed =
                  !!usage &&
                  ((usage.playbook_versions?.length ?? 0) > 0 ||
                    (usage.deals?.length ?? 0) > 0);

                return (
                  <li key={cfg.id}>
                    <button
                      type="button"
                      onClick={() => handleSelectConfig(cfg.id)}
                      className={[
                        "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
                        isSelected || isEditing
                          ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                          : isCurrentDealConfig
                            ? "border-[var(--accent-primary)]/50 bg-[var(--accent-muted)]/50"
                            : "border-[var(--border-soft)] hover:border-[var(--border-strong)]",
                      ].join(" ")}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={[
                              "truncate font-semibold",
                              isSelected || isEditing
                                ? "text-[var(--accent-primary)]"
                                : "text-[var(--text-primary)]",
                            ].join(" ")}
                          >
                            {cfg.name}
                          </span>
                          {isCurrentDealConfig && (
                            <span className="shrink-0 rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                              {t("modelConfig.list.currentBadge")}
                            </span>
                          )}
                        </div>
                        <div
                          className={[
                            "mt-0.5 flex items-center gap-2 text-[10px]",
                            isSelected || isEditing
                              ? "text-[var(--accent-primary)]"
                              : "text-[var(--text-muted)]",
                          ].join(" ")}
                        >
                          <span className="font-mono">
                            {cfg.id.slice(0, 8)}…
                          </span>
                          {isUsed ? (
                            <span>{t("modelConfig.list.inUse")}</span>
                          ) : usage ? (
                            <span className="text-[var(--color-success-text)]">
                              {t("modelConfig.list.free")}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* ── Правая панель ─────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            {rightMode === "create"
              ? t("modelConfig.rightPanel.newProfile")
              : rightMode === "edit"
                ? t("modelConfig.rightPanel.editing")
                : rightMode === "view"
                  ? t("modelConfig.rightPanel.profile")
                  : t("modelConfig.rightPanel.details")}
          </h2>

          {rightMode === null && (
            <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-xs text-[var(--text-muted)]">
              {t("modelConfig.rightPanel.emptyPrompt")}
            </p>
          )}

          {rightMode === "view" && renderViewDetail()}

          {(rightMode === "create" || rightMode === "edit") && renderForm()}
        </section>
      </div>
    </div>
  );
};

export default ModelConfigManagerPanel;


