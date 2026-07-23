// src/pages/tenant-instructions/TenantOverrideDetailPage.tsx
// Detail страница tenant-level override.
// Показывает patch ops, статус, stale warning.
// Действия: validate, activate, archive.

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import {
  useTenantOverrides,
  useValidateTenantOverride,
  useActivateTenantOverride,
  useArchiveTenantOverride,
} from "../../hooks/instructions/useInstructionOverrides";
import { useAuth } from "../../hooks/useAuth";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import StaleWarningBanner from "../../components/instructions/StaleWarningBanner";
import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import type {
  InstructionOverrideValidationResponse,
  JsonPatchOperation,
} from "../../types/instructions";

const TenantOverrideDetailPage: React.FC = () => {
  const { overrideId } = useParams<{ overrideId: string }>();
  const navigate = useNavigate();

  // tenantId — так же как в TenantOverridesPage
  const { tenantId: authTenantId } = useAuth();
  const tenantId = authTenantId ?? "";

  // Загружаем список и находим нужный override
  const { data, isLoading, isError, refetch } = useTenantOverrides(
    tenantId || null,
  );
  const override = data?.items.find((o) => o.id === overrideId) ?? null;

  // Mutations
  const validateMutation = useValidateTenantOverride();
  const activateMutation = useActivateTenantOverride();
  const archiveMutation = useArchiveTenantOverride();

  // Local state
  const [validationResult, setValidationResult] =
    useState<InstructionOverrideValidationResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);

  // Patch ops для preview (read-only на этой странице — изменение через новый draft)
  const patchOps: JsonPatchOperation[] = override?.patch_ops ?? [];

  const canActivate =
    override?.status === "draft" && !override?.is_stale;

  const canArchive =
    override?.status === "draft" || override?.status === "active";

  const handleValidate = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);
    setValidationResult(null);

    try {
      const result = await validateMutation.mutateAsync({
        tenantId,
        overrideId,
      });
      setValidationResult(result);
    } catch {
      setActionError("Не удалось выполнить валидацию.");
    }
  };

  const handleActivate = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);
    setActionSuccess(null);

    try {
      await activateMutation.mutateAsync({ tenantId, overrideId });
      setActionSuccess("Override активирован.");
      await refetch();
    } catch {
      setActionError(
        "Не удалось активировать override. Override может быть stale или уже активен.",
      );
    }
  };

  const handleArchiveConfirm = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);

    try {
      await archiveMutation.mutateAsync({ tenantId, overrideId });
      setShowArchiveDialog(false);
      setActionSuccess("Override архивирован.");
      await refetch();
    } catch {
      setShowArchiveDialog(false);
      setActionError("Не удалось архивировать override.");
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
          <InlineAlert
            tone="error"
            message="Override не найден или нет доступа."
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(-1)}
          >
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
            { label: "Tenant Admin", to: "/tenant-admin" },
            { label: "Инструкции", to: "/tenant-admin/instructions" },
            {
              label: "Overrides",
              to: "/tenant-admin/instructions/overrides",
            },
            { label: override.id.slice(0, 8) + "…" },
          ]}
          title="Tenant Override"
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

        {/* Messages */}
        <InlineAlert tone="error" message={actionError} />
        <InlineAlert tone="success" message={actionSuccess} />

        {/* Stale warning */}
        {override.is_stale && (
          <StaleWarningBanner scope="tenant" />
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
              {override.global_instruction_version_id
                ? `${override.global_instruction_version_id.slice(0, 8)}…`
                : override.instruction_version_id
                  ? `${override.instruction_version_id.slice(0, 8)}…`
                  : "—"}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Base Hash
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {override.base_content_hash.slice(0, 12)}…
            </div>
          </div>
        </div>

        {/* Patch ops — read only view */}
        <PageSection title="Patch Operations">
          <PatchOpsEditor
            value={patchOps}
            onChange={() => {
              // Read-only на этой странице.
              // Изменение patch_ops — через создание нового override draft.
            }}
            disabled={true}
            label="Текущие patch operations (RFC 6902)"
          />
          <p className="mt-2 text-[11px] text-[var(--text-muted)]">
            Для изменения patch operations создайте новый override draft
            с обновлёнными операциями.
          </p>
        </PageSection>

        {/* Validation */}
        {override.status === "draft" && (
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
                        <li
                          key={i}
                          className="text-[11px] text-[#b91c1c]"
                        >
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

            {override.is_stale && override.status === "draft" && (
              <p className="text-[11px] text-[#b91c1c]">
                Нельзя активировать stale override.
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

      {/* Archive confirm */}
      <ConfirmDialog
        open={showArchiveDialog}
        title="Архивировать override?"
        description="Override будет архивирован и перестанет применяться. Это действие нельзя отменить."
        confirmLabel="Архивировать"
        cancelLabel="Отмена"
        isConfirming={archiveMutation.isPending}
        onConfirm={() => void handleArchiveConfirm()}
        onCancel={() => setShowArchiveDialog(false)}
      />
    </div>
  );
};

export default TenantOverrideDetailPage;


