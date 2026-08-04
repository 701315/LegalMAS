// =============================================================
// src/components/settings/ProjectMembersPanel.tsx
// =============================================================

import React from "react";
import { Loader2, Shield, UserPlus, Users } from "lucide-react";
import {
  useProjectMembers,
  useAvailableProjectUsers,
  useCreateProjectMember,
  useUpdateProjectMember,
  useDeleteProjectMember,
} from "../../api/projectMembers";
import type {
  ProjectMember,
  AvailableProjectUser,
} from "../../api/projectMembers";
import type { ProjectRole } from "../../api/auth";
import type { ApiError } from "../../types";
import { useDealPermissions } from "../../hooks/usePermissions";
import Button from "../ui/Button";
import PageSection from "../ui/PageSection";

type FormMode = "create" | "edit";

interface CreateMemberFormState {
  userId: string;
  role: ProjectRole;
}

interface EditMemberFormState {
  memberId?: string;
  role: ProjectRole;
}

interface ProjectMembersPanelProps {
  dealId: string;
  onBack?: () => void;
  backButton?: React.ReactNode;
}

const EMPTY_CREATE_FORM: CreateMemberFormState = {
  userId: "",
  role: "viewer",
};

const EMPTY_EDIT_FORM: EditMemberFormState = {
  memberId: undefined,
  role: "viewer",
};

const ROLE_LABEL: Record<ProjectRole, string> = {
  admin: "Администратор проекта",
  editor: "Редактор проекта",
  viewer: "Только просмотр",
};

const SYSTEM_ROLE_LABEL: Record<string, string> = {
  superadmin: "Суперадмин",
  tenant_admin: "Администратор клиента",
  member: "Участник",
};

const ALERT_ERROR_CLASS =
  "rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3";

const selectClassName =
  "w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]";

const ProjectMembersPanel: React.FC<ProjectMembersPanelProps> = ({
  dealId,
  backButton,
}) => {
  const { canManageRequests } = useDealPermissions(dealId);
  const canManageMembers = canManageRequests;

  const { data: members, isLoading: isMembersLoading } =
    useProjectMembers(dealId);
  const { data: availableUsers, isLoading: isAvailableUsersLoading } =
    useAvailableProjectUsers(dealId);

  const createMutation = useCreateProjectMember(dealId);
  const updateMutation = useUpdateProjectMember(dealId);
  const deleteMutation = useDeleteProjectMember(dealId);

  const [formMode, setFormMode] = React.useState<FormMode | null>(null);
  const [createForm, setCreateForm] =
    React.useState<CreateMemberFormState>(EMPTY_CREATE_FORM);
  const [editForm, setEditForm] =
    React.useState<EditMemberFormState>(EMPTY_EDIT_FORM);
  const [errorText, setErrorText] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] =
    React.useState<ProjectMember | null>(null);

  const membersList = members ?? [];
  const availableUsersList = availableUsers ?? [];

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
    setCreateForm(EMPTY_CREATE_FORM);
  }, []);

  const openEditForm = React.useCallback((member: ProjectMember) => {
    setErrorText(null);
    setConfirmDelete(null);
    setFormMode("edit");
    setEditForm({
      memberId: member.member_id,
      role: member.role,
    });
  }, []);

  const closeForm = React.useCallback(() => {
    setFormMode(null);
    setCreateForm(EMPTY_CREATE_FORM);
    setEditForm(EMPTY_EDIT_FORM);
    setErrorText(null);
  }, []);

  const handleCreateFormChange = React.useCallback(
    (field: keyof CreateMemberFormState, value: string) => {
      setCreateForm((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const handleEditFormChange = React.useCallback(
    (field: keyof EditMemberFormState, value: string) => {
      setEditForm((prev) => ({ ...prev, [field]: value as ProjectRole }));
    },
    [],
  );

  const handleSave = React.useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      setErrorText(null);

      try {
        if (formMode === "create") {
          if (!createForm.userId) {
            setErrorText("Выберите пользователя.");
            return;
          }

          await createMutation.mutateAsync({
            user_id: createForm.userId,
            role: createForm.role,
          });
        } else if (formMode === "edit" && editForm.memberId) {
          await updateMutation.mutateAsync({
            memberId: editForm.memberId,
            data: {
              role: editForm.role,
            },
          });
        }

        closeForm();
      } catch (error) {
        const apiErr = error as ApiError;
        if (apiErr.detail === "USER_ALREADY_IN_PROJECT") {
          setErrorText("Пользователь уже добавлен в этот проект.");
        } else {
          setErrorText(apiErr.detail || "Не удалось сохранить участника.");
        }
      }
    },
    [closeForm, createMutation, createForm, editForm, formMode, updateMutation],
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

  const getAvailableUserLabel = (user: AvailableProjectUser): string => {
    const name = user.full_name?.trim();
    if (name) {
      return `${name} — ${user.email}`;
    }
    return user.email;
  };

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
      subtitle="Назначение существующих пользователей клиента в проект и управление их проектными ролями."
      rightSlot={
        <div className="flex flex-wrap items-center gap-2">
          {backButton}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<UserPlus size={14} />}
            onClick={openCreateForm}
            disabled={availableUsersList.length === 0}
          >
            Добавить участника
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {errorText && !formMode && !confirmDelete ? (
          <div className={ALERT_ERROR_CLASS}>
            <p className="text-sm font-medium text-[var(--color-error-text)]">
              Не удалось выполнить действие
            </p>
            <p className="mt-1 text-sm text-[var(--color-error-text)]">
              {errorText}
            </p>
          </div>
        ) : null}

        <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
          {isMembersLoading ? (
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
                Добавьте первого участника проекта из числа пользователей
                клиента.
              </p>

              <div className="mt-5 flex justify-center">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  leftIcon={<UserPlus size={14} />}
                  onClick={openCreateForm}
                  disabled={availableUsersList.length === 0}
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
                      Пользователь
                    </th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Системная роль
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
                      <td className="px-3 py-2.5">
                        <div className="text-sm font-medium text-[var(--text-primary)]">
                          {member.full_name || member.email}
                        </div>
                        <div className="text-xs text-[var(--text-secondary)]">
                          {member.email}
                        </div>
                      </td>

                      <td className="px-3 py-2.5">
                        <span className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                          {SYSTEM_ROLE_LABEL[member.system_role] ??
                            member.system_role}
                        </span>
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
                            Роль
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

        {formMode === "create" ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                Новый участник
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                Добавить пользователя в проект
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Выберите существующего пользователя клиента и назначьте ему
                роль в проекте.
              </p>
            </div>

            <form className="space-y-4 px-5 py-5" onSubmit={handleSave}>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    Пользователь
                  </label>

                  {isAvailableUsersLoading ? (
                    <div className="flex items-center rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-muted)]">
                      <Loader2
                        size={16}
                        className="mr-2 animate-spin text-[var(--accent-primary)]"
                      />
                      Загружаем список пользователей…
                    </div>
                  ) : (
                    <select
                      value={createForm.userId}
                      onChange={(e) =>
                        handleCreateFormChange("userId", e.target.value)
                      }
                      className={selectClassName}
                    >
                      <option value="">Выберите пользователя</option>
                      {availableUsersList.map((u) => (
                        <option key={u.user_id} value={u.user_id}>
                          {getAvailableUserLabel(u)}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    Роль в проекте
                  </label>
                  <select
                    value={createForm.role}
                    onChange={(e) =>
                      handleCreateFormChange("role", e.target.value)
                    }
                    className={selectClassName}
                  >
                    <option value="admin">Администратор</option>
                    <option value="editor">Редактор</option>
                    <option value="viewer">Только просмотр</option>
                  </select>
                </div>
              </div>

              {errorText ? (
                <div className={ALERT_ERROR_CLASS}>
                  <p className="text-sm font-medium text-[var(--color-error-text)]">
                    Проверьте данные формы
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-error-text)]">
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
                  Добавить
                </Button>
              </div>
            </form>
          </section>
        ) : null}

        {formMode === "edit" ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                Редактирование
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                Изменить роль участника
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Измените роль пользователя внутри проекта.
              </p>
            </div>

            <form className="space-y-4 px-5 py-5" onSubmit={handleSave}>
              <div className="max-w-sm">
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                  Роль в проекте
                </label>
                <select
                  value={editForm.role}
                  onChange={(e) =>
                    handleEditFormChange("role", e.target.value)
                  }
                  className={selectClassName}
                >
                  <option value="admin">Администратор</option>
                  <option value="editor">Редактор</option>
                  <option value="viewer">Только просмотр</option>
                </select>
              </div>

              {errorText ? (
                <div className={ALERT_ERROR_CLASS}>
                  <p className="text-sm font-medium text-[var(--color-error-text)]">
                    Не удалось изменить роль
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-error-text)]">
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
                Это действие удалит пользователя только из текущего проекта.
                Сам пользователь останется в системе.
              </p>
            </div>

            <div className="space-y-4 px-5 py-5">
              <p className="text-sm text-[var(--text-secondary)]">
                Удалить участника{" "}
                <span className="font-semibold text-[var(--text-primary)]">
                  {confirmDelete.full_name || confirmDelete.email}
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


