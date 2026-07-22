// src/pages/instructions/DocTypeDetailPage.tsx
// Detail страница для конкретного doc_type_code.
// Показывает все версии + quick actions.

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { GitBranch, Plus, RefreshCw } from "lucide-react";

import {
  useDocTypeVersions,
  useInstructionCatalog,
} from "../../hooks/instructions/useInstructionVersions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

const DocTypeDetailPage: React.FC = () => {
  const { docType } = useParams<{ docType: string }>();
  const navigate = useNavigate();

  // Берём метаданные из каталога
  const { data: catalog } = useInstructionCatalog();
  const catalogItem = catalog?.items.find(
    (i) => i.doc_type_code === docType,
  ) ?? null;

  const {
    data: versionsData,
    isLoading,
    isError,
    refetch,
  } = useDocTypeVersions(docType ?? null);

  const versions = versionsData?.items ?? [];

  const handleOpenVersion = (versionId: string) => {
    navigate(
      `/admin/instructions/doc-types/${docType}/versions/${versionId}`,
    );
  };

  const publishedVersions = versions.filter(
    (v) => v.version_status === "published",
  );
  const draftVersions = versions.filter(
    (v) => v.version_status === "draft",
  );
  const archivedVersions = versions.filter(
    (v) => v.version_status === "archived",
  );

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            { label: "Doc-Types", to: "/admin/instructions/doc-types" },
            { label: catalogItem?.name ?? docType ?? "..." },
          ]}
          title={catalogItem?.name ?? docType ?? "Doc-Type"}
          subtitle={`Тип документа: ${docType}`}
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
              {/* Кнопка создания draft — если нет активного draft */}
              {draftVersions.length === 0 && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigate(
                      `/admin/instructions/doc-types/${docType}/versions/new`,
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

        {/* Catalog meta */}
        {catalogItem && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3">
            <div className="flex items-center gap-4 flex-wrap text-[11px] text-[var(--text-muted)]">
              {catalogItem.category && (
                <span>Категория: <span className="text-[var(--text-primary)]">{catalogItem.category}</span></span>
              )}
              {catalogItem.risk_level && (
                <span>Риск: <span className="text-[var(--text-primary)]">{catalogItem.risk_level}</span></span>
              )}
              {catalogItem.jurisdiction && (
                <span>Юрисдикция: <span className="text-[var(--text-primary)]">{catalogItem.jurisdiction}</span></span>
              )}
              {catalogItem.language && (
                <span>Язык: <span className="text-[var(--text-primary)]">{catalogItem.language}</span></span>
              )}
              <span>
                Версий всего:{" "}
                <span className="text-[var(--text-primary)]">
                  {catalogItem.total_versions_count}
                </span>
              </span>
            </div>
          </div>
        )}

        {/* Versions */}
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
          {isLoading && (
            <LoadingBlock text="Загружаем версии..." rows={4} />
          )}

          {isError && (
            <InlineAlert
              tone="error"
              message="Не удалось загрузить версии инструкции."
            />
          )}

          {!isLoading && !isError && versions.length === 0 && (
            <EmptyState
              title="Версий нет"
              description="Для этого типа документа ещё не создано ни одной версии."
              action={
                <Button
                  variant="secondary"
                  size="sm"
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

          {!isLoading && !isError && versions.length > 0 && (
            <div className="space-y-4">
              {/* Drafts */}
              {draftVersions.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Черновики ({draftVersions.length})
                  </div>
                  <ul className="space-y-1.5">
                    {draftVersions.map((v) => (
                      <li key={v.id}>
                        <VersionRow
                          version={v}
                          onClick={() => handleOpenVersion(v.id)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Published */}
              {publishedVersions.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Published ({publishedVersions.length})
                  </div>
                  <ul className="space-y-1.5">
                    {publishedVersions.map((v) => (
                      <li key={v.id}>
                        <VersionRow
                          version={v}
                          onClick={() => handleOpenVersion(v.id)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Archived */}
              {archivedVersions.length > 0 && (
                <div>
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Archived ({archivedVersions.length})
                  </div>
                  <ul className="space-y-1.5">
                    {archivedVersions.map((v) => (
                      <li key={v.id}>
                        <VersionRow
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

// ─────────────────────────────────────────────────────────────
// Вспомогательный компонент: строка версии
// ─────────────────────────────────────────────────────────────

import type { InstructionVersionItem } from "../../types/instructions";

interface VersionRowProps {
  version: InstructionVersionItem;
  onClick: () => void;
}

const VersionRow: React.FC<VersionRowProps> = ({ version, onClick }) => {
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
              {version.name}
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

export default DocTypeDetailPage;


