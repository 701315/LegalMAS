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
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Field from "../components/ui/Field";
import InlineAlert from "../components/InlineAlert";
import LoadingBlock from "../components/ui/LoadingBlock";
import PageSection from "../components/ui/PageSection";
import type { ApiError, PlaybookVersionShort, ModelConfig } from "../types";

interface State {
  versions: PlaybookVersionShort[];
  modelConfigs: ModelConfig[];
  isLoading: boolean;
  error: string | null;
}

const selectClassName =
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-2 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60";

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

  const loadVersions = async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const res = await client.get<PlaybookVersionShort[]>("/api/v1/playbooks");
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
    void loadVersions();
    void loadModelConfigs();
  }, []);

  const filteredVersions = useMemo(() => {
    if (!modelConfigIdFromQuery) {
      return state.versions;
    }
    return state.versions;
  }, [state.versions, modelConfigIdFromQuery]);

  const handleBack = () => {
    navigate("/admin/model-configs");
  };

  const handleSelectVersion = (version: PlaybookVersionShort) => {
    setSelectedVersionId(version.id);
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
      await client.patch(`/api/v1/playbooks/${selectedVersionId}/model-config`, {
        model_config_id: selectedModelConfigId,
      });

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

  const selectedVersion = useMemo(() => {
    if (!selectedVersionId) return null;
    return state.versions.find((v) => v.id === selectedVersionId) ?? null;
  }, [selectedVersionId, state.versions]);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-1">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
              Admin · Playbook Versions
            </p>
            <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
              Версии плейбуков и профили моделей
            </h1>
            <p className="text-xs text-[var(--text-secondary)]">
              Здесь можно переназначить профиль модели для версий плейбуков,
              чтобы потом удалить устаревшие ModelConfig.
            </p>
            {modelConfigIdFromQuery && (
              <p className="text-[11px] text-[var(--text-muted)]">
                Открыто из профиля модели:{" "}
                <span className="font-mono text-[var(--text-secondary)]">
                  {modelConfigIdFromQuery}
                </span>
                . Вы можете перевести версии плейбуков на другой профиль.
              </p>
            )}
          </div>

          <Button variant="secondary" size="sm" onClick={handleBack}>
            ← К профилям моделей
          </Button>
        </div>

        <InlineAlert tone="error" message={state.error} />
        <InlineAlert tone="error" message={saveError} />
        <InlineAlert tone="success" message={saveSuccess} />

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <PageSection title="Версии плейбуков">
            {state.isLoading ? (
              <LoadingBlock text="Загружаем версии плейбуков..." rows={6} />
            ) : filteredVersions.length === 0 ? (
              <EmptyState
                title="Версии плейбуков пока не созданы"
                description="Когда версии появятся, здесь можно будет выбрать нужную и переназначить для неё профиль модели."
              />
            ) : (
              <ul className="max-h-96 space-y-1 overflow-y-auto pr-1">
                {filteredVersions.map((version) => (
                  <li key={version.id}>
                    <button
                      type="button"
                      onClick={() => handleSelectVersion(version)}
                      className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                        selectedVersionId === version.id
                          ? "border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--text-primary)]"
                          : "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
                      }`}
                    >
                      <div className="font-semibold text-[var(--text-primary)]">
                        {version.name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                        Версия: {version.semver} · Статус: {version.status}
                      </div>
                      <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                        Playbook ID: {version.playbook_id}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </PageSection>

          <PageSection
            title="Профиль модели для версии"
            rightSlot={
              selectedVersion ? (
                <span className="text-[11px] text-[var(--text-muted)]">
                  ID: {selectedVersion.id}
                </span>
              ) : null
            }
          >
            {!selectedVersionId ? (
              <EmptyState
                title="Версия плейбука не выбрана"
                description="Сначала выберите версию плейбука слева, затем назначьте ей нужный профиль модели."
              />
            ) : state.modelConfigs.length === 0 ? (
              <EmptyState
                title="Профили моделей не найдены"
                description="Сначала создайте хотя бы один профиль модели на странице профилей."
              />
            ) : (
              <div className="space-y-4 text-xs">
                <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-3">
                  <p className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Выбранная версия
                  </p>
                  <p className="mt-1 font-semibold text-[var(--text-primary)]">
                    {selectedVersion?.name}
                  </p>
                  <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                    Semver: {selectedVersion?.semver} · Статус:{" "}
                    {selectedVersion?.status}
                  </p>
                </div>

                <Field label="Профиль модели (ModelConfig)">
                  <select
                    value={selectedModelConfigId || ""}
                    onChange={(e) => handleChangeModelConfig(e.target.value)}
                    className={selectClassName}
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
                </Field>

                <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
                  Выберите новый профиль модели. После сохранения эта версия
                  плейбука перестанет ссылаться на старый ModelConfig, и его
                  можно будет удалить, если он больше нигде не используется.
                  {selectedModelConfigName && (
                    <span className="block mt-2 text-[var(--text-primary)]">
                      Сейчас выбран профиль:{" "}
                      <span className="font-semibold">
                        {selectedModelConfigName}
                      </span>
                      .
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-end border-t border-[var(--border)] pt-3">
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    onClick={handleSave}
                    disabled={isSaving}
                  >
                    {isSaving
                      ? "Сохраняем..."
                      : "Сохранить профиль для версии"}
                  </Button>
                </div>
              </div>
            )}
          </PageSection>
        </div>
      </div>
    </div>
  );
};

export default AdminPlaybookVersionsPage;
