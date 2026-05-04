// =============================================================
// src/pages/ProjectMembersPage.tsx
// Управление участниками проекта (по capability, обычно admin проекта).
// =============================================================

// =============================================================
// src/pages/ProjectMembersPage.tsx
// Управление участниками проекта (по capability, обычно admin проекта).
// =============================================================

import React, { useState } from "react";
import { useNavigate, useParams, Navigate } from "react-router-dom";
import {
  useProjectMembers,
  useCreateProjectMember,
  useUpdateProjectMember,
  useDeleteProjectMember,
} from "../api/projectMembers";
import type { ProjectMember } from "../api/projectMembers";
import type { ProjectRole } from "../api/auth";
import type { ApiError } from "../types";
import { useDealPermissions } from "../hooks/usePermissions";
import Button from "../components/ui/Button";

type FormMode = "create" | "edit";

interface MemberFormState {
  memberId?: string;
  name: string;
  login: string;
  password: string;
  role: ProjectRole;
}

const EMPTY_FORM: MemberFormState = {
  memberId: undefined,
  name: "",
  login: "",
  password: "",
  role: "viewer",
};

const ProjectMembersPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const { canManageRequests } = useDealPermissions(dealId as string);
  const canManageMembers = canManageRequests;

  const { data: members, isLoading } = useProjectMembers(dealId as string);
  const createMutation = useCreateProjectMember(dealId as string);
  const updateMutation = useUpdateProjectMember(dealId as string);
  const deleteMutation = useDeleteProjectMember(dealId as string);

  const [formMode, setFormMode] = useState<FormMode | null>(null);
  const [form, setForm] = useState<MemberFormState>(EMPTY_FORM);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<ProjectMember | null>(
    null,
  );

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  if (!canManageMembers) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg-base)] px-4">
        <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center shadow-2xl shadow-black/40">
          <p className="mb-4 text-sm text-[var(--text-secondary)]">
            У вас нет прав для управления участниками этого проекта.
          </p>
          <Button
            type="button"
            size="md"
            variant="secondary"
            onClick={() => navigate(`/projects/${dealId}`)}
          >
            ← Вернуться к проекту
          </Button>
        </div>
      </div>
    );
  }

  const handleBack = () => {
    navigate(`/projects/${dealId}`);
  };

  const openCreateForm = () => {
    setErrorText(null);
    setFormMode("create");
    setForm(EMPTY_FORM);
  };

  const openEditForm = (m: ProjectMember) => {
    setErrorText(null);
    setFormMode("edit");
    setForm({
      memberId: m.member_id,
      name: m.name,
      login: m.login,
      password: "",
      role: m.role,
    });
  };

  const closeForm = () => {
    setFormMode(null);
    setForm(EMPTY_FORM);
    setErrorText(null);
  };

  const handleFormChange = (field: keyof MemberFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);

    if (!form.name.trim()) {
      setErrorText("Укажите имя пользователя.");
      return;
    }
    if (!form.login.trim()) {
      setErrorText("Укажите логин.");
      return;
    }
    if (formMode === "create" && !form.password.trim()) {
      setErrorText("Укажите пароль для нового пользователя.");
      return;
    }

    try {
      if (formMode === "create") {
        await createMutation.mutateAsync({
          name: form.name.trim(),
          login: form.login.trim(),
          password: form.password.trim(),
          role: form.role,
        });
      } else if (formMode === "edit" && form.memberId) {
        await updateMutation.mutateAsync({
          memberId: form.memberId,
          data: {
            name: form.name.trim(),
            login: form.login.trim(),
            role: form.role,
            password: form.password.trim() || undefined,
          },
        });
      }
      closeForm();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.detail === "LOGIN_TAKEN") {
        setErrorText("Такой логин уже занят. Выберите другой.");
      } else {
        setErrorText(apiErr.detail || "Не удалось сохранить участника.");
      }
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setErrorText(null);
    try {
      await deleteMutation.mutateAsync(confirmDelete.member_id);
      setConfirmDelete(null);
    } catch (err) {
      const apiErr = err as ApiError;
      setErrorText(
        apiErr.detail ||
          "Не удалось удалить участника. Попробуйте позже.",
      );
    }
  };

  const membersList = members ?? [];

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-4 animate-fadein">
        {/* Заголовок */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
              Участники проекта
            </h1>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Проект:{" "}
              <span className="font-mono text-[11px] text-[var(--text-muted)]">
                {dealId}
              </span>
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={handleBack}
          >
            ← Назад к проекту
          </Button>
        </div>

        {/* Таблица участников */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Список участников
            </h2>
            <Button
              type="button"
              size="sm"
              variant="primary"
              onClick={openCreateForm}
            >
              Добавить участника
            </Button>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              <div className="skeleton h-4 w-1/3" />
              <div className="skeleton h-4 w-full" />
              <div className="skeleton h-4 w-11/12" />
            </div>
          ) : membersList.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">
              В этом проекте пока нет участников.
            </p>
          ) : (
            <table className="w-full border-collapse">
              <thead className="border-b border-[var(--border)]">
                <tr>
                  <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Имя
                  </th>
                  <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Логин
                  </th>
                  <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Роль в проекте
                  </th>
                  <th className="px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {membersList.map((m) => (
                  <tr
                    key={m.member_id}
                    className="border-b border-[var(--border)] hover:bg-white/3 transition-colors"
                  >
                    <td className="px-3 py-2.5 text-sm text-[var(--text-primary)] font-medium">
                      {m.name}
                    </td>
                    <td className="px-3 py-2.5 text-sm text-[var(--text-secondary)]">
                      {m.login}
                    </td>
                    <td className="px-3 py-2.5 text-sm text-[var(--text-secondary)]">
                      {m.role}
                    </td>
                    <td className="px-3 py-2.5 text-right text-sm text-[var(--text-secondary)]">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="mr-2"
                        onClick={() => openEditForm(m)}
                      >
                        Редактировать
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="danger"
                        onClick={() => setConfirmDelete(m)}
                      >
                        Удалить
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Ошибка вне форм */}
        {errorText && !formMode && !confirmDelete && (
          <p className="text-sm text-red-400">{errorText}</p>
        )}

        {/* Форма добавления/редактирования */}
        {formMode && (
          <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              {formMode === "create"
                ? "Добавить участника"
                : "Редактировать участника"}
            </h2>

            <form className="space-y-3" onSubmit={handleSave}>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                  Имя пользователя
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => handleFormChange("name", e.target.value)}
                  className="input-base"
                  placeholder="Например: Иванов Иван"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                  Логин
                </label>
                <input
                  type="text"
                  value={form.login}
                  onChange={(e) => handleFormChange("login", e.target.value)}
                  className="input-base"
                  placeholder="Например: ivanov"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                  Пароль{" "}
                  {formMode === "edit" && (
                    <span className="text-[11px] font-normal normal-case text-[var(--text-muted)]">
                      {" "}
                      (оставьте пустым, чтобы не менять)
                    </span>
                  )}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) =>
                    handleFormChange("password", e.target.value)
                  }
                  className="input-base"
                  placeholder={
                    formMode === "create"
                      ? "Придумайте пароль"
                      : "Новый пароль (необязательно)"
                  }
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
                  Роль в проекте
                </label>
                <select
                  value={form.role}
                  onChange={(e) =>
                    handleFormChange("role", e.target.value as ProjectRole)
                  }
                  className="input-base"
                >
                  <option value="admin">Администратор</option>
                  <option value="editor">Права правки</option>
                  <option value="viewer">Только просмотр</option>
                </select>
              </div>

              {errorText && (
                <p className="text-sm text-red-400">{errorText}</p>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={closeForm}
                >
                  Отмена
                </Button>
                <Button type="submit" size="sm" variant="primary">
                  Сохранить
                </Button>
              </div>
            </form>
          </div>
        )}

        {/* Блок подтверждения удаления (пока без глобального ConfirmDialog) */}
        {confirmDelete && (
          <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4">
            <p className="text-sm text-[var(--text-secondary)]">
              Удалить участника{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {confirmDelete.name}
              </span>{" "}
              из проекта?
            </p>
            <div className="flex items-center justify-end gap-3">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setConfirmDelete(null)}
              >
                Отмена
              </Button>
              <Button
                type="button"
                size="sm"
                variant="danger"
                onClick={handleDelete}
              >
                Да, удалить
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProjectMembersPage;



