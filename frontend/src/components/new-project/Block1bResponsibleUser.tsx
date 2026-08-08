// =============================================================
// src/components/new-project/Block1bResponsibleUser.tsx
//
// Второй подэтап Блока 1 — выбор ответственного пользователя.
//
// Появляется только после создания deal (когда dealId доступен).
// Использует useAvailableProjectUsers для получения списка
// пользователей tenant'а, которых можно добавить в проект.
//
// При выборе — создаёт project member с ролью admin.
// Можно пропустить — блок 1 считается завершённым.
// =============================================================

import React from "react";
import { Loader2, UserPlus } from "lucide-react";

import {
  useAvailableProjectUsers,
  useCreateProjectMember,
} from "../../api/projectMembers";
import type { AvailableProjectUser } from "../../api/projectMembers";

import Button from "../ui/Button";
import Field from "../ui/Field";
import InlineAlert from "../InlineAlert";

interface Block1bResponsibleUserProps {
  dealId: string;
  /** Вызывается когда пользователь выбран или шаг пропущен */
  onCompleted: (selectedUserName: string | null) => void;
}

function getUserLabel(user: AvailableProjectUser): string {
  const name = user.full_name?.trim();

  if (name) {
    return `${name} — ${user.email}`;
  }

  return user.email;
}

function getUserDisplayName(user: AvailableProjectUser): string {
  return user.full_name?.trim() || user.email;
}

const selectClassName = [
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)]",
  "px-3 py-2 text-sm text-[var(--text-primary)]",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-[var(--accent-primary)]/35",
  "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
  "disabled:cursor-not-allowed disabled:opacity-60",
].join(" ");

const Block1bResponsibleUser: React.FC<Block1bResponsibleUserProps> = ({
  dealId,
  onCompleted,
}) => {
  const {
    data: availableUsers,
    isLoading: isUsersLoading,
  } = useAvailableProjectUsers(dealId);

  const createMember = useCreateProjectMember(dealId);

  const [selectedUserId, setSelectedUserId] = React.useState("");
  const [errorText, setErrorText] = React.useState<string | null>(null);

  const availableUsersList = availableUsers ?? [];
  const isAdding = createMember.isPending;

  const selectedUser = React.useMemo(
    () =>
      selectedUserId
        ? availableUsersList.find((u) => u.user_id === selectedUserId) ?? null
        : null,
    [availableUsersList, selectedUserId],
  );

  const handleAdd = React.useCallback(async () => {
    if (!selectedUserId || isAdding) {
      return;
    }

    setErrorText(null);

    try {
      await createMember.mutateAsync({
        user_id: selectedUserId,
        role: "admin",
      });

      const displayName = selectedUser
        ? getUserDisplayName(selectedUser)
        : null;

      onCompleted(displayName);
    } catch (err: unknown) {
      let message = "Не удалось добавить участника.";

      if (typeof err === "object" && err !== null) {
        const maybeDetail = (err as { detail?: unknown }).detail;

        if (typeof maybeDetail === "string") {
          if (maybeDetail === "USER_ALREADY_IN_PROJECT") {
            message = "Этот пользователь уже добавлен в проект.";
          } else {
            message = maybeDetail;
          }
        }
      }

      setErrorText(message);
    }
  }, [createMember, isAdding, onCompleted, selectedUser, selectedUserId]);

  const handleSkip = React.useCallback(() => {
    onCompleted(null);
  }, [onCompleted]);

  return (
    <div className="space-y-4">
      {errorText ? <InlineAlert tone="error" message={errorText} /> : null}

      {isUsersLoading ? (
        <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-4">
          <Loader2
            className="h-4 w-4 animate-spin text-[var(--accent-primary)]"
            aria-hidden="true"
          />
          <span className="text-sm text-[var(--text-muted)]">
            Загружаем список пользователей…
          </span>
        </div>
      ) : availableUsersList.length === 0 ? (
        <div className="space-y-3">
          <div className="subtle-panel px-4 py-3">
            <p className="text-sm text-[var(--text-secondary)]">
              В организации пока нет доступных пользователей для назначения
              ответственным. Участников проекта можно будет добавить позже в
              настройках.
            </p>
          </div>

          <div className="flex justify-end">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleSkip}
            >
              Продолжить без ответственного
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <Field
            label="Ответственный пользователь"
            hint="Будет добавлен в проект с ролью администратора. Можно изменить позже в настройках проекта."
          >
            <select
              value={selectedUserId}
              onChange={(e) => {
                setSelectedUserId(e.target.value);
                setErrorText(null);
              }}
              className={selectClassName}
              disabled={isAdding}
            >
              <option value="">Выберите пользователя</option>
              {availableUsersList.map((user) => (
                <option key={user.user_id} value={user.user_id}>
                  {getUserLabel(user)}
                </option>
              ))}
            </select>
          </Field>

          <div className="subtle-panel px-4 py-3">
            <div className="flex items-start gap-3">
              <div
                className="mt-0.5 shrink-0 text-[var(--text-muted)]"
                aria-hidden="true"
              >
                <UserPlus className="h-4 w-4" />
              </div>

              <div className="min-w-0">
                <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
                  Выбранный пользователь будет автоматически добавлен в проект
                  как администратор. Это необязательный шаг — ответственного
                  можно назначить позже.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] pt-4">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleSkip}
              disabled={isAdding}
            >
              Пропустить
            </Button>

            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleAdd}
              isLoading={isAdding}
              disabled={!selectedUserId || isAdding}
            >
              Назначить ответственного
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Block1bResponsibleUser;


