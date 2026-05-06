// src/pages/AdminPlaybookLinesPage.tsx

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import client from "../api/client";
import ConfirmDialog from "../components/ConfirmDialog";
import InlineAlert from "../components/InlineAlert";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Field from "../components/ui/Field";
import LoadingBlock from "../components/ui/LoadingBlock";
import PageSection from "../components/ui/PageSection";
import type {
  ApiError,
  PlaybookLineDetail,
  PlaybookLineItemPayload,
  PlaybookLineShort,
  PlaybookTopicInfo,
} from "../types";
import { getApiErrorMessage, isApiErrorStatus } from "../utils/apiErrors";

const inputClassName =
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-2 py-1 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60";

const smallSelectClassName =
  "rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-1 py-0.5 text-[11px] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60";

const fullSelectClassName =
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-1 py-0.5 text-[11px] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-60";

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
  const [isCatalogLoading, setIsCatalogLoading] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const [errorText, setErrorText] = useState<string | null>(null);
  const [successText, setSuccessText] = useState<string | null>(null);

  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);

  const [title, setTitle] = useState("");
  const [dealType, setDealType] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [language, setLanguage] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<PlaybookLineItemPayload[]>([]);

  const [topics, setTopics] = useState<PlaybookTopicInfo[]>([]);

  const isBusy = isSaving || isDeleting;
  const isUiLocked = isBusy || isDetailLoading;
  const canAddItems = !isCatalogLoading && topics.length > 0 && !isUiLocked;
  const canSave = !isUiLocked && !!title.trim();
  const canDelete = !!currentLine && !isUiLocked;

  const topicByCode = useMemo(() => {
    const map = new Map<string, PlaybookTopicInfo>();
    for (const topic of topics) {
      map.set(topic.topic_code, topic);
    }
    return map;
  }, [topics]);

  const clearMessages = () => {
    setErrorText(null);
    setSuccessText(null);
  };

  const resetForm = () => {
    setCurrentLine(null);
    setTitle("");
    setDescription("");
    setDealType("");
    setJurisdiction("");
    setLanguage("");
    setItems([]);
  };

  const normalizeItems = (
    rawItems: PlaybookLineItemPayload[] = [],
  ): PlaybookLineItemPayload[] => {
    return [...rawItems]
      .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0))
      .map((item, index) => ({
        ...item,
        order_index: index,
      }));
  };

  const buildPayload = () => {
    return {
      title: title.trim(),
      description: description.trim() || null,
      deal_type: dealType.trim() || null,
      jurisdiction: jurisdiction.trim() || null,
      language: language.trim() || null,
      items: items.map((item, index) => ({
        ...item,
        order_index: index,
      })),
    };
  };

  const validateBeforeSave = (): string | null => {
    if (!title.trim()) {
      return "Укажите название шаблона.";
    }

    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];

      if (!item.topic_code) {
        return `Элемент #${index + 1}: выберите тему.`;
      }

      if (item.kind === "check" && !item.check_code) {
        return `Элемент #${index + 1}: выберите проверку для типа check.`;
      }
    }

    return null;
  };

  const loadLines = async () => {
    setIsLoading(true);
    setErrorText(null);

    try {
      const res = await client.get<PlaybookLineShort[]>("/api/v1/playbooks/lines");
      setLines(res.data || []);
    } catch (err) {
      setErrorText(
        getApiErrorMessage(err, "Не удалось загрузить шаблоны playbook."),
      );
    } finally {
      setIsLoading(false);
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
      console.error("Failed to load playbook catalog:", apiErr.detail);
    } finally {
      setIsCatalogLoading(false);
    }
  };

  const loadLineDetail = async (lineId: string) => {
    setIsDetailLoading(true);
    clearMessages();

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
      setItems(normalizeItems(res.data.items || []));
    } catch (err) {
      setErrorText(
        getApiErrorMessage(err, "Не удалось загрузить шаблон playbook."),
      );
    } finally {
      setIsDetailLoading(false);
    }
  };

  useEffect(() => {
    void loadLines();
    void loadCatalog();
  }, []);

  useEffect(() => {
    if (!playbookIdFromQuery || lines.length === 0 || isBusy) return;

    const line = lines.find((entry) => entry.id === playbookIdFromQuery);
    if (!line) return;

    setSelectedLineId(line.id);
    void loadLineDetail(line.id);
  }, [playbookIdFromQuery, lines]); // isBusy специально не включаем

  const handleCreateNew = () => {
    if (isUiLocked) return;

    setSelectedLineId(null);
    clearMessages();
    resetForm();
  };

  const handleSelectLine = (line: PlaybookLineShort) => {
    if (isUiLocked) return;

    setSelectedLineId(line.id);
    void loadLineDetail(line.id);
  };

  const handleAddItem = () => {
    if (!canAddItems) return;

    const defaultTopicCode = topics[0]?.topic_code || "";

    setItems((prev) => [
      ...prev,
      {
        kind: "topic",
        topic_code: defaultTopicCode,
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
    if (isUiLocked) return;

    setItems((prev) =>
      prev.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              [field]: value,
            }
          : item,
      ),
    );
  };

  const handleTopicChange = (index: number, newTopicCode: string) => {
    if (isUiLocked) return;

    setItems((prev) =>
      prev.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              topic_code: newTopicCode,
              check_code: "",
            }
          : item,
      ),
    );
  };

  const handleKindChange = (index: number, newKind: "topic" | "check") => {
    if (isUiLocked) return;

    setItems((prev) =>
      prev.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              kind: newKind,
              check_code: newKind === "topic" ? "" : item.check_code,
            }
          : item,
      ),
    );
  };

  const handleRemoveItem = (index: number) => {
    if (isUiLocked) return;

    setItems((prev) =>
      prev
        .filter((_, itemIndex) => itemIndex !== index)
        .map((item, itemIndex) => ({
          ...item,
          order_index: itemIndex,
        })),
    );
  };

  const handleMoveItemUp = (index: number) => {
    if (isUiLocked || index === 0) return;

    setItems((prev) => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return next.map((item, itemIndex) => ({
        ...item,
        order_index: itemIndex,
      }));
    });
  };

  const handleMoveItemDown = (index: number) => {
    if (isUiLocked) return;

    setItems((prev) => {
      if (index >= prev.length - 1) return prev;

      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next.map((item, itemIndex) => ({
        ...item,
        order_index: itemIndex,
      }));
    });
  };

  const handleSave = async () => {
    if (!canSave) return;

    clearMessages();

    const validationError = validateBeforeSave();
    if (validationError) {
      setErrorText(validationError);
      return;
    }

    setIsSaving(true);

    try {
      const payload = buildPayload();

      const res = currentLine
        ? await client.put<PlaybookLineDetail>(
            `/api/v1/playbooks/lines/${currentLine.id}`,
            payload,
          )
        : await client.post<PlaybookLineDetail>(
            "/api/v1/playbooks/lines",
            payload,
          );

      setCurrentLine(res.data);
      setSelectedLineId(res.data.id);
      setTitle(res.data.title || "");
      setDescription(res.data.description || "");
      setDealType(res.data.deal_type || "");
      setJurisdiction(res.data.jurisdiction || "");
      setLanguage(res.data.language || "");
      setItems(normalizeItems(res.data.items || []));

      await loadLines();
      setSuccessText("Шаблон сохранён.");
    } catch (err) {
      setErrorText(
        getApiErrorMessage(err, "Не удалось сохранить шаблон playbook."),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const openDeleteDialog = () => {
    if (!canDelete) return;
    clearMessages();
    setIsDeleteDialogOpen(true);
  };

  const closeDeleteDialog = () => {
    if (isDeleting) return;
    setIsDeleteDialogOpen(false);
  };

  const handleDeleteConfirmed = async () => {
    if (!currentLine) return;

    setIsDeleting(true);
    clearMessages();

    try {
      await client.delete<void>(`/api/v1/playbooks/lines/${currentLine.id}`);

      setIsDeleteDialogOpen(false);
      setSelectedLineId(null);
      resetForm();
      await loadLines();
      setSuccessText("Шаблон удалён.");
    } catch (err) {
      if (isApiErrorStatus(err, 409)) {
        setErrorText(
          getApiErrorMessage(
            err,
            "Шаблон нельзя удалить, потому что он используется в проектах или запусках.",
          ),
        );
      } else if (isApiErrorStatus(err, 404)) {
        setErrorText(
          getApiErrorMessage(err, "Шаблон уже удалён или не найден."),
        );
        setIsDeleteDialogOpen(false);
        setSelectedLineId(null);
        resetForm();
        await loadLines();
      } else {
        setErrorText(
          getApiErrorMessage(err, "Не удалось удалить шаблон playbook."),
        );
      }
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-6xl space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
                Admin · Playbook
              </p>
              <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
                Конструктор шаблонов Playbook
              </h1>
              <p className="text-xs text-[var(--text-secondary)]">
                Настройка логических линий (шаблонов) и их состава для проектов.
              </p>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                dealId ? navigate(`/projects/${dealId}`) : navigate("/projects")
              }
            >
              ← Вернуться к проектам
            </Button>
          </div>

          <InlineAlert tone="error" message={errorText} />
          <InlineAlert tone="success" message={successText} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <PageSection
              title="Шаблоны playbook"
              rightSlot={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCreateNew}
                  disabled={isUiLocked}
                >
                  + Новый
                </Button>
              }
            >
              {isLoading ? (
                <LoadingBlock text="Загружаем список шаблонов..." rows={6} />
              ) : lines.length === 0 ? (
                <EmptyState
                  title="Шаблоны ещё не созданы"
                  description="Создайте первый шаблон playbook, чтобы настроить набор тем и проверок для проектов."
                  action={
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleCreateNew}
                      disabled={isUiLocked}
                    >
                      Создать шаблон
                    </Button>
                  }
                />
              ) : (
                <ul className="max-h-80 space-y-1 overflow-y-auto pr-1">
                  {lines.map((line) => (
                    <li key={line.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectLine(line)}
                        disabled={isUiLocked}
                        className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                          selectedLineId === line.id
                            ? "border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--text-primary)]"
                            : "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
                        }`}
                      >
                        <div className="font-semibold text-[var(--text-primary)]">
                          {line.title}
                        </div>

                        {line.description && (
                          <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                            {line.description}
                          </div>
                        )}

                        <div className="mt-1 text-[11px] text-[var(--text-muted)]">
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

            <PageSection
              className="lg:col-span-2"
              title={currentLine ? "Редактирование шаблона" : "Новый шаблон"}
              rightSlot={
                currentLine ? (
                  <span className="text-[11px] text-[var(--text-muted)]">
                    ID: {currentLine.id}
                  </span>
                ) : null
              }
            >
              {isDetailLoading && (
                <div className="mb-3">
                  <LoadingBlock text="Загружаем данные шаблона..." rows={4} />
                </div>
              )}

              <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
                <Field label="Название" required>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    disabled={isUiLocked}
                    className={inputClassName}
                    placeholder="Например: Real estate RU / M&A RU..."
                  />
                </Field>

                <Field label="Тип сделки">
                  <input
                    type="text"
                    value={dealType}
                    onChange={(e) => setDealType(e.target.value)}
                    disabled={isUiLocked}
                    className={inputClassName}
                    placeholder="real_estate, mna, nda..."
                  />
                </Field>

                <Field label="Юрисдикция">
                  <input
                    type="text"
                    value={jurisdiction}
                    onChange={(e) => setJurisdiction(e.target.value)}
                    disabled={isUiLocked}
                    className={inputClassName}
                    placeholder="RU, EN, DE..."
                  />
                </Field>

                <Field label="Язык">
                  <input
                    type="text"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    disabled={isUiLocked}
                    className={inputClassName}
                    placeholder="ru, en..."
                  />
                </Field>

                <div className="md:col-span-2">
                  <Field label="Описание">
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      disabled={isUiLocked}
                      className={inputClassName}
                      rows={2}
                      placeholder="Краткое описание, для каких проектов используется этот шаблон."
                    />
                  </Field>
                </div>
              </div>

              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-[var(--text-primary)]">
                    Состав шаблона (темы / проверки)
                  </h3>

                  <div className="flex items-center gap-2">
                    {!canAddItems && topics.length === 0 && (
                      <span className="text-[11px] text-[var(--text-muted)]">
                        Каталог тем не загружен
                      </span>
                    )}

                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleAddItem}
                      disabled={!canAddItems}
                    >
                      + Элемент
                    </Button>
                  </div>
                </div>

                {topics.length === 0 ? (
                  <EmptyState
                    title="Каталог тем недоступен"
                    description="Каталог тем и проверок не загружен или пуст. Проверьте endpoint /playbooks/catalog."
                  />
                ) : items.length === 0 ? (
                  <EmptyState
                    title="Состав шаблона пуст"
                    description="Добавьте тему или проверку, чтобы сформировать содержимое playbook‑шаблона."
                    action={
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleAddItem}
                        disabled={!canAddItems}
                      >
                        Добавить элемент
                      </Button>
                    }
                  />
                ) : (
                  <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-card)]">
                    <table className="w-full table-fixed border-collapse text-[11px]">
                      <thead className="bg-[var(--bg-elevated-soft)]">
                        <tr className="text-[var(--text-muted)]">
                          <th className="w-8 px-2 py-1 text-left font-medium">
                            #
                          </th>
                          <th className="w-24 px-2 py-1 text-left font-medium">
                            Тип
                          </th>
                          <th className="w-64 px-2 py-1 text-left font-medium">
                            Topic
                          </th>
                          <th className="px-2 py-1 text-left font-medium">
                            Check
                          </th>
                          <th className="w-24 px-2 py-1 text-left font-medium">
                            Порядок
                          </th>
                          <th className="w-16 px-2 py-1 text-left font-medium">
                            Удалить
                          </th>
                        </tr>
                      </thead>

                      <tbody>
                        {items.map((item, index) => {
                          const topic = item.topic_code
                            ? topicByCode.get(item.topic_code)
                            : undefined;
                          const checks = topic?.checks || [];

                          return (
                            <tr
                              key={`${item.kind}-${item.topic_code || "empty"}-${index}`}
                              className="border-t border-[var(--border)]/70 align-top"
                            >
                              <td className="px-2 py-1 text-[var(--text-muted)]">
                                {index + 1}
                              </td>

                              <td className="px-2 py-1">
                                <select
                                  value={item.kind}
                                  onChange={(e) =>
                                    handleKindChange(
                                      index,
                                      e.target.value as "topic" | "check",
                                    )
                                  }
                                  disabled={isUiLocked}
                                  className={smallSelectClassName}
                                >
                                  <option value="topic">topic</option>
                                  <option value="check">check</option>
                                </select>
                              </td>

                              <td className="px-2 py-1">
                                <select
                                  value={item.topic_code || ""}
                                  onChange={(e) =>
                                    handleTopicChange(index, e.target.value)
                                  }
                                  disabled={isUiLocked}
                                  className={fullSelectClassName}
                                >
                                  <option value="">— не выбрано —</option>
                                  {topics.map((topicEntry) => (
                                    <option
                                      key={topicEntry.topic_code}
                                      value={topicEntry.topic_code}
                                    >
                                      {topicEntry.topic_code} —{" "}
                                      {topicEntry.topic_name}
                                    </option>
                                  ))}
                                </select>
                              </td>

                              <td className="px-2 py-1">
                                {item.kind === "topic" ? (
                                  <span className="text-[11px] text-[var(--text-muted)]">
                                    Для типа topic check не используется
                                  </span>
                                ) : checks.length === 0 ? (
                                  <span className="text-[11px] text-[var(--text-muted)]">
                                    Нет проверок для выбранной темы
                                  </span>
                                ) : (
                                  <select
                                    value={item.check_code || ""}
                                    onChange={(e) =>
                                      handleItemChange(
                                        index,
                                        "check_code",
                                        e.target.value,
                                      )
                                    }
                                    disabled={isUiLocked}
                                    className={fullSelectClassName}
                                  >
                                    <option value="">
                                      — выберите проверку —
                                    </option>
                                    {checks.map((check) => (
                                      <option
                                        key={check.code}
                                        value={check.code}
                                      >
                                        {check.code} — {check.title}
                                      </option>
                                    ))}
                                  </select>
                                )}
                              </td>

                              <td className="px-2 py-1">
                                <div className="flex items-center gap-1">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleMoveItemUp(index)}
                                    disabled={index === 0 || isUiLocked}
                                    className="px-2 py-1 text-[10px]"
                                  >
                                    ↑
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleMoveItemDown(index)}
                                    disabled={
                                      index === items.length - 1 || isUiLocked
                                    }
                                    className="px-2 py-1 text-[10px]"
                                  >
                                    ↓
                                  </Button>
                                </div>
                              </td>

                              <td className="px-2 py-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRemoveItem(index)}
                                  disabled={isUiLocked}
                                  className="px-2 py-1 text-[10px] text-red-400 hover:bg-red-500/10 hover:text-red-300"
                                >
                                  ✕
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-[var(--border)] pt-3">
                {currentLine ? (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={openDeleteDialog}
                    disabled={!canDelete}
                  >
                    Удалить шаблон
                  </Button>
                ) : (
                  <span className="text-[11px] text-[var(--text-muted)]">
                    Сначала сохраните шаблон, затем его можно будет удалить.
                  </span>
                )}

                <div className="ml-auto flex items-center gap-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleSave}
                    disabled={!canSave}
                    isLoading={isSaving}
                  >
                    Сохранить шаблон
                  </Button>
                </div>
              </div>
            </PageSection>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={isDeleteDialogOpen}
        title="Удалить шаблон?"
        description={
          currentLine
            ? `Шаблон "${currentLine.title}" будет удалён без возможности восстановления. Если он используется в проектах или исторических запусках анализа, сервер отклонит удаление.`
            : "Шаблон будет удалён без возможности восстановления."
        }
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        isConfirming={isDeleting}
        onConfirm={handleDeleteConfirmed}
        onCancel={closeDeleteDialog}
      />
    </>
  );
};

export default AdminPlaybookLinesPage;



