// =============================================================
// src/pages/AdminTenantProjectsPage.tsx
// Список проектов конкретного клиента — вид superadmin.
// Маршрут: /admin/tenants/:tenantId/projects
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  FolderOpen,
  Calendar,
  Users,
  FileText,
  Clock,
} from "lucide-react";
import { useTenant, useTenantDeals, type TenantDeal } from "../api/admin";
import Button from "../components/ui/Button";

// ─────────────────────────────────────────────────────────────
// Утилиты
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

function getStatusConfig(
  status: string,
  tFn: (key: string, options?: Record<string, unknown>) => string,
) {
  const baseClass = "bg-[var(--bg-elevated-soft)] text-[var(--text-muted)] border-[var(--border-soft)]";
  const classMap: Record<string, string> = {
    active: "bg-[var(--color-success-bg)] text-[var(--color-success-text)] border-[var(--color-success-border)]",
  };

  const label = tFn(`tenantProjects.statuses.${status}`, { defaultValue: status });
  return {
    label,
    className: classMap[status] ?? baseClass,
  };
}

// ─────────────────────────────────────────────────────────────
// DealCard
// ─────────────────────────────────────────────────────────────

interface DealCardProps {
  deal: TenantDeal;
  t: (key: string, options?: Record<string, unknown>) => string;
  locale: string;
}

const DealCard: React.FC<DealCardProps> = ({ deal, t, locale }) => {
  const statusCfg = getStatusConfig(deal.status, t);

  return (
    <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md">
      {/* Заголовок карточки */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <FolderOpen className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
          <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {deal.name}
          </h3>
        </div>
        <span
          className={[
            "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
            statusCfg.className,
          ].join(" ")}
        >
          {statusCfg.label}
        </span>
      </div>

      {/* Мета */}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          <Calendar className="h-3 w-3 shrink-0" />
          <span>{t("tenantProjects.created", { date: formatDate(deal.created_at, locale) })}</span>
        </div>

        {deal.created_by_email && (
          <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
            <Clock className="h-3 w-3 shrink-0" />
            <span className="truncate">{deal.created_by_email}</span>
          </div>
        )}

        <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          <FileText className="h-3 w-3 shrink-0" />
          <span>{t("tenantProjects.documents", { count: deal.documents_count })}</span>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          <Users className="h-3 w-3 shrink-0" />
          <span>{t("tenantProjects.members", { count: deal.members_count })}</span>
        </div>
      </div>
    </article>
  );
};

// ─────────────────────────────────────────────────────────────
// AdminTenantProjectsPage
// ─────────────────────────────────────────────────────────────

const AdminTenantProjectsPage: React.FC = () => {
  const { t, i18n } = useTranslation("admin");
  const { tenantId } = useParams<{ tenantId: string }>();
  const navigate = useNavigate();

  const { data: tenant, isLoading: tenantLoading } = useTenant(
    tenantId ?? null,
  );
  const {
    data: deals,
    isLoading: dealsLoading,
    error,
  } = useTenantDeals(tenantId ?? null);

  const isLoading = tenantLoading || dealsLoading;

  // ── Загрузка ────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
        <div className="animate-fadein space-y-4">
          <div className="skeleton h-8 w-64 rounded-xl" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton h-32 rounded-2xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Клиент не найден ────────────────────────────────────────
  if (!tenant) {
    return (
      <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
        <div className="animate-fadein">
          <div className="max-w-4xl rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <p className="text-sm text-[var(--text-secondary)]">
              {t("tenantProjects.notFound")}
            </p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-4"
              onClick={() => navigate("/admin")}
            >
              {t("tenantProjects.back")}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const dealList = deals ?? [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-8">
        {/* ── Заголовок страницы (на фоне) ─────────────────── */}
        <header>
          <button
            type="button"
            onClick={() => navigate(`/admin/tenants/${tenant.id}`)}
            className="mb-2 flex items-center gap-1.5 rounded-md text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {tenant.name}
          </button>

          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            {t("tenantProjects.title")}
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            <Link
              to="/admin"
              className="rounded-sm transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
            >
              {t("tenantProjects.breadcrumbClients")}
            </Link>
            <span className="mx-1.5">·</span>
            <Link
              to={`/admin/tenants/${tenant.id}`}
              className="rounded-sm transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
            >
              {tenant.name}
            </Link>
            <span className="mx-1.5">·</span>
            {t("tenantProjects.totalProjects", { count: dealList.length })}
          </p>
        </header>

        {/* ── Ошибка ───────────────────────────────────────── */}
        {error && (
          <div className="max-w-3xl rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] p-5 text-sm text-[var(--color-error-text)]">
            {t("tenantProjects.error")}
          </div>
        )}

        {/* ── Пусто ────────────────────────────────────────── */}
        {!error && dealList.length === 0 && (
          <div className="max-w-3xl rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <FolderOpen className="mx-auto mb-3 h-8 w-8 text-[var(--text-muted)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              {t("tenantProjects.empty")}
            </p>
          </div>
        )}

        {/* ── Сетка проектов ───────────────────────────────── */}
        {!error && dealList.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {dealList.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                t={t}
                locale={i18n.language}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminTenantProjectsPage;


