// src/pages/AdminPlaybookLinesPage.tsx

import React, { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import type {
  PlaybookLineShort,
  PlaybookLineDetail,
  PlaybookLineItemPayload,
  PlaybookTopicInfo,
  ApiError,
} from "../types";

import { useNavigate, useSearchParams } from "react-router-dom";


const AdminPlaybookLinesPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const playbookIdFromQuery = searchParams.get("playbook_id");

  const [lines, setLines] = useState<PlaybookLineShort[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [currentLine, setCurrentLine] = useState<PlaybookLineDetail | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  // Форма линии
  const [title, setTitle] = useState("");
  const [dealType, setDealType] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [language, setLanguage] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<PlaybookLineItemPayload[]>([]);

  // Каталог тем и проверок
  const [topics, setTopics] = useState<PlaybookTopicInfo[]>([]);
  const [isCatalogLoading, setIsCatalogLoading] = useState(false);

  const topicByCode = useMemo(() => {
    const map = new Map<string, PlaybookTopicInfo>();
    for (const t of topics) {
      map.set(t.topic_code, t);
    }
    return map;
  }, [topics]);

  const loadLines = async () => {
    setIsLoading(true);
    setErrorText(null);
    try {
      const res = await client.get<PlaybookLineShort[]>("/api/v1/playbooks/lines");
      setLines(res.data || []);
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(apiErr.detail || "Не удалось загрузить шаблоны playbook.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadLineDetail = async (lineId: string) => {
    setErrorText(null);
    try {
      const res = await client.get<PlaybookLineDetail>(
        `/api/v1/playbooks/lines/${lineId}`,
      );
      setCurrentLine(res.data);
      setTitle(res.data.title || "");
      setDescription(res.data.description || "");
      setDealType(res.data.deal_type || "");
      setJurisdiction(res.data.jurisdiction || "");
      setLanguage(res.data.language || "");
      setItems(res.data.items || []);
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(apiErr.detail || "Не удалось загрузить шаблон playbook.");
    }
  };

  const loadCatalog = async () => {
    setIsCatalogLoading(true);
    try {
      const res = await client.get<PlaybookTopicInfo[]>(
        "/api/v1/playbooks/catalog",
      );
      setTopics(res.data || []);
    } catch (err) {
      const apiErr = err as ApiError;
      // каталог — вспомогательная штука, не блокируем весь UI
      console.error("Failed to load playbook catalog", apiErr.detail);
    } finally {
      setIsCatalogLoading(false);
    }
  };

  useEffect(() => {
    loadLines();
    loadCatalog();
  }, []);

  
  useEffect(() => {
    if (!playbookIdFromQuery || lines.length === 0) return;
    const line = lines.find((l) => l.id === playbookIdFromQuery);
    if (line) {
      setSelectedLineId(line.id);
      loadLineDetail(line.id);
    }
  }, [playbookIdFromQuery, lines]);


  const handleSelectLine = (line: PlaybookLineShort) => {
    setSelectedLineId(line.id);
    loadLineDetail(line.id);
  };

  const handleAddItem = () => {
    setItems((prev) => [
      ...prev,
      {
        kind: "topic",
        topic_code: topics[0]?.topic_code || "",
        check_code: "",
        order_index: prev.length,
      },
    ]);
  };

  const handleItemChange = (
    index: number,
    field: keyof PlaybookLineItemPayload,
    value: string,
  ) => {
    setItems((prev) =>
      prev.map((it, i) =>
        i === index
          ? {
              ...it,
              [field]: value,
            }
          : it,
      ),
    );
  };

  const handleSave = async () => {
    setIsSaving(true);
    setErrorText(null);
    try {
      const payload = {
        title,
        description: description || null,
        deal_type: dealType || null,
        jurisdiction: jurisdiction || null,
        language: language || null,
        items: items.map((it, idx) => ({
          ...it,
          order_index: idx,
        })),
      };

      let res;
      if (currentLine) {
        res = await client.put<PlaybookLineDetail>(
          `/api/v1/playbooks/lines/${currentLine.id}`,
          payload,
        );
      } else {
        res = await client.post<PlaybookLineDetail>(
          "/api/v1/playbooks/lines",
          payload,
        );
      }

      setCurrentLine(res.data);
      setSelectedLineId(res.data.id);
      await loadLines();
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(apiErr.detail || "Не удалось сохранить шаблон playbook.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateNew = () => {
    setSelectedLineId(null);
    setCurrentLine(null);
    setTitle("");
    setDescription("");
    setDealType("");
    setJurisdiction("");
    setLanguage("");
    setItems([]);
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-6xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Конструктор шаблонов Playbook
            </h1>
            <p className="text-sm text-gray-500">
              Настройка логических линий (шаблонов) и их состава.
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            ← На главную
          </button>
        </div>

        {errorText && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {errorText}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Список линий */}
          <div className="bg-white rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-gray-800">
                Шаблоны playbook
              </h2>
              <button
                type="button"
                onClick={handleCreateNew}
                className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
              >
                + Новый
              </button>
            </div>
            {isLoading ? (
              <p className="text-xs text-gray-500">Загружаем шаблоны…</p>
            ) : lines.length === 0 ? (
              <p className="text-xs text-gray-500">
                Шаблоны playbook пока не настроены.
              </p>
            ) : (
              <ul className="space-y-1 max-h-80 overflow-y-auto">
                {lines.map((line) => (
                  <li key={line.id}>
                    <button
                      type="button"
                      onClick={() => handleSelectLine(line)}
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

          {/* Форма линии */}
          <div className="bg-white rounded-lg border p-4 space-y-3 lg:col-span-2">
            <h2 className="text-sm font-semibold text-gray-800 mb-2">
              {currentLine ? "Редактирование шаблона" : "Новый шаблон"}
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block text-gray-600 mb-1">Название</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full border rounded px-2 py-1 text-xs"
                />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Тип сделки</label>
                <input
                  type="text"
                  value={dealType}
                  onChange={(e) => setDealType(e.target.value)}
                  className="w-full border rounded px-2 py-1 text-xs"
                  placeholder="real_estate, mna, nda..."
                />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Юрисдикция</label>
                <input
                  type="text"
                  value={jurisdiction}
                  onChange={(e) => setJurisdiction(e.target.value)}
                  className="w-full border rounded px-2 py-1 text-xs"
                  placeholder="RU, EN, DE..."
                />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Язык</label>
                <input
                  type="text"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full border rounded px-2 py-1 text-xs"
                  placeholder="ru, en..."
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-gray-600 mb-1">Описание</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full border rounded px-2 py-1 text-xs"
                  rows={2}
                />
              </div>
            </div>

            <div className="mt-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-gray-800">
                  Состав шаблона (темы / проверки)
                </h3>
                <button
                  type="button"
                  onClick={handleAddItem}
                  className="text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700"
                  disabled={isCatalogLoading || topics.length === 0}
                >
                  + Элемент
                </button>
              </div>
              {topics.length === 0 ? (
                <p className="text-xs text-gray-500">
                  Каталог тем и проверок не загружен или пуст. Проверьте
                  /playbooks/catalog.
                </p>
              ) : items.length === 0 ? (
                <p className="text-xs text-gray-500">
                  Пока нет элементов. Добавьте тему или проверку.
                </p>
              ) : (
                <table className="w-full text-[11px] border">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="border px-2 py-1 text-left">Тип</th>
                      <th className="border px-2 py-1 text-left">Topic</th>
                      <th className="border px-2 py-1 text-left">Check</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it, index) => {
                      const topic = it.topic_code
                        ? topicByCode.get(it.topic_code)
                        : undefined;
                      const checks = topic?.checks || [];
                      return (
                        <tr key={index}>
                          <td className="border px-2 py-1">
                            <select
                              value={it.kind}
                              onChange={(e) =>
                                handleItemChange(
                                  index,
                                  "kind",
                                  e.target.value as "topic" | "check",
                                )
                              }
                              className="border rounded px-1 py-0.5 text-[11px]"
                            >
                              <option value="topic">topic</option>
                              <option value="check">check</option>
                            </select>
                          </td>
                          <td className="border px-2 py-1">
                            <select
                              value={it.topic_code || ""}
                              onChange={(e) => {
                                const newTopicCode = e.target.value;
                                handleItemChange(index, "topic_code", newTopicCode);
                                // если сменили тему, сбрасываем check_code
                                handleItemChange(index, "check_code", "");
                              }}
                              className="w-full border rounded px-1 py-0.5 text-[11px]"
                            >
                              <option value="">— не выбрано —</option>
                              {topics.map((t) => (
                                <option key={t.topic_code} value={t.topic_code}>
                                  {t.topic_code} — {t.topic_name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="border px-2 py-1">
                            {it.kind === "topic" ? (
                              <span className="text-gray-400">
                                Для типа topic check не используется
                              </span>
                            ) : checks.length === 0 ? (
                              <span className="text-gray-400">
                                Нет проверок для выбранной темы
                              </span>
                            ) : (
                              <select
                                value={it.check_code || ""}
                                onChange={(e) =>
                                  handleItemChange(index, "check_code", e.target.value)
                                }
                                className="w-full border rounded px-1 py-0.5 text-[11px]"
                              >
                                <option value="">— выберите проверку —</option>
                                {checks.map((c) => (
                                  <option key={c.code} value={c.code}>
                                    {c.code} — {c.title}
                                  </option>
                                ))}
                              </select>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            <div className="pt-3 border-t flex items-center justify-end gap-3 mt-3">
              <button
                type="button"
                onClick={handleSave}
                disabled={isSaving || !title}
                className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {isSaving ? "Сохраняем..." : "Сохранить шаблон"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminPlaybookLinesPage;
