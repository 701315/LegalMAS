// =============================================================
// src/pages/AdminPage.tsx
// Admin Panel — Clients (Tenants) list.
// Access restricted to superadmins only.
// =============================================================

import React, {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import {
  Building2,
  Plus,
  Users,
  FolderOpen,
  Search,
  X,
  Copy,
  Check,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  LayoutGrid,
  List,
  Download,
  ChevronRight,
} from "lucide-react";
import {
  useTenants,
  useDeactivateTenant,
  useActivateTenant,
  type Tenant,
} from "../api/admin";
import {
  exportTenantsExcel,
  exportTenantsWord,
  exportTenantsPDF,
} from "../api/adminExports";
import Button from "../components/ui/Button";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import TenantsTable, {
  type SortKey,
  type SortDir,
} from "../components/admin/TenantsTable";

// ─────────────────────────────────────────────────────────────
// Types & Constants
// ─────────────────────────────────────────────────────────────

type ViewMode = "cards" | "table";

interface SortOption {
  key: SortKey;
  label: string;
  defaultDir: SortDir;
}

const SORT_OPTIONS: SortOption[] = [
  { key: "name", label: "name", defaultDir: "asc" },
  { key: "created_at", label: "created_at", defaultDir: "desc" },
  { key: "deals_count", label: "deals_count", defaultDir: "desc" },
  { key: "users_count", label: "users_count", defaultDir: "desc" },
];

const LS_VIEW_MODE = "adminPage.viewMode";
const LS_SORT_KEY = "adminPage.sortKey";
const LS_SORT_DIR = "adminPage.sortDir";

// ─────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────

function formatDate(value: string, locale: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function filterTenants(list: Tenant[], query: string): Tenant[] {
  const q = query.trim().toLowerCase();
  if (!q) return list;
  return list.filter(
    (t) =>
      t.name.toLowerCase().includes(q) ||
      t.slug.toLowerCase().includes(q) ||
      t.id.toLowerCase().includes(q),
  );
}

function sortTenants(
  list: Tenant[],
  key: SortKey,
  dir: SortDir,
  locale: string,
): Tenant[] {
  const collator = new Intl.Collator(locale, { sensitivity: "base" });
  const multiplier = dir === "asc" ? 1 : -1;

  return [...list].sort((a, b) => {
    switch (key) {
      case "name":
        return collator.compare(a.name, b.name) * multiplier;
      case "created_at":
        return (
          (new Date(a.created_at).getTime() -
            new Date(b.created_at).getTime()) *
          multiplier
        );
      case "deals_count":
        return (a.deals_count - b.deals_count) * multiplier;
      case "users_count":
        return (a.users_count - b.users_count) * multiplier;
      default:
        return 0;
    }
  });
}

function readFromLS<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): T {
  try {
    const v = localStorage.getItem(key);
    if (v && (allowed as readonly string[]).includes(v)) return v as T;
  } catch {
    // localStorage might be unavailable (e.g. Safari private mode)
  }
  return fallback;
}

function writeToLS(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Silent fail
  }
}

// ─────────────────────────────────────────────────────────────
// SearchInput
// ─────────────────────────────────────────────────────────────

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  placeholder,
}) => {
  const { t } = useTranslation("admin");
  const resolvedPlaceholder = placeholder || t("clients.search.placeholder");

  return (
    <div className="relative w-full sm:w-96">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]"
        aria-hidden="true"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={resolvedPlaceholder}
        autoComplete="off"
        spellCheck={false}
        className={[
          "w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)]",
          "py-2 pl-9 pr-9 text-sm text-[var(--text-primary)]",
          "outline-none transition-colors",
          "placeholder:text-[var(--text-muted)]",
          "focus:border-[var(--accent-primary)]",
        ].join(" ")}
      />
      {value.length > 0 && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={t("search.clear", { ns: "common" })}
          className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)]"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// ViewToggle
// ─────────────────────────────────────────────────────────────

interface ViewToggleProps {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
}

const ViewToggle: React.FC<ViewToggleProps> = ({ value, onChange }) => {
  const { t } = useTranslation("admin");
  return (
    <div
      role="group"
      aria-label={t("clients.views.ariaLabel")}
      className="inline-flex rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-0.5"
    >
      <button
        type="button"
        onClick={() => onChange("cards")}
        aria-pressed={value === "cards"}
        title={t("clients.views.cards")}
        className={[
          "flex h-8 w-8 items-center justify-center rounded-lg transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-1",
          value === "cards"
            ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
            : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
        ].join(" ")}
      >
        <LayoutGrid className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => onChange("table")}
        aria-pressed={value === "table"}
        title={t("clients.views.table")}
        className={[
          "flex h-8 w-8 items-center justify-center rounded-lg transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-1",
          value === "table"
            ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
            : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
        ].join(" ")}
      >
        <List className="h-4 w-4" />
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// ExportMenu
// ─────────────────────────────────────────────────────────────

interface ExportMenuProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onExportExcel: () => void;
  onExportWord: () => void;
  onExportPDF: () => void;
  disabled?: boolean;
}

const ExportMenu: React.FC<ExportMenuProps> = ({
  isOpen,
  onToggle,
  onClose,
  onExportExcel,
  onExportWord,
  onExportPDF,
  disabled = false,
}) => {
  const { t } = useTranslation("admin");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const slideoutId = useId();

  const restoreFocusToTrigger = useCallback(() => {
    triggerRef.current?.focus();
  }, []);

  const closeAndRestoreFocus = useCallback(() => {
    restoreFocusToTrigger();
    onClose();
  }, [restoreFocusToTrigger, onClose]);

  /**
   * Wrap an export handler so focus returns to the trigger button
   * BEFORE the parent collapses the slideout (which applies `inert`).
   * Ordering matters: if we focused after the parent state change,
   * React would apply `inert` while focus is still inside the
   * container, and the browser would move focus to <body>.
   */
  const handleExport = useCallback(
    (handler: () => void) => () => {
      restoreFocusToTrigger();
      handler();
    },
    [restoreFocusToTrigger],
  );

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) onClose();
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAndRestoreFocus();
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose, closeAndRestoreFocus]);

  return (
    <div ref={containerRef} className="relative flex items-center">
      <Button
        ref={triggerRef}
        type="button"
        size="sm"
        variant={isOpen ? "outline" : "secondary"}
        onClick={onToggle}
        disabled={disabled}
        aria-expanded={isOpen}
        aria-controls={slideoutId}
        leftIcon={<Download className="h-4 w-4" />}
        rightIcon={
          <ChevronRight
            className={`h-4 w-4 transition-transform duration-200 ${
              isOpen ? "rotate-90" : "rotate-0"
            }`}
          />
        }
        className={
          isOpen
            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
            : ""
        }
      >
        {t("clients.export.button")}
      </Button>

      <div
        id={slideoutId}
        className={`ml-2 flex origin-left items-center gap-2 overflow-hidden transition-all duration-300 ease-out ${
          isOpen
            ? "max-w-[340px] translate-x-0 opacity-100"
            : "pointer-events-none max-w-0 -translate-x-2 opacity-0"
        }`}
        inert={!isOpen}
      >
        <div className="flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-2 py-1.5 shadow-sm">
          <Button
            size="sm"
            variant="secondary"
            onClick={handleExport(onExportExcel)}
          >
            {t("clients.export.excel")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleExport(onExportWord)}
          >
            {t("clients.export.word")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handleExport(onExportPDF)}
          >
            {t("clients.export.pdf")}
          </Button>
        </div>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// SortDropdown
// ─────────────────────────────────────────────────────────────

interface SortDropdownProps {
  sortKey: SortKey;
  sortDir: SortDir;
  onChange: (key: SortKey, dir: SortDir) => void;
}

const SortDropdown: React.FC<SortDropdownProps> = ({
  sortKey,
  sortDir,
  onChange,
}) => {
  const { t } = useTranslation("admin");
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const activeOption = SORT_OPTIONS.find((opt) => opt.key === sortKey);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  const handleOptionClick = (option: SortOption) => {
    if (option.key === sortKey) {
      onChange(sortKey, sortDir === "asc" ? "desc" : "asc");
    } else {
      onChange(option.key, option.defaultDir);
      setIsOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <Button
        type="button"
        size="sm"
        variant={isOpen ? "outline" : "secondary"}
        onClick={() => setIsOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        leftIcon={<ArrowUpDown className="h-3.5 w-3.5" />}
        rightIcon={
          sortDir === "asc" ? (
            <ArrowUp className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
          ) : (
            <ArrowDown className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
          )
        }
        className={
          isOpen
            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
            : ""
        }
      >
        <span className="hidden text-[var(--text-muted)] sm:inline">
          {t("clients.sort.prefix")}
        </span>
        {t(`clients.sort.options.${activeOption?.key}`)}
      </Button>

      {isOpen && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1.5 w-64 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-card)] shadow-lg"
        >
          <div className="border-b border-[var(--border)] px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              {t("clients.sort.by")}
            </p>
          </div>

          <div className="py-1">
            {SORT_OPTIONS.map((option) => {
              const isActive = option.key === sortKey;
              return (
                <button
                  key={option.key}
                  type="button"
                  role="menuitem"
                  onClick={() => handleOptionClick(option)}
                  className={[
                    "flex w-full items-center justify-between gap-2 px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
                  ].join(" ")}
                >
                  <span className="font-medium">{t(`clients.sort.options.${option.key}`)}</span>
                  <span className="flex items-center gap-1 text-xs">
                    {isActive &&
                      (sortDir === "asc" ? (
                        <>
                          <ArrowUp className="h-3 w-3 text-[var(--accent-primary)]" />
                          <span className="text-[var(--accent-primary)]">
                            {t("clients.sort.asc")}
                          </span>
                        </>
                      ) : (
                        <>
                          <ArrowDown className="h-3 w-3 text-[var(--accent-primary)]" />
                          <span className="text-[var(--accent-primary)]">
                            {t("clients.sort.desc")}
                          </span>
                        </>
                      ))}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="border-t border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2">
            <p className="text-[10px] text-[var(--text-muted)]">
              {t("clients.sort.directionsHint")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// CopyableId
// ─────────────────────────────────────────────────────────────

const CopyableId: React.FC<{ id: string }> = ({ id }) => {
  const { t } = useTranslation("admin");
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Silent fail
    }
  };

  return (
    <div className="mt-0.5 flex items-center gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-faint)]">
        ID
      </span>
      <code
        className="select-all font-mono text-[11px] text-[var(--text-secondary)]"
        title={t("clients.card.idTooltip", { defaultValue: "Click to select, button to copy" })}
      >
        {id}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? t("clients.card.copied") : t("clients.card.copyId")}
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-1"
      >
        {copied ? (
          <Check className="h-3 w-3 text-[var(--color-success-text)]" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// TenantCard
// ─────────────────────────────────────────────────────────────

interface TenantCardProps {
  tenant: Tenant;
  onDeactivate: () => void;
  onActivate: () => void;
  onManage: () => void;
}

const TenantCard: React.FC<TenantCardProps> = ({
  tenant,
  onDeactivate,
  onActivate,
  onManage,
}) => {
  const { t, i18n } = useTranslation("admin");

  return (
    <article
      className={[
        "rounded-2xl border bg-[var(--bg-card)] p-5 shadow-sm transition-all duration-200",
        tenant.is_active
          ? "border-[var(--border)] hover:border-[var(--border-strong)] hover:shadow-md"
          : "border-[var(--border-soft)] opacity-60",
      ].join(" ")}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Building2 className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
          <h2 className="truncate text-base font-semibold text-[var(--text-primary)]">
            {tenant.name}
          </h2>
          {!tenant.is_active && (
            <span className="shrink-0 rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-muted)]">
              {t("clients.card.deactivated")}
            </span>
          )}
        </div>

        <p className="mt-1 text-xs text-[var(--text-muted)]">
          slug: {tenant.slug}
        </p>

        <CopyableId id={tenant.id} />

        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {t("clients.card.created", { date: formatDate(tenant.created_at, i18n.language) })}
        </p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Link
          to={`/admin/tenants/${tenant.id}`}
          className="group rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2 transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--accent-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
        >
          <div className="flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5 text-[var(--text-muted)] transition-colors group-hover:text-[var(--accent-primary)]" />
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)] transition-colors group-hover:text-[var(--accent-primary)]">
              {t("clients.card.users")}
            </p>
          </div>
          <p className="mt-1 text-lg font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
            {tenant.users_count}
          </p>
        </Link>

        <Link
          to={`/admin/tenants/${tenant.id}/projects`}
          className="group rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2 transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--accent-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
        >
          <div className="flex items-center gap-1.5">
            <FolderOpen className="h-3.5 w-3.5 text-[var(--text-muted)] transition-colors group-hover:text-[var(--accent-primary)]" />
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)] transition-colors group-hover:text-[var(--accent-primary)]">
              {t("clients.card.projects")}
            </p>
          </div>
          <p className="mt-1 text-lg font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
            {tenant.deals_count}
          </p>
        </Link>
      </div>

      {tenant.notes && (
        <p className="mt-3 text-xs text-[var(--text-secondary)]">
          {tenant.notes}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          className="flex-1"
          onClick={onManage}
        >
          {t("clients.card.manage")}
        </Button>

        {tenant.is_active ? (
          <Button size="sm" variant="danger" onClick={onDeactivate}>
            {t("clients.card.deactivate")}
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={onActivate}>
            {t("clients.card.activate")}
          </Button>
        )}
      </div>
    </article>
  );
};

// ─────────────────────────────────────────────────────────────
// AdminPage
// ─────────────────────────────────────────────────────────────

const AdminPage: React.FC = () => {
  const { t, i18n } = useTranslation("admin");
  const navigate = useNavigate();

  const [includeInactive, setIncludeInactive] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const [viewMode, setViewMode] = useState<ViewMode>(() =>
    readFromLS<ViewMode>(LS_VIEW_MODE, ["cards", "table"], "cards"),
  );
  const [sortKey, setSortKey] = useState<SortKey>(() =>
    readFromLS<SortKey>(
      LS_SORT_KEY,
      ["name", "created_at", "deals_count", "users_count"],
      "name",
    ),
  );
  const [sortDir, setSortDir] = useState<SortDir>(() =>
    readFromLS<SortDir>(LS_SORT_DIR, ["asc", "desc"], "asc"),
  );

  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);

  const [confirmTarget, setConfirmTarget] = useState<Tenant | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    "deactivate" | "activate" | null
  >(null);

  const { data: tenants, isLoading, error } = useTenants(includeInactive);
  const deactivateMutation = useDeactivateTenant();
  const activateMutation = useActivateTenant();

  useEffect(() => {
    writeToLS(LS_VIEW_MODE, viewMode);
  }, [viewMode]);
  useEffect(() => {
    writeToLS(LS_SORT_KEY, sortKey);
  }, [sortKey]);
  useEffect(() => {
    writeToLS(LS_SORT_DIR, sortDir);
  }, [sortDir]);

  const handleConfirm = async () => {
    if (!confirmTarget || !confirmAction) return;
    if (confirmAction === "deactivate") {
      await deactivateMutation.mutateAsync(confirmTarget.id);
    } else {
      await activateMutation.mutateAsync(confirmTarget.id);
    }
    setConfirmTarget(null);
    setConfirmAction(null);
  };

  const handleCancel = () => {
    setConfirmTarget(null);
    setConfirmAction(null);
  };

  const handleSortChange = (key: SortKey, dir: SortDir) => {
    setSortKey(key);
    setSortDir(dir);
  };

  const tenantList = tenants ?? [];
  const totalCount = tenantList.length;
  const activeCount = tenantList.filter((t) => t.is_active).length;

  const processedList = useMemo(() => {
    const filtered = filterTenants(tenantList, searchQuery);
    return sortTenants(filtered, sortKey, sortDir, i18n.language);
  }, [tenantList, searchQuery, sortKey, sortDir, i18n.language]);

  const isSearching = searchQuery.trim().length > 0;
  const filteredCount = processedList.length;

  const handleExportExcel = async () => {
    try {
      await exportTenantsExcel(processedList);
      setIsExportMenuOpen(false);
    } catch (err) {
      console.error(err);
      alert(t("clients.export.errorExcel"));
    }
  };

  const handleExportWord = async () => {
    try {
      await exportTenantsWord(processedList);
      setIsExportMenuOpen(false);
    } catch (err) {
      console.error(err);
      alert(t("clients.export.errorWord"));
    }
  };

  const handleExportPDF = async () => {
    try {
      await exportTenantsPDF(processedList);
      setIsExportMenuOpen(false);
    } catch (err) {
      console.error(err);
      alert(t("clients.export.errorPdf"));
    }
  };

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Header ──────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                {t("clients.header.title")}
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                {t("clients.header.total", { count: totalCount })}
                <span className="mx-1.5 text-[var(--text-muted)]">·</span>
                {t("clients.header.active", { count: activeCount })}
                <span className="mx-1.5 text-[var(--text-muted)]">·</span>
                <label className="inline-flex cursor-pointer items-center gap-1.5 align-middle hover:text-[var(--text-primary)]">
                  <input
                    type="checkbox"
                    checked={includeInactive}
                    onChange={(e) => setIncludeInactive(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-[var(--border)] align-middle"
                  />
                  {t("clients.header.showDeactivated")}
                </label>
              </p>
            </div>

            <Button
              size="sm"
              variant="primary"
              onClick={() => navigate("/admin/tenants/new")}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              {t("clients.header.newClient")}
            </Button>
          </div>
        </header>

        {/* ── Sticky Control Panel ────────────────────────────── */}
        {!isLoading && !error && totalCount > 0 && (
          <div
            className={[
              "sticky -top-4 z-10 -mx-4 md:-top-5 md:-mx-5",
              "border-b border-[var(--border-soft)] bg-[var(--bg-surface)]/95",
              "px-4 py-3 backdrop-blur-sm md:px-5",
            ].join(" ")}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-1 items-center gap-3">
                <SearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  placeholder={t("clients.search.placeholder")}
                />
                {isSearching && (
                  <p className="hidden text-xs text-[var(--text-muted)] sm:block">
                    {t("catalog.searchResults", { ns: "instructions", filtered: filteredCount, total: totalCount })}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <ExportMenu
                  isOpen={isExportMenuOpen}
                  onToggle={() => setIsExportMenuOpen((v) => !v)}
                  onClose={() => setIsExportMenuOpen(false)}
                  onExportExcel={handleExportExcel}
                  onExportWord={handleExportWord}
                  onExportPDF={handleExportPDF}
                  disabled={filteredCount === 0}
                />
                <SortDropdown
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onChange={handleSortChange}
                />
                <ViewToggle value={viewMode} onChange={setViewMode} />
              </div>
            </div>

            {isSearching && (
              <p className="mt-2 text-xs text-[var(--text-muted)] sm:hidden">
                {t("catalog.searchResults", { ns: "instructions", filtered: filteredCount, total: totalCount })}
              </p>
            )}
          </div>
        )}

        {/* ── Skeleton ────────────────────────────────────────── */}
        {isLoading && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm"
              >
                <div className="skeleton mb-3 h-5 w-48" />
                <div className="skeleton mb-2 h-4 w-32" />
                <div className="skeleton mt-4 h-16 w-full" />
              </div>
            ))}
          </div>
        )}

        {/* ── Error ───────────────────────────────────────────── */}
        {error && !isLoading && (
          <div className="rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] p-5 text-sm text-[var(--color-error-text)]">
            {t("clients.error")}
          </div>
        )}

        {/* ── Empty State ─────────────────────────────────────── */}
        {!isLoading && !error && totalCount === 0 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <Building2 className="mx-auto mb-3 h-8 w-8 text-[var(--text-muted)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              {t("clients.empty.title")}
            </p>
            <div className="mt-4 flex justify-center">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate("/admin/tenants/new")}
              >
                {t("clients.empty.button")}
              </Button>
            </div>
          </div>
        )}

        {/* ── No Results Found ────────────────────────────────── */}
        {!isLoading && !error && totalCount > 0 && filteredCount === 0 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <Search className="mx-auto mb-3 h-8 w-8 text-[var(--text-muted)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              {t("clients.notFound.title", { query: searchQuery.trim() })}
            </p>
            <div className="mt-4 flex justify-center">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setSearchQuery("")}
              >
                {t("clients.notFound.button")}
              </Button>
            </div>
          </div>
        )}

        {/* ── Clients List ────────────────────────────────────── */}
        {!isLoading && !error && filteredCount > 0 && (
          <>
            {viewMode === "cards" ? (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {processedList.map((tenant) => (
                  <TenantCard
                    key={tenant.id}
                    tenant={tenant}
                    onDeactivate={() => {
                      setConfirmTarget(tenant);
                      setConfirmAction("deactivate");
                    }}
                    onActivate={() => {
                      setConfirmTarget(tenant);
                      setConfirmAction("activate");
                    }}
                    onManage={() => navigate(`/admin/tenants/${tenant.id}`)}
                  />
                ))}
              </div>
            ) : (
              <TenantsTable
                tenants={processedList}
                sortKey={sortKey}
                sortDir={sortDir}
                onSortChange={handleSortChange}
                onDeactivate={(t) => {
                  setConfirmTarget(t);
                  setConfirmAction("deactivate");
                }}
                onActivate={(t) => {
                  setConfirmTarget(t);
                  setConfirmAction("activate");
                }}
              />
            )}
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirmTarget !== null}
        title={
          confirmAction === "deactivate"
            ? t("clients.confirm.deactivateTitle", { name: confirmTarget?.name ?? "" })
            : t("clients.confirm.activateTitle", { name: confirmTarget?.name ?? "" })
        }
        description={
          confirmAction === "deactivate"
            ? t("clients.confirm.deactivateDesc")
            : t("clients.confirm.activateDesc")
        }
        confirmLabel={
          confirmAction === "deactivate" ? t("clients.confirm.deactivateButton") : t("clients.confirm.activateButton")
        }
        cancelLabel={t("clients.confirm.cancelButton")}
        confirmVariant={confirmAction === "deactivate" ? "danger" : "primary"}
        isLoading={
          deactivateMutation.isPending || activateMutation.isPending
        }
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  );
};

export default AdminPage;


