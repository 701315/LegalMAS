// frontend/src/pages/tenant-instructions/TenantOwnedPlaybooksPage.tsx
//
// Каталог tenant-owned playbooks организации.
// Read-only listing — детальная работа с playbook происходит в Playbook Studio.

import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Layers,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import { useAuth } from "../../hooks/useAuth";
import {
  useTenantOwnedPlaybooks,
  type TenantPlaybookItem,
} from "../../api/tenantPlaybooks";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

// ─────────────────────────────────────────────────────────────
// SearchInput
// ─────────────────────────────────────────────────────────────

interface SearchInputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  placeholder,
}) => {
  const { t } = useTranslation("common");
  const resolvedPlaceholder = placeholder ?? t("search.placeholder");

  return (
    <div className="relative w-full">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]"
        aria-hidden="true"
      />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={resolvedPlaceholder}
        autoComplete="off"
        className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] py-2 pl-9 pr-9 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
      />
      {value.length > 0 && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={t("search.clear")}
          className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// PlaybookCard
// ─────────────────────────────────────────────────────────────

const PlaybookCard: React.FC<{
  item: TenantPlaybookItem;
  onOpen: () => void;
}> = ({ item, onOpen }) => {
  const { t } = useTranslation("instructions");

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
          <Layers className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
            {item.title}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
            {item.code}
          </p>
          {item.description && (
            <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
              {item.description}
            </p>
          )}
          {(item.deal_type ||
            item.jurisdiction ||
            item.language ||
            item.risk_profile) && (
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[var(--text-muted)]">
              {item.deal_type && (
                <span>
                  {t("tenantPlaybooks.card.deal")}: {item.deal_type}
                </span>
              )}
              {item.jurisdiction && (
                <span>
                  {t("tenantPlaybooks.card.jurisdiction")}: {item.jurisdiction}
                </span>
              )}
              {item.language && (
                <span>
                  {t("tenantPlaybooks.card.language")}: {item.language}
                </span>
              )}
              {item.risk_profile && (
                <span>
                  {t("tenantPlaybooks.card.risk")}: {item.risk_profile}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  );
};

// ─────────────────────────────────────────────────────────────
// TenantOwnedPlaybooksPage
// ─────────────────────────────────────────────────────────────

const TenantOwnedPlaybooksPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const navigate = useNavigate();
  const { tenantId } = useAuth();
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, refetch } =
    useTenantOwnedPlaybooks(tenantId ?? null);

  const playbooks = data ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return playbooks;
    return playbooks.filter(
      (p) =>
        p.title.toLowerCase().includes(q) ||
        p.code.toLowerCase().includes(q) ||
        (p.description?.toLowerCase().includes(q) ?? false) ||
        (p.deal_type?.toLowerCase().includes(q) ?? false),
    );
  }, [playbooks, search]);

  const isSearching = search.trim().length > 0;

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/tenant-admin/instructions")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                {t("tenantPlaybooks.backToInstructions")}
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                {t("tenantPlaybooks.title")}
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                {t("tenantPlaybooks.subtitle")}
              </p>

              {!isLoading && !isError && playbooks.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    {t("tenantPlaybooks.stats", { count: playbooks.length })}
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                {t("tenantPlaybooks.refresh")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  navigate("/tenant-admin/instructions/playbook-studio")
                }
                leftIcon={<Plus className="h-3.5 w-3.5" />}
              >
                {t("tenantPlaybooks.createInStudio")}
              </Button>
            </div>
          </div>
        </header>

        {/* ── Инфо ────────────────────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            {t("tenantPlaybooks.infoTitle")}
          </div>
          <div className="mt-4 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3">
            <p className="text-sm leading-6 text-[var(--text-secondary)]">
              {t("tenantPlaybooks.infoTextPrefix")}
              <button
                type="button"
                onClick={() =>
                  navigate("/tenant-admin/instructions/playbook-studio")
                }
                className="font-semibold text-[var(--accent-primary)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 rounded"
              >
                {t("tenantPlaybooks.infoLinkText")}
              </button>
              {t("tenantPlaybooks.infoTextSuffix")}
            </p>
          </div>
        </section>

        {/* ── Поиск ───────────────────────────────────────────── */}
        {!isLoading && !isError && playbooks.length > 0 && (
          <div className="flex items-center gap-3">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={t("tenantPlaybooks.searchPlaceholder")}
            />
            {isSearching && (
              <p className="hidden shrink-0 text-xs text-[var(--text-muted)] sm:block">
                {t("tenantPlaybooks.searchFound", {
                  filtered: filtered.length,
                  total: playbooks.length,
                })}
              </p>
            )}
          </div>
        )}

        {/* ── States ──────────────────────────────────────────── */}
        {isLoading && (
          <LoadingBlock text={t("tenantPlaybooks.loading")} rows={6} />
        )}

        {isError && (
          <InlineAlert
            tone="error"
            message={t("tenantPlaybooks.loadError")}
          />
        )}

        {!isLoading && !isError && playbooks.length === 0 && (
          <EmptyState
            title={t("tenantPlaybooks.emptyTitle")}
            description={t("tenantPlaybooks.emptyDesc")}
            action={
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  navigate("/tenant-admin/instructions/playbook-studio")
                }
                leftIcon={<Plus className="h-3.5 w-3.5" />}
              >
                {t("tenantPlaybooks.createInStudio")}
              </Button>
            }
          />
        )}

        {!isLoading && !isError && playbooks.length > 0 && filtered.length === 0 && (
          <EmptyState
            title={t("tenantPlaybooks.noResultsTitle")}
            description={t("tenantPlaybooks.noResultsDesc")}
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSearch("")}
              >
                {t("tenantPlaybooks.clearSearch")}
              </Button>
            }
          />
        )}

        {/* ── Список ───────────────────────────────────────────── */}
        {!isLoading && !isError && filtered.length > 0 && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {filtered.map((item) => (
              <PlaybookCard
                key={item.id}
                item={item}
                onOpen={() =>
                  navigate(
                    `/tenant-admin/instructions/playbook-studio?playbook=${item.id}`,
                  )
                }
              />
            ))}
          </div>
        )}

      </div>
    </div>
  );
};

export default TenantOwnedPlaybooksPage;


