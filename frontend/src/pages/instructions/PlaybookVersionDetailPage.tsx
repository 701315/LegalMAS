// src/pages/instructions/PlaybookVersionDetailPage.tsx
// Detail страница версии global playbook.
// Read-only — global playbook versions управляются через playbook domain.

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";

import {
  useGlobalPlaybooks,
  useGlobalPlaybookVersions,
} from "../../hooks/instructions/useInstructionVersions";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

const PlaybookVersionDetailPage: React.FC = () => {
  const { t } = useTranslation("playbooks");
  const { playbookId, versionId } = useParams<{
    playbookId: string;
    versionId: string;
  }>();
  const navigate = useNavigate();

  const { data: playbooks, isLoading: isPlaybooksLoading } =
    useGlobalPlaybooks();
  const playbook = playbooks?.find((p) => p.id === playbookId) ?? null;

  const {
    data: versions,
    isLoading: isVersionsLoading,
    isError,
    refetch,
  } = useGlobalPlaybookVersions(playbookId ?? null);

  const version = versions?.find((v) => v.id === versionId) ?? null;

  const isLoading = isPlaybooksLoading || isVersionsLoading;

  // ── Loading ─────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein p-4 md:p-5">
          <LoadingBlock text={t("globalPlaybookDetail.versionPage.loading")} rows={4} />
        </div>
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────

  if (isError || (!isLoading && !version)) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein space-y-3 p-4 md:p-5">
          <InlineAlert
            tone="error"
            message={t("globalPlaybookDetail.versionPage.notFoundError")}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(-1)}
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
          >
            {t("globalPlaybookDetail.versionPage.backAction")}
          </Button>
        </div>
      </div>
    );
  }

  // ── Not found ───────────────────────────────────────────────

  if (!version) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein p-4 md:p-5">
          <EmptyState
            title={t("globalPlaybookDetail.versionPage.notFoundTitle")}
            description={t("globalPlaybookDetail.versionPage.notFoundDescription")}
          />
        </div>
      </div>
    );
  }

  // ── Main ────────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ─────────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() =>
                  navigate(
                    `/admin/instructions/global-playbooks/${playbookId}`,
                  )
                }
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                {playbook?.title ?? t("globalPlaybookDetail.versionPage.fallbackPlaybookLabel")}
              </button>

              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                  {version.name}
                </h1>
                <VersionStatusBadge status={version.status} size="sm" />
              </div>

              {playbook?.title && (
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {t("globalPlaybookDetail.versionPage.playbookLabel", { title: playbook.title })}
                </p>
              )}
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              aria-label={t("globalPlaybookDetail.refreshAriaVersionData")}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              {t("globalPlaybookDetail.refreshAction")}
            </Button>
          </div>
        </header>

        {/* ── Метаданные версии ──────────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            {t("globalPlaybookDetail.versionPage.metadataSectionTitle")}
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {t("globalPlaybookDetail.versionPage.metadata.playbookId")}
              </div>
              <div className="mt-1 break-all font-mono text-[10px] text-[var(--text-primary)]">
                {version.playbook_id}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {t("globalPlaybookDetail.versionPage.metadata.versionId")}
              </div>
              <div className="mt-1 break-all font-mono text-[10px] text-[var(--text-primary)]">
                {version.id}
              </div>
            </div>
            {version.semver && (
              <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
                <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  {t("globalPlaybookDetail.versionPage.metadata.semver")}
                </div>
                <div className="mt-1 font-mono font-semibold text-[var(--text-primary)]">
                  v{version.semver}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── Информация ─────────────────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            {t("globalPlaybookDetail.versionPage.infoSectionTitle")}
          </h2>

          <div className="space-y-3">
            <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3">
              <p className="text-xs text-[var(--text-secondary)]">
                {t("globalPlaybookDetail.versionPage.readOnlyNotice")}
                <button
                  type="button"
                  onClick={() =>
                    navigate(`/projects/${playbookId}/playbooks/admin`)
                  }
                  className="text-[var(--accent-primary)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 rounded"
                >
                  {t("globalPlaybookDetail.versionPage.readOnlyLinkLabel")}
                </button>
                {t("globalPlaybookDetail.versionPage.readOnlyNoticeTail")}
              </p>
            </div>

            {versions && versions.length > 1 && (
              <div>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  {t("globalPlaybookDetail.versionPage.otherVersionsLabel")}
                </div>
                <ul className="space-y-1.5">
                  {versions
                    .filter((v) => v.id !== versionId)
                    .map((v) => (
                      <li key={v.id}>
                        <button
                          type="button"
                          onClick={() =>
                            navigate(
                              `/admin/instructions/global-playbooks/${playbookId}/versions/${v.id}`,
                            )
                          }
                          className="flex w-full items-center justify-between rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2.5 text-xs transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--bg-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                        >
                          <span className="font-medium text-[var(--text-primary)]">
                            {v.name}
                          </span>
                          <VersionStatusBadge status={v.status} size="xs" />
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default PlaybookVersionDetailPage;


