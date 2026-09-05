// =============================================================
// src/pages/instructions/GlobalInstructionDetailPage.tsx
// Combined detail workspace for global checks: metadata, versions sidebar, and draft editor.
//
// Routing parameters:
//   /admin/instructions/global-checks/:instructionCode
//   /admin/instructions/global-checks/:instructionCode?version=<id>
// =============================================================

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Copy, Eye, Plus, GitBranch, Archive } from "lucide-react";

import {
  useGlobalInstructionCatalog,
  useGlobalInstructionVersions,
  useGlobalInstructionVersionDetail,
  useCloneGlobalInstructionDraft,
  useValidateGlobalInstructionDraft,
  usePublishGlobalInstructionDraft,
  useCreateGlobalInstructionDraft,
  useArchiveGlobalInstructionVersion,
} from "../../hooks/instructions/useGlobalInstructions";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import DraftEditForm from "../../components/instructions/DraftEditForm";
import ValidationResultPanel from "../../components/instructions/ValidationResultPanel";
import PublishConfirmDialog from "../../components/instructions/PublishConfirmDialog";
import ConfirmDialog from "../../components/ui/ConfirmDialog";

import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type {
  GlobalInstructionVersionDetailItem,
  GlobalInstructionVersionItem,
  GlobalInstructionVersionValidationResponse,
} from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────

const EMPTY_INSTRUCTION_YAML_SKELETON = `id: new_instruction
name: New instruction
group: ""
description: ""
doc_types: []
severity: medium
detector_type: hybrid

llm:
  context_k: 5
  temperature: 0.0
  max_tokens: 700

retrieval:
  context_k: 6
  max_chunks: 10
  rerank: true

evidence:
  required: true
  min_snippet_length: 20
  max_snippet_length: 600
`;

// ─────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────

function formatDate(value: string | null | undefined, locale: string): string | null {
  if (!value) return null;
  try {
    return new Date(value).toLocaleDateString(locale);
  } catch {
    return null;
  }
}

function pickDefaultVersionId(
  versions: GlobalInstructionVersionItem[],
): string | null {
  if (versions.length === 0) return null;
  const drafts = versions.filter((v) => v.version_status === "draft");
  if (drafts.length > 0) return drafts[0].id;
  const published = versions.filter((v) => v.version_status === "published");
  if (published.length > 0) return published[0].id;
  return versions[0].id;
}

// ─────────────────────────────────────────────────────────────
// InstructionInfoCard
// ─────────────────────────────────────────────────────────────

interface InstructionInfoCardProps {
  instructionCode: string;
  name: string;
  group: string | null;
  totalVersions: number;
  hasPublished: boolean;
  draftCount: number;
}

const InstructionInfoCard: React.FC<InstructionInfoCardProps> = ({
  instructionCode,
  name,
  group,
  totalVersions,
  hasPublished,
  draftCount,
}) => {
  const { t } = useTranslation("instructions");

  return (
    <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {t("card.about")}
      </h3>

      <div className="mt-3 space-y-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
            {t("card.name")}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
            {name}
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
            {t("card.code")}
          </div>
          <div className="mt-0.5 break-all font-mono text-xs text-[var(--text-secondary)]">
            {instructionCode}
          </div>
        </div>

        {group && (
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              {t("card.group")}
            </div>
            <div className="mt-0.5 text-xs text-[var(--text-primary)]">{group}</div>
          </div>
        )}

        <div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
              {t("card.total")}
            </div>
            <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
              {totalVersions}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
              {t("card.published")}
            </div>
            <div
              className={[
                "mt-0.5 text-sm font-semibold",
                hasPublished
                  ? "text-[var(--color-success-text)]"
                  : "text-[var(--text-muted)]",
              ].join(" ")}
            >
              {hasPublished ? t("detail.hasPublishedYes") : t("detail.hasPublishedNo")}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
              {t("card.draft")}
            </div>
            <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
              {draftCount}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────
// SelectedVersionCard
// ─────────────────────────────────────────────────────────────

interface SelectedVersionCardProps {
  version: GlobalInstructionVersionDetailItem | null;
  onNavigateToParent: (parentVersionId: string) => void;
}

const SelectedVersionCard: React.FC<SelectedVersionCardProps> = ({
  version,
  onNavigateToParent,
}) => {
  const { t, i18n } = useTranslation("instructions");

  return (
    <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {t("card.selectedVersion")}
      </h3>

      {version ? (
        <div className="mt-3 space-y-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              {t("card.name")}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                {version.name ?? t("card.untitled")}
              </span>
              <VersionStatusBadge status={version.version_status} size="xs" />
            </div>
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              ID
            </div>
            <div className="mt-0.5 break-all font-mono text-[11px] text-[var(--text-secondary)]">
              {version.id}
            </div>
          </div>

          {(version.semver || version.published_at) && (
            <div className="grid grid-cols-2 gap-2">
              {version.semver && (
                <div>
                  <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                    {t("card.semver")}
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-[var(--text-primary)]">
                    v{version.semver}
                  </div>
                </div>
              )}
              {version.published_at && (
                <div>
                  <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                    {t("card.publishedLabel")}
                  </div>
                  <div className="mt-0.5 text-xs text-[var(--text-primary)]">
                    {formatDate(version.published_at, i18n.language)}
                  </div>
                </div>
              )}
            </div>
          )}

          {version.change_summary && (
            <div className="border-t border-[var(--border-soft)] pt-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("card.changeSummary")}
              </div>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                {version.change_summary}
              </p>
            </div>
          )}

          {version.parent_version_id && (
            <div className="border-t border-[var(--border-soft)] pt-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("card.basedOn")}
              </div>
              <button
                type="button"
                onClick={() => onNavigateToParent(version.parent_version_id!)}
                className="mt-1 break-all font-mono text-[11px] text-[var(--accent-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 rounded"
              >
                {version.parent_version_id}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-3 space-y-3" aria-hidden="true">
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              {t("card.name")}
            </div>
            <div className="mt-1 h-4 w-3/4 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              ID
            </div>
            <div className="mt-1 h-3 w-full animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("card.semver")}
              </div>
              <div className="mt-1 h-3 w-12 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {t("card.publishedLabel")}
              </div>
              <div className="mt-1 h-3 w-20 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// ─────────────────────────────────────────────────────────────
// VersionSidebarItem
// ─────────────────────────────────────────────────────────────

interface VersionSidebarItemProps {
  version: GlobalInstructionVersionItem;
  isSelected: boolean;
  onClick: () => void;
}

const VersionSidebarItem: React.FC<VersionSidebarItemProps> = ({
  version,
  isSelected,
  onClick,
}) => {
  const { t, i18n } = useTranslation("instructions");
  const publishedAt = formatDate(version.published_at, i18n.language);
  const updatedAt = formatDate(version.updated_at, i18n.language);
  const displayDate = publishedAt ?? updatedAt;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isSelected ? "true" : undefined}
      className={[
        "group w-full rounded-xl border px-3 py-2.5 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
        isSelected
          ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] shadow-sm"
          : "border-[var(--border-soft)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-[var(--text-primary)]">
            {version.name ?? t("card.untitled")}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-[var(--text-muted)]">
            <span className="font-mono">{version.id.slice(0, 8)}…</span>
            {displayDate && <span>{displayDate}</span>}
          </div>
        </div>
        <VersionStatusBadge status={version.version_status} size="xs" />
      </div>
    </button>
  );
};

// ─────────────────────────────────────────────────────────────
// VersionGroup + VersionsSidebar
// ─────────────────────────────────────────────────────────────

const VersionGroup: React.FC<{
  label: string;
  count: number;
  versions: GlobalInstructionVersionItem[];
  selectedVersionId: string | null;
  onSelectVersion: (id: string) => void;
}> = ({ label, count, versions, selectedVersionId, onSelectVersion }) => (
  <div>
    <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
      {label}{" "}
      <span className="text-[var(--text-faint)]">· {count}</span>
    </div>
    <div className="space-y-1.5">
      {versions.map((v) => (
        <VersionSidebarItem
          key={v.id}
          version={v}
          isSelected={v.id === selectedVersionId}
          onClick={() => onSelectVersion(v.id)}
        />
      ))}
    </div>
  </div>
);

interface VersionsSidebarProps {
  versions: GlobalInstructionVersionItem[];
  selectedVersionId: string | null;
  onSelectVersion: (versionId: string) => void;
  isLoading: boolean;
  isError: boolean;
}

const VersionsSidebar: React.FC<VersionsSidebarProps> = ({
  versions,
  selectedVersionId,
  onSelectVersion,
  isLoading,
  isError,
}) => {
  const { t } = useTranslation("instructions");
  const drafts = versions.filter((v) => v.version_status === "draft");
  const published = versions.filter((v) => v.version_status === "published");
  const archived = versions.filter((v) => v.version_status === "archived");

  return (
    <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {t("card.versions")}
        </h3>
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
          <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{versions.length}</span>
        </div>
      </div>

      <div className="mt-3">
        {isLoading && <LoadingBlock text={t("card.loadingVersions")} rows={3} />}

        {isError && (
          <InlineAlert
            tone="error"
            message={t("card.versionsError")}
          />
        )}

        {!isLoading && !isError && versions.length === 0 && (
          <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-4 text-center text-[11px] text-[var(--text-muted)]">
            {t("card.emptyVersions")}
          </p>
        )}

        {!isLoading && !isError && versions.length > 0 && (
          <div className="space-y-4">
            {drafts.length > 0 && (
              <VersionGroup
                label={t("card.draftsGroup")}
                count={drafts.length}
                versions={drafts}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
            {published.length > 0 && (
              <VersionGroup
                label={t("card.publishedGroup")}
                count={published.length}
                versions={published}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
            {archived.length > 0 && (
              <VersionGroup
                label={t("card.archivedGroup")}
                count={archived.length}
                versions={archived}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
          </div>
        )}
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────
// VersionEditorPane
// ─────────────────────────────────────────────────────────────

interface VersionEditorPaneProps {
  instructionCode: string;
  versionId: string;
  hasAnyDraft: boolean;
  onVersionLoaded: (version: GlobalInstructionVersionDetailItem) => void;
  onDraftCreated: (newDraftId: string) => void;
}

const VersionEditorPane: React.FC<VersionEditorPaneProps> = ({
  instructionCode,
  versionId,
  hasAnyDraft,
  onVersionLoaded,
  onDraftCreated,
}) => {
  const { t } = useTranslation("instructions");
  const navigate = useNavigate();

  const {
    data: version,
    isLoading,
    isError,
    refetch,
  } = useGlobalInstructionVersionDetail(versionId);

  const cloneDraft = useCloneGlobalInstructionDraft();
  const validateDraft = useValidateGlobalInstructionDraft();
  const publishDraft = usePublishGlobalInstructionDraft();
  const archiveVersion = useArchiveGlobalInstructionVersion();

  const [validationResult, setValidationResult] =
    useState<GlobalInstructionVersionValidationResponse | null>(null);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setValidationResult(null);
    setActionError(null);
    setShowArchiveDialog(false);
  }, [versionId]);

  useEffect(() => {
    if (version) {
      onVersionLoaded(version);
    }
  }, [version, onVersionLoaded]);

  const isDraft = version?.version_status === "draft";
  const isPublished = version?.version_status === "published";
  const isArchived = version?.version_status === "archived";
  const canPublish = isDraft && validationResult?.is_valid === true;

  const handleCloneDraft = async () => {
    setActionError(null);
    try {
      const newDraft = await cloneDraft.mutateAsync({
        versionId,
        body: {
          change_summary: t("editor.cloneSummary", {
            name: version?.name ?? versionId,
          }),
        },
      });
      onDraftCreated(newDraft.id);
    } catch {
      setActionError(t("editor.cloneDraftError"));
    }
  };

  const handleValidate = async () => {
    setActionError(null);
    setValidationResult(null);
    try {
      const result = await validateDraft.mutateAsync({ versionId });
      setValidationResult(result);
    } catch {
      setActionError(t("editor.validateDraftError"));
    }
  };

  const handlePublishConfirm = async () => {
    setActionError(null);
    try {
      await publishDraft.mutateAsync({ versionId });
      setShowPublishDialog(false);
      await refetch();
    } catch {
      setShowPublishDialog(false);
      setActionError(t("editor.publishDraftError"));
    }
  };

  if (isLoading) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <LoadingBlock text={t("detail.loading")} rows={6} />
      </section>
    );
  }

  if (isError || !version) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <InlineAlert
          tone="error"
          message={t("detail.error")}
        />
        <div className="mt-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              navigate(`/admin/instructions/global-checks/${instructionCode}`)
            }
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
          >
            {t("detail.backButton")}
          </Button>
        </div>
      </section>
    );
  }

  const handleArchiveConfirm = async () => {
    setActionError(null);
    try {
      await archiveVersion.mutateAsync({ versionId });
      setShowArchiveDialog(false);
      await refetch();
    } catch {
      setShowArchiveDialog(false);
      setActionError(t("editor.archiveVersionError"));
    }
  };

  const alerts = actionError ? (
    <InlineAlert tone="error" message={actionError} />
  ) : null;

  if (isPublished || isArchived) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        {alerts}

        {isPublished && (
          <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("editor.editPublished")}
                </h3>
                <p className="mt-0.5 max-w-2xl text-xs text-[var(--text-muted)]">
                  {hasAnyDraft
                    ? t("editor.hasDraftActive")
                    : t("editor.immutablePublished")}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {hasAnyDraft ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onDraftCreated("__navigate_to_draft__")}
                    leftIcon={<Eye className="h-3.5 w-3.5" />}
                  >
                    {t("editor.openDraftButton")}
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void handleCloneDraft()}
                    isLoading={cloneDraft.isPending}
                    disabled={cloneDraft.isPending}
                    leftIcon={<Copy className="h-3.5 w-3.5" />}
                  >
                    {t("editor.createDraftButton")}
                  </Button>
                )}

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowArchiveDialog(true)}
                  isLoading={archiveVersion.isPending}
                  disabled={archiveVersion.isPending}
                  leftIcon={<Archive className="h-3.5 w-3.5" />}
                >
                  {t("editor.archiveButton")}
                </Button>
              </div>
            </div>
          </section>
        )}

        {isArchived && (
          <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-[var(--text-secondary)]">
                  {t("editor.archivedVersionTitle")}
                </h3>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                  {t("editor.archivedVersionDesc")}
                </p>
              </div>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleCloneDraft()}
                isLoading={cloneDraft.isPending}
                disabled={cloneDraft.isPending}
                leftIcon={<Copy className="h-3.5 w-3.5" />}
                className="shrink-0"
              >
                {t("editor.restoreAsDraftButton")}
              </Button>
            </div>
          </section>
        )}

        {version.source_yaml && (
          <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("editor.sourceYaml")}
              </h3>
              <Eye
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
            </div>
            <pre className="min-h-0 flex-1 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono leading-relaxed text-[var(--text-primary)]">
              {version.source_yaml}
            </pre>
          </section>
        )}
        <ConfirmDialog
          open={showArchiveDialog}
          title={t("editor.archiveConfirmTitle")}
          description={t("editor.archiveConfirmDesc", { name: version.name ?? version.instruction_code })}
          confirmLabel={t("editor.archiveConfirmLabel")}
          cancelLabel={t("actions.cancel", { ns: "common" })}
          confirmVariant="danger"
          isLoading={archiveVersion.isPending}
          onConfirm={() => void handleArchiveConfirm()}
          onCancel={() => setShowArchiveDialog(false)}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      {alerts}

      <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">
          {t("editor.editDraft")}
        </h3>
        <DraftEditForm
          versionId={version.id}
          initialData={version}
          onSaveSuccess={() => void refetch()}
          instructionType="global"
        />
      </section>

      <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {t("editor.validation")}
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            {t("editor.validationDesc")}
          </p>
        </div>

        <div className="space-y-3">
          {validationResult && (
            <ValidationResultPanel result={validationResult} />
          )}

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-[var(--text-muted)]">
              {validationResult
                ? validationResult.is_valid
                  ? t("editor.validationSuccess")
                  : t("editor.validationFailed")
                : t("editor.validationPrompt")}
            </p>
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={() => void handleValidate()}
              isLoading={validateDraft.isPending}
              disabled={validateDraft.isPending}
              className="shrink-0"
            >
              {t("editor.validateButton")}
            </Button>
          </div>
        </div>
      </section>

      <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {t("editor.publishing")}
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            {t("editor.publishingDesc")}
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--text-muted)]">
            {canPublish
              ? t("editor.publishingReady")
              : t("editor.publishingPrompt")}
          </p>
          <Button
            variant="primary"
            size="sm"
            type="button"
            onClick={() => setShowPublishDialog(true)}
            disabled={!canPublish}
            className="shrink-0"
          >
            {t("editor.publishButton")}
          </Button>
        </div>
      </section>

      <PublishConfirmDialog
        open={showPublishDialog}
        versionName={version.name ?? version.instruction_code}
        docTypeCode={version.instruction_code}
        isPublishing={publishDraft.isPending}
        onConfirm={() => void handlePublishConfirm()}
        onCancel={() => setShowPublishDialog(false)}
      />
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// GlobalInstructionDetailPage
// ─────────────────────────────────────────────────────────────

const GlobalInstructionDetailPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const { instructionCode } = useParams<{ instructionCode: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const versionParam = searchParams.get("version");

  const { data: catalog } = useGlobalInstructionCatalog();
  const catalogItem =
    catalog?.items.find((i) => i.instruction_code === instructionCode) ?? null;

  const {
    data: versionsData,
    isLoading: isVersionsLoading,
    isError: isVersionsError,
  } = useGlobalInstructionVersions(instructionCode ?? null);

  const versions = useMemo(
    () => versionsData?.items ?? [],
    [versionsData?.items],
  );

  const createDraft = useCreateGlobalInstructionDraft();
  const [createDraftError, setCreateDraftError] = useState<string | null>(null);
  const [selectedVersionDetail, setSelectedVersionDetail] =
    useState<GlobalInstructionVersionDetailItem | null>(null);

  const pendingVersionIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (versions.length === 0) return;
    if (pendingVersionIdRef.current) return;
    const paramIsValid =
      versionParam && versions.some((v) => v.id === versionParam);
    if (paramIsValid) return;
    const defaultId = pickDefaultVersionId(versions);
    if (defaultId) {
      setSearchParams({ version: defaultId }, { replace: true });
    }
  }, [versions, versionParam, setSearchParams]);

  useEffect(() => {
    if (!pendingVersionIdRef.current) return;
    const pendingId = pendingVersionIdRef.current;
    const isInList = versions.some((v) => v.id === pendingId);
    if (isInList) {
      pendingVersionIdRef.current = null;
    }
  }, [versions]);

  const selectedVersionId: string | null = (() => {
    if (pendingVersionIdRef.current) return pendingVersionIdRef.current;
    if (versionParam && versions.some((v) => v.id === versionParam))
      return versionParam;
    return pickDefaultVersionId(versions);
  })();

  useEffect(() => {
    if (
      selectedVersionDetail &&
      selectedVersionDetail.id !== selectedVersionId
    ) {
      setSelectedVersionDetail(null);
    }
  }, [selectedVersionId, selectedVersionDetail]);

  const handleSelectVersion = (versionId: string) => {
    setSearchParams({ version: versionId }, { replace: false });
  };

  const handleNavigateToParent = (parentVersionId: string) => {
    setSearchParams({ version: parentVersionId }, { replace: false });
  };

  const handleDraftCreated = (newDraftId: string) => {
    if (newDraftId === "__navigate_to_draft__") {
      const firstDraft = versions.find((v) => v.version_status === "draft");
      if (firstDraft) {
        setSearchParams({ version: firstDraft.id }, { replace: false });
      }
      return;
    }
    pendingVersionIdRef.current = newDraftId;
    setSearchParams({ version: newDraftId }, { replace: false });
  };

  const handleCreateFirstDraft = async () => {
    if (!instructionCode) return;
    setCreateDraftError(null);
    try {
      const localizedYaml = EMPTY_INSTRUCTION_YAML_SKELETON.replace(
        "New instruction",
        t("detail.newInstructionSkeletonName"),
      );
      const newDraft = await createDraft.mutateAsync({
        instructionCode,
        body: {
          source_yaml: localizedYaml,
          change_summary: t("detail.firstDraftSummary"),
        },
      });
      pendingVersionIdRef.current = newDraft.id;
      setSearchParams({ version: newDraft.id }, { replace: false });
    } catch {
      setCreateDraftError(t("detail.createDraftError"));
    }
  };

  const draftCount = versions.filter((v) => v.version_status === "draft").length;
  const hasPublished = versions.some((v) => v.version_status === "published");
  const totalVersions = versions.length;
  const hasAnyDraft = draftCount > 0;

  const displayName =
    catalogItem?.name ?? instructionCode ?? t("detail.fallbackTitle");

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">

      {/* ── Шапка ─────────────────────────────────────────────── */}
      <header className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <button
              type="button"
              onClick={() => navigate("/admin/instructions/global-checks")}
              className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              {t("detail.backToList")}
            </button>

            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {displayName}
            </h1>

            {instructionCode && (
              <p className="mt-2 font-mono text-sm text-[var(--text-secondary)]">
                {instructionCode}
              </p>
            )}
          </div>
        </div>
      </header>

      {/* ── Top-level alerts ──────────────────────────────────── */}
      {createDraftError && (
        <div className="shrink-0">
          <InlineAlert tone="error" message={createDraftError} />
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────── */}
      {!isVersionsLoading && !isVersionsError && versions.length === 0 && (
        <EmptyState
          title={t("detail.emptyVersionsTitle")}
          description={t("detail.emptyVersionsDesc")}
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleCreateFirstDraft()}
              isLoading={createDraft.isPending}
              disabled={createDraft.isPending}
              leftIcon={<Plus className="h-3.5 w-3.5" />}
            >
              {t("detail.createFirstDraft")}
            </Button>
          }
        />
      )}

      {/* ── Основной layout ───────────────────────────────────── */}
      {(isVersionsLoading || versions.length > 0) && (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">

          {/* Sidebar */}
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto overscroll-contain xl:col-span-1">
            <InstructionInfoCard
              instructionCode={instructionCode ?? ""}
              name={displayName}
              group={catalogItem?.group ?? null}
              totalVersions={totalVersions}
              hasPublished={hasPublished}
              draftCount={draftCount}
            />

            {selectedVersionId && (
              <SelectedVersionCard
                version={selectedVersionDetail}
                onNavigateToParent={handleNavigateToParent}
              />
            )}

            <VersionsSidebar
              versions={versions}
              selectedVersionId={selectedVersionId}
              onSelectVersion={handleSelectVersion}
              isLoading={isVersionsLoading}
              isError={isVersionsError}
            />
          </div>

          {/* Editor pane */}
          <div className="flex min-h-0 min-w-0 flex-col overflow-y-auto overscroll-contain xl:col-span-2">
            {selectedVersionId && instructionCode ? (
              <VersionEditorPane
                key={selectedVersionId}
                instructionCode={instructionCode}
                versionId={selectedVersionId}
                hasAnyDraft={hasAnyDraft}
                onVersionLoaded={setSelectedVersionDetail}
                onDraftCreated={handleDraftCreated}
              />
            ) : (
              <section className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated-soft)] p-10 text-center">
                <p className="text-sm text-[var(--text-muted)]">
                  {t("detail.selectVersionPrompt")}
                </p>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default GlobalInstructionDetailPage;


