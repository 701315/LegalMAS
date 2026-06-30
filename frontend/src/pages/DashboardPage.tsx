// =============================================================
// src/pages/DashboardPage.tsx
// Дашборд: список проектов пользователя.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useUserProjects } from "../hooks/useUserProjects";
import { useDeleteProject } from "../hooks/useDeleteProject";
import type { ApiError } from "../types";
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

interface DeleteTarget {
  dealId: string;
  dealName: string;
}

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { userId, userName, globalRole } = useAuth();

  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<DeleteTarget | null>(null);

  React.useEffect(() => {
    if (!userId) {
      navigate("/login");
    }
  }, [userId, navigate]);

  const { data, isLoading, error } = useUserProjects(userId);
  const deleteProjectMutation = useDeleteProject(userId);

  const projects = data ?? [];

  const handleOpenProject = (dealId: string) => {
    navigate(`/projects/${dealId}`);
  };

  const handleCreateProject = () => {
    navigate("/projects/new");
  };

  const handleRequestDelete = (dealId: string, dealName: string) => {
    setDeleteError(null);
    setDeleteTarget({ dealId, dealName });
  };

  const handleCancelDelete = () => {
    setDeleteTarget(null);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;

    const { dealId } = deleteTarget;

    setDeleteError(null);
    setDeletingId(dealId);

    try {
      await deleteProjectMutation.mutateAsync(dealId);
      setDeleteTarget(null);
    } catch (err: unknown) {
      const e = err as unknown;

      let detailFromResponse: string | undefined;
      let detailFromApiError: string | undefined;
      let messageFromError: string | undefined;

      if (typeof e === "object" && e !== null) {
        if ("response" in e) {
          const resp = (e as { response?: { data?: ApiError } }).response;
          detailFromResponse = resp?.data?.detail;
        }
        if (
          "detail" in e &&
          typeof (e as { detail?: unknown }).detail === "string"
        ) {
          detailFromApiError = (e as { detail?: string }).detail;
        }
        if (
          "message" in e &&
          typeof (e as { message?: unknown }).message === "string"
        ) {
          messageFromError = (e as { message?: string }).message;
        }
      }

      const msg =
        detailFromApiError ??
        detailFromResponse ??
        messageFromError ??
        "Не удалось удалить проект. Возможно, есть связанные данные в системе.";

      setDeleteError(msg);
      setDeleteTarget(null);
    } finally {
      setDeletingId(null);
    }
  };

  if (!userId) {
    return null;
  }

  const canCreateProject =
    globalRole === "superadmin" || globalRole === "tenant_admin";

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6 md:px-6">
      <div className="mx-auto max-w-6xl animate-fadein space-y-5">

        {/* Шапка */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-col gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Мои проекты
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Управление проектами, доступными текущему пользователю.
              </p>

              <div className="mt-3 flex flex-wrap gap-2 text-[12px] text-[var(--text-secondary)]">
                <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1">
                  Пользователь: {userName || userId}
                </span>
                <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1">
                  Проектов: {projects.length}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Ошибка удаления */}
        {deleteError && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {deleteError}
          </div>
        )}

        {/* Скелетон */}
        {isLoading && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <div className="mb-4 h-4 w-40 skeleton" />
            <div className="space-y-2">
              <div className="h-4 w-full skeleton" />
              <div className="h-4 w-11/12 skeleton" />
              <div className="h-4 w-9/12 skeleton" />
            </div>
          </div>
        )}

        {/* Ошибка загрузки */}
        {error && !isLoading && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center text-sm text-rose-700">
            Не удалось загрузить проекты.
          </div>
        )}

        {/* Пусто */}
        {!isLoading && !error && projects.length === 0 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-10 text-center shadow-sm">
            <div className="mx-auto max-w-md">
              <p className="text-sm text-[var(--text-secondary)]">
                Пока нет проектов, к которым у вас есть доступ.
              </p>
              {canCreateProject && (
                <div className="mt-5 flex justify-center">
                  <Button
                    size="md"
                    variant="secondary"
                    onClick={handleCreateProject}
                  >
                    Создать первый проект
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Карточки проектов */}
        {!isLoading && !error && projects.length > 0 && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {projects.map((p) => (
              <article
                key={p.deal_id}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:bg-[var(--bg-card-hover)] hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-semibold text-[var(--text-primary)]">
                      {p.deal_name}
                    </h2>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      Создан: {formatDate(p.created_at)}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">
                      Роль в проекте: {p.role}
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Контактное лицо
                    </p>
                    <p className="mt-1 text-sm text-[var(--text-primary)]">
                      {p.contact_person || "Не указано"}
                    </p>
                  </div>

                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Deal ID
                    </p>
                    <p className="mt-1 truncate font-mono text-[12px] text-[var(--text-secondary)]">
                      {p.deal_id}
                    </p>
                  </div>
                </div>

                <div className="mt-5 flex items-center justify-between gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="flex-1"
                    onClick={() => handleOpenProject(p.deal_id)}
                  >
                    Открыть проект
                  </Button>

                  {(globalRole === "superadmin" ||
                    globalRole === "tenant_admin") && (
                    <Button
                      type="button"
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        handleRequestDelete(p.deal_id, p.deal_name)
                      }
                      isLoading={deletingId === p.deal_id}
                    >
                      {deletingId === p.deal_id ? "Удаляем…" : "Удалить"}
                    </Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Удалить проект «${deleteTarget?.dealName ?? ""}»?`}
        description="Это действие нельзя отменить. Все связанные данные могут быть удалены безвозвратно."
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        confirmVariant="danger"
        isLoading={deletingId !== null}
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />
    </div>
  );
};

export default DashboardPage;


