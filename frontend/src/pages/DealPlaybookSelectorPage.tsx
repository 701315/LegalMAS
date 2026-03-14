// =============================================================
// src/pages/DealPlaybookSelectorPage.tsx
// Выбор / создание playbook для конкретной сделки.
// Работает поверх новых эндпоинтов /playbooks.
// =============================================================

import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import client from "../api/client";
import { useDealPermissions } from "../hooks/usePermissions";
import type {
  Deal,
  PlaybookLine,
  PlaybookVersionShort,
  PlaybookVersionDetail,
  ApiError,
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

  const [lines, setLines] = useState<PlaybookLine[]>([]);
  const [versions, setVersions] = useState<PlaybookVersionShort[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    null,
  );
  const [versionDetail, setVersionDetail] =
    useState<PlaybookVersionDetail | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isApplying, setIsApplying] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

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

        // Если для сделки уже есть playbook_version_id — выделим его
        if (deal?.playbook_version_id) {
          setSelectedVersionId(deal.playbook_version_id);
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
  }, [dealId, deal?.playbook_version_id]);

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
          // Детали не обязательны для выбора, просто не показываем состав
          setVersionDetail(null);
        }
      }
    }

    if (selectedVersionId) {
      loadVersionDetail(selectedVersionId);
    }
    return () => {
      cancelled = true;
    };
  }, [selectedVersionId]);

  const handleSelectLine = (lineId: string) => {
    setSelectedLineId(lineId);
    // Сбрасываем выбранную версию, чтобы пользователь явно выбрал одну из списка
    setSelectedVersionId(null);
    setVersionDetail(null);
  };

  const handleSelectVersion = (versionId: string) => {
    setSelectedVersionId(versionId);
  };

  const handleApplyPlaybook = async () => {
    if (!selectedVersionId) {
      setErrorText("Сначала выберите версию playbook.");
      return;
    }

    setIsApplying(true);
    setErrorText(null);
    try {
      // PATCH /deals/{deal_id}/playbook — предполагаемый эндпоинт.
      // Если он уже есть и название другое — подправим URL/метод.
      await client.patch(`/api/v1/deals/${dealId}/playbook`, {
        playbook_version_id: selectedVersionId,
      });

      navigate(`/projects/${dealId}`);
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
    ? versions.filter((v) => v.playbook_id === selectedLineId)
    : versions;

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
              Проект: {deal?.name || dealId}
            </p>
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
                          {line.jurisdiction && `Юрисдикция: ${line.jurisdiction} · `}
                          {line.language && `Язык: ${line.language}`}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Колонка 2: версии выбранного playbook (или все, если линия не выбрана) */}
            <div className="bg-white rounded-lg border p-4 space-y-2">
              <h2 className="text-sm font-semibold text-gray-800 mb-2">
                Версии playbook
              </h2>
              {visibleVersions.length === 0 ? (
                <p className="text-xs text-gray-500">
                  Для выбранного шаблона пока нет версий.
                </p>
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
                          {v.name} <span className="text-[11px] text-gray-500">({v.semver})</span>
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
                  disabled={!selectedVersionId || isApplying}
                  className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                >
                  {isApplying ? "Применяем..." : "Применить к проекту"}
                </button>
              </div>
            </div>

            {/* Колонка 3: состав выбранной версии (упрощённо) */}
            <div className="bg-white rounded-lg border p-4 space-y-2">
              <h2 className="text-sm font-semibold text-gray-800 mb-2">
                Состав playbook
              </h2>
              {!selectedVersionId ? (
                <p className="text-xs text-gray-500">
                  Выберите версию playbook, чтобы посмотреть её состав.
                </p>
              ) : !versionDetail ? (
                <p className="text-xs text-gray-500">
                  Загружаем состав playbook…
                </p>
              ) : (
                <div className="text-xs text-gray-700 space-y-2 max-h-80 overflow-y-auto">
                  <div>
                    <div className="font-semibold">Общая информация</div>
                    <div className="text-gray-600">
                      Имя: {versionDetail.name} ({versionDetail.semver})
                    </div>
                    <div className="text-gray-600">Статус: {versionDetail.status}</div>
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
                        {JSON.stringify(versionDetail.dd_request_templates, null, 2)}
                      </pre>
                    ) : (
                      <div className="text-gray-500">
                        DD request templates не заданы.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DealPlaybookSelectorPage;
