// frontend/src/pages/tenant-instructions/TenantBaseDocTypeDetailPage.tsx
//
// Read-only detail страница базовой doc-type instruction для tenant admin.
//
// URL: /tenant-admin/instructions/base-doc-types/:docType
//      /tenant-admin/instructions/base-doc-types/:docType?version=<id>

import React, { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye, GitBranch } from "lucide-react";

import {
  useBaseDocTypeCatalog,
  useBaseDocTypeVersions,
  useBaseDocTypeVersionDetail,
} from "../../api/baseInstructions";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import type {
  InstructionCatalogItem,
  InstructionVersionItem,
} from "../../types/instructions";

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(
  value: string | null | undefined,
  locale: string,
): string | null {
  if (!value) return null;
  try {
    return new Date(value).toLocaleDateString(locale);
  } catch {
    return null;
  }
}

function pickDefaultVersionId(
  versions: InstructionVersionItem[],
): string | null {
  if (versions.length === 0) return null;
  const published = versions.find((v) => v.version_status === "published");
  if (published) return published.id;
  return versions[0].id;
}

// ── DocTypeInfoCard ────────────────────────────────────────────────────────────

const DocTypeInfoCard: React.FC<{
  docTypeCode: string;
  name: string;
  item: InstructionCatalogItem;
}> = ({ docTypeCode, name, item }) => {
  const { t } = useTranslation("instructions");

  return (
    <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {t("tenantBase.detail.info.aboutDocType")}
      </h3>

      <div className="mt-3 space-y-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
            {t("tenantBase.detail.info.name")}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
            {name}
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
            {t("tenantBase.detail.info.code")}
          </div>
          <div className="mt-0.5 break-all font-mono text-xs text-[var(--text-secondary)]">
            {docTypeCode}
          </div>
        </div>

        {(item.parent ||
          item.risk_level ||
          item.language ||
          item.jurisdiction) && (
          <div className="grid grid-cols-2 gap-2">
            {item.parent && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("tenantBase.detail.info.parent")}
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-primary)]">
                  {item.parent}
                </div>
              </div>
            )}
            {item.risk_level && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("tenantBase.detail.info.risk")}
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-primary)]">
                  {item.risk_level}
                </div>
              </div>
            )}
            {item.language && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("tenantBase.detail.info.language")}
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-primary)]">
                  {item.language}
                </div>
              </div>
            )}
            {item.jurisdiction && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                  {t("tenantBase.detail.info.jurisdiction")}
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-primary)]">
                  {item.jurisdiction}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-3 gap-2 border-t border-[var(--border-soft)] pt-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
              {t("tenantBase.detail.info.total")}
            </div>
            <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
              {item.total_versions_count}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
              {t("tenantBase.detail.info.published")}
            </div>
            <div
              className={[
                "mt-0.5 text-sm font-semibold",
                item.has_published
                  ? "text-[var(--color-success-text)]"
                  : "text-[var(--text-muted)]",
              ].join(" ")}
            >
              {item.has_published
                ? t("tenantBase.detail.info.yes")
                : t("tenantBase.detail.info.no")}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.1em] text-[var(--text-faint)]">
              {t("tenantBase.detail.info.draft")}
            </div>
            <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
              {item.draft_versions_count}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

// ── VersionSidebarItem ─────────────────────────────────────────────────────────

const VersionSidebarItem: React.FC<{
  version: InstructionVersionItem;
  isSelected: boolean;
  onClick: () => void;
}> = ({ version, isSelected, onClick }) => {
  const { t, i18n } = useTranslation("instructions");
  const publishedAt = formatDate(version.published_at, i18n.language);
  const updatedAt = formatDate(version.updated_at, i18n.language);
  const displayDate = publishedAt ?? updatedAt;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={isSelected ? "true" : undefined}
      className={[
        "group w-full rounded-xl border px-3 py-2.5 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
        isSelected
          ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] shadow-sm"
          : "border-[var(--border-soft)] bg-[var(--bg-card)] hover:border-[var(--border-strong)]",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-[var(--text-primary)]">
            {version.name ?? t("tenantBase.detail.sidebar.unnamed")}
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

// ── VersionGroup ───────────────────────────────────────────────────────────────

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

// ── VersionsSidebar ────────────────────────────────────────────────────────────

const VersionsSidebar: React.FC<{
  versions: InstructionVersionItem[];
  selectedVersionId: string | null;
  onSelectVersion: (versionId: string) => void;
  isLoading: boolean;
  isError: boolean;
}> = ({ versions, selectedVersionId, onSelectVersion, isLoading, isError }) => {
  const { t } = useTranslation("instructions");
  const drafts = versions.filter((v) => v.version_status === "draft");
  const published = versions.filter((v) => v.version_status === "published");
  const archived = versions.filter((v) => v.version_status === "archived");

  return (
    <section className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {t("tenantBase.detail.sidebar.title")}
        </h3>
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
          <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{versions.length}</span>
        </div>
      </div>

      <div className="mt-3">
        {isLoading && (
          <LoadingBlock
            text={t("tenantBase.detail.sidebar.loading")}
            rows={3}
          />
        )}

        {isError && (
          <InlineAlert
            tone="error"
            message={t("tenantBase.detail.sidebar.loadError")}
          />
        )}

        {!isLoading && !isError && versions.length === 0 && (
          <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-4 text-center text-[11px] text-[var(--text-muted)]">
            {t("tenantBase.detail.sidebar.emptyDocType")}
          </p>
        )}

        {!isLoading && !isError && versions.length > 0 && (
          <div className="space-y-4">
            {drafts.length > 0 && (
              <VersionGroup
                label={t("tenantBase.detail.sidebar.drafts")}
                count={drafts.length}
                versions={drafts}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
            {published.length > 0 && (
              <VersionGroup
                label={t("tenantBase.detail.sidebar.published")}
                count={published.length}
                versions={published}
                selectedVersionId={selectedVersionId}
                onSelectVersion={onSelectVersion}
              />
            )}
            {archived.length > 0 && (
              <VersionGroup
                label={t("tenantBase.detail.sidebar.archived")}
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

// ── VersionViewPane ────────────────────────────────────────────────────────────

const VersionViewPane: React.FC<{
  versionId: string;
}> = ({ versionId }) => {
  const { t } = useTranslation("instructions");
  const { data: version, isLoading, isError } =
    useBaseDocTypeVersionDetail(versionId);

  if (isLoading) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <LoadingBlock text={t("tenantBase.detail.viewer.loading")} rows={6} />
      </section>
    );
  }

  if (isError || !version) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
        <InlineAlert
          tone="error"
          message={t("tenantBase.detail.viewer.loadError")}
        />
      </section>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {version.source_yaml ? (
        <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              {t("tenantBase.detail.viewer.sourceYaml")}
            </h3>
            <div className="flex items-center gap-2">
              <VersionStatusBadge
                status={version.version_status}
                size="xs"
              />
              <Eye
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
            </div>
          </div>
          <pre className="min-h-0 flex-1 overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-3 text-[11px] font-mono leading-relaxed text-[var(--text-primary)]">
            {version.source_yaml}
          </pre>
        </section>
      ) : (
        <section className="flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated-soft)] p-10 text-center">
          <p className="text-sm text-[var(--text-muted)]">
            {t("tenantBase.detail.viewer.noYaml")}
          </p>
        </section>
      )}
    </div>
  );
};

// ── Page ───────────────────────────────────────────────────────────────────────

const TenantBaseDocTypeDetailPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const { docType } = useParams<{ docType: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const versionParam = searchParams.get("version");

  const { data: catalog } = useBaseDocTypeCatalog();
  const catalogItem =
    catalog?.items.find((i) => i.doc_type_code === docType) ?? null;

  const {
    data: versionsData,
    isLoading: isVersionsLoading,
    isError: isVersionsError,
  } = useBaseDocTypeVersions(docType ?? null);

  const versions = useMemo(
    () => versionsData?.items ?? [],
    [versionsData?.items],
  );

  const pendingVersionIdRef = useRef<string | null>(null);

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

  useEffect(() => {
    if (!pendingVersionIdRef.current) return;
    if (versions.some((v) => v.id === pendingVersionIdRef.current)) {
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

  const displayName =
    catalogItem?.name ?? docType ?? t("tenantBase.detail.fallbackDocType");

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-4 py-4 md:px-5 md:py-5">

      {/* ── Шапка ─────────────────────────────────────────────── */}
      <header className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
        <button
          type="button"
          onClick={() =>
            navigate("/tenant-admin/instructions/base-doc-types")
          }
          className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t("tenantBase.detail.backToDocTypes")}
        </button>

        <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
          {displayName}
        </h1>

        {docType && displayName !== docType && (
          <p className="mt-2 font-mono text-sm text-[var(--text-secondary)]">
            {docType}
          </p>
        )}
      </header>

      {/* ── Empty ─────────────────────────────────────────────── */}
      {!isVersionsLoading && !isVersionsError && versions.length === 0 && (
        <EmptyState
          title={t("tenantBase.detail.empty.title")}
          description={t("tenantBase.detail.empty.descDocType")}
        />
      )}

      {/* ── Main layout ───────────────────────────────────────── */}
      {(isVersionsLoading || versions.length > 0) && (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-3">

          {/* Sidebar */}
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto overscroll-contain xl:col-span-1">
            {catalogItem && (
              <DocTypeInfoCard
                docTypeCode={docType ?? ""}
                name={displayName}
                item={catalogItem}
              />
            )}

            <VersionsSidebar
              versions={versions}
              selectedVersionId={selectedVersionId}
              onSelectVersion={(id) =>
                setSearchParams({ version: id }, { replace: false })
              }
              isLoading={isVersionsLoading}
              isError={isVersionsError}
            />
          </div>

          {/* View pane */}
          <div className="flex min-h-0 min-w-0 flex-col overflow-y-auto overscroll-contain xl:col-span-2">
            {selectedVersionId ? (
              <VersionViewPane
                key={selectedVersionId}
                versionId={selectedVersionId}
              />
            ) : (
              <section className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated-soft)] p-10 text-center">
                <p className="text-sm text-[var(--text-muted)]">
                  {t("tenantBase.detail.selectPrompt")}
                </p>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantBaseDocTypeDetailPage;


