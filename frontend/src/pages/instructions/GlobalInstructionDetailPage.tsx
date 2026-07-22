// src/pages/instructions/GlobalInstructionDetailPage.tsx
// Detail страница для конкретного instruction_code.
// Зеркало DocTypeDetailPage.

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { GitBranch, Plus, RefreshCw } from "lucide-react";

import {
  useGlobalInstructionCatalog,
  useGlobalInstructionVersions,
} from "../../hooks/instructions/useGlobalInstructions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { GlobalInstructionVersionItem } from "../../types/instructions";

const GlobalInstructionDetailPage: React.FC = () => {
  const { instructionCode } = useParams<{ instructionCode: string }>();
  const navigate = useNavigate();

  const { data: catalog } = useGlobalInstructionCatalog();
  const catalogItem =
    catalog?.items.find((i) => i.instruction_code === instructionCode) ?? null;

  const {
    data: versionsData,
    isLoading,
    isError,
    refetch,
  } = useGlobalInstructionVersions(instructionCode ?? null);

  const versions = versionsData?.items ?? [];

  const handleOpenVersion = (versionId: string) => {
    navigate(
      `/admin/instructions/global-checks/${instructionCode}/versions/${versionId}`,
    );
  };

  const publishedVersions = versions.filter(
    (v) => v.version_status === "published",
  );
  const draftVersions = versions.filter((v) => v.version_status === "draft");
  const archivedVersions = versions.filter(
    (v) => v.version_status === "archived",
  );

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            {
              label: "Global Instructions",
              to: "/admin/instructions/global-checks",
            },
            { label: catalogItem?.name ?? instructionCode ?? "..." },
          ]}
          title={catalogItem?.name ?? instructionCode ?? "Global Instruction"}
          subtitle={`Код: ${instructionCode}${catalogItem?.group ? ` · ${catalogItem.group}` : ""}`}
          rightSlot={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                aria-label="Обновить"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              {draftVersions.length === 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigate(
                      `/admin/instructions/global-checks/${instructionCode}/versions/new`,
                    )
                  }
                >
                  <Plus className="h-3.5 w-3.5 mr-1" aria-hidden="true" />
                  Новый draft
                </Button>
              )}
            </div>
          }
        />

        {catalogItem && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3">
            <div className="flex items-center gap-4 flex-wrap text-[11px] text-[var(--text-muted)]">
              {catalogItem.group && (
                <span>
                  Группа:{" "}
                  <span className="text-[var(--text-primary)]">
                    {catalogItem.group}
                  </span>
                </span>
              )}
              <span>
                Версий всего:{" "}
                <span className="text-[var(--text-primary)]">
                  {catalogItem.total_versions_count}
                </span>
              </span>
              <span>
                Published:{" "}
                <span
                  className={
                    catalogItem.has_published
                      ? "text-[color:var(--color-success-text)]"
                      : "text-[var(--text-muted)]"
                  }
                >
                  {catalogItem.has_published ? "да" : "нет"}
                </span>
              </span>
            </div>
          </div>
        )}

        <PageSection
          title="Версии"
          rightSlot={
            <div className="flex items-center gap-1.5">
              <GitBranch
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
              <span className="text-[11px] text-[var(--text-muted)]">
                {versions.length}
              </span>
            </div>
          }
        >
          {isLoading && <LoadingBlock text="Загружаем версии..." rows={4} />}

          {isError && (
            <InlineAlert
              tone="error"
              message="Не удалось загрузить версии инструкции."
            />
          )}

          {!isLoading && !isError && versions.length === 0 && (
            <EmptyState
              title="Версий нет"
              description="Для этой инструкции ещё не создано ни одной версии."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigate(
                      `/admin/instructions/global-checks/${instructionCode}/versions/new`,
                    )
                  }
                >
                  Создать первый draft
                </Button>
              }
            />
          )}

          {!isLoading && !isError && versions.length > 0 && (
            <div className="space-y-4">
              {draftVersions.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Черновики ({draftVersions.length})
                  </div>
                  <ul className="space-y-1.5">
                    {draftVersions.map((v) => (
                      <li key={v.id}>
                        <GlobalVersionRow
                          version={v}
                          onClick={() => handleOpenVersion(v.id)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {publishedVersions.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Published ({publishedVersions.length})
                  </div>
                  <ul className="space-y-1.5">
                    {publishedVersions.map((v) => (
                      <li key={v.id}>
                        <GlobalVersionRow
                          version={v}
                          onClick={() => handleOpenVersion(v.id)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {archivedVersions.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Archived ({archivedVersions.length})
                  </div>
                  <ul className="space-y-1.5">
                    {archivedVersions.map((v) => (
                      <li key={v.id}>
                        <GlobalVersionRow
                          version={v}
                          onClick={() => handleOpenVersion(v.id)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </PageSection>
      </div>
    </div>
  );
};

interface GlobalVersionRowProps {
  version: GlobalInstructionVersionItem;
  onClick: () => void;
}

const GlobalVersionRow: React.FC<GlobalVersionRowProps> = ({
  version,
  onClick,
}) => {
  const publishedAt = version.published_at
    ? new Date(version.published_at).toLocaleDateString("ru-RU")
    : null;
  const updatedAt = version.updated_at
    ? new Date(version.updated_at).toLocaleDateString("ru-RU")
    : null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5 text-left text-xs transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-[var(--text-primary)]">
              {version.name ?? version.instruction_code}
            </span>
            {version.change_summary && (
              <span className="truncate text-[11px] text-[var(--text-secondary)]">
                {version.change_summary}
              </span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
            <span className="font-mono">{version.id.slice(0, 8)}…</span>
            {publishedAt && <span>Published: {publishedAt}</span>}
            {updatedAt && !publishedAt && <span>Updated: {updatedAt}</span>}
            {version.source_sha256 && (
              <span className="font-mono">
                sha: {version.source_sha256.slice(0, 8)}
              </span>
            )}
          </div>
        </div>
        <VersionStatusBadge status={version.version_status} size="xs" />
      </div>
    </button>
  );
};

export default GlobalInstructionDetailPage;


