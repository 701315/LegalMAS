// =============================================================
// src/components/settings/ProjectMembersPanel.tsx
// =============================================================

import React from "react";
import { useTranslation, Trans } from "react-i18next";
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

const ALERT_ERROR_CLASS =
  "rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3";

const selectClassName =
  "w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]";

const ProjectMembersPanel: React.FC<ProjectMembersPanelProps> = ({
  dealId,
  backButton,
}) => {
  const { t } = useTranslation(["admin", "common"]);
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
  const isAddMemberDisabled = availableUsersList.length === 0;
  const addMemberDisabledReason =
    isAddMemberDisabled && !isAvailableUsersLoading
      ? t("projectMembers.addMemberDisabledTooltip")
      : undefined;

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
            setErrorText(t("projectMembers.errors.selectUser"));
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
          setErrorText(t("projectMembers.errors.alreadyInProject"));
        } else {
          setErrorText(
            apiErr.detail ?? t("projectMembers.errors.saveFailed"),
          );
        }
      }
    },
    [closeForm, createMutation, createForm, editForm, formMode, t, updateMutation],
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
        apiErr.detail ?? t("projectMembers.errors.deleteFailed"),
      );
    }
  }, [confirmDelete, deleteMutation, t]);

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
        title={t("projectMembers.title")}
        subtitle={t("projectMembers.subtitleNoAccess")}
        rightSlot={backButton}
      >
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 shadow-sm">
          <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
              <Shield size={28} className="text-[var(--text-muted)]" />
            </div>

            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {t("projectMembers.noAccess.heading")}
            </h2>

            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              {t("projectMembers.noAccess.description")}
            </p>
          </div>
        </div>
      </PageSection>
    );
  }

  return (
    <PageSection
      title={t("projectMembers.title")}
      subtitle={t("projectMembers.subtitle")}
      rightSlot={
        <div className="flex flex-wrap items-center gap-2">
          {backButton}
          <span
            title={addMemberDisabledReason}
            className="inline-flex"
          >
            <Button
              type="button"
              size="sm"
              variant="secondary"
              leftIcon={<UserPlus size={14} />}
              onClick={openCreateForm}
              disabled={isAddMemberDisabled}
            >
              {t("projectMembers.addMember")}
            </Button>
          </span>
        </div>
      }
    >
      <div className="space-y-4">
        {errorText && !formMode && !confirmDelete ? (
          <div className={ALERT_ERROR_CLASS}>
            <p className="text-sm font-medium text-[var(--color-error-text)]">
              {t("projectMembers.errors.actionFailed")}
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
                {t("projectMembers.loading")}
              </span>
            </div>
          ) : membersList.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
                <Users size={26} className="text-[var(--text-muted)]" />
              </div>

              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                {t("projectMembers.empty.heading")}
              </h2>

              <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-muted)]">
                {t("projectMembers.empty.description")}
              </p>

              <div className="mt-5 flex justify-center">
                <span
                  title={addMemberDisabledReason}
                  className="inline-flex"
                >
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    leftIcon={<UserPlus size={14} />}
                    onClick={openCreateForm}
                    disabled={isAddMemberDisabled}
                  >
                    {t("projectMembers.addMember")}
                  </Button>
                </span>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]">
                  <tr>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      {t("projectMembers.table.user")}
                    </th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      {t("projectMembers.table.systemRole")}
                    </th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      {t("projectMembers.table.projectRole")}
                    </th>
                    <th className="px-3 py-2.5 text-right text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      {t("projectMembers.table.actions")}
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
                          {t(
                            `projectMembers.systemRoles.${member.system_role}`,
                            { defaultValue: member.system_role },
                          )}
                        </span>
                      </td>

                      <td className="px-3 py-2.5">
                        <span className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                          {t(`projectMembers.roles.${member.role}Full`, {
                            defaultValue: member.role,
                          })}
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
                            {t("projectMembers.table.editRole")}
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
                            {t("projectMembers.table.delete")}
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
                {t("projectMembers.createForm.label")}
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {t("projectMembers.createForm.heading")}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {t("projectMembers.createForm.description")}
              </p>
            </div>

            <form className="space-y-4 px-5 py-5" onSubmit={handleSave}>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                    {t("projectMembers.table.user")}
                  </label>

                  {isAvailableUsersLoading ? (
                    <div className="flex items-center rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-sm text-[var(--text-muted)]">
                      <Loader2
                        size={16}
                        className="mr-2 animate-spin text-[var(--accent-primary)]"
                      />
                      {t("projectMembers.createForm.loadingUsers")}
                    </div>
                  ) : (
                    <select
                      value={createForm.userId}
                      onChange={(e) =>
                        handleCreateFormChange("userId", e.target.value)
                      }
                      className={selectClassName}
                    >
                      <option value="">
                        {t("projectMembers.createForm.selectUser")}
                      </option>
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
                    {t("projectMembers.table.projectRole")}
                  </label>
                  <select
                    value={createForm.role}
                    onChange={(e) =>
                      handleCreateFormChange("role", e.target.value)
                    }
                    className={selectClassName}
                  >
                    <option value="admin">
                      {t("projectMembers.roles.admin")}
                    </option>
                    <option value="editor">
                      {t("projectMembers.roles.editor")}
                    </option>
                    <option value="viewer">
                      {t("projectMembers.roles.viewer")}
                    </option>
                  </select>
                </div>
              </div>

              {errorText ? (
                <div className={ALERT_ERROR_CLASS}>
                  <p className="text-sm font-medium text-[var(--color-error-text)]">
                    {t("projectMembers.errors.checkForm")}
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
                  {t("actions.cancel", { ns: "common" })}
                </Button>

                <Button
                  type="submit"
                  size="sm"
                  variant="secondary"
                  isLoading={isSaving}
                >
                  {t("projectMembers.createForm.add")}
                </Button>
              </div>
            </form>
          </section>
        ) : null}

        {formMode === "edit" ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                {t("projectMembers.editForm.label")}
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {t("projectMembers.editForm.heading")}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {t("projectMembers.editForm.description")}
              </p>
            </div>

            <form className="space-y-4 px-5 py-5" onSubmit={handleSave}>
              <div className="max-w-sm">
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                  {t("projectMembers.table.projectRole")}
                </label>
                <select
                  value={editForm.role}
                  onChange={(e) =>
                    handleEditFormChange("role", e.target.value)
                  }
                  className={selectClassName}
                >
                  <option value="admin">
                    {t("projectMembers.roles.admin")}
                  </option>
                  <option value="editor">
                    {t("projectMembers.roles.editor")}
                  </option>
                  <option value="viewer">
                    {t("projectMembers.roles.viewer")}
                  </option>
                </select>
              </div>

              {errorText ? (
                <div className={ALERT_ERROR_CLASS}>
                  <p className="text-sm font-medium text-[var(--color-error-text)]">
                    {t("projectMembers.errors.roleChangeFailed")}
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
                  {t("actions.cancel", { ns: "common" })}
                </Button>

                <Button
                  type="submit"
                  size="sm"
                  variant="secondary"
                  isLoading={isSaving}
                >
                  {t("projectMembers.editForm.save")}
                </Button>
              </div>
            </form>
          </section>
        ) : null}

        {confirmDelete ? (
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                {t("projectMembers.deleteConfirm.label")}
              </p>
              <h2 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {t("projectMembers.deleteConfirm.heading")}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {t("projectMembers.deleteConfirm.description")}
              </p>
            </div>

            <div className="space-y-4 px-5 py-5">
              <p className="text-sm text-[var(--text-secondary)]">
                <Trans
                  t={t}
                  i18nKey="projectMembers.deleteConfirm.confirmQuestion"
                  values={{
                    name:
                      confirmDelete.full_name || confirmDelete.email,
                  }}
                  components={{
                    bold: (
                      <span className="font-semibold text-[var(--text-primary)]" />
                    ),
                  }}
                />
              </p>

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] pt-4">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirmDelete(null)}
                >
                  {t("actions.cancel", { ns: "common" })}
                </Button>

                <Button
                  type="button"
                  size="sm"
                  variant="danger"
                  isLoading={isDeleteLoading}
                  onClick={handleDelete}
                >
                  {t("projectMembers.deleteConfirm.confirmButton")}
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


