// =============================================================
// src/components/playbook/DealPlaybookSelectorPanel.tsx
// =============================================================

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";

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
  const { t } = useTranslation("playbooks");

  const map: Record<string, { label: string; cls: string }> = {
    draft: {
      label: t("selectorPanel.status.draft"),
      cls: "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
    },
    published: {
      label: t("selectorPanel.status.published"),
      cls: "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
    },
    archived: {
      label: t("selectorPanel.status.archived"),
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
  const { t, i18n } = useTranslation("playbooks");
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
          t("selectorPanel.errors.historyLoadFailed"),
        ),
      );
    } finally {
      setIsHistoryLoading(false);
    }
  }, [dealId, t]);

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
      setErrorText(t("selectorPanel.errors.noVersion"));
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
      setSuccessText(t("selectorPanel.errors.draftCreated")); // Note: matching semantic success text
      setIsApplyConfirmOpen(false);
      onFinished?.();
    } catch (err) {
      if (isApiErrorStatus(err, 409)) {
        setErrorText(
          getApiErrorMessage(
            err,
            t("selectorPanel.errors.conflict"),
          ),
        );
      } else {
        setErrorText(
          getApiErrorMessage(
            err,
            t("selectorPanel.errors.applyFailed"),
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
    t,
  ]);

  const handleApplyPlaybook = useCallback(async () => {
    if (!selectedVersionId) {
      setErrorText(t("selectorPanel.errors.noVersion"));
      return;
    }

    if (currentVersionId && currentVersionId !== selectedVersionId) {
      setIsApplyConfirmOpen(true);
      return;
    }

    await applyPlaybook();
  }, [applyPlaybook, currentVersionId, selectedVersionId, t]);

  const handleCreateVersionForSelectedLine = useCallback(async () => {
    if (!selectedLineId) return;

    if (!selectedModelConfigId) {
      setCreateVersionError(t("selectorPanel.errors.noModel"));
      return;
    }

    setIsCreatingVersion(true);
    setCreateVersionError(null);
    clearMessages();

    try {
      const line = lines.find((entry) => String(entry.id) === selectedLineId);

      const payload: PlaybookCreateRequest = {
        name: line?.title ?? t("selectorPanel.errors.defaultNewVersion"),
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
      setSuccessText(t("selectorPanel.errors.draftCreated"));
    } catch (err) {
      setCreateVersionError(
        getApiErrorMessage(err, t("selectorPanel.errors.createFailed")),
      );
    } finally {
      setIsCreatingVersion(false);
    }
  }, [clearMessages, lines, selectedLineId, selectedModelConfigId, t]);

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
              t("selectorPanel.templates.loading"),
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
  }, [effectiveDeal?.playbook_version_id, t]);

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
              t("selectorPanel.errors.modelsLoadFailed"),
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
  }, [t]);

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
                {t("selectorPanel.noPermissions")}
              </p>

              <Button variant="secondary" size="sm" onClick={handleBack}>
                {t("selectorPanel.backButton")}
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <PageSection
        title={t("selectorPanel.title")}
        subtitle={t("selectorPanel.subtitle")}
        rightSlot={headerActions}
      >
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center shadow-sm">
          <p className="text-sm text-[var(--text-secondary)]">
            {t("selectorPanel.noPermissions")}
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
            {t("selectorPanel.backLink")}
          </button>

          <header>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {t("selectorPanel.title")}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {effectiveDeal?.name ?? dealId}
            </p>

            {currentVersionId ? (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                <Trans
                  t={t}
                  i18nKey="selectorPanel.currentVersion"
                  values={{ versionId: currentVersionId }}
                  components={{
                    bold: (
                      <span className="font-medium text-[var(--text-primary)]" />
                    ),
                  }}
                />
              </p>
            ) : (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {t("selectorPanel.noVersionSelected")}
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
        <PageSection title={t("selectorPanel.templates.title")}>
          {isLoading ? (
            <LoadingBlock text={t("selectorPanel.templates.loading")} rows={6} />
          ) : lines.length === 0 ? (
            <EmptyState
              title={t("selectorPanel.templates.emptyTitle")}
              description={t("selectorPanel.templates.emptyDesc")}
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
                          line.deal_type &&
                            t("selectorPanel.templates.meta.type", {
                              type: line.deal_type,
                            }),
                          line.jurisdiction &&
                            t("selectorPanel.templates.meta.jurisdiction", {
                              jurisdiction: line.jurisdiction,
                            }),
                          line.language &&
                            t("selectorPanel.templates.meta.language", {
                              language: line.language,
                            }),
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

        <PageSection title={t("selectorPanel.versions.title")}>
          {createVersionError && (
            <InlineAlert tone="error" message={createVersionError} />
          )}

          {!selectedLineId ? (
            <EmptyState
              title={t("selectorPanel.versions.emptyLineTitle")}
              description={t("selectorPanel.versions.emptyLineDesc")}
            />
          ) : visibleVersions.length === 0 ? (
            <div className="space-y-3">
              <EmptyState
                title={t("selectorPanel.versions.emptyVersionsTitle")}
                description={t("selectorPanel.versions.emptyVersionsDesc")}
              />

              <div>
                <label className={`mb-1 block ${metaLabelClassName}`}>
                  {t("selectorPanel.versions.modelConfigLabel")}
                </label>

                {isModelConfigsLoading ? (
                  <LoadingBlock
                    text={t("selectorPanel.versions.loadingModels")}
                    rows={2}
                  />
                ) : modelConfigsError ? (
                  <InlineAlert tone="error" message={modelConfigsError} />
                ) : modelConfigs.length === 0 ? (
                  <EmptyState
                    title={t("selectorPanel.versions.noModelsTitle")}
                    description={t("selectorPanel.versions.noModelsDesc")}
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
                  {t("selectorPanel.versions.createDraftButton")}
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
                  {t("selectorPanel.versions.draftWarning")}
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
                  {isSameAsCurrent
                    ? t("selectorPanel.versions.alreadyApplied")
                    : t("selectorPanel.versions.applyButton")}
                </Button>
              </div>
            </>
          )}
        </PageSection>

        <div className={mode === "embedded" ? "xl:col-span-2" : undefined}>
          <PageSection
            title={t("selectorPanel.details.title")}
            rightSlot={
              selectedLineId ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleEditSelectedLine}
                  disabled={isUiLocked}
                >
                  {t("selectorPanel.details.editTemplate")}
                </Button>
              ) : null
            }
          >
            {!selectedLineId ? (
              <EmptyState
                title={t("selectorPanel.details.emptyTitle")}
                description={t("selectorPanel.details.emptyDesc")}
              />
            ) : selectedVersionId && versionDetail ? (
              <div className="max-h-80 space-y-3 overflow-y-auto text-xs text-[var(--text-primary)]">
                <div>
                  <div className={metaLabelClassName}>
                    {t("selectorPanel.details.generalInfo")}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[var(--text-secondary)]">
                    <span>
                      {versionDetail.name} ({versionDetail.semver})
                    </span>
                    <VersionStatusBadge status={versionDetail.status} />
                  </div>
                </div>

                <div>
                  <div className={`mt-2 ${metaLabelClassName}`}>
                    {t("selectorPanel.details.sectionsProfiles")}
                  </div>

                  {versionDetail.section_markers ? (
                    <pre className="mt-1 overflow-x-auto rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-2 text-[11px] text-[var(--text-secondary)]">
                      {JSON.stringify(versionDetail.section_markers, null, 2)}
                    </pre>
                  ) : (
                    <div className="mt-1 text-[var(--text-muted)]">
                      {t("selectorPanel.details.sectionsEmpty")}
                    </div>
                  )}
                </div>

                <div>
                  <div className={`mt-2 ${metaLabelClassName}`}>
                    {t("selectorPanel.details.ddRequests")}
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
                      {t("selectorPanel.details.ddRequestsEmpty")}
                    </div>
                  )}
                </div>
              </div>
            ) : selectedLineDetail ? (
              <div className="max-h-80 space-y-3 overflow-y-auto text-xs text-[var(--text-primary)]">
                <div>
                  <div className={metaLabelClassName}>
                    {t("selectorPanel.details.template")}
                  </div>
                  <div className="mt-1 font-medium text-[var(--text-secondary)]">
                    {selectedLineDetail.title}
                  </div>
                  <div className="mt-0.5 text-[var(--text-muted)]">
                    {[
                      selectedLineDetail.deal_type &&
                        t("selectorPanel.templates.meta.type", {
                          type: selectedLineDetail.deal_type,
                        }),
                      selectedLineDetail.jurisdiction &&
                        t("selectorPanel.templates.meta.jurisdiction", {
                          jurisdiction: selectedLineDetail.jurisdiction,
                        }),
                      selectedLineDetail.language &&
                        t("selectorPanel.templates.meta.language", {
                          language: selectedLineDetail.language,
                        }),
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
                    {t("selectorPanel.details.checks")}
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
                      {t("selectorPanel.details.checksEmpty")}
                    </div>
                  )}
                </div>
              </div>
            ) : selectedLineId ? (
              <LoadingBlock
                text={t("selectorPanel.details.loading")}
                rows={4}
              />
            ) : null}

            <div className="mt-5 border-t border-[var(--border-soft)] pt-3">
              <h3 className={`mb-2 ${metaLabelClassName}`}>
                {t("selectorPanel.history.title")}
              </h3>

              {isHistoryLoading ? (
                <LoadingBlock
                  text={t("selectorPanel.history.loading")}
                  rows={3}
                />
              ) : historyError ? (
                <InlineAlert tone="error" message={historyError} />
              ) : history.length === 0 ? (
                <EmptyState
                  title={t("selectorPanel.history.emptyTitle")}
                  description={t("selectorPanel.history.emptyDesc")}
                />
              ) : (
                <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
                  {history.map((item, index) => (
                    <li
                      key={index}
                      className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-2 py-1"
                    >
                      <div className="text-[var(--text-secondary)]">
                        {new Date(item.created_at).toLocaleString(
                          i18n.language,
                        )}{" "}
                        — {item.actor}
                        {item.actor_role && (
                          <span className="text-[var(--text-muted)]">
                            {" "}
                            ({item.actor_role})
                          </span>
                        )}
                      </div>

                      <div className="text-[var(--text-muted)]">
                        {t("selectorPanel.history.was", {
                          oldValue:
                            item.old_playbook_version_id ||
                            t("selectorPanel.history.wasNotSet"),
                        })}{" "}
                        {t("selectorPanel.history.to", {
                          newValue:
                            item.new_playbook_version_id ||
                            t("selectorPanel.history.notSet"),
                        })}
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
          title={t("selectorPanel.confirm.title")}
          description={t("selectorPanel.confirm.description")}
          confirmLabel={t("selectorPanel.confirm.confirmLabel")}
          cancelLabel={t("selectorPanel.confirm.cancelLabel")}
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
        title={t("selectorPanel.title")}
        subtitle={t("selectorPanel.subtitleEmbedded")}
        rightSlot={headerActions}
      >
        <div className="min-w-0 text-[var(--text-primary)]">{content}</div>
      </PageSection>

      <ConfirmDialog
        open={isApplyConfirmOpen}
        title={t("selectorPanel.confirm.title")}
        description={t("selectorPanel.confirm.description")}
        confirmLabel={t("selectorPanel.confirm.confirmLabel")}
        cancelLabel={t("selectorPanel.confirm.cancelLabel")}
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


