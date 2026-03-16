// =============================================================
// src/pages/DealPlaybookSelectorPage.tsx
// Выбор / создание playbook для конкретной сделки.
// Работает поверх новых эндпоинтов /playbooks.
// =============================================================

import React, { useEffect, useState, useMemo, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client from "../api/client";
import { useDealPermissions } from "../hooks/usePermissions";
import type {
  Deal,
  DealDetail,
  PlaybookLine,
  PlaybookLineDetail,
  PlaybookVersionShort,
  PlaybookVersionDetail,
  PlaybookCreateRequest,
  PlaybookCreateResponse,
  ApiError,
  DealPlaybookHistoryItem,
  // новый тип: одна конфигурация модели
  // (должен быть описан в ../types)
  // interface ModelConfig { id: string; name: string; description?: string | null; }
  ModelConfig,
} from "../types";

interface DealPlaybookSelectorPageProps {
  /** Если сделка уже загружена выше по иерархии — можно пробросить её сюда. */
  deal?: Deal;
}

const DealPlaybookSelectorPage: React.FC<DealPlaybookSelectorPageProps> = ({
  deal,
}) => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

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
  const [createVersionError, setCreateVersionError] = useState<string | null>(
    null,
  );

  const [history, setHistory] = useState<DealPlaybookHistoryItem[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // ---- НОВОЕ: модели (ModelConfig) ----
  /** Список доступных конфигураций моделей, с которыми можно запускать плейбуки. */
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  /** Выбранная конфигурация модели для создания новой версии плейбука. */
  const [selectedModelConfigId, setSelectedModelConfigId] = useState<string | null>(null);
  /** Ошибки загрузки списка моделей. */
  const [modelConfigsError, setModelConfigsError] = useState<string | null>(null);
  const [isModelConfigsLoading, setIsModelConfigsLoading] = useState(false);
  // -------------------------------------

  if (!dealId) {
    return (
      <div className="p-6 text-center text-red-600">
        dealId не указан в маршруте.
      </div>
    );
  }

  const { canViewOverview } = useDealPermissions(dealId);
  const canEditPlaybook = canViewOverview;

  if (!canEditPlaybook) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md bg-white rounded-lg border shadow p-6 text-center">
          <p className="text-sm text-gray-700 mb-4">
            У вас нет прав для настройки playbook этого проекта.
          </p>
          <button
            type="button"
            onClick={() => navigate(`/projects/${dealId}`)}
            className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
          >
            Вернуться к проекту
          </button>
        </div>
      </div>
    );
  }

  const handleBack = () => {
    navigate(`/projects/${dealId}`);
  };

  const effectiveDeal = dealDetail ?? deal ?? null;

  // Загрузка истории смен playbook-версий для сделки
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
      const apiErr = err as ApiError;
      setHistoryError(
        apiErr.detail || "Не удалось загрузить историю смен playbook.",
      );
    } finally {
      setIsHistoryLoading(false);
    }
  }, [dealId]);

  // Загружаем актуальное состояние сделки (чтобы иметь свежий playbook_version_id)
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
        // Если не смогли загрузить — используем deal из пропсов, если он есть
      }
    }

    loadDeal();
    return () => {
      cancelled = true;
    };
  }, [dealId]);

  // История смен playbook-версий для сделки — первичная загрузка
  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Для быстрого доступа к PlaybookLine по id
  const lineById = useMemo(() => {
    const map = new Map<string, PlaybookLine>();
    for (const l of lines) {
      map.set(l.id, l);
    }
    return map;
  }, [lines]);

  const selectedLine = selectedLineId ? lineById.get(selectedLineId) : null;

  // Загрузка списка логических плейбуков и версий
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setIsLoading(true);
      setErrorText(null);
      try {
        const [linesRes, versionsRes] = await Promise.all([
          client.get<PlaybookLine[]>("/api/v1/playbooks/lines"),
          client.get<PlaybookVersionShort[]>("/api/v1/playbooks"),
        ]);

        if (cancelled) return;

        setLines(linesRes.data || []);
        setVersions(versionsRes.data || []);

        const currentPlaybookVersionId =
          effectiveDeal?.playbook_version_id ?? null;

        // Если для сделки уже есть playbook_version_id — восстанавливаем выбор
        if (currentPlaybookVersionId) {
          const version = (versionsRes.data || []).find(
            (v) => v.id === currentPlaybookVersionId,
          );
          if (version) {
            setSelectedVersionId(version.id);
            if (version.playbook_id) {
              setSelectedLineId(version.playbook_id);
            }
          }
        }
      } catch (err) {
        const apiErr = err as ApiError;
        if (!cancelled) {
          setErrorText(
            apiErr.detail ||
              "Не удалось загрузить список playbook. Попробуйте позже.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadData();
    return () => {
      cancelled = true;
    };
  }, [dealId, effectiveDeal?.playbook_version_id]);

  // НОВОЕ: загрузка списка ModelConfig
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
        // Если ещё ничего не выбрано, а список не пуст — выбираем первую модель по умолчанию
        if (list.length > 0) {
          setSelectedModelConfigId((prev) => prev ?? list[0].id);
        }
      } catch (err) {
        const apiErr = err as ApiError;
        if (!cancelled) {
          setModelConfigsError(
            apiErr.detail ||
              "Не удалось загрузить список моделей (ModelConfig). Обратитесь к администратору.",
          );
        }
      } finally {
        if (!cancelled) {
          setIsModelConfigsLoading(false);
        }
      }
    }

    loadModelConfigs();
    return () => {
      cancelled = true;
    };
  }, []);

  // Когда выбрана версия — подтягиваем её детали (состав)
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
      loadVersionDetail(selectedVersionId);
    } else {
      setVersionDetail(null);
    }
    return () => {
      cancelled = true;
    };
  }, [selectedVersionId]);

  // Когда выбрана линия — подтягиваем её детали (состав шаблона)
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
      loadLineDetail(selectedLineId);
    } else {
      setSelectedLineDetail(null);
    }

    return () => {
      cancelled = true;
    };
  }, [selectedLineId]);

  const handleSelectLine = (lineId: string) => {
    setSelectedLineId(lineId);
    setSelectedVersionId(null);
    setVersionDetail(null);
    setCreateVersionError(null);
  };

  const handleSelectVersion = (versionId: string) => {
    setSelectedVersionId(versionId);
  };

  const handleApplyPlaybook = async () => {
    if (!selectedVersionId) {
      setErrorText("Сначала выберите версию playbook.");
      return;
    }

    const currentId = effectiveDeal?.playbook_version_id;
    if (currentId && currentId !== selectedVersionId) {
      const ok = window.confirm(
        "У этого проекта уже есть выбранная версия playbook. " +
          "Старая версия будет заменена на новую. Продолжить?",
      );
      if (!ok) {
        return;
      }
    }

    setIsApplying(true);
    setErrorText(null);
    try {
      await client.patch(`/api/v1/deals/${dealId}/playbook`, {
        playbook_version_id: selectedVersionId,
      });

      // Обновляем историю сразу после успешной смены playbook
      await loadHistory();

      // Можно остаться на странице; сейчас оставляем поведение как есть
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(
        apiErr.detail ||
          "Не удалось применить playbook к проекту. Попробуйте позже.",
      );
    } finally {
      setIsApplying(false);
    }
  };

  // Фильтруем версии по выбранной линии (если линия выбрана)
  const visibleVersions = selectedLineId
    ? versions.filter(
        (v) =>
          v.playbook_id === selectedLineId &&
          (v.status === "default" || v.status === "active"),
      )
    : [];

  // Создание версии из выбранного шаблона
  const handleCreateVersionForSelectedLine = async () => {
    if (!selectedLineId) return;

    // Без выбранной модели запрещаем создавать версию и показываем понятную ошибку
    if (!selectedModelConfigId) {
      setCreateVersionError("Сначала выберите модель (ModelConfig) для этого playbook.");
      return;
    }

    setIsCreatingVersion(true);
    setCreateVersionError(null);
    try {
      const line = lines.find((l) => l.id === selectedLineId);
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
        // КЛЮЧЕВОЕ: привязка к выбранной модели
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
    } catch (err) {
      const apiErr = err as ApiError;
      setCreateVersionError(
        apiErr.detail || "Не удалось создать версию playbook.",
      );
    } finally {
      setIsCreatingVersion(false);
    }
  };

  const handleEditSelectedLine = () => {
    if (!selectedLineId) return;
    navigate(
      `/projects/${dealId}/playbooks/admin?playbook_id=${selectedLineId}`,
    );
  };

  const currentVersionId = effectiveDeal?.playbook_version_id ?? null;
  const isSameAsCurrent =
    currentVersionId && selectedVersionId === currentVersionId;

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* Заголовок */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Playbook проекта
            </h1>
            <p className="text-sm text-gray-500">
              Проект: {effectiveDeal?.name || dealId}
            </p>
            {effectiveDeal?.playbook_version_id ? (
              <p className="text-xs text-gray-500 mt-0.5">
                Текущая версия для проекта: {effectiveDeal.playbook_version_id}
              </p>
            ) : (
              <p className="text-xs text-gray-400 mt-0.5">
                Текущая версия playbook для проекта не выбрана.
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleBack}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            ← Назад к проекту
          </button>
        </div>

        {errorText && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {errorText}
          </div>
        )}

        {isLoading ? (
          <p className="text-sm text-gray-500">Загружаем playbook…</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Колонка 1: список логических плейбуков (шаблонов) */}
            <div className="bg-white rounded-lg border p-4 space-y-2">
              <h2 className="text-sm font-semibold text-gray-800 mb-2">
                Шаблоны playbook
              </h2>
              {lines.length === 0 ? (
                <p className="text-xs text-gray-500">
                  Шаблоны playbook пока не настроены.
                </p>
              ) : (
                <ul className="space-y-1 max-h-80 overflow-y-auto">
                  {lines.map((line) => (
                    <li key={line.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectLine(line.id)}
                        className={`w-full text-left px-3 py-2 rounded text-xs border ${
                          selectedLineId === line.id
                            ? "border-blue-600 bg-blue-50 text-blue-700"
                            : "border-gray-200 hover:bg-gray-50 text-gray-800"
                        }`}
                      >
                        <div className="font-semibold">{line.title}</div>
                        {line.description && (
                          <div className="text-[11px] text-gray-500">
                            {line.description}
                          </div>
                        )}
                        <div className="text-[11px] text-gray-400 mt-1">
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
            </div>

            {/* Колонка 2: версии выбранного playbook */}
            <div className="bg-white rounded-lg border p-4 space-y-2">
              <h2 className="text-sm font-semibold text-gray-800 mb-2">
                Версии playbook
              </h2>

              {createVersionError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-[11px] rounded p-2 mb-1">
                  {createVersionError}
                </div>
              )}

              {!selectedLineId ? (
                <p className="text-xs text-gray-500">
                  Сначала выберите шаблон playbook слева.
                </p>
              ) : visibleVersions.length === 0 ? (
                <>
                  <p className="text-xs text-gray-500 mb-2">
                    Для выбранного шаблона пока нет версий. Создайте первую
                    версию и выберите, под какой моделью её запускать.
                  </p>

                  {/* Выбор ModelConfig для новой версии */}
                  <div className="mb-2">
                    <label className="block text-[11px] font-medium text-gray-700 mb-1">
                      Модель для этого playbook (ModelConfig)
                    </label>

                    {isModelConfigsLoading ? (
                      <p className="text-[11px] text-gray-500">
                        Загружаем список моделей…
                      </p>
                    ) : modelConfigsError ? (
                      <p className="text-[11px] text-red-600">
                        {modelConfigsError}
                      </p>
                    ) : modelConfigs.length === 0 ? (
                      <p className="text-[11px] text-gray-500">
                        Нет доступных моделей. Обратитесь к администратору.
                      </p>
                    ) : (
                      <select
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                        value={selectedModelConfigId ?? ""}
                        onChange={(e) =>
                          setSelectedModelConfigId(
                            e.target.value || null,
                          )
                        }
                      >
                        {modelConfigs.map((mc) => (
                          <option key={mc.id} value={mc.id}>
                            {mc.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={handleCreateVersionForSelectedLine}
                    disabled={isCreatingVersion || !selectedModelConfigId}
                    className="text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-60"
                  >
                    {isCreatingVersion
                      ? "Создаём версию..."
                      : "Создать версию из шаблона"}
                  </button>
                </>
              ) : (
                <ul className="space-y-1 max-h-80 overflow-y-auto">
                  {visibleVersions.map((v) => (
                    <li key={v.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectVersion(v.id)}
                        className={`w-full text-left px-3 py-2 rounded text-xs border ${
                          selectedVersionId === v.id
                            ? "border-blue-600 bg-blue-50 text-blue-700"
                            : "border-gray-200 hover:bg-gray-50 text-gray-800"
                        }`}
                      >
                        <div className="font-semibold">
                          {v.name}{" "}
                          <span className="text-[11px] text-gray-500">
                            ({v.semver})
                          </span>
                        </div>
                        <div className="text-[11px] text-gray-400 mt-1">
                          Статус: {v.status}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="pt-3 border-t flex items-center justify-end gap-3 mt-3">
                <button
                  type="button"
                  onClick={handleApplyPlaybook}
                  disabled={
                    !selectedVersionId || isApplying || !!isSameAsCurrent
                  }
                  className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                >
                  {isApplying
                    ? "Применяем..."
                    : isSameAsCurrent
                    ? "Уже применено"
                    : "Применить к проекту"}
                </button>
              </div>
            </div>

            {/* Колонка 3: состав выбранного шаблона / версии + история */}
            <div className="bg-white rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-sm font-semibold text-gray-800">
                  Состав playbook
                </h2>
                {selectedLineId && (
                  <button
                    type="button"
                    onClick={handleEditSelectedLine}
                    className="px-2 py-1 text-[11px] rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  >
                    Редактировать шаблон
                  </button>
                )}
              </div>

              {selectedLine && (
                <p className="text-[11px] text-gray-500 mb-1">
                  Шаблон: {selectedLine.title}
                  {selectedLine.deal_type && ` · Тип: ${selectedLine.deal_type}`}
                  {selectedLine.jurisdiction &&
                    ` · Юрисдикция: ${selectedLine.jurisdiction}`}
                  {selectedLine.language && ` · Язык: ${selectedLine.language}`}
                </p>
              )}

              {!selectedLineId ? (
                <p className="text-xs text-gray-500">
                  Выберите шаблон playbook слева. Затем создайте или выберите
                  версию в средней колонке, либо измените состав шаблона.
                </p>
              ) : selectedVersionId && versionDetail ? (
                <div className="text-xs text-gray-700 space-y-2 max-h-80 overflow-y-auto">
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
                    <div className="font-semibold mt-2">Секции / профили</div>
                    {versionDetail.section_markers ? (
                      <pre className="bg-gray-50 border rounded p-2 overflow-x-auto">
                        {JSON.stringify(versionDetail.section_markers, null, 2)}
                      </pre>
                    ) : (
                      <div className="text-gray-500">
                        Section markers не заданы.
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="font-semibold mt-2">DD-запросы</div>
                    {versionDetail.dd_request_templates ? (
                      <pre className="bg-gray-50 border rounded p-2 overflow-x-auto">
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
                <div className="text-xs text-gray-700 space-y-2 max-h-80 overflow-y-auto">
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
                      <div className="text-gray-600 mt-1">
                        Описание: {selectedLineDetail.description}
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="font-semibold mt-2">
                      Состав шаблона (темы / проверки)
                    </div>
                    {selectedLineDetail.items &&
                    selectedLineDetail.items.length > 0 ? (
                      <ul className="mt-1 space-y-1">
                        {selectedLineDetail.items.map((item, idx) => (
                          <li
                            key={idx}
                            className="border rounded px-2 py-1 bg-gray-50"
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
                <p className="text-xs text-gray-500">
                  Загружаем состав шаблона…
                </p>
              )}

              {/* История смен playbook-версий */}
              <div className="mt-4 pt-3 border-t">
                <h3 className="text-sm font-semibold text-gray-800 mb-2">
                  История смен playbook
                </h3>

                {isHistoryLoading ? (
                  <p className="text-xs text-gray-500">Загружаем историю…</p>
                ) : historyError ? (
                  <p className="text-xs text-red-600">{historyError}</p>
                ) : history.length === 0 ? (
                  <p className="text-xs text-gray-500">
                    Пока нет записей об изменении playbook для этой сделки.
                  </p>
                ) : (
                  <ul className="space-y-1 max-h-48 overflow-y-auto text-xs">
                    {history.map((item, idx) => (
                      <li
                        key={idx}
                        className="border border-gray-200 rounded px-2 py-1 bg-gray-50"
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
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DealPlaybookSelectorPage;
