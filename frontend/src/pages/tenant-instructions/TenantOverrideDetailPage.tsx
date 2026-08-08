// src/pages/tenant-instructions/TenantOverrideDetailPage.tsx

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import {
  useTenantOverrides,
  useValidateTenantOverride,
  useActivateTenantOverride,
  useArchiveTenantOverride,
} from "../../hooks/instructions/useInstructionOverrides";
import { useAuth } from "../../hooks/useAuth";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import StaleWarningBanner from "../../components/instructions/StaleWarningBanner";
import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import type {
  InstructionOverrideValidationResponse,
  JsonPatchOperation,
} from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// MetaItem
// ─────────────────────────────────────────────────────────────

const MetaItem: React.FC<{ label: string; value: string }> = ({
  label,
  value,
}) => (
  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
      {label}
    </p>
    <p className="mt-0.5 break-all font-mono text-[11px] text-[var(--text-primary)]">
      {value}
    </p>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const TenantOverrideDetailPage: React.FC = () => {
  const { overrideId } = useParams<{ overrideId: string }>();
  const navigate = useNavigate();

  const { tenantId: authTenantId } = useAuth();
  const tenantId = authTenantId ?? "";

  const { data, isLoading, isError, refetch } = useTenantOverrides(
    tenantId || null,
  );
  const override = data?.items.find((o) => o.id === overrideId) ?? null;

  const validateMut = useValidateTenantOverride();
  const activateMut = useActivateTenantOverride();
  const archiveMut = useArchiveTenantOverride();

  const [validationResult, setValidationResult] =
    useState<InstructionOverrideValidationResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);

  const patchOps: JsonPatchOperation[] = override?.patch_ops ?? [];

  const canActivate = override?.status === "draft" && !override?.is_stale;
  const canArchive =
    override?.status === "draft" || override?.status === "active";

  const handleValidate = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);
    setValidationResult(null);
    try {
      const result = await validateMut.mutateAsync({ tenantId, overrideId });
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
      await activateMut.mutateAsync({ tenantId, overrideId });
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
      await archiveMut.mutateAsync({ tenantId, overrideId });
      setShowArchiveDialog(false);
      setActionSuccess("Override архивирован.");
      await refetch();
    } catch {
      setShowArchiveDialog(false);
      setActionError("Не удалось архивировать override.");
    }
  };

  // ── Loading ─────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein p-4 md:p-5">
          <LoadingBlock text="Загружаем override…" rows={4} />
        </div>
      </div>
    );
  }

  // ── Error / not found ───────────────────────────────────────

  if (isError || (!isLoading && !override)) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein space-y-4 p-4 md:p-5">
          <InlineAlert
            tone="error"
            message="Override не найден или нет доступа."
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate("/tenant-admin/instructions/overrides")}
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
          >
            К списку overrides
          </Button>
        </div>
      </div>
    );
  }

  if (!override) return null;

  const baseVersionId =
    override.global_instruction_version_id ??
    override.instruction_version_id ??
    null;

  return (
    <>
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein space-y-4 p-4 md:p-5">

          {/* ── Шапка ───────────────────────────────────────────── */}
          <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <button
                  type="button"
                  onClick={() =>
                    navigate("/tenant-admin/instructions/overrides")
                  }
                  className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Overrides
                </button>

                <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                  Tenant Override
                </h1>
                {override.change_summary && (
                  <p className="mt-2 text-sm text-[var(--text-secondary)]">
                    {override.change_summary}
                  </p>
                )}
              </div>

              <OverrideStatusBadge
                status={override.status}
                isStale={override.is_stale}
                size="sm"
              />
            </div>
          </header>

          {/* ── Alerts ──────────────────────────────────────────── */}
          {actionError && <InlineAlert tone="error" message={actionError} />}
          {actionSuccess && <InlineAlert tone="success" message={actionSuccess} />}

          {/* ── Stale warning ────────────────────────────────────── */}
          {override.is_stale && <StaleWarningBanner scope="tenant" />}

          {/* ── Детали ──────────────────────────────────────────── */}
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Детали
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetaItem label="Override ID" value={override.id} />
              <MetaItem
                label="Base Version"
                value={baseVersionId ? `${baseVersionId.slice(0, 8)}…` : "—"}
              />
              <MetaItem
                label="Base Hash"
                value={`${override.base_content_hash.slice(0, 12)}…`}
              />
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <MetaItem
                label="Scope"
                value={
                  override.global_instruction_version_id
                    ? "Global instruction"
                    : "Doc-type instruction"
                }
              />
              <MetaItem
                label="Patch ops"
                value={`${patchOps.length} операций`}
              />
            </div>
          </section>

          {/* ── Patch Operations ─────────────────────────────────── */}
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Patch Operations
            </h2>
            <PatchOpsEditor
              value={patchOps}
              onChange={() => {
                /* read-only */
              }}
              disabled={true}
              label="Текущие patch operations (RFC 6902)"
            />
            <p className="mt-3 text-xs text-[var(--text-muted)]">
              Для изменения patch operations создайте новый override draft
              с обновлёнными операциями.
            </p>
          </section>

          {/* ── Валидация ────────────────────────────────────────── */}
          {override.status === "draft" && (
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                Валидация
              </h2>
              <div className="space-y-3">
                {validationResult && (
                  <div
                    className={[
                      "rounded-xl border p-4",
                      validationResult.is_valid
                        ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)]"
                        : "border-[var(--color-error-border)] bg-[var(--color-error-bg)]",
                    ].join(" ")}
                  >
                    <p
                      className={[
                        "text-xs font-semibold",
                        validationResult.is_valid
                          ? "text-[var(--color-success-text)]"
                          : "text-[var(--color-error-text)]",
                      ].join(" ")}
                    >
                      {validationResult.is_valid
                        ? "Валидация успешна"
                        : "Валидация не прошла"}
                    </p>
                    {validationResult.errors.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {validationResult.errors.map((e, i) => (
                          <li
                            key={i}
                            className="text-[11px] text-[var(--color-error-text)]"
                          >
                            • {e}
                          </li>
                        ))}
                      </ul>
                    )}
                    {validationResult.checks_count != null && (
                      <p className="mt-2 text-[11px] text-[var(--text-muted)]">
                        Checks: {validationResult.checks_count}
                      </p>
                    )}
                  </div>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleValidate()}
                  isLoading={validateMut.isPending}
                  disabled={validateMut.isPending}
                >
                  Валидировать
                </Button>
              </div>
            </section>
          )}

          {/* ── Действия ─────────────────────────────────────────── */}
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Действия
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              {canActivate && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleActivate()}
                  isLoading={activateMut.isPending}
                  disabled={activateMut.isPending}
                >
                  Активировать
                </Button>
              )}

              {override.is_stale && override.status === "draft" && (
                <p className="text-[11px] text-[var(--color-error-text)]">
                  Нельзя активировать stale override — создайте новый.
                </p>
              )}

              {canArchive && (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setShowArchiveDialog(true)}
                  disabled={archiveMut.isPending || activateMut.isPending}
                >
                  Архивировать
                </Button>
              )}

              {override.status === "archived" && (
                <p className="text-[11px] text-[var(--text-muted)]">
                  Override архивирован. Создайте новый при необходимости.
                </p>
              )}
            </div>
          </section>

        </div>
      </div>

      <ConfirmDialog
        open={showArchiveDialog}
        title="Архивировать override?"
        description="Override будет архивирован и перестанет применяться. Это действие нельзя отменить."
        confirmLabel="Архивировать"
        cancelLabel="Отмена"
        isConfirming={archiveMut.isPending}
        onConfirm={() => void handleArchiveConfirm()}
        onCancel={() => setShowArchiveDialog(false)}
      />
    </>
  );
};

export default TenantOverrideDetailPage;


