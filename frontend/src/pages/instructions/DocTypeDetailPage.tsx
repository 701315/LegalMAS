// src/pages/instructions/DocTypeDetailPage.tsx
// Объединённая страница: инструкция + версии + редактор версии.
//
// URL:
//   /admin/instructions/doc-types/:docType
//   /admin/instructions/doc-types/:docType?version=<id>

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Copy, Eye, GitBranch, Plus } from "lucide-react";

import {
  useDocTypeVersions,
  useInstructionCatalog,
  useInstructionVersionDetail,
  useCloneInstructionDraft,
  useValidateInstructionDraft,
  usePublishInstructionDraft,
} from "../../hooks/instructions/useInstructionVersions";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import DraftEditForm from "../../components/instructions/DraftEditForm";
import ValidationResultPanel from "../../components/instructions/ValidationResultPanel";
import PublishConfirmDialog from "../../components/instructions/PublishConfirmDialog";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type {
  InstructionVersionDetailItem,
  InstructionVersionItem,
  InstructionVersionValidationResponse,
} from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Утилиты
// ─────────────────────────────────────────────────────────────

function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    return new Date(value).toLocaleDateString("ru-RU");
  } catch {
    return null;
  }
}

function pickDefaultVersionId(
  versions: InstructionVersionItem[],
): string | null {
  if (versions.length === 0) return null;
  const draft = versions.find((v) => v.version_status === "draft");
  if (draft) return draft.id;
  const published = versions.find((v) => v.version_status === "published");
  if (published) return published.id;
  return versions[0].id;
}

// ─────────────────────────────────────────────────────────────
// DocTypeInfoCard
// ─────────────────────────────────────────────────────────────

interface DocTypeInfoCardProps {
  docTypeCode: string;
  name: string;
  totalVersions: number;
  hasPublished: boolean;
  draftCount: number;
}

const DocTypeInfoCard: React.FC<DocTypeInfoCardProps> = ({
  docTypeCode,
  name,
  totalVersions,
  hasPublished,
  draftCount,
}) => (
  <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
    <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
      О типе документа
    </h3>

    <div className="mt-3 space-y-3">
      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
          Название
        </div>
        <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
          {name}
        </div>
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
          Код
        </div>
        <div className="mt-0.5 break-all font-mono text-xs text-[var(--text-secondary)]">
          {docTypeCode}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
            Всего
          </div>
          <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
            {totalVersions}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
            Published
          </div>
          <div
            className={[
              "mt-0.5 text-sm font-semibold",
              hasPublished
                ? "text-[color:var(--color-success-text)]"
                : "text-[var(--text-muted)]",
            ].join(" ")}
          >
            {hasPublished ? "да" : "нет"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
            Draft
          </div>
          <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
            {draftCount}
          </div>
        </div>
      </div>
    </div>
  </section>
);

// ─────────────────────────────────────────────────────────────
// SelectedVersionCard
// ─────────────────────────────────────────────────────────────

interface SelectedVersionCardProps {
  version: InstructionVersionDetailItem | null;
  docType: string;
  onNavigateToParent: (parentVersionId: string) => void;
}

const SelectedVersionCard: React.FC<SelectedVersionCardProps> = ({
  version,
  onNavigateToParent,
}) => (
  <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
    <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
      Выбранная версия
    </h3>

    {version ? (
      <div className="mt-3 space-y-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
            Название
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              {version.name ?? "Без названия"}
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
                  Semver
                </div>
                <div className="mt-0.5 font-mono text-xs text-[var(--text-primary)]">
                  v{version.semver}
                </div>
              </div>
            )}
            {version.published_at && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  Published
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-primary)]">
                  {formatDate(version.published_at)}
                </div>
              </div>
            )}
          </div>
        )}

        {version.change_summary && (
          <div className="border-t border-[var(--border-soft)] pt-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              Описание изменений
            </div>
            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
              {version.change_summary}
            </p>
          </div>
        )}

        {version.parent_version_id && (
          <div className="border-t border-[var(--border-soft)] pt-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              На основе версии
            </div>
            <button
              type="button"
              onClick={() => onNavigateToParent(version.parent_version_id!)}
              className="mt-1 break-all font-mono text-[11px] text-[var(--accent-primary)] hover:underline"
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
            Название
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
              Semver
            </div>
            <div className="mt-1 h-3 w-12 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
              Published
            </div>
            <div className="mt-1 h-3 w-20 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
          </div>
        </div>
      </div>
    )}
  </section>
);

// ─────────────────────────────────────────────────────────────
// VersionSidebarItem
// ─────────────────────────────────────────────────────────────

interface VersionSidebarItemProps {
  version: InstructionVersionItem;
  isSelected: boolean;
  onClick: () => void;
}

const VersionSidebarItem: React.FC<VersionSidebarItemProps> = ({
  version,
  isSelected,
  onClick,
}) => {
  const publishedAt = formatDate(version.published_at);
  const updatedAt = formatDate(version.updated_at);
  const displayDate = publishedAt ?? updatedAt;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isSelected ? "true" : undefined}
      className={[
        "group w-full rounded-xl border px-3 py-2.5 text-left transition-all",
        isSelected
          ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] shadow-sm"
          : "border-[var(--border-soft)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-[var(--text-primary)]">
            {version.name ?? "Без названия"}
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
  versions: InstructionVersionItem[];
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
  versions: InstructionVersionItem[];
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
  const drafts = versions.filter((v) => v.version_status === "draft");
  const published = versions.filter((v) => v.version_status === "published");
  const archived = versions.filter((v) => v.version_status === "archived");

  return (
    <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Версии
        </h3>
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
          <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{versions.length}</span>
        </div>
      </div>

      <div className="mt-3">
        {isLoading && <LoadingBlock text="Загружаем версии…" rows={3} />}

        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить версии инструкции."
          />
        )}

        {!isLoading && !isError && versions.length === 0 && (
          <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-4 text-center text-[11px] text-[var(--text-muted)]">
            Для этого типа документа ещё нет версий.
          </p>
        )}

        {!isLoading && !isError && versions.length > 0 && (
          <div className="space-y-4">
            {drafts.length > 0 && (
              <VersionGroup
                label="Черновики"
                count={drafts.length}
                versions={drafts}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
            {published.length > 0 && (
              <VersionGroup
                label="Published"
                count={published.length}
                versions={published}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
            {archived.length > 0 && (
              <VersionGroup
                label="Archived"
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
  docType: string;
  versionId: string;
  hasAnyDraft: boolean;
  onVersionLoaded: (version: InstructionVersionDetailItem) => void;
  onDraftCreated: (newDraftId: string) => void;
}

const VersionEditorPane: React.FC<VersionEditorPaneProps> = ({
  docType,
  versionId,
  hasAnyDraft,
  onVersionLoaded,
  onDraftCreated,
}) => {
  const navigate = useNavigate();

  const {
    data: version,
    isLoading,
    isError,
    refetch,
  } = useInstructionVersionDetail(versionId);

  const cloneDraft = useCloneInstructionDraft();
  const validateDraft = useValidateInstructionDraft();
  const publishDraft = usePublishInstructionDraft();

  const [validationResult, setValidationResult] =
    useState<InstructionVersionValidationResponse | null>(null);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setValidationResult(null);
    setActionError(null);
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
          change_summary: `Клон версии ${version?.name ?? versionId}`,
        },
      });
      onDraftCreated(newDraft.id);
    } catch {
      setActionError("Не удалось создать черновик. Попробуйте ещё раз.");
    }
  };

  const handleValidate = async () => {
    setActionError(null);
    setValidationResult(null);
    try {
      const result = await validateDraft.mutateAsync({ versionId });
      setValidationResult(result);
    } catch {
      setActionError("Не удалось выполнить валидацию. Попробуйте ещё раз.");
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
      setActionError(
        "Не удалось опубликовать версию. Убедитесь что валидация прошла успешно.",
      );
    }
  };

  // ── Loading / Error ────────────────────────────────────────

  if (isLoading) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <LoadingBlock text="Загружаем версию инструкции…" rows={6} />
      </section>
    );
  }

  if (isError || !version) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <InlineAlert
          tone="error"
          message="Не удалось загрузить версию инструкции. Проверьте корректность ссылки."
        />
        <div className="mt-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              navigate(`/admin/instructions/doc-types/${docType}`)
            }
          >
            ← К типу документа
          </Button>
        </div>
      </section>
    );
  }

  const alerts = actionError ? (
    <InlineAlert tone="error" message={actionError} />
  ) : null;

  // ── Published / Archived ───────────────────────────────────

  if (isPublished || isArchived) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        {alerts}

        {isPublished && (
          <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                  Редактировать эту версию
                </h3>
                <p className="mt-0.5 max-w-2xl text-xs text-[var(--text-muted)]">
                  {hasAnyDraft
                    ? "У этого типа документа уже есть активный черновик. Откройте его в списке версий слева, чтобы продолжить редактирование."
                    : "Published-версия immutable. Создайте черновик на основе этой версии, чтобы внести изменения."}
                </p>
              </div>
              {hasAnyDraft ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onDraftCreated("__navigate_to_draft__")}
                  leftIcon={<Eye className="h-3.5 w-3.5" />}
                  className="shrink-0"
                >
                  Открыть черновик
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleCloneDraft()}
                  isLoading={cloneDraft.isPending}
                  disabled={cloneDraft.isPending}
                  leftIcon={<Copy className="h-3.5 w-3.5" />}
                  className="shrink-0"
                >
                  Создать черновик
                </Button>
              )}
            </div>
          </section>
        )}

        {isArchived && (
          <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-5">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)]">
              Archived-версия
            </h3>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              Эта версия выведена из активного использования. Можно просмотреть
              YAML ниже.
            </p>
          </section>
        )}

        {version.source_yaml && (
          <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                Source YAML
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
      </div>
    );
  }

  // ── Draft: editable ────────────────────────────────────────

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      {alerts}

      <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">
          Редактирование черновика
        </h3>
        <DraftEditForm
          versionId={version.id}
          initialData={version}
          onSaveSuccess={() => void refetch()}
          instructionType="doc-type"
        />
      </section>

      <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Валидация
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Проверьте черновик перед публикацией. Валидация выполняется на
            сервере.
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
                  ? "Валидация прошла. Можно публиковать."
                  : "Исправьте ошибки и валидируйте снова."
                : "Запустите валидацию перед публикацией."}
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
              Валидировать
            </Button>
          </div>
        </div>
      </section>

      <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Публикация
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Доступна только после успешной валидации.
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--text-muted)]">
            {canPublish
              ? "Черновик готов к публикации. После публикации версия станет immutable."
              : "Сначала выполните валидацию и убедитесь, что ошибок нет."}
          </p>
          <Button
            variant="primary"
            size="sm"
            type="button"
            onClick={() => setShowPublishDialog(true)}
            disabled={!canPublish}
            className="shrink-0"
          >
            Опубликовать
          </Button>
        </div>
      </section>

      <PublishConfirmDialog
        open={showPublishDialog}
        versionName={version.name ?? version.doc_type_code}
        docTypeCode={version.doc_type_code}
        isPublishing={publishDraft.isPending}
        onConfirm={() => void handlePublishConfirm()}
        onCancel={() => setShowPublishDialog(false)}
      />
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// DocTypeDetailPage
// ─────────────────────────────────────────────────────────────

const DocTypeDetailPage: React.FC = () => {
  const { docType } = useParams<{ docType: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const versionParam = searchParams.get("version");

  const { data: catalog } = useInstructionCatalog();
  const catalogItem =
    catalog?.items.find((i) => i.doc_type_code === docType) ?? null;

  const {
    data: versionsData,
    isLoading: isVersionsLoading,
    isError: isVersionsError,
  } = useDocTypeVersions(docType ?? null);

  const versions = useMemo(
    () => versionsData?.items ?? [],
    [versionsData?.items],
  );

  const [selectedVersionDetail, setSelectedVersionDetail] =
    useState<InstructionVersionDetailItem | null>(null);

  const pendingVersionIdRef = useRef<string | null>(null);

  // Автовыбор дефолтной версии
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

  // Сброс pending ref когда новая версия появилась в списке
  useEffect(() => {
    if (!pendingVersionIdRef.current) return;
    const pendingId = pendingVersionIdRef.current;
    if (versions.some((v) => v.id === pendingId)) {
      pendingVersionIdRef.current = null;
    }
  }, [versions]);

  const selectedVersionId: string | null = (() => {
    if (pendingVersionIdRef.current) return pendingVersionIdRef.current;
    if (versionParam && versions.some((v) => v.id === versionParam)) {
      return versionParam;
    }
    return pickDefaultVersionId(versions);
  })();

  // Сброс detail при смене версии
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

  const handleDraftCreated = useCallback(
    (newDraftId: string) => {
      if (newDraftId === "__navigate_to_draft__") {
        const firstDraft = versions.find((v) => v.version_status === "draft");
        if (firstDraft) {
          setSearchParams({ version: firstDraft.id }, { replace: false });
        }
        return;
      }
      pendingVersionIdRef.current = newDraftId;
      setSearchParams({ version: newDraftId }, { replace: false });
    },
    [versions, setSearchParams],
  );

  const draftCount = versions.filter(
    (v) => v.version_status === "draft",
  ).length;
  const hasPublished = versions.some((v) => v.version_status === "published");
  const totalVersions = versions.length;
  const hasAnyDraft = draftCount > 0;

  const displayName =
    catalogItem?.name ?? docType ?? "Doc-Type";

  return (
    <div className="h-full overflow-hidden px-6 py-6 md:px-8 md:py-8">
      <div className="flex h-full min-h-0 flex-col gap-6">

        {/* ── Back-link ──────────────────────────────────────── */}
        <button
          type="button"
          onClick={() => navigate("/admin/instructions/doc-types")}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Инструкции по типам документов
        </button>

        {/* ── Header ─────────────────────────────────────────── */}
        <header className="shrink-0">
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            {displayName}
          </h1>
          {docType && displayName !== docType && (
            <p className="mt-0.5 font-mono text-xs text-[var(--text-muted)]">
              {docType}
            </p>
          )}
        </header>

        {/* ── Empty state ────────────────────────────────────── */}
        {!isVersionsLoading && !isVersionsError && versions.length === 0 && (
          <EmptyState
            title="Версий нет"
            description="Для этого типа документа ещё не создано ни одной версии."
            action={
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<Plus className="h-3.5 w-3.5" />}
                onClick={() =>
                  navigate(
                    `/admin/instructions/doc-types/${docType}/versions/new`,
                  )
                }
              >
                Создать первый draft
              </Button>
            }
          />
        )}

        {/* ── Основной layout: sidebar 1/3 + editor 2/3 ─────── */}
        {(isVersionsLoading || versions.length > 0) && (
          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">

            {/* Sidebar */}
            <div className="flex min-h-0 flex-col gap-4 overflow-y-auto xl:col-span-1">
              <DocTypeInfoCard
                docTypeCode={docType ?? ""}
                name={displayName}
                totalVersions={totalVersions}
                hasPublished={hasPublished}
                draftCount={draftCount}
              />

              {selectedVersionId && (
                <SelectedVersionCard
                  version={selectedVersionDetail}
                  docType={docType ?? ""}
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
            <div className="flex min-h-0 min-w-0 flex-col xl:col-span-2">
              {selectedVersionId && docType ? (
                <VersionEditorPane
                  key={selectedVersionId}
                  docType={docType}
                  versionId={selectedVersionId}
                  hasAnyDraft={hasAnyDraft}
                  onVersionLoaded={setSelectedVersionDetail}
                  onDraftCreated={handleDraftCreated}
                />
              ) : (
                <section className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated-soft)] p-10 text-center">
                  <p className="text-sm text-[var(--text-muted)]">
                    Выберите версию из списка слева.
                  </p>
                </section>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocTypeDetailPage;



