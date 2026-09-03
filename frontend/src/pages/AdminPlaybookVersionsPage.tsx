// src/pages/AdminPlaybookVersionsPage.tsx
// Админ-страница для управления версиями плейбуков (PlaybookVersion).
//
// Позволяет:
// - посмотреть список всех PlaybookVersion;
// - при наличии modelConfigId в query подсветить контекст;
// - сменить профиль модели для версии плейбука.

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, GitBranch, RefreshCw, Save } from "lucide-react";
import { useTranslation } from "react-i18next";

import client from "../api/client";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import InlineAlert from "../components/InlineAlert";
import LoadingBlock from "../components/ui/LoadingBlock";
import type { ApiError, PlaybookVersionShort, ModelConfig } from "../types";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface PageState {
  versions: PlaybookVersionShort[];
  modelConfigs: ModelConfig[];
  isLoading: boolean;
  error: string | null;
}

// ─────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────

const selectClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

// ─────────────────────────────────────────────────────────────
// SectionCard
// ─────────────────────────────────────────────────────────────

interface SectionCardProps {
  title: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
}

const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  rightSlot,
  children,
}) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {title}
        </h2>
        {subtitle && (
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">{subtitle}</p>
        )}
      </div>
      {rightSlot && <div className="shrink-0">{rightSlot}</div>}
    </div>
    {children}
  </section>
);

// ─────────────────────────────────────────────────────────────
// AdminPlaybookVersionsPage
// ─────────────────────────────────────────────────────────────

const AdminPlaybookVersionsPage: React.FC = () => {
  const { t } = useTranslation("admin");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const modelConfigIdFromQuery = searchParams.get("modelConfigId");

  const [state, setState] = useState<PageState>({
    versions: [],
    modelConfigs: [],
    isLoading: false,
    error: null,
  });

  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedModelConfigId, setSelectedModelConfigId] = useState<
    string | null
  >(modelConfigIdFromQuery);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // ── Data loading ────────────────────────────────────────
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
          t("versions.errors.loadVersions"),
      }));
    }
  };

  const loadModelConfigs = async () => {
    try {
      const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
      setState((prev) => ({ ...prev, modelConfigs: res.data || [] }));
    } catch (err) {
      const apiErr = err as ApiError;
      setState((prev) => ({
        ...prev,
        error:
          prev.error ||
          apiErr.detail ||
          t("versions.errors.loadConfigs"),
      }));
    }
  };

  useEffect(() => {
    void loadVersions();
    void loadModelConfigs();
  }, []);

  const handleRefresh = async () => {
    await Promise.all([loadVersions(), loadModelConfigs()]);
  };

  // ── Handlers ────────────────────────────────────────────
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
      setSaveSuccess(t("versions.success"));
    } catch (err) {
      const apiErr = err as ApiError;
      setSaveError(
        apiErr.detail || t("versions.errors.saveFailed"),
      );
    } finally {
      setIsSaving(false);
    }
  };

  // ── Derived ─────────────────────────────────────────────
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
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        {/* ── Back-link ────────────────────────────────────── */}
        <button
          type="button"
          onClick={() => navigate("/admin/instructions")}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t("versions.back")}
        </button>

        {/* ── Header ───────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-4">
          <header>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {t("versions.title")}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("versions.subtitle")}
            </p>
            {modelConfigIdFromQuery && (
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                {t("versions.contextPrefix")}{" "}
                <span className="font-mono text-[var(--text-secondary)]">
                  {modelConfigIdFromQuery.slice(0, 12)}…
                </span>
              </p>
            )}
          </header>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleRefresh()}
            aria-label={t("versions.refresh")}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
          />
        </div>

        {/* ── Alerts ───────────────────────────────────────── */}
        {state.error && <InlineAlert tone="error" message={state.error} />}
        {saveError && <InlineAlert tone="error" message={saveError} />}
        {saveSuccess && <InlineAlert tone="success" message={saveSuccess} />}

        {/* ── Main grid: узкая левая + широкая правая ─────── */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(320px,1fr)_2fr]">
          {/* ── Список версий ─────────────────────────────── */}
          <SectionCard
            title={t("versions.listTitle")}
            rightSlot={
              !state.isLoading && state.versions.length > 0 ? (
                <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                  <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{state.versions.length}</span>
                </div>
              ) : undefined
            }
          >
            {state.isLoading ? (
              <LoadingBlock text={t("versions.loading")} rows={5} />
            ) : state.versions.length === 0 ? (
              <EmptyState
                title={t("versions.emptyTitle")}
                description={t("versions.emptyDesc")}
              />
            ) : (
              <ul className="max-h-[36rem] space-y-1.5 overflow-y-auto">
                {state.versions.map((version) => {
                  const isSelected = selectedVersionId === version.id;
                  return (
                    <li key={version.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectVersion(version)}
                        className={[
                          "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors",
                          isSelected
                            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                            : "border-[var(--border-soft)] hover:border-[var(--border-strong)]",
                        ].join(" ")}
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="truncate font-semibold text-[var(--text-primary)]">
                              {version.name}
                            </span>
                            {version.semver && (
                              <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">
                                v{version.semver}
                              </span>
                            )}
                          </div>
                          <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
                            <span>{version.status}</span>
                            <span>·</span>
                            <span className="font-mono">
                              {version.id.slice(0, 8)}…
                            </span>
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </SectionCard>

          {/* ── Профиль модели для версии ─────────────────── */}
          <SectionCard
            title={t("versions.profileTitle")}
            subtitle={t("versions.profileSubtitle")}
          >
            {!selectedVersionId ? (
              <EmptyState
                title={t("versions.noVersionTitle")}
                description={t("versions.noVersionDesc")}
              />
            ) : state.modelConfigs.length === 0 ? (
              <EmptyState
                title={t("versions.noConfigsTitle")}
                description={t("versions.noConfigsDesc")}
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate("/admin/model-configs")}
                  >
                    {t("versions.openConfigs")}
                  </Button>
                }
              />
            ) : (
              <div className="space-y-4">
                {/* Selected version context */}
                <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                    {t("versions.selectedVersion")}
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {selectedVersion?.name}
                    </span>
                    {selectedVersion?.semver && (
                      <span className="font-mono text-[10px] text-[var(--text-muted)]">
                        v{selectedVersion.semver}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
                    <span>{selectedVersion?.status}</span>
                    <span>·</span>
                    <span className="font-mono">{selectedVersion?.id}</span>
                  </div>
                </div>

                {/* ModelConfig select */}
                <div>
                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    {t("versions.modelConfigLabel")}
                  </label>
                  <select
                    value={selectedModelConfigId || ""}
                    onChange={(e) => handleChangeModelConfig(e.target.value)}
                    className={selectClassName}
                    disabled={isSaving}
                  >
                    <option value="">
                      {t("versions.noProfileOption")}
                    </option>
                    {state.modelConfigs.map((mc) => (
                      <option key={mc.id} value={mc.id}>
                        {mc.name}
                      </option>
                    ))}
                  </select>
                  {selectedModelConfigName && (
                    <p className="mt-1.5 text-[10px] text-[var(--text-muted)]">
                      {t("versions.selectedProfilePrefix")}{" "}
                      <span className="font-semibold text-[var(--text-primary)]">
                        {selectedModelConfigName}
                      </span>
                    </p>
                  )}
                </div>

                {/* Explanation */}
                <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3 text-[11px] leading-relaxed text-[var(--text-muted)]">
                  {t("versions.explanation")}
                </div>

                {/* Save */}
                <div className="flex items-center justify-end border-t border-[var(--border-soft)] pt-3">
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    onClick={() => void handleSave()}
                    disabled={isSaving}
                    isLoading={isSaving}
                    leftIcon={<Save className="h-3.5 w-3.5" />}
                  >
                    {t("versions.saveButton")}
                  </Button>
                </div>
              </div>
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
};

export default AdminPlaybookVersionsPage;



