// =============================================================
// src/pages/ModelConfigsAdminPage.tsx
// Админ-страница для управления профилями моделей (ModelConfig).
//
// Позволяет:
// - посмотреть список всех ModelConfig;
// - создать новый профиль (name + параметры);
// - отредактировать существующий профиль;
// - удалить профиль;
// - при наличии dealId в query-строке привязать профиль к конкретной сделке
//   ("Выбрать для проекта" -> PATCH /deals/{dealId}/model-config).
//   Также показывает, где профиль используется (плейбуки / проекты).
// =============================================================

import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import type {
  ApiError,
  ModelConfig,
  ModelConfigCreateInput,
  ModelConfigUpdateInput,
} from "../types";

type ModelConfigUsage = {
  model_config_id: string;
  playbook_versions: { id: string; name: string; semver: string; status: string }[];
  deals: { id: string; name: string; status: string }[];
};

interface ModelConfigsAdminPageState {
  items: ModelConfig[];
  isLoading: boolean;
  error: string | null;
  usage: Record<string, ModelConfigUsage | undefined>;
}

type Mode = "create" | "edit" | null;

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

const ModelConfigsAdminPage: React.FC = () => {
  const navigate = useNavigate();

  // Если страница открыта с параметром dealId, значит нас вызвали
  // из конкретной сделки и нужно показывать кнопку "Выбрать для проекта".
  const params = new URLSearchParams(window.location.search);
  const dealIdFromQuery = params.get("dealId");

  const [state, setState] = useState<ModelConfigsAdminPageState>({
    items: [],
    isLoading: false,
    error: null,
    usage: {},
  });

  const [mode, setMode] = useState<Mode>(null);
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

  // Загрузка usage для списка ModelConfig
  const loadUsageForConfigs = async (configs: ModelConfig[]) => {
    const usageMap: Record<string, ModelConfigUsage> = {};

    await Promise.all(
      configs.map(async (cfg) => {
        try {
          const res = await client.get<ModelConfigUsage>(
            `/api/v1/model-configs/${cfg.id}/usage`,
          );
          usageMap[cfg.id] = res.data;
        } catch {
          // Если не удалось загрузить usage для конкретного профиля — пропускаем
        }
      }),
    );

    setState((prev) => ({
      ...prev,
      usage: usageMap,
    }));
  };

  // Загрузка списка ModelConfig
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
  }, []);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  const handleBack = () => {
    // Если нас вызвали из сделки, логично вернуться назад в историю,
    // иначе — в общий админский раздел.
    if (dealIdFromQuery) {
      navigate(-1);
    } else {
      navigate("/admin");
    }
  };

  // Начать создание нового профиля
  const startCreate = () => {
    setMode("create");
    setSelectedId(null);
    setFormError(null);
    setFormValues(defaultCreateValues);
  };

  // Начать редактирование существующего
  const startEdit = (config: ModelConfig) => {
    setMode("edit");
    setSelectedId(config.id);
    setFormError(null);

    // Так как backend сейчас не отдаёт retrieval_config/scoring_config
    // напрямую, здесь мы заполняем только name и embeddings.
    // Числовые поля даём по умолчанию, пользователь может их скорректировать.
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
  };

  const resetForm = () => {
    setMode(null);
    setSelectedId(null);
    setFormError(null);
    setFormValues(defaultCreateValues);
  };

  // Обновление полей формы
  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    numeric: boolean = false,
  ) => {
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
  };

  const validateForm = (): boolean => {
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
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mode) return;

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "create") {
        const payload: ModelConfigCreateInput = {
          name: formValues.name.trim(),
          embeddings_primary:
            formValues.embeddings_primary || "intfloat/multilingual-e5-large",
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
      } else if (mode === "edit" && selectedId) {
        const payload: ModelConfigUpdateInput = {
          name: formValues.name.trim(),
          embeddings_primary:
            formValues.embeddings_primary || "intfloat/multilingual-e5-large",
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
  };

  const handleDelete = async (config: ModelConfig) => {
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
    try {
      await client.delete(`/api/v1/model-configs/${config.id}`);
      await loadConfigs();

      if (selectedId === config.id) {
        resetForm();
      }
    } catch (err) {
      const apiErr = err as ApiError;
      setDeleteError(
        apiErr.detail || "Не удалось удалить профиль модели. Попробуйте позже.",
      );
    } finally {
      setIsDeleting(false);
    }
  };

  // Привязать профиль модели к конкретной сделке (если есть dealId в query)
  const handleSelectForDeal = async (config: ModelConfig) => {
    if (!dealIdFromQuery) {
      return;
    }

    const ok = window.confirm(
      `Выбрать профиль модели "${config.name}" для текущего проекта?\n\n` +
        "Этот профиль будет использован при запуске анализа по сделке.",
    );
    if (!ok) return;

    setIsSelecting(true);
    setSelectError(null);
    try {
      await client.patch(`/api/v1/deals/${dealIdFromQuery}/model-config`, {
        model_config_id: config.id,
      });

      // После успешного выбора возвращаемся на предыдущую страницу (страницу сделки)
      navigate(-1);
    } catch (err) {
      const apiErr = err as ApiError;
      setSelectError(
        apiErr.detail ||
          "Не удалось сохранить профиль модели для сделки. Попробуйте позже.",
      );
    } finally {
      setIsSelecting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Заголовок */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Профили моделей (ModelConfig)
            </h1>
            <p className="text-sm text-gray-500">
              Здесь можно создавать и настраивать профили моделей, которые затем
              используются плейбуками и проектами.
            </p>
            {dealIdFromQuery && (
              <p className="text-xs text-gray-500 mt-1">
                Страница открыта из конкретного проекта: можно выбрать профиль
                модели для этой сделки.
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleBack}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            ← Назад
          </button>
        </div>

        {/* Общие ошибки */}
        {state.error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {state.error}
          </div>
        )}
        {deleteError && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {deleteError}
          </div>
        )}
        {selectError && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {selectError}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Левая колонка: список профилей */}
          <div className="bg-white rounded-lg border p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-800">
                Список профилей
              </h2>
              <button
                type="button"
                onClick={startCreate}
                className="px-2 py-1 text-xs rounded bg-green-600 text-white hover:bg-green-700"
              >
                + Новый профиль
              </button>
            </div>

            {state.isLoading ? (
              <p className="text-xs text-gray-500">Загружаем профили…</p>
            ) : state.items.length === 0 ? (
              <p className="text-xs text-gray-500">
                Пока нет ни одного профиля модели. Создайте первый.
              </p>
            ) : (
              <ul className="space-y-2 max-h-96 overflow-y-auto">
                {state.items.map((cfg) => {
                  const usage = state.usage[cfg.id];
                  const isUsed =
                    !!usage &&
                    ((usage.playbook_versions &&
                      usage.playbook_versions.length > 0) ||
                      (usage.deals && usage.deals.length > 0));

                  return (
                    <li
                      key={cfg.id}
                      className={`border rounded px-3 py-2 text-xs flex items-center justify-between ${
                        selectedId === cfg.id
                          ? "border-blue-600 bg-blue-50"
                          : "border-gray-200 bg-white"
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-gray-800">
                          {cfg.name}
                        </div>
                        <div className="text-[11px] text-gray-500">
                          ID: {cfg.id}
                        </div>
                        <div className="text-[11px] text-gray-500 mt-0.5">
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
                                  onClick={() =>
                                    navigate(
                                      `/admin/playbook-versions?modelConfigId=${encodeURIComponent(
                                        cfg.id,
                                      )}`,
                                    )
                                  }
                                  className="ml-1 underline text-blue-600"
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
                              <span className="text-green-600">
                                Не используется (можно безопасно удалить)
                              </span>
                            )
                          ) : (
                            <span className="text-gray-400">
                              Загружаем информацию об использовании…
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => startEdit(cfg)}
                          className="px-2 py-1 text-[11px] rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                        >
                          Редактировать
                        </button>

                        {dealIdFromQuery && (
                          <button
                            type="button"
                            onClick={() => handleSelectForDeal(cfg)}
                            disabled={isSelecting}
                            className="px-2 py-1 text-[11px] rounded border border-blue-300 text-blue-700 hover:bg-blue-50 disabled:opacity-60"
                          >
                            Выбрать для проекта
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => handleDelete(cfg)}
                          disabled={isDeleting}
                          className="px-2 py-1 text-[11px] rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-60"
                        >
                          Удалить
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Правая колонка: форма */}
          <div className="bg-white rounded-lg border p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              {mode === "create"
                ? "Создание нового профиля"
                : mode === "edit"
                ? "Редактирование профиля"
                : "Выберите профиль слева или создайте новый"}
            </h2>

            {mode ? (
              <form onSubmit={handleSubmit} className="space-y-3">
                {formError && (
                  <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded p-2">
                    {formError}
                  </div>
                )}

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Имя профиля
                  </label>
                  <input
                    type="text"
                    name="name"
                    value={formValues.name}
                    onChange={(e) => handleInputChange(e, false)}
                    className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                    placeholder="например, default-v1, fast-v1, quality-v1"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Embeddings primary
                  </label>
                  <input
                    type="text"
                    name="embeddings_primary"
                    value={formValues.embeddings_primary}
                    onChange={(e) => handleInputChange(e, false)}
                    className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                  />
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    Основная модель эмбеддингов (используется в ретривере и
                    классификации).
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Embeddings fallback (опционально)
                  </label>
                  <input
                    type="text"
                    name="embeddings_fallback"
                    value={formValues.embeddings_fallback ?? ""}
                    onChange={(e) => handleInputChange(e, false)}
                    className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                  />
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    Запасная модель эмбеддингов или оставьте пустым.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      candidate_n
                    </label>
                    <input
                      type="number"
                      name="candidate_n"
                      value={formValues.candidate_n}
                      onChange={(e) => handleInputChange(e, true)}
                      className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                    />
                    <p className="text-[11px] text-gray-500 mt-0.5">
                      Сколько документов/фрагментов рассматривать при поиске
                      (быстрее = меньше).
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      llm_context_k
                    </label>
                    <input
                      type="number"
                      name="llm_context_k"
                      value={formValues.llm_context_k}
                      onChange={(e) => handleInputChange(e, true)}
                      className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                    />
                    <p className="text-[11px] text-gray-500 mt-0.5">
                      Сколько контекста отдавать LLM (меньше = быстрее,
                      больше = точнее).
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      dense_weight
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      name="dense_weight"
                      value={formValues.dense_weight}
                      onChange={(e) => handleInputChange(e, true)}
                      className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      sparse_weight
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      name="sparse_weight"
                      value={formValues.sparse_weight}
                      onChange={(e) => handleInputChange(e, true)}
                      className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                      metadata_boost
                    </label>
                    <input
                      type="number"
                      step="0.05"
                      name="metadata_boost"
                      value={formValues.metadata_boost}
                      onChange={(e) => handleInputChange(e, true)}
                      className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                    />
                  </div>
                </div>
                <p className="text-[11px] text-gray-500">
                  Веса управляют балансом между эмбеддингами, BM25 и
                  метаданными. В сумме они должны давать положительное число.
                </p>

                <div className="flex items-center justify-end gap-2 pt-3 border-t mt-3">
                  <button
                    type="button"
                    onClick={resetForm}
                    className="px-3 py-1.5 text-xs rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  >
                    Отмена
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="px-4 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                  >
                    {isSubmitting
                      ? "Сохраняем..."
                      : mode === "create"
                      ? "Создать профиль"
                      : "Сохранить изменения"}
                  </button>
                </div>
              </form>
            ) : (
              <p className="text-xs text-gray-500">
                Для начала выберите профиль слева или нажмите{" "}
                <span className="font-semibold">«Новый профиль»</span>, чтобы
                добавить конфигурацию модели.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelConfigsAdminPage;
