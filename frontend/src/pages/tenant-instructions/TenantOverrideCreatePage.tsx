// src/pages/tenant-instructions/TenantOverrideCreatePage.tsx

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { useAuth } from "../../hooks/useAuth";
import {
  useCreateTenantOverrideDraft,
  useCreateTenantGlobalOverrideDraft,
} from "../../hooks/instructions/useInstructionOverrides";
import {
  useInstructionCatalog,
  useDocTypeVersions,
} from "../../hooks/instructions/useInstructionVersions";
import {
  useGlobalInstructionCatalog,
  useGlobalInstructionVersions,
} from "../../hooks/instructions/useGlobalInstructions";

import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { JsonPatchOperation } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

type OverrideKind = "doc-type" | "global";

type VersionLike = {
  id: string;
  name?: string | null;
  semver?: string | null;
  status?: string | null;
};

function normalizeVersions(input: unknown): VersionLike[] {
  if (Array.isArray(input)) return input as VersionLike[];
  if (
    typeof input === "object" &&
    input !== null &&
    "items" in input &&
    Array.isArray((input as { items?: unknown }).items)
  ) {
    return (input as { items: VersionLike[] }).items;
  }
  return [];
}

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const selectClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const TenantOverrideCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const { tenantId } = useAuth();

  const [kind, setKind] = useState<OverrideKind>("doc-type");
  const [selectedDocTypeCode, setSelectedDocTypeCode] = useState("");
  const [selectedGlobalInstructionCode, setSelectedGlobalInstructionCode] =
    useState("");
  const [selectedBaseVersionId, setSelectedBaseVersionId] = useState("");
  const [changeSummary, setChangeSummary] = useState("");
  const [patchOps, setPatchOps] = useState<JsonPatchOperation[]>([]);
  const [errorText, setErrorText] = useState<string | null>(null);

  const createDocTypeMut = useCreateTenantOverrideDraft();
  const createGlobalMut = useCreateTenantGlobalOverrideDraft();

  const {
    data: docTypeCatalog,
    isLoading: isDocTypeCatalogLoading,
    isError: isDocTypeCatalogError,
  } = useInstructionCatalog();

  const {
    data: globalCatalog,
    isLoading: isGlobalCatalogLoading,
    isError: isGlobalCatalogError,
  } = useGlobalInstructionCatalog();

  const docTypeCatalogItems = docTypeCatalog?.items ?? [];
  const globalCatalogItems = globalCatalog?.items ?? [];

  const { data: docTypeVersionsData, isLoading: isDocTypeVersionsLoading } =
    useDocTypeVersions(
      kind === "doc-type" && selectedDocTypeCode ? selectedDocTypeCode : null,
    );

  const { data: globalVersionsData, isLoading: isGlobalVersionsLoading } =
    useGlobalInstructionVersions(
      kind === "global" && selectedGlobalInstructionCode
        ? selectedGlobalInstructionCode
        : null,
    );

  const docTypeVersions = useMemo(
    () => normalizeVersions(docTypeVersionsData),
    [docTypeVersionsData],
  );
  const globalVersions = useMemo(
    () => normalizeVersions(globalVersionsData),
    [globalVersionsData],
  );

  const availableDocTypeBaseVersions = useMemo(
    () => docTypeVersions.filter((v) => v.status === "published"),
    [docTypeVersions],
  );
  const availableGlobalBaseVersions = useMemo(
    () => globalVersions.filter((v) => v.status === "published"),
    [globalVersions],
  );

  useEffect(() => {
    if (kind === "doc-type") {
      if (!selectedDocTypeCode && docTypeCatalogItems.length > 0) {
        setSelectedDocTypeCode(docTypeCatalogItems[0].doc_type_code);
      }
    } else {
      if (!selectedGlobalInstructionCode && globalCatalogItems.length > 0) {
        setSelectedGlobalInstructionCode(globalCatalogItems[0].instruction_code);
      }
    }
  }, [
    kind,
    selectedDocTypeCode,
    selectedGlobalInstructionCode,
    docTypeCatalogItems,
    globalCatalogItems,
  ]);

  useEffect(() => {
    if (kind === "doc-type") {
      setSelectedBaseVersionId(
        availableDocTypeBaseVersions.length > 0
          ? availableDocTypeBaseVersions[0].id
          : "",
      );
    } else {
      setSelectedBaseVersionId(
        availableGlobalBaseVersions.length > 0
          ? availableGlobalBaseVersions[0].id
          : "",
      );
    }
  }, [kind, availableDocTypeBaseVersions, availableGlobalBaseVersions]);

  const isSubmitting = createDocTypeMut.isPending || createGlobalMut.isPending;

  const canSubmit =
    !!tenantId && !!selectedBaseVersionId && patchOps.length > 0 && !isSubmitting;

  const baseVersions =
    kind === "doc-type" ? availableDocTypeBaseVersions : availableGlobalBaseVersions;

  const isCatalogLoading =
    kind === "doc-type" ? isDocTypeCatalogLoading : isGlobalCatalogLoading;
  const isVersionsLoading =
    kind === "doc-type" ? isDocTypeVersionsLoading : isGlobalVersionsLoading;
  const hasCatalogError =
    kind === "doc-type" ? isDocTypeCatalogError : isGlobalCatalogError;

  const handleSubmit = async () => {
    if (!tenantId) {
      setErrorText("Не удалось определить tenant. Выйдите и войдите снова.");
      return;
    }
    if (!selectedBaseVersionId) {
      setErrorText("Выберите базовую published-версию инструкции.");
      return;
    }
    if (patchOps.length === 0) {
      setErrorText("Добавьте хотя бы одну JSON Patch операцию.");
      return;
    }

    setErrorText(null);

    try {
      let createdId: string | undefined;

      if (kind === "doc-type") {
        const result = await createDocTypeMut.mutateAsync({
          tenantId,
          body: {
            instruction_version_id: selectedBaseVersionId,
            patch_ops: patchOps,
            change_summary: changeSummary.trim() || null,
          },
        });
        createdId =
          (result as { item?: { id?: string }; id?: string }).item?.id ??
          (result as { id?: string }).id;
      } else {
        const result = await createGlobalMut.mutateAsync({
          tenantId,
          body: {
            global_instruction_version_id: selectedBaseVersionId,
            patch_ops: patchOps,
            change_summary: changeSummary.trim() || null,
          },
        });
        createdId =
          (result as { item?: { id?: string }; id?: string }).item?.id ??
          (result as { id?: string }).id;
      }

      if (!createdId) {
        throw new Error("Backend did not return created override id.");
      }

      navigate(`/tenant-admin/instructions/overrides/${createdId}`);
    } catch (err) {
      setErrorText(
        err instanceof Error
          ? err.message
          : "Не удалось создать override draft.",
      );
    }
  };

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/tenant-admin/instructions/overrides")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Overrides
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Создать Tenant Override
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Создайте draft override поверх published-версии базовой инструкции.
              </p>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate("/tenant-admin/instructions/overrides")}
              disabled={isSubmitting}
            >
              Отмена
            </Button>
          </div>
        </header>

        {/* ── Error ────────────────────────────────────────────── */}
        {errorText && <InlineAlert tone="error" message={errorText} />}

        {/* ── Базовая инструкция ───────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Базовая инструкция
          </h2>

          <div className="mt-4 space-y-4">
            {/* Kind toggle */}
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-[var(--text-primary)]">
                <input
                  type="radio"
                  name="override-kind"
                  checked={kind === "doc-type"}
                  onChange={() => setKind("doc-type")}
                  disabled={isSubmitting}
                />
                Doc-Type instruction
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--text-primary)]">
                <input
                  type="radio"
                  name="override-kind"
                  checked={kind === "global"}
                  onChange={() => setKind("global")}
                  disabled={isSubmitting}
                />
                Global instruction
              </label>
            </div>

            {/* Catalog selector */}
            {isCatalogLoading ? (
              <LoadingBlock
                text="Загружаем каталог базовых инструкций…"
                rows={3}
              />
            ) : hasCatalogError ? (
              <InlineAlert
                tone="error"
                message="Не удалось загрузить каталог базовых инструкций."
              />
            ) : kind === "doc-type" ? (
              <div className="space-y-1.5">
                <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                  Тип документа
                </label>
                <select
                  className={selectClassName}
                  value={selectedDocTypeCode}
                  onChange={(e) => setSelectedDocTypeCode(e.target.value)}
                  disabled={isSubmitting}
                >
                  {docTypeCatalogItems.map((item) => (
                    <option key={item.doc_type_code} value={item.doc_type_code}>
                      {item.name} ({item.doc_type_code})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="space-y-1.5">
                <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                  Global instruction
                </label>
                <select
                  className={selectClassName}
                  value={selectedGlobalInstructionCode}
                  onChange={(e) =>
                    setSelectedGlobalInstructionCode(e.target.value)
                  }
                  disabled={isSubmitting}
                >
                  {globalCatalogItems.map((item) => (
                    <option
                      key={item.instruction_code}
                      value={item.instruction_code}
                    >
                      {item.name} ({item.instruction_code})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Version selector */}
            {isVersionsLoading ? (
              <LoadingBlock text="Загружаем published-версии…" rows={2} />
            ) : baseVersions.length === 0 ? (
              <EmptyState
                title="Published-версии не найдены"
                description="Для выбранной базовой инструкции нет published-версий, поверх которых можно создать override."
              />
            ) : (
              <div className="space-y-1.5">
                <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                  Published base version
                </label>
                <select
                  className={selectClassName}
                  value={selectedBaseVersionId}
                  onChange={(e) => setSelectedBaseVersionId(e.target.value)}
                  disabled={isSubmitting}
                >
                  {baseVersions.map((version) => (
                    <option key={version.id} value={version.id}>
                      {version.name ?? version.id}
                      {version.semver ? ` (v${version.semver})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </section>

        {/* ── Метаданные ───────────────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Метаданные
          </h2>
          <div className="mt-4 space-y-1.5">
            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              Change summary
            </label>
            <input
              type="text"
              className={inputClassName}
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
              disabled={isSubmitting}
              placeholder="Например: ослабить порог warning, добавить tenant-specific wording"
            />
          </div>
        </section>

        {/* ── JSON Patch Operations ────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            JSON Patch Operations
          </h2>
          <PatchOpsEditor
            value={patchOps}
            onChange={setPatchOps}
            disabled={isSubmitting}
            label="RFC 6902 patch operations"
          />
        </section>

        {/* ── Actions ──────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 shadow-sm">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate("/tenant-admin/instructions/overrides")}
            disabled={isSubmitting}
          >
            Отмена
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            isLoading={isSubmitting}
          >
            Создать draft override
          </Button>
        </div>
      </div>
    </div>
  );
};

export default TenantOverrideCreatePage;


