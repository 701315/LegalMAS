// =============================================================
// src/pages/AdminPage.tsx
// Административная панель — список клиентов.
// Доступно только для superadmin.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Plus, Users, FolderOpen } from "lucide-react";
import {
  useTenants,
  useDeactivateTenant,
  useActivateTenant,
  type Tenant,
} from "../api/admin";
import Button from "../components/ui/Button";
import ConfirmDialog from "../components/ui/ConfirmDialog";

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

const AdminPage: React.FC = () => {
  const navigate = useNavigate();
  const [includeInactive, setIncludeInactive] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<Tenant | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    "deactivate" | "activate" | null
  >(null);

  const { data: tenants, isLoading, error } = useTenants(includeInactive);
  const deactivateMutation = useDeactivateTenant();
  const activateMutation = useActivateTenant();

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

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6 md:px-6">
      <div className="mx-auto max-w-6xl animate-fadein space-y-5">

        {/* Шапка */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Административная панель
              </h1>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Управление клиентами системы и их пользователями.
              </p>
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={() => navigate("/admin/tenants/new")}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Новый клиент
            </Button>
          </div>

          {/* Фильтр */}
          <div className="mt-4 flex items-center gap-2">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => setIncludeInactive(e.target.checked)}
                className="h-4 w-4 rounded border-[var(--border)]"
              />
              Показать деактивированных
            </label>
          </div>
        </header>

        {/* Скелетон */}
        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm"
              >
                <div className="skeleton mb-3 h-5 w-48" />
                <div className="skeleton h-4 w-32" />
              </div>
            ))}
          </div>
        )}

        {/* Ошибка */}
        {error && !isLoading && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            Не удалось загрузить список клиентов.
          </div>
        )}

        {/* Пусто */}
        {!isLoading && !error && (tenants ?? []).length === 0 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <Building2 className="mx-auto mb-3 h-8 w-8 text-[var(--text-muted)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              Клиентов пока нет.
            </p>
            <div className="mt-4 flex justify-center">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate("/admin/tenants/new")}
              >
                Создать первого клиента
              </Button>
            </div>
          </div>
        )}

        {/* Список клиентов */}
        {!isLoading && !error && (tenants ?? []).length > 0 && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {(tenants ?? []).map((tenant) => (
              <article
                key={tenant.id}
                className={[
                  "rounded-2xl border bg-[var(--bg-card)] p-5 shadow-sm transition-all duration-200",
                  tenant.is_active
                    ? "border-[var(--border)] hover:border-[var(--border-strong)] hover:shadow-md"
                    : "border-[var(--border-soft)] opacity-60",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Building2 className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
                      <h2 className="truncate text-base font-semibold text-[var(--text-primary)]">
                        {tenant.name}
                      </h2>
                      {!tenant.is_active && (
                        <span className="shrink-0 rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-muted)]">
                          Деактивирован
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      slug: {tenant.slug}
                    </p>
                    <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                      Создан: {formatDate(tenant.created_at)}
                    </p>
                  </div>
                </div>

                {/* Статистика */}
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <Users className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                        Пользователи
                      </p>
                    </div>
                    <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                      {tenant.users_count}
                    </p>
                  </div>

                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <FolderOpen className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                        Проекты
                      </p>
                    </div>
                    <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                      {tenant.deals_count}
                    </p>
                  </div>
                </div>

                {tenant.notes && (
                  <p className="mt-3 text-xs text-[var(--text-secondary)]">
                    {tenant.notes}
                  </p>
                )}

                {/* Действия */}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="flex-1"
                    onClick={() =>
                      navigate(`/admin/tenants/${tenant.id}`)
                    }
                  >
                    Управление
                  </Button>

                  {tenant.is_active ? (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        setConfirmTarget(tenant);
                        setConfirmAction("deactivate");
                      }}
                    >
                      Деактивировать
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setConfirmTarget(tenant);
                        setConfirmAction("activate");
                      }}
                    >
                      Активировать
                    </Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmTarget !== null}
        title={
          confirmAction === "deactivate"
            ? `Деактивировать клиента «${confirmTarget?.name ?? ""}»?`
            : `Активировать клиента «${confirmTarget?.name ?? ""}»?`
        }
        description={
          confirmAction === "deactivate"
            ? "Все пользователи этого клиента потеряют доступ к системе. Данные не удаляются."
            : "Пользователи клиента снова смогут войти в систему."
        }
        confirmLabel={
          confirmAction === "deactivate" ? "Деактивировать" : "Активировать"
        }
        cancelLabel="Отмена"
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


