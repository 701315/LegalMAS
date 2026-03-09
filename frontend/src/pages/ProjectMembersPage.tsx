// =============================================================
// src/pages/ProjectMembersPage.tsx
// Управление участниками проекта (по capability, обычно admin проекта).
// =============================================================

import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useProjectMembers,
  useCreateProjectMember,
  useUpdateProjectMember,
  useDeleteProjectMember,
} from "../api/projectMembers";
import type {
  ProjectMember,
} from "../api/projectMembers";
import type { ProjectRole } from "../api/auth";
import { useDealPermissions } from "../hooks/usePermissions";

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

  const [formMode, setFormMode] = useState<FormMode | null>(null);
  const [form, setForm] = useState<MemberFormState>(EMPTY_FORM);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<ProjectMember | null>(
    null,
  );

  if (!dealId) {
    return (
      <div className="p-6 text-center text-red-600">
        dealId не указан в маршруте.
      </div>
    );
  }

  // Права по проекту: управление участниками завязываем на canManageRequests
  // (при необходимости можно ввести отдельный capability для управления участниками).
  const { canManageRequests } = useDealPermissions(dealId);
  const canManageMembers = canManageRequests;

  if (!canManageMembers) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md bg-white rounded-lg border shadow p-6 text-center">
          <p className="text-sm text-gray-700 mb-4">
            У вас нет прав для управления участниками этого проекта.
          </p>
          <button
            type="button"
            onClick={() => navigate(`/projects/${dealId}`)}
            className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
          >
            Вернуться к проекту
          </button>
        </div>
      </div>
    );
  }

  const { data: members, isLoading } = useProjectMembers(dealId);
  const createMutation = useCreateProjectMember(dealId);
  const updateMutation = useUpdateProjectMember(dealId);
  const deleteMutation = useDeleteProjectMember(dealId);

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

  const handleFormChange = (
    field: keyof MemberFormState,
    value: string,
  ) => {
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
    } catch (err: any) {
      if (err?.detail === "LOGIN_TAKEN") {
        setErrorText("Такой логин уже занят. Выберите другой.");
      } else {
        setErrorText(err?.detail || "Не удалось сохранить участника.");
      }
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setErrorText(null);
    try {
      await deleteMutation.mutateAsync(confirmDelete.member_id);
      setConfirmDelete(null);
    } catch (err: any) {
      setErrorText(
        err?.detail || "Не удалось удалить участника. Попробуйте позже.",
      );
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Заголовок */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Участники проекта
            </h1>
            <p className="text-sm text-gray-500">
              Проект: {dealId}
            </p>
          </div>
          <button
            type="button"
            onClick={handleBack}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          >
            ← Назад к проекту
          </button>
        </div>

        {/* Таблица участников */}
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-800">
              Список участников
            </h2>
            <button
              type="button"
              onClick={openCreateForm}
              className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
            >
              Добавить участника
            </button>
          </div>

          {isLoading ? (
            <p className="text-sm text-gray-500">
              Загружаем список участников…
            </p>
          ) : (members ?? []).length === 0 ? (
            <p className="text-sm text-gray-500">
              В этом проекте пока нет участников.
            </p>
          ) : (
            <table className="w-full text-sm border-t border-gray-200">
              <thead>
                <tr className="bg-gray-50">
                  <th className="text-left px-2 py-2 font-medium text-gray-700">
                    Имя
                  </th>
                  <th className="text-left px-2 py-2 font-medium text-gray-700">
                    Логин
                  </th>
                  <th className="text-left px-2 py-2 font-medium text-gray-700">
                    Роль в проекте
                  </th>
                  <th className="text-right px-2 py-2 font-medium text-gray-700">
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {(members ?? []).map((m) => (
                  <tr key={m.member_id} className="border-t border-gray-100">
                    <td className="px-2 py-2 text-gray-800">
                      {m.name}
                    </td>
                    <td className="px-2 py-2 text-gray-600">
                      {m.login}
                    </td>
                    <td className="px-2 py-2 text-gray-600">
                      {m.role}
                    </td>
                    <td className="px-2 py-2 text-right space-x-2">
                      <button
                        type="button"
                        onClick={() => openEditForm(m)}
                        className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
                      >
                        Редактировать
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDelete(m)}
                        className="text-xs px-2 py-1 rounded border border-red-500 text-red-600 hover:bg-red-50"
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Ошибка вне форм */}
        {errorText && !formMode && !confirmDelete && (
          <p className="text-sm text-red-600">
            {errorText}
          </p>
        )}

        {/* Форма добавления/редактирования */}
        {formMode && (
          <div className="bg-white rounded-lg border p-4 space-y-3">
            <h2 className="text-sm font-semibold text-gray-800">
              {formMode === "create"
                ? "Добавить участника"
                : "Редактировать участника"}
            </h2>

            <form className="space-y-3" onSubmit={handleSave}>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Имя пользователя
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    handleFormChange("name", e.target.value)
                  }
                  className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Например: Иванов Иван"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Логин
                </label>
                <input
                  type="text"
                  value={form.login}
                  onChange={(e) =>
                    handleFormChange("login", e.target.value)
                  }
                  className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Например: ivanov"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Пароль{" "}
                  {formMode === "edit" && (
                    <span className="text-xs text-gray-500">
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
                  className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder={
                    formMode === "create"
                      ? "Придумайте пароль"
                      : "Новый пароль (необязательно)"
                  }
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Роль в проекте
                </label>
                <select
                  value={form.role}
                  onChange={(e) =>
                    handleFormChange("role", e.target.value)
                  }
                  className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="admin">Администратор</option>
                  <option value="editor">Права правки</option>
                  <option value="viewer">Только просмотр</option>
                </select>
              </div>

              {errorText && (
                <p className="text-sm text-red-600">
                  {errorText}
                </p>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeForm}
                  className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700"
                >
                  Сохранить
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Блок подтверждения удаления */}
        {confirmDelete && (
          <div className="bg-white rounded-lg border p-4 space-y-3">
            <p className="text-sm text-gray-800">
              Удалить участника{" "}
              <span className="font-semibold">
                {confirmDelete.name}
              </span>{" "}
              из проекта?
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleDelete}
                className="px-4 py-2 text-sm font-medium rounded bg-red-600 text-white hover:bg-red-700"
              >
                Да, удалить
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProjectMembersPage;
