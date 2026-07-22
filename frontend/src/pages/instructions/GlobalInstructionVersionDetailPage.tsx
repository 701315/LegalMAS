// src/pages/instructions/GlobalInstructionVersionDetailPage.tsx
// Detail страница конкретной global instruction version.
// Зеркало DocTypeVersionDetailPage.

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Copy, Eye, RefreshCw } from "lucide-react";

import {
  useGlobalInstructionVersionDetail,
  useCloneGlobalInstructionDraft,
  useValidateGlobalInstructionDraft,
  usePublishGlobalInstructionDraft,
} from "../../hooks/instructions/useGlobalInstructions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import DraftEditForm from "../../components/instructions/DraftEditForm";
import ValidationResultPanel from "../../components/instructions/ValidationResultPanel";
import PublishConfirmDialog from "../../components/instructions/PublishConfirmDialog";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { GlobalInstructionVersionValidationResponse } from "../../types/instructions";

const GlobalInstructionVersionDetailPage: React.FC = () => {
  const { instructionCode, versionId } = useParams<{
    instructionCode: string;
    versionId: string;
  }>();
  const navigate = useNavigate();

  // ── Data fetching ────────────────────────────────────────────
  const {
    data: version,
    isLoading,
    isError,
    refetch,
  } = useGlobalInstructionVersionDetail(versionId ?? null);

  // ── Mutations ────────────────────────────────────────────────
  const cloneDraft = useCloneGlobalInstructionDraft();
  const validateDraft = useValidateGlobalInstructionDraft();
  const publishDraft = usePublishGlobalInstructionDraft();

  // ── Local UI state ───────────────────────────────────────────
  const [validationResult, setValidationResult] =
    useState<GlobalInstructionVersionValidationResponse | null>(null);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cloneSuccess, setCloneSuccess] = useState<string | null>(null);

  // ── Derived ──────────────────────────────────────────────────
  const isDraft = version?.version_status === "draft";
  const isPublished = version?.version_status === "published";
  const isArchived = version?.version_status === "archived";
  const canPublish = isDraft && validationResult?.is_valid === true;

  // ── Handlers ─────────────────────────────────────────────────

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
        `Создан новый черновик: ${newDraft.name ?? newDraft.instruction_code}. Переходим к редактированию.`,
      );
      setTimeout(() => {
        navigate(
          `/admin/instructions/global-checks/${instructionCode}/versions/${newDraft.id}`,
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
      setActionError("Не удалось выполнить валидацию. Попробуйте ещё раз.");
    }
  };

  const handlePublishConfirm = async () => {
    if (!versionId) return;
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

  // ── Loading / Error ──────────────────────────────────────────

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
        <div className="mx-auto max-w-4xl space-y-3">
          <InlineAlert
            tone="error"
            message="Не удалось загрузить версию инструкции. Проверьте корректность ссылки."
          />
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            ← Назад
          </Button>
        </div>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">

        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            {
              label: "Global Instructions",
              to: "/admin/instructions/global-checks",
            },
            {
              label: instructionCode ?? "...",
              to: `/admin/instructions/global-checks/${instructionCode}`,
            },
            { label: version.name ?? version.instruction_code },
          ]}
          title={version.name ?? version.instruction_code}
          subtitle={`${version.instruction_code} · ${version.id}`}
          rightSlot={
            <div className="flex items-center gap-2">
              <VersionStatusBadge status={version.version_status} size="sm" />
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
              Instruction Code
            </div>
            <div className="mt-0.5 font-mono font-semibold text-[var(--text-primary)]">
              {version.instruction_code}
            </div>
          </div>
          {version.group && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Group
              </div>
              <div className="mt-0.5 font-semibold text-[var(--text-primary)]">
                {version.group}
              </div>
            </div>
          )}
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

        {/* ── Published / Archived: read-only ─────────────── */}
        {(isPublished || isArchived) && (
          <>
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

            {isArchived && (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
                <div className="text-xs font-semibold text-[var(--text-secondary)]">
                  Archived версия
                </div>
                <div className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  Эта версия выведена из активного использования.
                  Можно просмотреть YAML ниже.
                </div>
              </div>
            )}

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

        {/* ── Draft: edit + validate + publish ──────────── */}
        {isDraft && (
          <>
            <PageSection title="Редактирование черновика">
              {/*
                instructionType="global" → DraftEditForm использует
                globalETagAdapters внутри, обращается к:
                  GET /api/v1/admin/global-instruction-versions/:id  (ETag fetch)
                  PATCH /api/v1/admin/global-instruction-versions/:id (save)
                и инвалидирует globalInstructionQueryKeys.versionDetail
              */}
              <DraftEditForm
                versionId={version.id}
                initialData={version}
                onSaveSuccess={() => void refetch()}
                instructionType="global"
              />
            </PageSection>

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
                  `/admin/instructions/global-checks/${instructionCode}/versions/${version.parent_version_id}`,
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
        versionName={version.name ?? version.instruction_code}
        docTypeCode={version.instruction_code}
        isPublishing={publishDraft.isPending}
        onConfirm={() => void handlePublishConfirm()}
        onCancel={() => setShowPublishDialog(false)}
      />
    </div>
  );
};

export default GlobalInstructionVersionDetailPage;



