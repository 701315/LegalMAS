import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

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

import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { JsonPatchOperation } from "../../types/instructions";

type OverrideKind = "doc-type" | "global";

type VersionLike = {
  id: string;
  name?: string | null;
  semver?: string | null;
  status?: string | null;
};

function normalizeVersions(input: unknown): VersionLike[] {
  if (Array.isArray(input)) {
    return input as VersionLike[];
  }

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

const selectClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

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

  const createDocTypeOverrideMutation = useCreateTenantOverrideDraft();
  const createGlobalOverrideMutation = useCreateTenantGlobalOverrideDraft();

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

  const {
    data: docTypeVersionsData,
    isLoading: isDocTypeVersionsLoading,
  } = useDocTypeVersions(kind === "doc-type" && selectedDocTypeCode ? selectedDocTypeCode : null);

  const {
    data: globalVersionsData,
    isLoading: isGlobalVersionsLoading,
  } = useGlobalInstructionVersions(
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

  const isSubmitting =
    createDocTypeOverrideMutation.isPending ||
    createGlobalOverrideMutation.isPending;

  const canSubmit =
    !!tenantId &&
    !!selectedBaseVersionId &&
    patchOps.length > 0 &&
    !isSubmitting;

  const handleSubmit = async () => {
    if (!tenantId) {
      setErrorText(
        "Не удалось определить tenant пользователя. Выйдите и войдите снова.",
      );
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
      if (kind === "doc-type") {
        const result = await createDocTypeOverrideMutation.mutateAsync({
          tenantId,
          body: {
            instruction_version_id: selectedBaseVersionId,
            patch_ops: patchOps,
            change_summary: changeSummary.trim() || null,
          },
        });

        const createdId =
          (result as { item?: { id?: string }; id?: string }).item?.id ??
          (result as { id?: string }).id;

        if (!createdId) {
          throw new Error("Backend did not return created override id.");
        }

        navigate(`/tenant-admin/instructions/overrides/${createdId}`);
        return;
      }

      const result = await createGlobalOverrideMutation.mutateAsync({
        tenantId,
        body: {
          global_instruction_version_id: selectedBaseVersionId,
          patch_ops: patchOps,
          change_summary: changeSummary.trim() || null,
        },
      });

      const createdId =
        (result as { item?: { id?: string }; id?: string }).item?.id ??
        (result as { id?: string }).id;

      if (!createdId) {
        throw new Error("Backend did not return created override id.");
      }

      navigate(`/tenant-admin/instructions/overrides/${createdId}`);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Не удалось создать override draft.";
      setErrorText(message);
    }
  };

  const baseVersions =
    kind === "doc-type"
      ? availableDocTypeBaseVersions
      : availableGlobalBaseVersions;

  const isCatalogLoading =
    kind === "doc-type" ? isDocTypeCatalogLoading : isGlobalCatalogLoading;

  const isVersionsLoading =
    kind === "doc-type" ? isDocTypeVersionsLoading : isGlobalVersionsLoading;

  const hasCatalogError =
    kind === "doc-type" ? isDocTypeCatalogError : isGlobalCatalogError;

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Tenant Admin", to: "/tenant-admin" },
            { label: "Инструкции", to: "/tenant-admin/instructions" },
            { label: "Overrides", to: "/tenant-admin/instructions/overrides" },
            { label: "Новый override" },
          ]}
          title="Создать Tenant Override"
          subtitle="Создайте draft override поверх published-версии базовой инструкции."
          rightSlot={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate("/tenant-admin/instructions/overrides")}
            >
              Отмена
            </Button>
          }
        />

        <InlineAlert tone="error" message={errorText} />

        <PageSection title="Базовая инструкция">
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-xs text-[var(--text-primary)]">
                <input
                  type="radio"
                  name="override-kind"
                  checked={kind === "doc-type"}
                  onChange={() => setKind("doc-type")}
                  disabled={isSubmitting}
                />
                Doc-Type instruction
              </label>

              <label className="flex items-center gap-2 text-xs text-[var(--text-primary)]">
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

            {isCatalogLoading ? (
              <LoadingBlock text="Загружаем каталог базовых инструкций..." rows={3} />
            ) : hasCatalogError ? (
              <InlineAlert
                tone="error"
                message="Не удалось загрузить каталог базовых инструкций."
              />
            ) : kind === "doc-type" ? (
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
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
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    Global instruction
                  </label>
                  <select
                    className={selectClassName}
                    value={selectedGlobalInstructionCode}
                    onChange={(e) => setSelectedGlobalInstructionCode(e.target.value)}
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
              </div>
            )}

            {isVersionsLoading ? (
              <LoadingBlock text="Загружаем published-версии..." rows={3} />
            ) : baseVersions.length === 0 ? (
              <EmptyState
                title="Published-версии не найдены"
                description="Для выбранной базовой инструкции нет published-версий, поверх которых можно создать override."
              />
            ) : (
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
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
        </PageSection>

        <PageSection title="Override metadata">
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
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
        </PageSection>

        <PageSection title="JSON Patch operations">
          <PatchOpsEditor
            value={patchOps}
            onChange={setPatchOps}
            disabled={isSubmitting}
            label="RFC 6902 patch operations"
          />
        </PageSection>

        <div className="flex items-center justify-end gap-2">
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


