// =============================================================
// src/pages/AdminTenantDetailPage.tsx
// Детальная страница клиента: пользователи + управление.
// Только для superadmin.
// =============================================================

import React, { useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  Eye,
  EyeOff,
  Pencil,
  UserPlus,
} from "lucide-react";
import {
  useTenant,
  useTenantUsers,
  useCreateTenantUser,
  useUpdateTenantUser,
  useDeactivateTenantUser,
  type AdminUser,
  type UserCreate,
  type UserUpdate,
} from "../api/admin";
import type { ApiError } from "../types";
import Button from "../components/ui/Button";
import ConfirmDialog from "../components/ui/ConfirmDialog";

// ─────────────────────────────────────────────────────────────
// Константы
// ─────────────────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  superadmin: "Супер-администратор",
  tenant_admin: "Администратор клиента",
  member: "Участник",
};

const SYSTEM_ROLE_OPTIONS = [
  { value: "tenant_admin", label: "Администратор клиента" },
  { value: "member", label: "Участник" },
] as const;

// ─────────────────────────────────────────────────────────────
// Формы
// ─────────────────────────────────────────────────────────────

interface CreateUserForm {
  email: string;
  password: string;
  full_name: string;
  system_role: "tenant_admin" | "member";
}

interface EditUserForm {
  userId: string;
  full_name: string;
  system_role: "tenant_admin" | "member";
  newPassword: string;
}

const EMPTY_CREATE_FORM: CreateUserForm = {
  email: "",
  password: "",
  full_name: "",
  system_role: "member",
};

const EMPTY_EDIT_FORM: EditUserForm = {
  userId: "",
  full_name: "",
  system_role: "member",
  newPassword: "",
};

type FormMode = "create" | "edit" | null;

// ─────────────────────────────────────────────────────────────
// AdminTenantDetailPage
// ─────────────────────────────────────────────────────────────

const AdminTenantDetailPage: React.FC = () => {
  const { tenantId } = useParams<{ tenantId: string }>();
  const navigate = useNavigate();

  const [formMode, setFormMode] = useState<FormMode>(null);
  const [createForm, setCreateForm] =
    useState<CreateUserForm>(EMPTY_CREATE_FORM);
  const [editForm, setEditForm] = useState<EditUserForm>(EMPTY_EDIT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<AdminUser | null>(
    null,
  );

  const [showCreatePassword, setShowCreatePassword] = useState(false);
  const [showEditPassword, setShowEditPassword] = useState(false);

  const { data: tenant, isLoading: tenantLoading } = useTenant(
    tenantId ?? null,
  );
  const { data: users, isLoading: usersLoading } = useTenantUsers(
    tenantId ?? null,
    true,
  );
  const createUserMutation = useCreateTenantUser(tenantId ?? "");
  const updateUserMutation = useUpdateTenantUser(tenantId ?? "");
  const deactivateMutation = useDeactivateTenantUser(tenantId ?? "");

  // ── Handlers ────────────────────────────────────────────────

  const handleCreateFormChange = (
    field: keyof CreateUserForm,
    value: string,
  ) => {
    setCreateForm((prev) => ({ ...prev, [field]: value }));
  };

  const openCreateForm = () => {
    setFormMode("create");
    setCreateForm(EMPTY_CREATE_FORM);
    setFormError(null);
    setShowCreatePassword(false);
  };

  const openEditForm = (user: AdminUser) => {
    setFormMode("edit");
    setEditForm({
      userId: user.id,
      full_name: user.full_name ?? "",
      system_role: user.system_role as "tenant_admin" | "member",
      newPassword: "",
    });
    setFormError(null);
    setShowEditPassword(false);
  };

  const handleEditFormChange = (
    field: keyof EditUserForm,
    value: string,
  ) => {
    setEditForm((prev) => ({ ...prev, [field]: value }));
  };

  const closeForm = () => {
    setFormMode(null);
    setFormError(null);
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!createForm.email.trim()) {
      setFormError("Укажите email.");
      return;
    }
    if (!createForm.password.trim() || createForm.password.length < 6) {
      setFormError("Пароль должен быть не менее 6 символов.");
      return;
    }

    try {
      const payload: UserCreate = {
        email: createForm.email.trim(),
        password: createForm.password,
        full_name: createForm.full_name.trim() || null,
        system_role: createForm.system_role,
      };

      await createUserMutation.mutateAsync(payload);
      closeForm();
    } catch (err: unknown) {
      const apiErr = err as ApiError | { message?: string } | null;
      const detail =
        (apiErr as ApiError)?.detail ??
        (apiErr as { message?: string })?.message ??
        "Не удалось создать пользователя.";
      setFormError(String(detail));
    }
  };

  const handleEditUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (editForm.newPassword && editForm.newPassword.length < 6) {
      setFormError("Пароль должен быть не менее 6 символов.");
      return;
    }

    try {
      const data: UserUpdate = {
        system_role: editForm.system_role,
        full_name: editForm.full_name.trim() || null,
        clear_full_name: !editForm.full_name.trim(),
      };

      if (editForm.newPassword.trim()) {
        data.password = editForm.newPassword;
      }

      await updateUserMutation.mutateAsync({
        userId: editForm.userId,
        data,
      });
      closeForm();
    } catch (err: unknown) {
      const apiErr = err as ApiError | { message?: string } | null;
      const detail =
        (apiErr as ApiError)?.detail ??
        (apiErr as { message?: string })?.message ??
        "Не удалось обновить пользователя.";
      setFormError(String(detail));
    }
  };

  const handleDeactivateConfirm = async () => {
    if (!deactivateTarget) return;
    await deactivateMutation.mutateAsync(deactivateTarget.id);
    setDeactivateTarget(null);
  };

  // ── Loading ─────────────────────────────────────────────────

  if (tenantLoading) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein space-y-4 p-4 md:p-5">
          <div className="skeleton h-8 w-48 rounded-xl" />
          <div className="skeleton h-32 rounded-2xl" />
        </div>
      </div>
    );
  }

  // ── Not found ───────────────────────────────────────────────

  if (!tenant) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein p-4 md:p-5">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
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

  const usersList = users ?? [];
  const activeUsers = usersList.filter((u) => u.is_active).length;

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <button
            type="button"
            onClick={() => navigate("/admin")}
            className="mb-3 inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] rounded-lg px-1 py-0.5"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Все клиенты
          </button>

          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {tenant.name}
            </h1>
            {!tenant.is_active && (
              <span className="shrink-0 rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-muted)]">
                Деактивирован
              </span>
            )}
          </div>

          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            slug: {tenant.slug}
            <span className="mx-1.5 text-[var(--text-muted)]">·</span>
            <Link
              to={`/admin/tenants/${tenant.id}/projects`}
              className="hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 rounded"
            >
              Проектов: {tenant.deals_count}
            </Link>
            <span className="mx-1.5 text-[var(--text-muted)]">·</span>
            Пользователей: {activeUsers} из {tenant.users_count}
          </p>

          {tenant.notes && (
            <p className="mt-3 text-sm text-[var(--text-secondary)]">
              {tenant.notes}
            </p>
          )}
        </header>

        {/* ── Секция пользователей ────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">

          {/* Заголовок секции */}
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Пользователи
            </h2>
            {tenant.is_active && (
              <Button
                size="sm"
                variant="secondary"
                onClick={openCreateForm}
                leftIcon={<UserPlus className="h-4 w-4" />}
              >
                Добавить
              </Button>
            )}
          </div>

          {/* Форма создания */}
          {formMode === "create" && (
            <div className="border-b border-[var(--border)] bg-[var(--bg-elevated-soft)] px-5 py-4">
              <h3 className="mb-4 text-sm font-semibold text-[var(--text-primary)]">
                Новый пользователь
              </h3>

              {formError && (
                <div className="mb-3 rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2 text-xs text-[var(--color-error-text)]">
                  {formError}
                </div>
              )}

              <form onSubmit={handleCreateUser} className="space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Email *
                    </label>
                    <input
                      type="email"
                      value={createForm.email}
                      onChange={(e) =>
                        handleCreateFormChange("email", e.target.value)
                      }
                      className="input-base w-full"
                      placeholder="user@company.com"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Пароль *
                    </label>
                    <div className="relative">
                      <input
                        type={showCreatePassword ? "text" : "password"}
                        value={createForm.password}
                        onChange={(e) =>
                          handleCreateFormChange("password", e.target.value)
                        }
                        className="input-base w-full pr-10"
                        placeholder="Минимум 6 символов"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCreatePassword((v) => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-secondary)] focus-visible:outline-none"
                        tabIndex={-1}
                        aria-label={showCreatePassword ? "Скрыть пароль" : "Показать пароль"}
                      >
                        {showCreatePassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Полное имя
                    </label>
                    <input
                      type="text"
                      value={createForm.full_name}
                      onChange={(e) =>
                        handleCreateFormChange("full_name", e.target.value)
                      }
                      className="input-base w-full"
                      placeholder="Иванов Иван Иванович"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Системная роль
                    </label>
                    <select
                      value={createForm.system_role}
                      onChange={(e) =>
                        handleCreateFormChange("system_role", e.target.value)
                      }
                      className="input-base w-full"
                    >
                      {SYSTEM_ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={closeForm}
                  >
                    Отмена
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    variant="primary"
                    isLoading={createUserMutation.isPending}
                  >
                    Создать
                  </Button>
                </div>
              </form>
            </div>
          )}

          {/* Форма редактирования */}
          {formMode === "edit" && (
            <div className="border-b border-[var(--border)] bg-[var(--bg-elevated-soft)] px-5 py-4">
              <h3 className="mb-4 text-sm font-semibold text-[var(--text-primary)]">
                Редактирование пользователя
              </h3>

              {formError && (
                <div className="mb-3 rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2 text-xs text-[var(--color-error-text)]">
                  {formError}
                </div>
              )}

              <form onSubmit={handleEditUser} className="space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Полное имя
                    </label>
                    <input
                      type="text"
                      value={editForm.full_name}
                      onChange={(e) =>
                        handleEditFormChange("full_name", e.target.value)
                      }
                      className="input-base w-full"
                      placeholder="Иванов Иван Иванович"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Системная роль
                    </label>
                    <select
                      value={editForm.system_role}
                      onChange={(e) =>
                        handleEditFormChange("system_role", e.target.value)
                      }
                      className="input-base w-full"
                    >
                      {SYSTEM_ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Новый пароль (оставьте пустым, чтобы не менять)
                    </label>
                    <div className="relative max-w-sm">
                      <input
                        type={showEditPassword ? "text" : "password"}
                        value={editForm.newPassword}
                        onChange={(e) =>
                          handleEditFormChange("newPassword", e.target.value)
                        }
                        className="input-base w-full pr-10"
                        placeholder="Минимум 6 символов"
                      />
                      <button
                        type="button"
                        onClick={() => setShowEditPassword((v) => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-secondary)] focus-visible:outline-none"
                        tabIndex={-1}
                        aria-label={showEditPassword ? "Скрыть пароль" : "Показать пароль"}
                      >
                        {showEditPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={closeForm}
                  >
                    Отмена
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    variant="primary"
                    isLoading={updateUserMutation.isPending}
                  >
                    Сохранить
                  </Button>
                </div>
              </form>
            </div>
          )}

          {/* Список пользователей */}
          <div className="divide-y divide-[var(--border-subtle)]">
            {usersLoading && (
              <div className="px-5 py-4">
                <div className="skeleton mb-2 h-4 w-48" />
                <div className="skeleton h-4 w-32" />
              </div>
            )}

            {!usersLoading && usersList.length === 0 && (
              <div className="px-5 py-6 text-center text-sm text-[var(--text-muted)]">
                Пользователей пока нет. Добавьте первого.
              </div>
            )}

            {usersList.map((u) => (
              <div
                key={u.id}
                className={[
                  "flex items-center justify-between gap-3 px-5 py-4",
                  !u.is_active && "opacity-50",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                    {u.full_name || u.email}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">{u.email}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                      {ROLE_LABEL[u.system_role] ?? u.system_role}
                    </span>
                    {!u.is_active && (
                      <span className="rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
                        Деактивирован
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {u.is_active && (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => openEditForm(u)}
                        aria-label="Редактировать пользователя"
                        className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => setDeactivateTarget(u)}
                      >
                        Деактивировать
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>

      <ConfirmDialog
        open={deactivateTarget !== null}
        title="Деактивировать пользователя?"
        description={`«${deactivateTarget?.full_name ?? deactivateTarget?.email ?? ""}» потеряет доступ к системе. Данные не удаляются.`}
        confirmLabel="Деактивировать"
        cancelLabel="Отмена"
        confirmVariant="danger"
        isLoading={deactivateMutation.isPending}
        onConfirm={handleDeactivateConfirm}
        onCancel={() => setDeactivateTarget(null)}
      />
    </div>
  );
};

export default AdminTenantDetailPage;


