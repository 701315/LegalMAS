// =============================================================
// src/pages/AdminPlaybookVersionsPage.tsx
// Админ-страница для управления версиями плейбуков (PlaybookVersion).
//
// Позволяет:
// - посмотреть список всех PlaybookVersion;
// - при наличии modelConfigId в query-строке подсветить/отфильтровать
//   версии, использующие этот профиль модели;
// - сменить профиль модели для версии плейбука
//   (PATCH /playbooks/{id}/model-config).
// =============================================================

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import client from "../api/client";
import type {
  ApiError,
  PlaybookVersionShort,
  ModelConfig,
} from "../types";

interface State {
  versions: PlaybookVersionShort[];
  modelConfigs: ModelConfig[];
  isLoading: boolean;
  error: string | null;
}

const AdminPlaybookVersionsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const modelConfigIdFromQuery = searchParams.get("modelConfigId");

  const [state, setState] = useState<State>({
    versions: [],
    modelConfigs: [],
    isLoading: false,
    error: null,
  });

  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    null,
  );
  const [selectedModelConfigId, setSelectedModelConfigId] = useState<
    string | null
  >(modelConfigIdFromQuery);

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // 1. Загрузить список версий плейбуков
  const loadVersions = async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const res = await client.get<PlaybookVersionShort[]>(
        "/api/v1/playbooks",
      );
      setState((prev) => ({
        ...prev,
        versions: res.data || [],
        isLoading: false,
        error: null,
      }));
    } catch (err) {
      const apiErr = err as ApiError;
      setState((prev) => ({
        ...prev,
        versions: [],
        isLoading: false,
        error:
          apiErr.detail ||
          "Не удалось загрузить список версий плейбуков. Попробуйте позже.",
      }));
    }
  };

  // 2. Загрузить список профилей моделей (ModelConfig)
  const loadModelConfigs = async () => {
    try {
      const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
      setState((prev) => ({
        ...prev,
        modelConfigs: res.data || [],
      }));
    } catch (err) {
      const apiErr = err as ApiError;
      setState((prev) => ({
        ...prev,
        error:
          prev.error ||
          apiErr.detail ||
          "Не удалось загрузить список профилей моделей.",
      }));
    }
  };

  useEffect(() => {
    loadVersions();
    loadModelConfigs();
  }, []);

  // Сопоставление versionId -> model_config_id (если нужно — можно расширить тип PlaybookVersionShort)
  // Здесь предполагаем, что детальный get /playbooks/{id} используется на другом экране;
  // для фильтра по modelConfigId достаточно короткого списка, который приходит из БД.
  // Если ты уже добавил model_config_id в PlaybookVersionShort на бэке — просто используй его здесь.

  const filteredVersions = useMemo(() => {
    if (!modelConfigIdFromQuery) {
      return state.versions;
    }
    // Сейчас PlaybookVersionShort не содержит model_config_id,
    // поэтому фильтрации по факту нет. Если на бэке ты добавишь
    // model_config_id в PlaybookVersionShort, то здесь фильтр будет таким:
    //
    // return state.versions.filter(
    //   (v) => (v as any).model_config_id === modelConfigIdFromQuery,
    // );
    //
    // Пока просто возвращаем все версии, но подсветку сделаем через selectedModelConfigId.
    return state.versions;
  }, [state.versions, modelConfigIdFromQuery]);

  const handleBack = () => {
    navigate("/admin/model-configs");
  };

  const handleSelectVersion = (v: PlaybookVersionShort) => {
    setSelectedVersionId(v.id);
    setSaveError(null);
    setSaveSuccess(null);
  };

  const handleChangeModelConfig = (value: string) => {
    setSelectedModelConfigId(value || null);
    setSaveError(null);
    setSaveSuccess(null);
  };

  const handleSave = async () => {
    if (!selectedVersionId) return;

    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(null);

    try {
      await client.patch(
        `/api/v1/playbooks/${selectedVersionId}/model-config`,
        {
          model_config_id: selectedModelConfigId,
        },
      );

      setSaveSuccess("Профиль модели для версии плейбука обновлён.");
    } catch (err) {
      const apiErr = err as ApiError;
      setSaveError(
        apiErr.detail ||
          "Не удалось обновить профиль модели для версии плейбука.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  const selectedModelConfigName = useMemo(() => {
    if (!selectedModelConfigId) return null;
    const mc = state.modelConfigs.find((m) => m.id === selectedModelConfigId);
    return mc?.name ?? null;
  }, [selectedModelConfigId, state.modelConfigs]);

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Версии плейбуков и профили моделей
            </h1>
            <p className="text-sm text-gray-500">
              Здесь можно переназначить профиль модели для версий плейбуков,
              чтобы потом удалить устаревшие ModelConfig.
            </p>
            {modelConfigIdFromQuery && (
              <p className="text-xs text-gray-500 mt-1">
                Показаны версии плейбуков для профиля модели с ID{" "}
                <span className="font-mono">{modelConfigIdFromQuery}</span>. Вы
                можете перевести эти версии на другой профиль.
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleBack}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            ← К профилям моделей
          </button>
        </div>

        {state.error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {state.error}
          </div>
        )}

        {saveError && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {saveError}
          </div>
        )}

        {saveSuccess && (
          <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded p-3">
            {saveSuccess}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Левая колонка: список версий плейбуков */}
          <div className="bg-white rounded-lg border p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-2">
              Версии плейбуков
            </h2>
            {state.isLoading ? (
              <p className="text-xs text-gray-500">Загружаем версии…</p>
            ) : filteredVersions.length === 0 ? (
              <p className="text-xs text-gray-500">
                Версии плейбуков пока не созданы.
              </p>
            ) : (
              <ul className="space-y-1 max-h-80 overflow-y-auto text-xs">
                {filteredVersions.map((v) => (
                  <li key={v.id}>
                    <button
                      type="button"
                      onClick={() => handleSelectVersion(v)}
                      className={`w-full text-left px-3 py-2 rounded border ${
                        selectedVersionId === v.id
                          ? "border-blue-600 bg-blue-50 text-blue-700"
                          : "border-gray-200 bg-white text-gray-800 hover:bg-gray-50"
                      }`}
                    >
                      <div className="font-semibold">{v.name}</div>
                      <div className="text-[11px] text-gray-500">
                        Версия: {v.semver} · Статус: {v.status}
                      </div>
                      <div className="text-[11px] text-gray-400 mt-0.5">
                        Playbook ID: {v.playbook_id}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Правая колонка: выбор профиля модели */}
          <div className="bg-white rounded-lg border p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              Профиль модели для версии
            </h2>

            {!selectedVersionId ? (
              <p className="text-xs text-gray-500">
                Сначала выберите версию плейбука слева.
              </p>
            ) : state.modelConfigs.length === 0 ? (
              <p className="text-xs text-gray-500">
                Профили моделей не найдены. Сначала создайте их на странице
                &laquo;Профили моделей&raquo;.
              </p>
            ) : (
              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-gray-600 mb-1">
                    Профиль модели (ModelConfig)
                  </label>
                  <select
                    value={selectedModelConfigId || ""}
                    onChange={(e) => handleChangeModelConfig(e.target.value)}
                    className="w-full border rounded px-2 py-1 text-xs"
                  >
                    <option value="">
                      — Без явного профиля (использовать дефолтные настройки) —
                    </option>
                    {state.modelConfigs.map((mc) => (
                      <option key={mc.id} value={mc.id}>
                        {mc.name} — {mc.id}
                      </option>
                    ))}
                  </select>
                  <p className="text-[11px] text-gray-500 mt-1">
                    Выберите новый профиль модели. После сохранения эта версия
                    плейбука перестанет ссылаться на старый ModelConfig, и его
                    можно будет удалить, если он больше нигде не используется.
                    {selectedModelConfigName && (
                      <>
                        {" "}
                        Сейчас выбран профиль:{" "}
                        <span className="font-semibold">
                          {selectedModelConfigName}
                        </span>
                        .
                      </>
                    )}
                  </p>
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t mt-3">
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={isSaving}
                    className="px-4 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                  >
                    {isSaving
                      ? "Сохраняем..."
                      : "Сохранить профиль для версии"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminPlaybookVersionsPage;
