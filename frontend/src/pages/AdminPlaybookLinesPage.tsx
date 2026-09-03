// =============================================================
// src/pages/AdminPlaybookLinesPage.tsx
// Конструктор шаблонов Playbook (admin UI).
// Позволяет создавать, редактировать и удалять логические линии
// (шаблоны) playbook, настраивая состав тем и проверок.
// Может работать как отдельная страница (mode="page")
// или встроенный блок (mode="embedded").
// =============================================================

import React, { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-2 py-1 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const smallSelectClassName =
  "rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-1 py-0.5 text-[11px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const fullSelectClassName =
  "w-full rounded-md border border-[var(--border)] bg-[var(--bg-input)] px-1 py-0.5 text-[11px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

function normalizeLineItems(
  rawItems: PlaybookLineItemPayload[] = [],
): PlaybookLineItemPayload[] {
  return [...rawItems]
    .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0))
    .map((item, index) => ({
      ...item,
      order_index: index,
    }));
}

interface AdminPlaybookLinesPageProps {
  mode?: "page" | "embedded";
  headerActions?: React.ReactNode;
  onCancel?: () => void;
  onFinished?: () => void;
  onDeleted?: () => void;
  initialPlaybookId?: string | null;
}

const AdminPlaybookLinesPage: React.FC<AdminPlaybookLinesPageProps> = ({
  mode = "page",
  headerActions,
  onCancel,
  onFinished,
  onDeleted,
  initialPlaybookId = null,
}) => {
  const { t } = useTranslation("playbooks");
  const navigate = useNavigate();

  const [searchParams] = useSearchParams();
  const { dealId } = useParams<{ dealId: string }>();

  const playbookIdFromQuery = searchParams.get("playbook_id");
  const effectivePlaybookId = initialPlaybookId ?? playbookIdFromQuery;

  const [lines, setLines] = React.useState<PlaybookLineShort[]>([]);
  const [selectedLineId, setSelectedLineId] = React.useState<string | null>(
    null,
  );
  const [currentLine, setCurrentLine] =
    React.useState<PlaybookLineDetail | null>(null);

  const [isLoading, setIsLoading] = React.useState(true);
  const [isCatalogLoading, setIsCatalogLoading] = React.useState(false);
  const [isDetailLoading, setIsDetailLoading] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState(false);

  const [errorText, setErrorText] = React.useState<string | null>(null);
  const [successText, setSuccessText] = React.useState<string | null>(null);

  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = React.useState(false);

  const [title, setTitle] = useState("");
  const [dealType, setDealType] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [language, setLanguage] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = React.useState<PlaybookLineItemPayload[]>([]);

  const [topics, setTopics] = React.useState<PlaybookTopicInfo[]>([]);

  const isBusy = isSaving || isDeleting;
  const isBusyRef = React.useRef(isBusy);
  isBusyRef.current = isBusy;

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

  const clearMessages = useCallback(() => {
    setErrorText(null);
    setSuccessText(null);
  }, []);

  const resetForm = () => {
    setCurrentLine(null);
    setTitle("");
    setDescription("");
    setDealType("");
    setJurisdiction("");
    setLanguage("");
    setItems([]);
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
      return t("lines.validation.titleRequired");
    }

    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];

      if (!item.topic_code) {
        return t("lines.validation.topicRequired", { index: index + 1 });
      }

      if (item.kind === "check" && !item.check_code) {
        return t("lines.validation.checkRequired", { index: index + 1 });
      }
    }

    return null;
  };

  const loadLines = async () => {
    setIsLoading(true);
    setErrorText(null);

    try {
      const res = await client.get<PlaybookLineShort[]>(
        "/api/v1/playbooks/lines",
      );
      setLines(res.data || []);
    } catch (err) {
      setErrorText(
        getApiErrorMessage(err, t("lines.errors.loadLines")),
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

  const loadLineDetail = useCallback(
    async (lineId: string) => {
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
        setItems(normalizeLineItems(res.data.items || []));
      } catch (err) {
        setErrorText(
          getApiErrorMessage(err, t("lines.errors.loadDetail")),
        );
      } finally {
        setIsDetailLoading(false);
      }
    },
    [clearMessages],
  );

  React.useEffect(() => {
    void loadLines();
    void loadCatalog();
  }, []);

  React.useEffect(() => {
    if (!effectivePlaybookId || lines.length === 0 || isBusyRef.current) {
      return;
    }

    const line = lines.find((entry) => entry.id === effectivePlaybookId);
    if (!line) return;

    setSelectedLineId(line.id);
    void loadLineDetail(line.id);
  }, [effectivePlaybookId, lines, loadLineDetail]);

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
      setItems(normalizeLineItems(res.data.items || []));

      await loadLines();
      setSuccessText(t("lines.messages.saved"));
      onFinished?.();
    } catch (err) {
      setErrorText(
        getApiErrorMessage(err, t("lines.errors.saveFailed")),
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
      setSuccessText(t("lines.messages.deleted"));
      onDeleted?.();
    } catch (err) {
      if (isApiErrorStatus(err, 409)) {
        setErrorText(
          getApiErrorMessage(
            err,
            t("lines.errors.cannotDeleteInUse"),
          ),
        );
      } else if (isApiErrorStatus(err, 404)) {
        setErrorText(
          getApiErrorMessage(err, t("lines.errors.notFound")),
        );
        setIsDeleteDialogOpen(false);
        setSelectedLineId(null);
        resetForm();
        await loadLines();
        onDeleted?.();
      } else {
        setErrorText(
          getApiErrorMessage(err, t("lines.errors.deleteFailed")),
        );
      }
    } finally {
      setIsDeleting(false);
    }
  };

  const handleBackFromPage = () => {
    if (onCancel) {
      onCancel();
      return;
    }

    if (dealId) {
      navigate(`/projects/${dealId}`);
    } else {
      navigate("/projects");
    }
  };

  const pageHeader =
    mode === "page" ? (
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
            {t("lines.header.badge")}
          </p>
          <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
            {t("lines.header.title")}
          </h1>
          <p className="text-xs text-[var(--text-secondary)]">
            {t("lines.header.subtitle")}
          </p>
        </div>

        <Button variant="secondary" size="sm" onClick={handleBackFromPage}>
          {t("lines.header.back")}
        </Button>
      </div>
    ) : null;

  const mainContent = (
    <>
      <InlineAlert tone="error" message={errorText} />
      <InlineAlert tone="success" message={successText} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <PageSection
          title={t("lines.list.title")}
          rightSlot={
            <Button
              variant="secondary"
              size="sm"
              onClick={handleCreateNew}
              disabled={isUiLocked}
            >
              {t("lines.list.new")}
            </Button>
          }
        >
          {isLoading ? (
            <LoadingBlock text={t("lines.list.loading")} rows={6} />
          ) : lines.length === 0 ? (
            <EmptyState
              title={t("lines.list.emptyTitle")}
              description={t("lines.list.emptyDesc")}
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCreateNew}
                  disabled={isUiLocked}
                >
                  {t("lines.list.createButton")}
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
                    className={[
                      "w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-60",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
                      selectedLineId === line.id
                        ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)]"
                        : "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]",
                    ].join(" ")}
                  >
                    <div className="font-semibold text-[var(--text-primary)]">
                      {line.title}
                    </div>

                    {line.description ? (
                      <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                        {line.description}
                      </div>
                    ) : null}

                    <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                      {line.deal_type ? t("lines.list.typePrefix", { type: line.deal_type }) : ""}
                      {line.jurisdiction
                        ? t("lines.list.jurisdictionPrefix", { jurisdiction: line.jurisdiction })
                        : ""}
                      {line.language ? t("lines.list.languagePrefix", { language: line.language }) : ""}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </PageSection>

        <PageSection
          className="lg:col-span-2"
          title={currentLine ? t("lines.form.editTitle") : t("lines.form.newTitle")}
          rightSlot={
            currentLine ? (
              <span className="text-[11px] text-[var(--text-muted)]">
                {t("lines.form.idLabel", { id: currentLine.id })}
              </span>
            ) : undefined
          }
        >
          {isDetailLoading ? (
            <div className="mb-3">
              <LoadingBlock text={t("lines.form.loadingDetail")} rows={4} />
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
            <Field label={t("lines.form.nameLabel")} required>
              <input
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                disabled={isUiLocked}
                className={inputClassName}
                placeholder={t("lines.form.namePlaceholder")}
              />
            </Field>

            <Field label={t("lines.form.dealTypeLabel")}>
              <input
                type="text"
                value={dealType}
                onChange={(event) => setDealType(event.target.value)}
                disabled={isUiLocked}
                className={inputClassName}
                placeholder={t("lines.form.dealTypePlaceholder")}
              />
            </Field>

            <Field label={t("lines.form.jurisdictionLabel")}>
              <input
                type="text"
                value={jurisdiction}
                onChange={(event) => setJurisdiction(event.target.value)}
                disabled={isUiLocked}
                className={inputClassName}
                placeholder={t("lines.form.jurisdictionPlaceholder")}
              />
            </Field>

            <Field label={t("lines.form.languageLabel")}>
              <input
                type="text"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                disabled={isUiLocked}
                className={inputClassName}
                placeholder={t("lines.form.languagePlaceholder")}
              />
            </Field>

            <div className="md:col-span-2">
              <Field label={t("lines.form.descriptionLabel")}>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  disabled={isUiLocked}
                  className={inputClassName}
                  rows={2}
                  placeholder={t("lines.form.descriptionPlaceholder")}
                />
              </Field>
            </div>
          </div>

          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold text-[var(--text-primary)]">
                {t("lines.items.title")}
              </h3>

              <div className="flex items-center gap-2">
                {!canAddItems && topics.length === 0 ? (
                  <span className="text-[11px] text-[var(--text-muted)]">
                    {t("lines.items.catalogNotLoaded")}
                  </span>
                ) : null}

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleAddItem}
                  disabled={!canAddItems}
                >
                  {t("lines.items.addItem")}
                </Button>
              </div>
            </div>

            {topics.length === 0 ? (
              <EmptyState
                title={t("lines.items.catalogUnavailableTitle")}
                description={t("lines.items.catalogUnavailableDesc")}
              />
            ) : items.length === 0 ? (
              <EmptyState
                title={t("lines.items.emptyTitle")}
                description={t("lines.items.emptyDesc")}
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleAddItem}
                    disabled={!canAddItems}
                  >
                    {t("lines.items.emptyButton")}
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
                        {t("lines.items.type")}
                      </th>
                      <th className="w-64 px-2 py-1 text-left font-medium">
                        {t("lines.items.topic")}
                      </th>
                      <th className="px-2 py-1 text-left font-medium">
                        {t("lines.items.check")}
                      </th>
                      <th className="w-24 px-2 py-1 text-left font-medium">
                        {t("lines.items.order")}
                      </th>
                      <th className="w-16 px-2 py-1 text-left font-medium">
                        {t("lines.items.delete")}
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
                              onChange={(event) =>
                                handleKindChange(
                                  index,
                                  event.target.value as "topic" | "check",
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
                              onChange={(event) =>
                                handleTopicChange(index, event.target.value)
                              }
                              disabled={isUiLocked}
                              className={fullSelectClassName}
                            >
                              <option value="">{t("lines.items.notSelected")}</option>
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
                                {t("lines.items.topicCheckUnused")}
                              </span>
                            ) : checks.length === 0 ? (
                              <span className="text-[11px] text-[var(--text-muted)]">
                                {t("lines.items.noChecksForTopic")}
                              </span>
                            ) : (
                              <select
                                value={item.check_code || ""}
                                onChange={(event) =>
                                  handleItemChange(
                                    index,
                                    "check_code",
                                    event.target.value,
                                  )
                                }
                                disabled={isUiLocked}
                                className={fullSelectClassName}
                              >
                                <option value="">
                                  {t("lines.items.selectCheck")}
                                </option>
                                {checks.map((check) => (
                                  <option key={check.code} value={check.code}>
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
                              className="px-2 py-1 text-[10px] text-[var(--color-error-text)] hover:bg-[var(--color-error-bg)] hover:text-[var(--color-error-text)]"
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

            <div className="mt-4 flex items-center justify-between border-t border-[var(--border)] pt-3">
              {currentLine ? (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={openDeleteDialog}
                  disabled={!canDelete}
                >
                  {t("lines.buttons.deleteTemplate")}
                </Button>
              ) : (
                <span className="text-[11px] text-[var(--text-muted)]">
                  {t("lines.buttons.saveFirstHint")}
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
                  {t("lines.buttons.saveTemplate")}
                </Button>
              </div>
            </div>
          </div>
        </PageSection>
      </div>
    </>
  );

  return (
    <>
      {mode === "page" ? (
        <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6">
          <div className="mx-auto max-w-6xl space-y-4">
            {pageHeader}
            {mainContent}
          </div>
        </div>
      ) : (
        <PageSection
          title={t("lines.header.title")}
          subtitle={t("lines.header.subtitle")}
          rightSlot={headerActions}
          contentClassName="px-5 pt-2 pb-4"
        >
          {mainContent}
        </PageSection>
      )}

      <ConfirmDialog
        open={isDeleteDialogOpen}
        title={t("lines.confirm.deleteTitle")}
        description={
          currentLine
            ? t("lines.confirm.deleteDescWithTitle", { title: currentLine.title })
            : t("lines.confirm.deleteDescGeneric")
        }
        confirmLabel={t("lines.confirm.deleteButton")}
        cancelLabel={t("lines.confirm.cancelButton")}
        isConfirming={isDeleting}
        onConfirm={handleDeleteConfirmed}
        onCancel={closeDeleteDialog}
      />
    </>
  );
};

export default AdminPlaybookLinesPage;



