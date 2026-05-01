// =============================================================
// src/pages/DealPlaybookSelectorPage.tsx
// Выбор / создание playbook для конкретной сделки.
// Работает поверх новых эндпоинтов /playbooks.
// Переписано под единый UI-kit страницы админского интерфейса.
// =============================================================

import React, { useEffect, useState, useMemo, useCallback } from "react";
import { useNavigate, useParams, Navigate } from "react-router-dom";

import client from "../api/client";
import { useDealPermissions } from "../hooks/usePermissions";

import Button from "../components/ui/Button";
import PageSection from "../components/ui/PageSection";
import EmptyState from "../components/ui/EmptyState";
import LoadingBlock from "../components/ui/LoadingBlock";
import InlineAlert from "../components/InlineAlert";
import ConfirmDialog from "../components/ConfirmDialog";

import {
  getApiErrorMessage,
  isApiErrorStatus,
} from "../utils/apiErrors";

import type {
  Deal,
  DealDetail,
  PlaybookLine,
  PlaybookLineDetail,
  PlaybookVersionShort,
  PlaybookVersionDetail,
  PlaybookCreateRequest,
  PlaybookCreateResponse,
  DealPlaybookHistoryItem,
  ModelConfig,
} from "../types";

interface DealPlaybookSelectorPageProps {
  /** Если сделка уже загружена выше по иерархии — можно пробросить её сюда. */
  deal?: Deal;
}

const selectClassName =
  "w-full rounded border border-gray-300 px-2 py-1 text-xs disabled:cursor-not-allowed disabled:bg-gray-50";

const DealPlaybookSelectorPage: React.FC<DealPlaybookSelectorPageProps> = ({
  deal,
}) => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const { canViewOverview } = useDealPermissions(dealId as string);
  const canEditPlaybook = canViewOverview;

  const [dealDetail, setDealDetail] = useState<DealDetail | null>(null);

  const [lines, setLines] = useState<PlaybookLine[]>([]);
  const [versions, setVersions] = useState<PlaybookVersionShort[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    null,
  );
  const [versionDetail, setVersionDetail] =
    useState<PlaybookVersionDetail | null>(null);
  const [selectedLineDetail, setSelectedLineDetail] =
    useState<PlaybookLineDetail | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isApplying, setIsApplying] = useState(false);
  const [isCreatingVersion, setIsCreatingVersion] = useState(false);

  const [errorText, setErrorText] = useState<string | null>(null);
  const [successText, setSuccessText] = useState<string | null>(null);
  const [createVersionError, setCreateVersionError] = useState<string | null>(
    null,
  );

  const [history, setHistory] = useState<DealPlaybookHistoryItem[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [selectedModelConfigId, setSelectedModelConfigId] = useState<
    string | null
  >(null);
  const [modelConfigsError, setModelConfigsError] = useState<string | null>(
    null,
  );
  const [isModelConfigsLoading, setIsModelConfigsLoading] = useState(false);

  const [isApplyConfirmOpen, setIsApplyConfirmOpen] = useState(false);

  const effectiveDeal = useMemo(
    () => dealDetail ?? deal ?? null,
    [dealDetail, deal],
  );

  const lineById = useMemo(() => {
    const map = new Map<string, PlaybookLine>();
    for (const line of lines) {
      map.set(line.id, line);
    }
    return map;
  }, [lines]);

  const selectedLine = selectedLineId ? lineById.get(selectedLineId) : null;

  const visibleVersions = useMemo(() => {
    if (!selectedLineId) return [];
    return versions.filter(
      (version) =>
        version.playbook_id === selectedLineId &&
        (version.status === "default" || version.status === "active"),
    );
  }, [versions, selectedLineId]);

  const currentVersionId = effectiveDeal?.playbook_version_id ?? null;
  const isSameAsCurrent =
    currentVersionId !== null && selectedVersionId === currentVersionId;

  const isUiLocked = isApplying || isCreatingVersion;

  const clearMessages = () => {
    setErrorText(null);
    setSuccessText(null);
  };

  const loadHistory = useCallback(async () => {
    if (!dealId) return;

    setIsHistoryLoading(true);
    setHistoryError(null);

    try {
      const res = await client.get<DealPlaybookHistoryItem[]>(
        `/api/v1/deals/${dealId}/playbook-history`,
      );
      setHistory(res.data || []);
    } catch (err) {
      setHistoryError(
        getApiErrorMessage(
          err,
          "Не удалось загрузить историю смен playbook.",
        ),
      );
    } finally {
      setIsHistoryLoading(false);
    }
  }, [dealId]);

  const handleBack = () => {
    if (!dealId) return;
    navigate(`/projects/${dealId}`);
  };

  const handleSelectLine = (lineId: string) => {
    if (isUiLocked) return;

    clearMessages();
    setSelectedLineId(lineId);
    setSelectedVersionId(null);
    setVersionDetail(null);
    setCreateVersionError(null);
  };

  const handleSelectVersion = (versionId: string) => {
    if (isUiLocked) return;

    clearMessages();
    setSelectedVersionId(versionId);
  };

  const applyPlaybook = async () => {
    if (!dealId) {
      setErrorText("dealId не указан.");
      return;
    }

    if (!selectedVersionId) {
      setErrorText("Сначала выберите версию playbook.");
      return;
    }

    setIsApplying(true);
    clearMessages();

    try {
      await client.patch(`/api/v1/deals/${dealId}/playbook`, {
        playbook_version_id: selectedVersionId,
      });

      setDealDetail((prev) =>
        prev
          ? {
              ...prev,
              playbook_version_id: selectedVersionId,
            }
          : prev,
      );

      await loadHistory();
      setSuccessText("Playbook успешно применён к проекту.");
      setIsApplyConfirmOpen(false);
    } catch (err) {
      if (isApiErrorStatus(err, 409)) {
        setErrorText(
          getApiErrorMessage(
            err,
            "Не удалось применить playbook: возник конфликт состояния.",
          ),
        );
      } else {
        setErrorText(
          getApiErrorMessage(
            err,
            "Не удалось применить playbook к проекту. Попробуйте позже.",
          ),
        );
      }
    } finally {
      setIsApplying(false);
    }
  };

  const handleApplyPlaybook = async () => {
    if (!dealId) {
      setErrorText("dealId не указан.");
      return;
    }

    if (!selectedVersionId) {
      setErrorText("Сначала выберите версию playbook.");
      return;
    }

    if (currentVersionId && currentVersionId !== selectedVersionId) {
      setIsApplyConfirmOpen(true);
      return;
    }

    await applyPlaybook();
  };

  const handleCreateVersionForSelectedLine = async () => {
    if (!dealId) {
      setCreateVersionError("dealId не указан.");
      return;
    }

    if (!selectedLineId) return;

    if (!selectedModelConfigId) {
      setCreateVersionError(
        "Сначала выберите модель (ModelConfig) для этого playbook.",
      );
      return;
    }

    setIsCreatingVersion(true);
    setCreateVersionError(null);
    clearMessages();

    try {
      const line = lines.find((entry) => entry.id === selectedLineId);

      const payload: PlaybookCreateRequest = {
        name: line?.title || "Новая версия",
        bundles: [],
        include_ids: [],
        exclude_ids: [],
        profile: null,
        semver: "1.0.0",
        status: "active",
        playbook_id: selectedLineId,
        from_line_id: selectedLineId,
        model_config_id: selectedModelConfigId,
      };

      const res = await client.post<PlaybookCreateResponse>(
        "/api/v1/playbooks",
        payload,
      );

      const newVersion: PlaybookVersionShort = {
        id: res.data.id,
        name: res.data.name,
        semver: res.data.semver,
        status: res.data.status,
        playbook_id: res.data.playbook_id ?? selectedLineId,
      };

      setVersions((prev) => [...prev, newVersion]);
      setSelectedVersionId(newVersion.id);
      setSuccessText("Новая версия playbook успешно создана.");
    } catch (err) {
      setCreateVersionError(
        getApiErrorMessage(err, "Не удалось создать версию playbook."),
      );
    } finally {
      setIsCreatingVersion(false);
    }
  };

  const handleEditSelectedLine = () => {
    if (!dealId || !selectedLineId) return;
    navigate(`/projects/${dealId}/playbooks/admin?playbook_id=${selectedLineId}`);
  };

  useEffect(() => {
    let cancelled = false;

    async function loadDeal() {
      if (!dealId) return;

      try {
        const res = await client.get<DealDetail>(`/api/v1/deals/${dealId}`);
        if (!cancelled) {
          setDealDetail(res.data);
        }
      } catch {
        // fallback to prop deal
      }
    }

    void loadDeal();

    return () => {
      cancelled = true;
    };
  }, [dealId]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      if (!dealId) return;

      setIsLoading(true);
      setErrorText(null);

      try {
        const [linesRes, versionsRes] = await Promise.all([
          client.get<PlaybookLine[]>("/api/v1/playbooks/lines"),
          client.get<PlaybookVersionShort[]>("/api/v1/playbooks"),
        ]);

        if (cancelled) return;

        const nextLines = linesRes.data || [];
        const nextVersions = versionsRes.data || [];

        setLines(nextLines);
        setVersions(nextVersions);

        const currentPlaybookVersionId =
          effectiveDeal?.playbook_version_id ?? null;

        if (currentPlaybookVersionId) {
          const version = nextVersions.find(
            (entry) => entry.id === currentPlaybookVersionId,
          );

          if (version) {
            setSelectedVersionId(version.id);
            if (version.playbook_id) {
              setSelectedLineId(version.playbook_id);
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setErrorText(
            getApiErrorMessage(
              err,
              "Не удалось загрузить список playbook. Попробуйте позже.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, [dealId, effectiveDeal?.playbook_version_id]);

  useEffect(() => {
    let cancelled = false;

    async function loadModelConfigs() {
      setIsModelConfigsLoading(true);
      setModelConfigsError(null);

      try {
        const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
        if (cancelled) return;

        const list = res.data || [];
        setModelConfigs(list);

        if (list.length > 0) {
          setSelectedModelConfigId((prev) => prev ?? list[0].id);
        }
      } catch (err) {
        if (!cancelled) {
          setModelConfigsError(
            getApiErrorMessage(
              err,
              "Не удалось загрузить список моделей (ModelConfig). Обратитесь к администратору.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setIsModelConfigsLoading(false);
        }
      }
    }

    void loadModelConfigs();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadVersionDetail(versionId: string) {
      setVersionDetail(null);

      try {
        const res = await client.get<PlaybookVersionDetail>(
          `/api/v1/playbooks/${versionId}`,
        );
        if (!cancelled) {
          setVersionDetail(res.data);
        }
      } catch {
        if (!cancelled) {
          setVersionDetail(null);
        }
      }
    }

    if (selectedVersionId) {
      void loadVersionDetail(selectedVersionId);
    } else {
      setVersionDetail(null);
    }

    return () => {
      cancelled = true;
    };
  }, [selectedVersionId]);

  useEffect(() => {
    let cancelled = false;

    async function loadLineDetail(lineId: string) {
      setSelectedLineDetail(null);

      try {
        const res = await client.get<PlaybookLineDetail>(
          `/api/v1/playbooks/lines/${lineId}`,
        );
        if (!cancelled) {
          setSelectedLineDetail(res.data);
        }
      } catch {
        if (!cancelled) {
          setSelectedLineDetail(null);
        }
      }
    }

    if (selectedLineId) {
      void loadLineDetail(selectedLineId);
    } else {
      setSelectedLineDetail(null);
    }

    return () => {
      cancelled = true;
    };
  }, [selectedLineId]);

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  if (!canEditPlaybook) {
    return (
      <div className="min-h-screen bg-gray-50 px-4">
        <div className="flex min-h-screen items-center justify-center">
          <div className="w-full max-w-md rounded-lg border bg-white p-6 text-center shadow-sm">
            <p className="mb-4 text-sm text-gray-700">
              У вас нет прав для настройки playbook этого проекта.
            </p>
            <Button variant="primary" size="md" onClick={handleBack}>
              Вернуться к проекту
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="min-h-screen bg-gray-50 px-4 py-6">
        <div className="mx-auto max-w-6xl space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                Playbook проекта
              </h1>
              <p className="text-sm text-gray-500">
                Проект: {effectiveDeal?.name || dealId}
              </p>

              {effectiveDeal?.playbook_version_id ? (
                <p className="mt-0.5 text-xs text-gray-500">
                  Текущая версия для проекта: {effectiveDeal.playbook_version_id}
                </p>
              ) : (
                <p className="mt-0.5 text-xs text-gray-400">
                  Текущая версия playbook для проекта не выбрана.
                </p>
              )}
            </div>

            <Button variant="secondary" size="sm" onClick={handleBack}>
              ← Назад к проекту
            </Button>
          </div>

          <InlineAlert tone="error" message={errorText} />
          <InlineAlert tone="success" message={successText} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <PageSection title="Шаблоны playbook">
              {isLoading ? (
                <LoadingBlock text="Загружаем шаблоны playbook..." rows={6} />
              ) : lines.length === 0 ? (
                <EmptyState
                  title="Шаблоны не настроены"
                  description="Создайте первый шаблон playbook в административном разделе, чтобы использовать его в проектах."
                />
              ) : (
                <ul className="max-h-80 space-y-1 overflow-y-auto">
                  {lines.map((line) => (
                    <li key={line.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectLine(line.id)}
                        disabled={isUiLocked}
                        className={`w-full rounded border px-3 py-2 text-left text-xs transition disabled:cursor-not-allowed disabled:opacity-60 ${
                          selectedLineId === line.id
                            ? "border-blue-600 bg-blue-50 text-blue-700"
                            : "border-gray-200 text-gray-800 hover:bg-gray-50"
                        }`}
                      >
                        <div className="font-semibold">{line.title}</div>

                        {line.description && (
                          <div className="text-[11px] text-gray-500">
                            {line.description}
                          </div>
                        )}

                        <div className="mt-1 text-[11px] text-gray-400">
                          {line.deal_type && `Тип: ${line.deal_type} · `}
                          {line.jurisdiction &&
                            `Юрисдикция: ${line.jurisdiction} · `}
                          {line.language && `Язык: ${line.language}`}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </PageSection>

            <PageSection title="Версии playbook">
              <InlineAlert tone="error" message={createVersionError} />

              {!selectedLineId ? (
                <EmptyState
                  title="Шаблон не выбран"
                  description="Сначала выберите шаблон playbook в левой колонке."
                />
              ) : visibleVersions.length === 0 ? (
                <div className="space-y-3">
                  <EmptyState
                    title="Версий пока нет"
                    description="Для выбранного шаблона ещё не создано ни одной версии. Выберите модель и создайте первую версию."
                  />

                  <div>
                    <label className="mb-1 block text-[11px] font-medium text-gray-700">
                      Модель для этого playbook (ModelConfig)
                    </label>

                    {isModelConfigsLoading ? (
                      <LoadingBlock text="Загружаем список моделей..." rows={3} />
                    ) : modelConfigsError ? (
                      <InlineAlert tone="error" message={modelConfigsError} />
                    ) : modelConfigs.length === 0 ? (
                      <EmptyState
                        title="Модели недоступны"
                        description="Нет доступных моделей. Обратитесь к администратору."
                      />
                    ) : (
                      <select
                        className={selectClassName}
                        value={selectedModelConfigId ?? ""}
                        onChange={(e) =>
                          setSelectedModelConfigId(e.target.value || null)
                        }
                        disabled={isUiLocked}
                      >
                        {modelConfigs.map((modelConfig) => (
                          <option key={modelConfig.id} value={modelConfig.id}>
                            {modelConfig.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  <div className="flex justify-start">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleCreateVersionForSelectedLine}
                      disabled={isCreatingVersion || !selectedModelConfigId}
                      isLoading={isCreatingVersion}
                    >
                      Создать версию из шаблона
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  <ul className="max-h-80 space-y-1 overflow-y-auto">
                    {visibleVersions.map((version) => (
                      <li key={version.id}>
                        <button
                          type="button"
                          onClick={() => handleSelectVersion(version.id)}
                          disabled={isUiLocked}
                          className={`w-full rounded border px-3 py-2 text-left text-xs transition disabled:cursor-not-allowed disabled:opacity-60 ${
                            selectedVersionId === version.id
                              ? "border-blue-600 bg-blue-50 text-blue-700"
                              : "border-gray-200 text-gray-800 hover:bg-gray-50"
                          }`}
                        >
                          <div className="font-semibold">
                            {version.name}{" "}
                            <span className="text-[11px] text-gray-500">
                              ({version.semver})
                            </span>
                          </div>
                          <div className="mt-1 text-[11px] text-gray-400">
                            Статус: {version.status}
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>

                  <div className="mt-3 flex items-center justify-end border-t pt-3">
                    <Button
                      variant="primary"
                      size="md"
                      onClick={handleApplyPlaybook}
                      disabled={!selectedVersionId || isApplying || isSameAsCurrent}
                      isLoading={isApplying}
                    >
                      {isSameAsCurrent ? "Уже применено" : "Применить к проекту"}
                    </Button>
                  </div>
                </>
              )}
            </PageSection>

            <PageSection
              title="Состав playbook"
              rightSlot={
                selectedLineId ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleEditSelectedLine}
                    disabled={isUiLocked}
                  >
                    Редактировать шаблон
                  </Button>
                ) : null
              }
            >
              {selectedLine && (
                <p className="mb-2 text-[11px] text-gray-500">
                  Шаблон: {selectedLine.title}
                  {selectedLine.deal_type && ` · Тип: ${selectedLine.deal_type}`}
                  {selectedLine.jurisdiction &&
                    ` · Юрисдикция: ${selectedLine.jurisdiction}`}
                  {selectedLine.language && ` · Язык: ${selectedLine.language}`}
                </p>
              )}

              {!selectedLineId ? (
                <EmptyState
                  title="Ничего не выбрано"
                  description="Выберите шаблон playbook слева, затем создайте или выберите версию в средней колонке, чтобы увидеть состав."
                />
              ) : selectedVersionId && versionDetail ? (
                <div className="max-h-80 space-y-2 overflow-y-auto text-xs text-gray-700">
                  <div>
                    <div className="font-semibold">Общая информация</div>
                    <div className="text-gray-600">
                      Версия: {versionDetail.name} ({versionDetail.semver})
                    </div>
                    <div className="text-gray-600">
                      Статус: {versionDetail.status}
                    </div>
                  </div>

                  <div>
                    <div className="mt-2 font-semibold">Секции / профили</div>
                    {versionDetail.section_markers ? (
                      <pre className="overflow-x-auto rounded border bg-gray-50 p-2">
                        {JSON.stringify(versionDetail.section_markers, null, 2)}
                      </pre>
                    ) : (
                      <div className="text-gray-500">
                        Section markers не заданы.
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="mt-2 font-semibold">DD-запросы</div>
                    {versionDetail.dd_request_templates ? (
                      <pre className="overflow-x-auto rounded border bg-gray-50 p-2">
                        {JSON.stringify(
                          versionDetail.dd_request_templates,
                          null,
                          2,
                        )}
                      </pre>
                    ) : (
                      <div className="text-gray-500">
                        DD request templates не заданы.
                      </div>
                    )}
                  </div>
                </div>
              ) : selectedLineDetail ? (
                <div className="max-h-80 space-y-2 overflow-y-auto text-xs text-gray-700">
                  <div>
                    <div className="font-semibold">Общая информация</div>
                    <div className="text-gray-600">
                      Имя: {selectedLineDetail.title}
                    </div>
                    <div className="text-gray-600">
                      Тип сделки: {selectedLineDetail.deal_type || "не задан"}
                    </div>
                    <div className="text-gray-600">
                      Юрисдикция:{" "}
                      {selectedLineDetail.jurisdiction || "не задана"}
                    </div>
                    <div className="text-gray-600">
                      Язык: {selectedLineDetail.language || "не задан"}
                    </div>

                    {selectedLineDetail.description && (
                      <div className="mt-1 text-gray-600">
                        Описание: {selectedLineDetail.description}
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="mt-2 font-semibold">
                      Состав шаблона (темы / проверки)
                    </div>

                    {selectedLineDetail.items &&
                    selectedLineDetail.items.length > 0 ? (
                      <ul className="mt-1 space-y-1">
                        {selectedLineDetail.items.map((item, index) => (
                          <li
                            key={index}
                            className="rounded border bg-gray-50 px-2 py-1"
                          >
                            <div className="text-gray-700">
                              Тип: {item.kind}
                            </div>
                            {item.topic_code && (
                              <div className="text-gray-600">
                                Topic: {item.topic_code}
                              </div>
                            )}
                            {item.check_code && (
                              <div className="text-gray-600">
                                Check: {item.check_code}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="text-gray-500">
                        В шаблоне пока нет элементов.
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <LoadingBlock text="Загружаем состав playbook..." rows={4} />
              )}

              <div className="mt-4 border-t pt-3">
                <h3 className="mb-2 text-sm font-semibold text-gray-800">
                  История смен playbook
                </h3>

                {isHistoryLoading ? (
                  <LoadingBlock text="Загружаем историю..." rows={3} />
                ) : historyError ? (
                  <InlineAlert tone="error" message={historyError} />
                ) : history.length === 0 ? (
                  <EmptyState
                    title="История пока пустая"
                    description="Пока нет записей об изменении playbook для этой сделки."
                  />
                ) : (
                  <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
                    {history.map((item, index) => (
                      <li
                        key={index}
                        className="rounded border border-gray-200 bg-gray-50 px-2 py-1"
                      >
                        <div className="text-gray-700">
                          {new Date(item.created_at).toLocaleString()} —{" "}
                          {item.actor}{" "}
                          {item.actor_role && (
                            <span className="text-gray-500">
                              ({item.actor_role})
                            </span>
                          )}
                        </div>

                        <div className="text-gray-600">
                          {item.old_playbook_version_id
                            ? `Было: ${item.old_playbook_version_id}`
                            : "Было: не задано"}
                        </div>

                        <div className="text-gray-600">
                          {item.new_playbook_version_id
                            ? `Стало: ${item.new_playbook_version_id}`
                            : "Стало: не задано"}
                        </div>

                        {(item.playbook_name || item.semver) && (
                          <div className="text-gray-500">
                            {item.playbook_name && `${item.playbook_name} `}
                            {item.semver && `(${item.semver})`}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </PageSection>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={isApplyConfirmOpen}
        title="Заменить текущий playbook?"
        description="У этого проекта уже есть выбранная версия playbook. Текущая версия будет заменена на новую. Продолжить?"
        confirmLabel="Да, заменить"
        cancelLabel="Отмена"
        isConfirming={isApplying}
        onConfirm={applyPlaybook}
        onCancel={() => {
          if (!isApplying) {
            setIsApplyConfirmOpen(false);
          }
        }}
      />
    </>
  );
};

export default DealPlaybookSelectorPage;


