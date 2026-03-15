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
import { useNavigate, useSearchParams, useParams } from "react-router-dom";

const AdminPlaybookLinesPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { dealId } = useParams<{ dealId: string }>();
  const playbookIdFromQuery = searchParams.get("playbook_id");

  const [lines, setLines] = useState<PlaybookLineShort[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [currentLine, setCurrentLine] = useState<PlaybookLineDetail | null>(
    null,
  );

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [successText, setSuccessText] = useState<string | null>(null);

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
      const res = await client.get<PlaybookLineShort[]>(
        "/api/v1/playbooks/lines",
      );
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
    setSuccessText(null);
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
      const sortedItems = [...(res.data.items || [])].sort(
        (a, b) => (a.order_index ?? 0) - (b.order_index ?? 0),
      );
      setItems(sortedItems);
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

  const resetForm = () => {
    setCurrentLine(null);
    setTitle("");
    setDescription("");
    setDealType("");
    setJurisdiction("");
    setLanguage("");
    setItems([]);
    setSuccessText(null);
    setErrorText(null);
  };

  const handleSelectLine = (line: PlaybookLineShort) => {
    setSelectedLineId(line.id);
    loadLineDetail(line.id);
  };

  const handleAddItem = () => {
    setItems((prev) => {
      const nextIndex = prev.length;
      const defaultTopicCode = topics[0]?.topic_code || "";
      return [
        ...prev,
        {
          kind: "topic",
          topic_code: defaultTopicCode,
          check_code: "",
          order_index: nextIndex,
        },
      ];
    });
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

  const handleRemoveItem = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleMoveItemUp = (index: number) => {
    if (index === 0) return;
    setItems((prev) => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return next;
    });
  };

  const handleMoveItemDown = (index: number) => {
    setItems((prev) => {
      if (index === prev.length - 1) return prev;
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next;
    });
  };

  const handleSave = async () => {
    setIsSaving(true);
    setErrorText(null);
    setSuccessText(null);
    try {
      const payload = {
        title: title.trim(),
        description: description.trim() || null,
        deal_type: dealType.trim() || null,
        jurisdiction: jurisdiction.trim() || null,
        language: language.trim() || null,
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
      setSuccessText("Шаблон сохранён.");
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(apiErr.detail || "Не удалось сохранить шаблон playbook.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateNew = () => {
    setSelectedLineId(null);
    resetForm();
  };

  const canAddItems = !isCatalogLoading && topics.length > 0;

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
            onClick={() =>
              dealId ? navigate(`/projects/${dealId}`) : navigate("/projects")
            }
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

        {successText && (
          <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded p-3">
            {successText}
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
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-gray-800">
                {currentLine ? "Редактирование шаблона" : "Новый шаблон"}
              </h2>
              {currentLine && (
                <span className="text-[11px] text-gray-400">
                  ID: {currentLine.id}
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block text-gray-600 mb-1">
                  Название<span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full border rounded px-2 py-1 text-xs"
                  placeholder="Например: Real estate RU / M&A RU..."
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
                  placeholder="Краткое описание, для каких проектов используется этот шаблон."
                />
              </div>
            </div>

            <div className="mt-3">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-gray-800">
                  Состав шаблона (темы / проверки)
                </h3>
                <div className="flex items-center gap-2">
                  {!canAddItems && (
                    <span className="text-[11px] text-gray-400">
                      Каталог тем не загружен
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={handleAddItem}
                    className="text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700"
                    disabled={!canAddItems}
                  >
                    + Элемент
                  </button>
                </div>
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
                      <th className="border px-2 py-1 text-left w-8">#</th>
                      <th className="border px-2 py-1 text-left">Тип</th>
                      <th className="border px-2 py-1 text-left">Topic</th>
                      <th className="border px-2 py-1 text-left">Check</th>
                      <th className="border px-2 py-1 text-left w-20">
                        Порядок
                      </th>
                      <th className="border px-2 py-1 text-left w-16">
                        Удалить
                      </th>
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
                          <td className="border px-2 py-1 align-top">
                            {index + 1}
                          </td>
                          <td className="border px-2 py-1 align-top">
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
                          <td className="border px-2 py-1 align-top">
                            <select
                              value={it.topic_code || ""}
                              onChange={(e) => {
                                const newTopicCode = e.target.value;
                                handleItemChange(
                                  index,
                                  "topic_code",
                                  newTopicCode,
                                );
                                handleItemChange(index, "check_code", "");
                              }}
                              className="w-full border rounded px-1 py-0.5 text-[11px]"
                            >
                              <option value="">— не выбрано —</option>
                              {topics.map((t) => (
                                <option
                                  key={t.topic_code}
                                  value={t.topic_code}
                                >
                                  {t.topic_code} — {t.topic_name}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="border px-2 py-1 align-top">
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
                                  handleItemChange(
                                    index,
                                    "check_code",
                                    e.target.value,
                                  )
                                }
                                className="w-full border rounded px-1 py-0.5 text-[11px]"
                              >
                                <option value="">
                                  — выберите проверку —
                                </option>
                                {checks.map((c) => (
                                  <option key={c.code} value={c.code}>
                                    {c.code} — {c.title}
                                  </option>
                                ))}
                              </select>
                            )}
                          </td>
                          <td className="border px-2 py-1 align-top">
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => handleMoveItemUp(index)}
                                disabled={index === 0}
                                className="px-1 py-0.5 border rounded text-[10px] disabled:opacity-40"
                              >
                                ↑
                              </button>
                              <button
                                type="button"
                                onClick={() => handleMoveItemDown(index)}
                                disabled={index === items.length - 1}
                                className="px-1 py-0.5 border rounded text-[10px] disabled:opacity-40"
                              >
                                ↓
                              </button>
                            </div>
                          </td>
                          <td className="border px-2 py-1 align-top">
                            <button
                              type="button"
                              onClick={() => handleRemoveItem(index)}
                              className="px-2 py-0.5 border rounded text-[10px] text-red-600 hover:bg-red-50"
                            >
                              ✕
                            </button>
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
                disabled={isSaving || !title.trim()}
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
