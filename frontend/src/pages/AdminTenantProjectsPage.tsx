// =============================================================
// src/pages/AdminTenantProjectsPage.tsx
// Список проектов конкретного клиента — вид superadmin.
// Маршрут: /admin/tenants/:tenantId/projects
// =============================================================

import React from "react";
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

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

// Статус проекта → человекочитаемая метка + цвет
const STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  active: {
    label: "Активен",
    className:
      "bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)] border-[color:var(--color-success-border)]",
  },
  draft: {
    label: "Черновик",
    className:
      "bg-[var(--bg-elevated-soft)] text-[var(--text-muted)] border-[var(--border-soft)]",
  },
  archived: {
    label: "Архив",
    className:
      "bg-[var(--bg-elevated-soft)] text-[var(--text-muted)] border-[var(--border-soft)]",
  },
  completed: {
    label: "Завершён",
    className:
      "bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] border-[var(--border-soft)]",
  },
};

function getStatusConfig(status: string) {
  return (
    STATUS_CONFIG[status] ?? {
      label: status,
      className:
        "bg-[var(--bg-elevated-soft)] text-[var(--text-muted)] border-[var(--border-soft)]",
    }
  );
}

// ─────────────────────────────────────────────────────────────
// DealCard
// ─────────────────────────────────────────────────────────────

interface DealCardProps {
  deal: TenantDeal;
}

const DealCard: React.FC<DealCardProps> = ({ deal }) => {
  const statusCfg = getStatusConfig(deal.status);

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
          <span>Создан: {formatDate(deal.created_at)}</span>
        </div>

        {deal.created_by_email && (
          <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
            <Clock className="h-3 w-3 shrink-0" />
            <span className="truncate">{deal.created_by_email}</span>
          </div>
        )}

        <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          <FileText className="h-3 w-3 shrink-0" />
          <span>Документов: {deal.documents_count}</span>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          <Users className="h-3 w-3 shrink-0" />
          <span>Участников: {deal.members_count}</span>
        </div>
      </div>
    </article>
  );
};

// ─────────────────────────────────────────────────────────────
// AdminTenantProjectsPage
// ─────────────────────────────────────────────────────────────

const AdminTenantProjectsPage: React.FC = () => {
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
              Клиент не найден.
            </p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-4"
              onClick={() => navigate("/admin")}
            >
              ← Все клиенты
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
            className="mb-2 flex items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {tenant.name}
          </button>

          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Проекты клиента
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            <Link
              to="/admin"
              className="hover:text-[var(--text-secondary)]"
            >
              Клиенты
            </Link>
            <span className="mx-1.5">·</span>
            <Link
              to={`/admin/tenants/${tenant.id}`}
              className="hover:text-[var(--text-secondary)]"
            >
              {tenant.name}
            </Link>
            <span className="mx-1.5">·</span>
            Всего проектов: {dealList.length}
          </p>
        </header>

        {/* ── Ошибка ───────────────────────────────────────── */}
        {error && (
          <div className="max-w-3xl rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            Не удалось загрузить проекты клиента.
          </div>
        )}

        {/* ── Пусто ────────────────────────────────────────── */}
        {!error && dealList.length === 0 && (
          <div className="max-w-3xl rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <FolderOpen className="mx-auto mb-3 h-8 w-8 text-[var(--text-muted)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              У клиента пока нет проектов.
            </p>
          </div>
        )}

        {/* ── Сетка проектов ───────────────────────────────── */}
        {!error && dealList.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {dealList.map((deal) => (
              <DealCard key={deal.id} deal={deal} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminTenantProjectsPage;


