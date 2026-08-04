// =============================================================
// src/components/playbook/DealPlaybookSelectorPanel.tsx
// =============================================================

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import client from "../../api/client";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useAuth } from "../../hooks/useAuth";

import Button from "../ui/Button";
import PageSection from "../ui/PageSection";
import EmptyState from "../ui/EmptyState";
import LoadingBlock from "../ui/LoadingBlock";
import InlineAlert from "../InlineAlert";
import ConfirmDialog from "../ConfirmDialog";

import { getApiErrorMessage, isApiErrorStatus } from "../../utils/apiErrors";

import type {
  Deal,
  DealDetail,
  PlaybookLineShort,
  PlaybookLineDetail,
  PlaybookVersionShort,
  PlaybookVersionDetail,
  PlaybookCreateRequest,
  PlaybookCreateResponse,
  DealPlaybookHistoryItem,
  ModelConfig,
} from "../../types";

export interface DealPlaybookSelectorPanelProps {
  dealId: string;
  deal?: Deal;
  mode?: "page" | "embedded";
  onFinished?: () => void;
  onCancel?: () => void;
  onDealPatched?: (patch: Partial<Deal>) => void;
  headerActions?: React.ReactNode;
  onEditTemplate?: (templateId: string) => void;
}

const VISIBLE_VERSION_STATUSES = new Set<string>(["draft", "published"]);

const selectClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const cardButtonBaseClassName = [
  "w-full rounded-2xl border px-3 py-2 text-left text-xs transition-colors",
  "disabled:cursor-not-allowed disabled:opacity-60",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
].join(" ");

const cardButtonIdleClassName =
  "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--bg-elevated-soft)]";

const cardButtonActiveClassName =
  "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]";

const metaLabelClassName =
  "text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]";

function VersionStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    draft: {
      label: "Черновик",
      cls: "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
    },
    published: {
      label: "Опубликована",
      cls: "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
    },
    archived: {
      label: "Архив",
      cls: "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
    },
  };

  const cfg = map[status] ?? {
    label: status,
    cls: "border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  );
}

const DealPlaybookSelectorPanel: React.FC<DealPlaybookSelectorPanelProps> = ({
  dealId,
  deal,
  mode = "page",
  onFinished,
  onCancel,
  onDealPatched,
  headerActions,
  onEditTemplate,
}) => {
  const navigate = useNavigate();
  const { canManageRequests } = useDealPermissions(dealId);
  const { globalRole } = useAuth();

  const canEditPlaybook =
    (globalRole === "superadmin" || globalRole === "tenant_admin") &&
    canManageRequests;

  const [dealDetail, setDealDetail] = useState<DealDetail | null>(null);
  const [lines, setLines] = useState<PlaybookLineShort[]>([]);
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

  const visibleVersions = useMemo(() => {
    if (!selectedLineId) return [];

    return versions.filter(
      (version) =>
        String(version.playbook_id) === selectedLineId &&
        VISIBLE_VERSION_STATUSES.has(version.status),
    );
  }, [versions, selectedLineId]);

  const currentVersionId = effectiveDeal?.playbook_version_id
    ? String(effectiveDeal.playbook_version_id)
    : null;

  const isSameAsCurrent =
    currentVersionId !== null && selectedVersionId === currentVersionId;

  const selectedVersionStatus = useMemo(
    () =>
      selectedVersionId
        ? (visibleVersions.find((v) => String(v.id) === selectedVersionId)
            ?.status ?? null)
        : null,
    [selectedVersionId, visibleVersions],
  );

  const isSelectedVersionDraft = selectedVersionStatus === "draft";
  const isUiLocked = isApplying || isCreatingVersion;

  const clearMessages = useCallback(() => {
    setErrorText(null);
    setSuccessText(null);
  }, []);

  const handleBack = useCallback(() => {
    if (onCancel) {
      onCancel();
      return;
    }

    navigate(`/projects/${dealId}`);
  }, [dealId, navigate, onCancel]);

  const loadHistory = useCallback(async () => {
    setIsHistoryLoading(true);
    setHistoryError(null);

    try {
      const res = await client.get<
        DealPlaybookHistoryItem[] | { items?: DealPlaybookHistoryItem[] }
      >(`/api/v1/deals/${dealId}/playbook-history`);

      const payload = res.data;
      setHistory(Array.isArray(payload) ? payload : (payload.items ?? []));
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

  const handleSelectLine = useCallback(
    (lineId: string) => {
      if (isUiLocked) return;

      clearMessages();
      setSelectedLineId(lineId);
      setSelectedVersionId(null);
      setVersionDetail(null);
      setCreateVersionError(null);
    },
    [clearMessages, isUiLocked],
  );

  const handleSelectVersion = useCallback(
    (versionId: string) => {
      if (isUiLocked) return;

      clearMessages();
      setSelectedVersionId(versionId);
    },
    [clearMessages, isUiLocked],
  );

  const applyPlaybook = useCallback(async () => {
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

      onDealPatched?.({
        playbook_version_id: selectedVersionId,
      });

      await loadHistory();
      setSuccessText("Playbook успешно применён к проекту.");
      setIsApplyConfirmOpen(false);
      onFinished?.();
    } catch (err) {
      if (isApiErrorStatus(err, 409)) {
        setErrorText(
          getApiErrorMessage(
            err,
            "Не удалось применить playbook: конфликт состояния.",
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
  }, [
    clearMessages,
    dealId,
    loadHistory,
    onDealPatched,
    onFinished,
    selectedVersionId,
  ]);

  const handleApplyPlaybook = useCallback(async () => {
    if (!selectedVersionId) {
      setErrorText("Сначала выберите версию playbook.");
      return;
    }

    if (currentVersionId && currentVersionId !== selectedVersionId) {
      setIsApplyConfirmOpen(true);
      return;
    }

    await applyPlaybook();
  }, [applyPlaybook, currentVersionId, selectedVersionId]);

  const handleCreateVersionForSelectedLine = useCallback(async () => {
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
      const line = lines.find((entry) => String(entry.id) === selectedLineId);

      const payload: PlaybookCreateRequest = {
        name: line?.title ?? "Новая версия",
        bundles: [],
        include_ids: [],
        exclude_ids: [],
        profile: null,
        semver: "1.0.0",
        status: "draft",
        playbook_id: selectedLineId,
        from_line_id: selectedLineId,
        model_config_id: selectedModelConfigId,
      };

      const res = await client.post<PlaybookCreateResponse>(
        "/api/v1/playbooks",
        payload,
      );

      const newVersion: PlaybookVersionShort = {
        id: String(res.data.id),
        name: res.data.name,
        semver: res.data.semver,
        status: res.data.status,
        playbook_id: res.data.playbook_id
          ? String(res.data.playbook_id)
          : selectedLineId,
      };

      setVersions((prev) => [...prev, newVersion]);
      setSelectedVersionId(newVersion.id);
      setSuccessText(
        "Черновик версии создан. Опубликуйте его в Playbook Studio, затем примените к проекту.",
      );
    } catch (err) {
      setCreateVersionError(
        getApiErrorMessage(err, "Не удалось создать версию playbook."),
      );
    } finally {
      setIsCreatingVersion(false);
    }
  }, [clearMessages, lines, selectedLineId, selectedModelConfigId]);

  const handleEditSelectedLine = useCallback(() => {
    if (!selectedLineId) return;
    onEditTemplate?.(selectedLineId);
  }, [selectedLineId, onEditTemplate]);

  useEffect(() => {
    let cancelled = false;

    async function loadDeal() {
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
      setIsLoading(true);
      setErrorText(null);

      try {
        const [linesRes, versionsRes] = await Promise.all([
          client.get<PlaybookLineShort[]>("/api/v1/playbooks/lines?scope=all"),
          client.get<PlaybookVersionShort[]>("/api/v1/playbooks"),
        ]);

        if (cancelled) return;

        const nextLines = linesRes.data ?? [];
        const nextVersions = versionsRes.data ?? [];

        setLines(nextLines);
        setVersions(nextVersions);

        const currentPlaybookVersionId = effectiveDeal?.playbook_version_id
          ? String(effectiveDeal.playbook_version_id)
          : null;

        if (currentPlaybookVersionId) {
          const version = nextVersions.find(
            (entry) => String(entry.id) === currentPlaybookVersionId,
          );

          if (version) {
            setSelectedVersionId(String(version.id));
            if (version.playbook_id) {
              setSelectedLineId(String(version.playbook_id));
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
  }, [effectiveDeal?.playbook_version_id]);

  useEffect(() => {
    let cancelled = false;

    async function loadModelConfigs() {
      setIsModelConfigsLoading(true);
      setModelConfigsError(null);

      try {
        const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
        if (cancelled) return;

        const list = res.data ?? [];
        setModelConfigs(list);

        if (list.length > 0) {
          setSelectedModelConfigId((prev) => prev ?? String(list[0].id));
        }
      } catch (err) {
        if (!cancelled) {
          setModelConfigsError(
            getApiErrorMessage(
              err,
              "Не удалось загрузить список моделей. Обратитесь к администратору.",
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

    async function loadSelectedLine(lineId: string) {
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
      void loadSelectedLine(selectedLineId);
    } else {
      setSelectedLineDetail(null);
    }

    return () => {
      cancelled = true;
    };
  }, [selectedLineId]);

  if (!canEditPlaybook) {
    if (mode === "page") {
      return (
        <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
          <div className="flex items-center justify-center py-20">
            <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center shadow-sm">
              <p className="mb-4 text-sm text-[var(--text-secondary)]">
                У вас нет прав для настройки playbook этого проекта.
              </p>

              <Button variant="secondary" size="sm" onClick={handleBack}>
                Вернуться назад
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <PageSection
        title="Playbook проекта"
        subtitle="Выбор, применение и просмотр состава playbook для текущей сделки."
        rightSlot={headerActions}
      >
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center shadow-sm">
          <p className="text-sm text-[var(--text-secondary)]">
            У вас нет прав для настройки playbook этого проекта.
          </p>
        </div>
      </PageSection>
    );
  }

  const content = (
    <>
      {mode === "page" && (
        <>
          <button
            type="button"
            onClick={handleBack}
            className="flex shrink-0 items-center gap-1.5 rounded-md text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
          >
            ← Назад к проекту
          </button>

          <header>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              Playbook проекта
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {effectiveDeal?.name ?? dealId}
            </p>

            {currentVersionId ? (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Текущая версия:{" "}
                <span className="font-medium text-[var(--text-primary)]">
                  {currentVersionId}
                </span>
              </p>
            ) : (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Для проекта ещё не выбран playbook.
              </p>
            )}
          </header>
        </>
      )}

      {errorText && <InlineAlert tone="error" message={errorText} />}
      {successText && <InlineAlert tone="success" message={successText} />}

      <div
        className={[
          "grid gap-4",
          mode === "page"
            ? "grid-cols-1 lg:grid-cols-3"
            : "grid-cols-1 xl:grid-cols-2",
        ].join(" ")}
      >
        <PageSection title="Шаблоны playbook">
          {isLoading ? (
            <LoadingBlock text="Загружаем шаблоны playbook..." rows={6} />
          ) : lines.length === 0 ? (
            <EmptyState
              title="Шаблоны не настроены"
              description="Создайте первый шаблон playbook в административном разделе."
            />
          ) : (
            <ul className="max-h-80 space-y-1 overflow-y-auto">
              {lines.map((line) => {
                const lineId = String(line.id);
                const isSelected = selectedLineId === lineId;

                return (
                  <li key={lineId}>
                    <button
                      type="button"
                      onClick={() => handleSelectLine(lineId)}
                      disabled={isUiLocked}
                      className={[
                        cardButtonBaseClassName,
                        isSelected
                          ? cardButtonActiveClassName
                          : cardButtonIdleClassName,
                      ].join(" ")}
                    >
                      <div className="font-semibold">{line.title}</div>

                      {line.description && (
                        <div className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                          {line.description}
                        </div>
                      )}

                      <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                        {[
                          line.deal_type && `Тип: ${line.deal_type}`,
                          line.jurisdiction &&
                            `Юрисдикция: ${line.jurisdiction}`,
                          line.language && `Язык: ${line.language}`,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </PageSection>

        <PageSection title="Версии playbook">
          {createVersionError && (
            <InlineAlert tone="error" message={createVersionError} />
          )}

          {!selectedLineId ? (
            <EmptyState
              title="Шаблон не выбран"
              description="Сначала выберите шаблон playbook в левой колонке."
            />
          ) : visibleVersions.length === 0 ? (
            <div className="space-y-3">
              <EmptyState
                title="Версий пока нет"
                description="Для выбранного шаблона ещё нет версий. Выберите модель и создайте первую."
              />

              <div>
                <label className={`mb-1 block ${metaLabelClassName}`}>
                  Модель (ModelConfig)
                </label>

                {isModelConfigsLoading ? (
                  <LoadingBlock text="Загружаем список моделей..." rows={2} />
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
                    onChange={(event) =>
                      setSelectedModelConfigId(event.target.value || null)
                    }
                    disabled={isUiLocked}
                  >
                    {modelConfigs.map((modelConfig) => (
                      <option
                        key={String(modelConfig.id)}
                        value={String(modelConfig.id)}
                      >
                        {modelConfig.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="flex justify-start">
                <Button
                  variant="secondary"
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
                {visibleVersions.map((version) => {
                  const versionId = String(version.id);
                  const isSelected = selectedVersionId === versionId;

                  return (
                    <li key={versionId}>
                      <button
                        type="button"
                        onClick={() => handleSelectVersion(versionId)}
                        disabled={isUiLocked}
                        className={[
                          cardButtonBaseClassName,
                          isSelected
                            ? cardButtonActiveClassName
                            : cardButtonIdleClassName,
                        ].join(" ")}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold">
                            {version.name}{" "}
                            <span className="text-[11px] font-normal text-[var(--text-muted)]">
                              ({version.semver})
                            </span>
                          </span>

                          <VersionStatusBadge status={version.status} />
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>

              {isSelectedVersionDraft && (
                <div className="mt-2 rounded-lg border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-xs text-[var(--color-warning-text)]">
                  Черновик нельзя применить к проекту — сначала опубликуйте
                  версию в Playbook Studio.
                </div>
              )}

              <div className="mt-4 flex items-center justify-end border-t border-[var(--border-soft)] pt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleApplyPlaybook}
                  disabled={
                    !selectedVersionId ||
                    isApplying ||
                    isSameAsCurrent ||
                    isSelectedVersionDraft
                  }
                  isLoading={isApplying}
                >
                  {isSameAsCurrent ? "Уже применено" : "Применить к проекту"}
                </Button>
              </div>
            </>
          )}
        </PageSection>

        <div className={mode === "embedded" ? "xl:col-span-2" : undefined}>
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
            {!selectedLineId ? (
              <EmptyState
                title="Ничего не выбрано"
                description="Выберите шаблон playbook, затем версию."
              />
            ) : selectedVersionId && versionDetail ? (
              <div className="max-h-80 space-y-3 overflow-y-auto text-xs text-[var(--text-primary)]">
                <div>
                  <div className={metaLabelClassName}>Общая информация</div>
                  <div className="mt-1 flex items-center gap-2 text-[var(--text-secondary)]">
                    <span>
                      {versionDetail.name} ({versionDetail.semver})
                    </span>
                    <VersionStatusBadge status={versionDetail.status} />
                  </div>
                </div>

                <div>
                  <div className={`mt-2 ${metaLabelClassName}`}>
                    Секции / профили
                  </div>

                  {versionDetail.section_markers ? (
                    <pre className="mt-1 overflow-x-auto rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-2 text-[11px] text-[var(--text-secondary)]">
                      {JSON.stringify(versionDetail.section_markers, null, 2)}
                    </pre>
                  ) : (
                    <div className="mt-1 text-[var(--text-muted)]">
                      Section markers не заданы.
                    </div>
                  )}
                </div>

                <div>
                  <div className={`mt-2 ${metaLabelClassName}`}>
                    DD-запросы
                  </div>

                  {versionDetail.dd_request_templates ? (
                    <pre className="mt-1 overflow-x-auto rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-2 text-[11px] text-[var(--text-secondary)]">
                      {JSON.stringify(
                        versionDetail.dd_request_templates,
                        null,
                        2,
                      )}
                    </pre>
                  ) : (
                    <div className="mt-1 text-[var(--text-muted)]">
                      DD request templates не заданы.
                    </div>
                  )}
                </div>
              </div>
            ) : selectedLineDetail ? (
              <div className="max-h-80 space-y-3 overflow-y-auto text-xs text-[var(--text-primary)]">
                <div>
                  <div className={metaLabelClassName}>Шаблон</div>
                  <div className="mt-1 font-medium text-[var(--text-secondary)]">
                    {selectedLineDetail.title}
                  </div>
                  <div className="mt-0.5 text-[var(--text-muted)]">
                    {[
                      selectedLineDetail.deal_type &&
                        `Тип: ${selectedLineDetail.deal_type}`,
                      selectedLineDetail.jurisdiction &&
                        `Юрисдикция: ${selectedLineDetail.jurisdiction}`,
                      selectedLineDetail.language &&
                        `Язык: ${selectedLineDetail.language}`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>

                  {selectedLineDetail.description && (
                    <div className="mt-1 text-[var(--text-muted)]">
                      {selectedLineDetail.description}
                    </div>
                  )}
                </div>

                <div>
                  <div className={`mt-2 ${metaLabelClassName}`}>
                    Проверки шаблона
                  </div>

                  {selectedLineDetail.items?.length > 0 ? (
                    <ul className="mt-1 space-y-1">
                      {selectedLineDetail.items.map((item, index) => (
                        <li
                          key={index}
                          className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1"
                        >
                          <div className="font-mono text-[10px] text-[var(--text-secondary)]">
                            {item.instruction_code}
                          </div>
                          <div className="text-[10px] text-[var(--text-muted)]">
                            {item.kind} · #{item.order_index}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="mt-1 text-[var(--text-muted)]">
                      В шаблоне пока нет элементов.
                    </div>
                  )}
                </div>
              </div>
            ) : selectedLineId ? (
              <LoadingBlock text="Загружаем состав playbook..." rows={4} />
            ) : null}

            <div className="mt-5 border-t border-[var(--border-soft)] pt-3">
              <h3 className={`mb-2 ${metaLabelClassName}`}>
                История смен playbook
              </h3>

              {isHistoryLoading ? (
                <LoadingBlock text="Загружаем историю..." rows={3} />
              ) : historyError ? (
                <InlineAlert tone="error" message={historyError} />
              ) : history.length === 0 ? (
                <EmptyState
                  title="История пока пустая"
                  description="Нет записей об изменении playbook для этой сделки."
                />
              ) : (
                <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
                  {history.map((item, index) => (
                    <li
                      key={index}
                      className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1"
                    >
                      <div className="text-[var(--text-secondary)]">
                        {new Date(item.created_at).toLocaleString()} —{" "}
                        {item.actor}
                        {item.actor_role && (
                          <span className="text-[var(--text-muted)]">
                            {" "}
                            ({item.actor_role})
                          </span>
                        )}
                      </div>

                      <div className="text-[var(--text-muted)]">
                        {item.old_playbook_version_id
                          ? `Было: ${item.old_playbook_version_id}`
                          : "Было: не задано"}{" "}
                        →{" "}
                        {item.new_playbook_version_id
                          ? item.new_playbook_version_id
                          : "не задано"}
                      </div>

                      {(item.playbook_name || item.semver) && (
                        <div className="text-[var(--text-muted)]">
                          {item.playbook_name}{" "}
                          {item.semver ? `(${item.semver})` : ""}
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
    </>
  );

  if (mode === "page") {
    return (
      <>
        <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
          <div className="animate-fadein space-y-6">{content}</div>
        </div>

        <ConfirmDialog
          open={isApplyConfirmOpen}
          title="Заменить текущий playbook?"
          description="Текущая версия playbook будет заменена. Продолжить?"
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
  }

  return (
    <>
      <PageSection
        title="Playbook проекта"
        subtitle="Выбор, применение и просмотр состава playbook."
        rightSlot={headerActions}
      >
        <div className="min-w-0 text-[var(--text-primary)]">{content}</div>
      </PageSection>

      <ConfirmDialog
        open={isApplyConfirmOpen}
        title="Заменить текущий playbook?"
        description="Текущая версия playbook будет заменена. Продолжить?"
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

export default DealPlaybookSelectorPanel;


