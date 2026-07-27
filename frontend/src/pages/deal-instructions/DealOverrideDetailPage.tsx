// src/pages/deal-instructions/DealOverrideDetailPage.tsx
// Detail deal-level override.
// Включает rebase flow — только deal overrides имеют rebase endpoint.

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import {
  useDealOverrides,
  useValidateDealOverride,
  useActivateDealOverride,
  useArchiveDealOverride,
  useRebaseDealOverride,
} from "../../hooks/instructions/useInstructionOverrides";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import StaleWarningBanner from "../../components/instructions/StaleWarningBanner";
import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import Field from "../../components/ui/Field";
import type {
  InstructionOverrideValidationResponse,
  JsonPatchOperation,
} from "../../types/instructions";

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

const DealOverrideDetailPage: React.FC = () => {
  const { dealId, docType: overrideId } = useParams<{
    dealId: string;
    docType: string;
  }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useDealOverrides(
    dealId ?? null,
  );
  const override = data?.items.find((o) => o.id === overrideId) ?? null;

  const validateMutation = useValidateDealOverride();
  const activateMutation = useActivateDealOverride();
  const archiveMutation = useArchiveDealOverride();
  const rebaseMutation = useRebaseDealOverride();

  // Local state
  const [validationResult, setValidationResult] =
    useState<InstructionOverrideValidationResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);

  // Rebase form state
  const [showRebaseForm, setShowRebaseForm] = useState(false);
  const [newBaseVersionId, setNewBaseVersionId] = useState("");
  const [rebasePatchOps, setRebasePatchOps] = useState<JsonPatchOperation[]>(
    override?.patch_ops ?? [],
  );

  const canActivate = override?.status === "draft" && !override?.is_stale;
  const canArchive =
    override?.status === "draft" || override?.status === "active";

  const handleValidate = async () => {
    if (!dealId || !overrideId) return;
    setActionError(null);
    setValidationResult(null);
    try {
      const result = await validateMutation.mutateAsync({ dealId, overrideId });
      setValidationResult(result);
    } catch {
      setActionError("Не удалось выполнить валидацию.");
    }
  };

  const handleActivate = async () => {
    if (!dealId || !overrideId) return;
    setActionError(null);
    try {
      await activateMutation.mutateAsync({ dealId, overrideId });
      setActionSuccess("Override активирован.");
      await refetch();
    } catch {
      setActionError("Не удалось активировать override.");
    }
  };

  const handleArchiveConfirm = async () => {
    if (!dealId || !overrideId) return;
    try {
      await archiveMutation.mutateAsync({ dealId, overrideId });
      setShowArchiveDialog(false);
      setActionSuccess("Override архивирован.");
      await refetch();
    } catch {
      setShowArchiveDialog(false);
      setActionError("Не удалось архивировать override.");
    }
  };

  const handleRebase = async () => {
    if (!dealId || !overrideId || !newBaseVersionId.trim()) return;
    setActionError(null);
    try {
      await rebaseMutation.mutateAsync({
        dealId,
        overrideId,
        body: {
          new_base_version_id: newBaseVersionId.trim(),
          new_patch_ops: rebasePatchOps,
        },
      });
      setActionSuccess("Rebase выполнен успешно. Override привязан к новой базовой версии.");
      setShowRebaseForm(false);
      await refetch();
    } catch {
      setActionError(
        "Не удалось выполнить rebase. Проверьте корректность новой базовой версии и patch ops.",
      );
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl">
          <LoadingBlock text="Загружаем override..." rows={4} />
        </div>
      </div>
    );
  }

  if (isError || (!isLoading && !override)) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl space-y-3">
          <InlineAlert tone="error" message="Override не найден." />
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            ← Назад
          </Button>
        </div>
      </div>
    );
  }

  if (!override) return null;

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Проект", to: `/projects/${dealId}` },
            {
              label: "Инструкции",
              to: `/projects/${dealId}/instructions`,
            },
            {
              label: "Overrides",
              to: `/projects/${dealId}/instructions/overrides`,
            },
            { label: override.id.slice(0, 8) + "…" },
          ]}
          title="Deal Override"
          subtitle={override.change_summary ?? override.id}
          rightSlot={
            <div className="flex items-center gap-2">
              <OverrideStatusBadge
                status={override.status}
                isStale={override.is_stale}
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

        <InlineAlert tone="error" message={actionError} />
        <InlineAlert tone="success" message={actionSuccess} />

        {/* Stale warning с rebase кнопкой */}
        {override.is_stale && (
          <StaleWarningBanner
            scope="deal"
            onRebase={() => {
              setRebasePatchOps(override.patch_ops);
              setShowRebaseForm(true);
            }}
            isRebasing={rebaseMutation.isPending}
          />
        )}

        {/* Meta */}
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-[11px] sm:grid-cols-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Override ID
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {override.id}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Base Version
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {override.instruction_version_id?.slice(0, 8) ?? "…"}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Scope
            </div>
            <div className="mt-0.5 font-semibold text-[var(--text-primary)]">
              {override.override_scope}
            </div>
          </div>
        </div>

        {/* Patch ops */}
        <PageSection title="Patch Operations">
          <PatchOpsEditor
            value={override.patch_ops}
            onChange={() => {}}
            disabled={true}
            label="Текущие patch operations (RFC 6902)"
          />
        </PageSection>

        {/* Rebase form */}
        {showRebaseForm && (
          <PageSection title="Rebase на новую базовую версию">
            <div className="space-y-3">
              <p className="text-[11px] text-[var(--text-secondary)]">
                Укажите ID новой базовой instruction version и при необходимости
                скорректируйте patch operations. После rebase override перестанет
                быть stale.
              </p>

              <Field label="Новая базовая version ID" required>
                <input
                  type="text"
                  value={newBaseVersionId}
                  onChange={(e) => setNewBaseVersionId(e.target.value)}
                  className={inputClassName}
                  placeholder="uuid новой базовой версии..."
                  disabled={rebaseMutation.isPending}
                />
              </Field>

              <PatchOpsEditor
                value={rebasePatchOps}
                onChange={setRebasePatchOps}
                disabled={rebaseMutation.isPending}
                label="Patch operations для новой базы"
              />

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] pt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowRebaseForm(false)}
                  disabled={rebaseMutation.isPending}
                >
                  Отмена
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleRebase()}
                  isLoading={rebaseMutation.isPending}
                  disabled={
                    !newBaseVersionId.trim() || rebaseMutation.isPending
                  }
                >
                  Выполнить Rebase
                </Button>
              </div>
            </div>
          </PageSection>
        )}

        {/* Validation */}
        {(override.status === "draft") && (
          <PageSection title="Валидация">
            <div className="space-y-3">
              {validationResult && (
                <div
                  className={[
                    "rounded-xl border px-4 py-3",
                    validationResult.is_valid
                      ? "border-[color:var(--color-success-border)] bg-[color:var(--color-success-bg)]"
                      : "border-[#dc2626]/30 bg-[#fef2f2]",
                  ].join(" ")}
                >
                  <div
                    className={[
                      "text-xs font-semibold",
                      validationResult.is_valid
                        ? "text-[color:var(--color-success-text)]"
                        : "text-[#b91c1c]",
                    ].join(" ")}
                  >
                    {validationResult.is_valid
                      ? "Валидация успешна"
                      : "Валидация не прошла"}
                  </div>
                  {validationResult.errors.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {validationResult.errors.map((e, i) => (
                        <li key={i} className="text-[11px] text-[#b91c1c]">
                          • {e}
                        </li>
                      ))}
                    </ul>
                  )}
                  {validationResult.checks_count != null && (
                    <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                      Checks: {validationResult.checks_count}
                    </div>
                  )}
                </div>
              )}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleValidate()}
                isLoading={validateMutation.isPending}
                disabled={validateMutation.isPending}
              >
                Валидировать
              </Button>
            </div>
          </PageSection>
        )}

        {/* Actions */}
        <PageSection title="Действия">
          <div className="flex items-center gap-2 flex-wrap">
            {canActivate && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleActivate()}
                isLoading={activateMutation.isPending}
                disabled={activateMutation.isPending}
              >
                Активировать
              </Button>
            )}
            {override.is_stale && (
              <p className="text-[11px] text-[#b91c1c]">
                Выполните rebase перед активацией.
              </p>
            )}
            {canArchive && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setShowArchiveDialog(true)}
                disabled={
                  archiveMutation.isPending || activateMutation.isPending
                }
              >
                Архивировать
              </Button>
            )}
          </div>
        </PageSection>
      </div>

      <ConfirmDialog
        open={showArchiveDialog}
        title="Архивировать override?"
        description="Override будет архивирован. Это действие нельзя отменить."
        confirmLabel="Архивировать"
        cancelLabel="Отмена"
        isConfirming={archiveMutation.isPending}
        onConfirm={() => void handleArchiveConfirm()}
        onCancel={() => setShowArchiveDialog(false)}
      />
    </div>
  );
};

export default DealOverrideDetailPage;


