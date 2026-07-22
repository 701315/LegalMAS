// src/pages/instructions/DocTypeVersionDetailPage.tsx
// Detail страница конкретной instruction version.
//
// Режимы:
// - published/archived: read-only, кнопка "Clone as draft"
// - draft: DraftEditForm + Validate + Publish flow

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Copy,
  Eye,
  RefreshCw,
} from "lucide-react";

import { useInstructionVersionDetail } from "../../hooks/instructions/useInstructionVersions";
import {
  useCloneInstructionDraft,
  useValidateInstructionDraft,
  usePublishInstructionDraft,
} from "../../hooks/instructions/useInstructionVersions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import DraftEditForm from "../../components/instructions/DraftEditForm";
import ValidationResultPanel from "../../components/instructions/ValidationResultPanel";
import PublishConfirmDialog from "../../components/instructions/PublishConfirmDialog";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { InstructionVersionValidationResponse } from "../../types/instructions";

const DocTypeVersionDetailPage: React.FC = () => {
  const { docType, versionId } = useParams<{
    docType: string;
    versionId: string;
  }>();
  const navigate = useNavigate();

  // ── Data fetching ──────────────────────────────────────────
  const {
    data: version,
    isLoading,
    isError,
    refetch,
  } = useInstructionVersionDetail(versionId ?? null);

  // ── Mutations ──────────────────────────────────────────────
  const cloneDraft = useCloneInstructionDraft();
  const validateDraft = useValidateInstructionDraft();
  const publishDraft = usePublishInstructionDraft();

  // ── Local UI state ─────────────────────────────────────────
  const [validationResult, setValidationResult] =
    useState<InstructionVersionValidationResponse | null>(null);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cloneSuccess, setCloneSuccess] = useState<string | null>(null);

  // ── Derived ────────────────────────────────────────────────
  const isDraft = version?.version_status === "draft";
  const isPublished = version?.version_status === "published";
  const isArchived = version?.version_status === "archived";

  // Можно публиковать если: draft + валидация прошла успешно
  const canPublish = isDraft && validationResult?.is_valid === true;

  // ── Handlers ───────────────────────────────────────────────

  const handleCloneDraft = async () => {
    if (!versionId) return;
    setActionError(null);
    setCloneSuccess(null);

    try {
      const newDraft = await cloneDraft.mutateAsync({
        versionId,
        body: {
          change_summary: `Клон версии ${version?.name ?? versionId}`,
        },
      });
      setCloneSuccess(
        `Создан новый черновик: ${newDraft.name}. Переходим к редактированию.`,
      );
      // Переходим на detail нового draft
      setTimeout(() => {
        navigate(
          `/admin/instructions/doc-types/${docType}/versions/${newDraft.id}`,
        );
      }, 1200);
    } catch {
      setActionError("Не удалось создать черновик. Попробуйте ещё раз.");
    }
  };

  const handleValidate = async () => {
    if (!versionId) return;
    setActionError(null);
    setValidationResult(null);

    try {
      const result = await validateDraft.mutateAsync({ versionId });
      setValidationResult(result);
    } catch {
      setActionError(
        "Не удалось выполнить валидацию. Попробуйте ещё раз.",
      );
    }
  };

  const handlePublishConfirm = async () => {
    if (!versionId) return;
    setActionError(null);

    try {
      await publishDraft.mutateAsync({ versionId });
      setShowPublishDialog(false);
      // Refetch чтобы показать новый статус
      await refetch();
    } catch {
      setShowPublishDialog(false);
      setActionError(
        "Не удалось опубликовать версию. Убедитесь что валидация прошла успешно.",
      );
    }
  };

  // ── Loading / Error states ─────────────────────────────────

  if (isLoading) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl">
          <LoadingBlock text="Загружаем версию инструкции..." rows={6} />
        </div>
      </div>
    );
  }

  if (isError || !version) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl">
          <InlineAlert
            tone="error"
            message="Не удалось загрузить версию инструкции. Проверьте корректность ссылки."
          />
          <div className="mt-3">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(-1)}
            >
              ← Назад
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">

        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            {
              label: "Doc-Types",
              to: "/admin/instructions/doc-types",
            },
            {
              label: docType ?? "...",
              to: `/admin/instructions/doc-types/${docType}`,
            },
            { label: version.name },
          ]}
          title={version.name}
          subtitle={`${version.doc_type_code} · ${version.id}`}
          rightSlot={
            <div className="flex items-center gap-2">
              <VersionStatusBadge
                status={version.version_status}
                size="sm"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                aria-label="Обновить"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          }
        />

        {/* Action messages */}
        <InlineAlert tone="error" message={actionError} />
        <InlineAlert tone="success" message={cloneSuccess} />

        {/* Version meta */}
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-[11px] sm:grid-cols-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Doc Type
            </div>
            <div className="mt-0.5 font-mono font-semibold text-[var(--text-primary)]">
              {version.doc_type_code}
            </div>
          </div>
          {version.semver && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Semver
              </div>
              <div className="mt-0.5 font-mono font-semibold text-[var(--text-primary)]">
                v{version.semver}
              </div>
            </div>
          )}
          {version.checks_count != null && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Checks
              </div>
              <div className="mt-0.5 font-semibold text-[var(--text-primary)]">
                {version.checks_count}
              </div>
            </div>
          )}
          {version.published_at && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Published
              </div>
              <div className="mt-0.5 font-semibold text-[var(--text-primary)]">
                {new Date(version.published_at).toLocaleDateString("ru-RU")}
              </div>
            </div>
          )}
        </div>

        {/* ── Published / Archived: read-only view ────────── */}
        {(isPublished || isArchived) && (
          <>
            {/* Clone as draft action */}
            {isPublished && (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3">
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-[var(--text-primary)]">
                    Редактировать эту версию
                  </div>
                  <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    Published версия immutable. Создайте новый черновик на
                    основе этой версии чтобы внести изменения.
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleCloneDraft()}
                  isLoading={cloneDraft.isPending}
                  disabled={cloneDraft.isPending}
                >
                  <Copy className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Создать черновик
                </Button>
              </div>
            )}

            {/* Source YAML readonly */}
            {version.source_yaml && (
              <PageSection
                title="Source YAML"
                rightSlot={
                  <Eye
                    className="h-3.5 w-3.5 text-[var(--text-muted)]"
                    aria-hidden="true"
                  />
                }
              >
                <pre className="max-h-96 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono text-[var(--text-primary)] leading-relaxed">
                  {version.source_yaml}
                </pre>
              </PageSection>
            )}
          </>
        )}

        {/* ── Draft: edit form + validate + publish ────────── */}
        {isDraft && (
          <>
            <PageSection title="Редактирование черновика">
              <DraftEditForm
                versionId={version.id}
                initialData={version}
                onSaveSuccess={() => void refetch()}
              />
            </PageSection>

            {/* Validate section */}
            <PageSection
              title="Валидация"
              subtitle="Проверьте черновик перед публикацией. Валидация выполняется на сервере."
            >
              <div className="space-y-3">
                {validationResult && (
                  <ValidationResultPanel result={validationResult} />
                )}

                <div className="flex items-center justify-between gap-3">
                  <p className="text-[11px] text-[var(--text-muted)]">
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
                  >
                    Валидировать
                  </Button>
                </div>
              </div>
            </PageSection>

            {/* Publish section */}
            <PageSection
              title="Публикация"
              subtitle="Доступна только после успешной валидации."
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[11px] text-[var(--text-muted)]">
                    {canPublish
                      ? "Черновик готов к публикации. После публикации версия станет immutable."
                      : "Сначала выполните валидацию и убедитесь что ошибок нет."}
                  </p>
                </div>

                <Button
                  variant="primary"
                  size="sm"
                  type="button"
                  onClick={() => setShowPublishDialog(true)}
                  disabled={!canPublish}
                >
                  Опубликовать
                </Button>
              </div>
            </PageSection>
          </>
        )}

        {/* Parent version reference */}
        {version.parent_version_id && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Создана на основе версии
            </div>
            <button
              type="button"
              onClick={() =>
                navigate(
                  `/admin/instructions/doc-types/${docType}/versions/${version.parent_version_id}`,
                )
              }
              className="mt-1 font-mono text-[11px] text-[var(--accent-primary)] hover:underline"
            >
              {version.parent_version_id}
            </button>
          </div>
        )}
      </div>

      {/* Publish confirm dialog */}
      <PublishConfirmDialog
        open={showPublishDialog}
        versionName={version.name}
        docTypeCode={version.doc_type_code}
        isPublishing={publishDraft.isPending}
        onConfirm={() => void handlePublishConfirm()}
        onCancel={() => setShowPublishDialog(false)}
      />
    </div>
  );
};

export default DocTypeVersionDetailPage;


