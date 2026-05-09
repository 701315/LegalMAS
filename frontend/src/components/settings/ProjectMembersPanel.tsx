// =============================================================
// src/components/settings/ProjectMembersPanel.tsx
// Embedded workspace panel для управления участниками проекта.
// Используется внутри SettingsTab и как shared-content для legacy route.
// =============================================================

import React from "react";
import { Loader2, Shield, UserPlus, Users } from "lucide-react";
import {
  useProjectMembers,
  useCreateProjectMember,
  useUpdateProjectMember,
  useDeleteProjectMember,
} from "../../api/projectMembers";
import type { ProjectMember } from "../../api/projectMembers";
import type { ProjectRole } from "../../api/auth";
import type { ApiError } from "../../types";
import { useDealPermissions } from "../../hooks/usePermissions";
import Button from "../ui/Button";
import PageSection from "../ui/PageSection";

type FormMode = "create" | "edit";

interface MemberFormState {
  memberId?: string;
  name: string;
  login: string;
  password: string;
  role: ProjectRole;
}

interface ProjectMembersPanelProps {
  dealId: string;
  onBack?: () => void;
  backButton?: React.ReactNode;
}

const EMPTY_FORM: MemberFormState = {
  memberId: undefined,
  name: "",
  login: "",
  password: "",
  role: "viewer",
};

const ROLE_LABEL: Record<ProjectRole, string> = {
  admin: "Администратор",
  editor: "Права правки",
  viewer: "Только просмотр",
};

const ALERT_ERROR_CLASS =
  "rounded-2xl border border-[var(--color-error,#ef4444)] bg-[color:color-mix(in_srgb,var(--color-error,#ef4444)_8%,var(--bg-card))] px-4 py-3";

const ProjectMembersPanel: React.FC<ProjectMembersPanelProps> = ({
  dealId,
  backButton,
}) => {
  const { canManageRequests } = useDealPermissions(dealId);
  const canManageMembers = canManageRequests;

  const { data: members, isLoading } = useProjectMembers(dealId);
  const createMutation = useCreateProjectMember(dealId);
  const updateMutation = useUpdateProjectMember(dealId);
  const deleteMutation = useDeleteProjectMember(dealId);

  const [formMode, setFormMode] = React.useState<FormMode | null>(null);
  const [form, setForm] = React.useState<MemberFormState>(EMPTY_FORM);
  const [errorText, setErrorText] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] =
    React.useState<ProjectMember | null>(null);

  const membersList = members ?? [];

  const isCreateLoading = createMutation.isPending;
  const isUpdateLoading = updateMutation.isPending;
  const isDeleteLoading = deleteMutation.isPending;
  const isSaving =
    (formMode === "create" && isCreateLoading) ||
    (formMode === "edit" && isUpdateLoading);

  const openCreateForm = React.useCallback(() => {
    setErrorText(null);
    setConfirmDelete(null);
    setFormMode("create");
    setForm(EMPTY_FORM);
  }, []);

  const openEditForm = React.useCallback((member: ProjectMember) => {
    setErrorText(null);
    setConfirmDelete(null);
    setFormMode("edit");
    setForm({
      memberId: member.member_id,
      name: member.name,
      login: member.login,
      password: "",
      role: member.role,
    });
  }, []);

  const closeForm = React.useCallback(() => {
    setFormMode(null);
    setForm(EMPTY_FORM);
    setErrorText(null);
  }, []);

  const handleFormChange = React.useCallback(
    (field: keyof MemberFormState, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const handleSave = React.useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
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
      } catch (error) {
        const apiErr = error as ApiError;
        if (apiErr.detail === "LOGIN_TAKEN") {
          setErrorText("Такой логин уже занят. Выберите другой.");
        } else {
          setErrorText(apiErr.detail || "Не удалось сохранить участника.");
        }
      }
    },
    [closeForm, createMutation, form, formMode, updateMutation],
  );

  const handleDelete = React.useCallback(async () => {
    if (!confirmDelete) return;

    setErrorText(null);

    try {
      await deleteMutation.mutateAsync(confirmDelete.member_id);
      setConfirmDelete(null);
    } catch (error) {
      const apiErr = error as ApiError;
      setErrorText(
        apiErr.detail || "Не удалось удалить участника. Попробуйте позже.",
      );
    }
  }, [confirmDelete, deleteMutation]);

  if (!canManageMembers) {
    return (
      <PageSection
        title="Участники проекта"
        subtitle="Управление составом команды проекта и доступами."
        rightSlot={backButton}
      >
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 shadow-sm">
          <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
              <Shield size={28} className="text-[var(--text-muted)]" />
            </div>

            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Доступ к управлению участниками ограничен
            </h2>

            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              У вас нет прав для управления составом команды этого проекта.
            </p>
          </div>
        </div>
      </PageSection>
    );
  }

  return (
    <PageSection
      title="Участники проекта"
      subtitle="Управление составом команды, ролями и доступом к рабочему пространству сделки."
      rightSlot={
        <div className="flex flex-wrap items-center gap-2">
          {backButton}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<UserPlus size={14} />}
            onClick={openCreateForm}
          >
            Добавить участника
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {errorText && !formMode && !confirmDelete ? (
          <div className={ALERT_ERROR_CLASS}>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              Не удалось выполнить действие
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {errorText}
            </p>
          </div>
        ) : null}

        <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
          {isLoading ? (
            <div className="flex items-center justify-center px-5 py-16">
              <Loader2
                size={18}
                className="mr-3 animate-spin text-[var(--accent-primary)]"
              />
              <span className="text-sm text-[var(--text-muted)]">
                Загружаем участников проекта…
              </span>
            </div>
          ) : membersList.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
                <Users size={26} className="text-[var(--text-muted)]" />
              </div>

              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                Участники ещё не добавлены
              </h2>

              <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-muted)]">
                Добавьте первого участника проекта, чтобы настроить состав
                команды и права доступа.
              </p>

              <div className="mt-5 flex justify-center">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  leftIcon={<UserPlus size={14} />}
                  onClick={openCreateForm}
                >
                  Добавить участника
                </Button>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]">
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
                  {membersList.map((member) => (
                    <tr
                      key={member.member_id}
                      className="border-b border-[var(--border)] transition-colors hover:bg-[var(--bg-elevated-soft)]"
                    >
                      <td className="px-3 py-2.5 text-sm font-medium text-[var(--text-primary)]">
                        {member.name}
                      </td>
                      <td className="px-3 py-2.5 text-sm text-[var(--text-secondary)]">
                        {member.login}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                          {ROLE_LABEL[member.role]}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => openEditForm(member)}
                          >
                            Редактировать
                          </Button>

                          <Button
                            type="button"
                            size="sm"
                            variant="danger"
                            onClick={() => {
                              setErrorText(null);
                              setFormMode(null);
                              setConfirmDelete(member);
                            }}
                          >
                            Удалить
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {formMode ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                {formMode === "create" ? "Новый участник" : "Редактирование"}
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {formMode === "create"
                  ? "Добавить участника"
                  : "Редактировать участника"}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Укажите имя, логин, роль в проекте и при необходимости пароль.
              </p>
            </div>

            <form className="space-y-4 px-5 py-5" onSubmit={handleSave}>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    Имя пользователя
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => handleFormChange("name", e.target.value)}
                    className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--border)]"
                    placeholder="Например: Иванов Иван"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    Логин
                  </label>
                  <input
                    type="text"
                    value={form.login}
                    onChange={(e) => handleFormChange("login", e.target.value)}
                    className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--border)]"
                    placeholder="Например: ivanov"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    Пароль
                  </label>
                  <input
                    type="password"
                    value={form.password}
                    onChange={(e) =>
                      handleFormChange("password", e.target.value)
                    }
                    className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--border)]"
                    placeholder={
                      formMode === "create"
                        ? "Придумайте пароль"
                        : "Новый пароль (необязательно)"
                    }
                  />
                  {formMode === "edit" ? (
                    <p className="mt-1.5 text-xs text-[var(--text-muted)]">
                      Оставьте поле пустым, если пароль менять не нужно.
                    </p>
                  ) : null}
                </div>

                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    Роль в проекте
                  </label>
                  <select
                    value={form.role}
                    onChange={(e) =>
                      handleFormChange("role", e.target.value as ProjectRole)
                    }
                    className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--border)]"
                  >
                    <option value="admin">Администратор</option>
                    <option value="editor">Права правки</option>
                    <option value="viewer">Только просмотр</option>
                  </select>
                </div>
              </div>

              {errorText ? (
                <div className={ALERT_ERROR_CLASS}>
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    Проверьте данные формы
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">
                    {errorText}
                  </p>
                </div>
              ) : null}

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] pt-4">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={closeForm}
                >
                  Отмена
                </Button>

                <Button
                  type="submit"
                  size="sm"
                  variant="secondary"
                  isLoading={isSaving}
                >
                  Сохранить
                </Button>
              </div>
            </form>
          </section>
        ) : null}

        {confirmDelete ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                Подтверждение
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                Удалить участника проекта
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Это действие удалит участника из текущего проекта.
              </p>
            </div>

            <div className="space-y-4 px-5 py-5">
              <p className="text-sm text-[var(--text-secondary)]">
                Удалить участника{" "}
                <span className="font-semibold text-[var(--text-primary)]">
                  {confirmDelete.name}
                </span>{" "}
                из проекта?
              </p>

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] pt-4">
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
                  isLoading={isDeleteLoading}
                  onClick={handleDelete}
                >
                  Да, удалить
                </Button>
              </div>
            </div>
          </section>
        ) : null}
      </div>
    </PageSection>
  );
};

export default ProjectMembersPanel;


