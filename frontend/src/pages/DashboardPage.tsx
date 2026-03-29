// =============================================================
// src/pages/DashboardPage.tsx
// Дашборд: список проектов пользователя.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useQuery } from "@tanstack/react-query";
import client from "../api/client";
import type { ProjectRole } from "../api/auth";
import type { ApiError } from "../types";

interface UserProject {
  deal_id: string;
  deal_name: string;
  role: ProjectRole;
  created_at: string;
  contact_person?: string | null;
}

// Низкоуровневая загрузка проектов пользователя
async function fetchUserProjects(userId: string): Promise<UserProject[]> {
  const res = await client.get<UserProject[]>(
    `/api/v1/user/${userId}/projects`,
  );
  return res.data;
}

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { userId, userName, globalRole } = useAuth();

  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);

  // Если по какой-то причине нет userId — отправим на логин (подстрахуемся)
  React.useEffect(() => {
    if (!userId) {
      navigate("/login");
    }
  }, [userId, navigate]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["user-projects", userId],
    queryFn: () => fetchUserProjects(userId!),
    enabled: !!userId,
  });

  const projects = data ?? [];

  const handleOpenProject = (dealId: string) => {
    navigate(`/projects/${dealId}`);
  };

  const handleCreateProject = () => {
    navigate("/projects/new");
  };

  const handleDeleteProject = async (dealId: string, dealName: string) => {
    const ok = window.confirm(
      `Удалить проект "${dealName}"?\n\n` +
        "Это действие нельзя отменить. Все связанные данные могут быть удалены безвозвратно.",
    );
    if (!ok) return;

    setDeleteError(null);
    setDeletingId(dealId);
    try {
      await client.delete(`/api/v1/deals/${dealId}`);
      await refetch();
    } catch (err: unknown) {
      const e = err as unknown;

      let detailFromResponse: string | undefined;
      let detailFromApiError: string | undefined;
      let messageFromError: string | undefined;

      if (typeof e === "object" && e !== null) {
        // axios-подобный объект с response.data.detail
        if ("response" in e) {
          const resp = (e as { response?: { data?: ApiError } }).response;
          detailFromResponse = resp?.data?.detail;
        }

        // прямой ApiError
        if (
          "detail" in e &&
          typeof (e as { detail?: unknown }).detail === "string"
        ) {
          detailFromApiError = (e as { detail?: string }).detail;
        }

        // обычный Error с message
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
    } finally {
      setDeletingId(null);
    }
  };

  if (!userId) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Мои проекты
            </h1>
            <p className="text-sm text-gray-500">
              Пользователь: {userName || userId} ({globalRole || "user"})
            </p>
          </div>

          {globalRole === "superadmin" && (
            <button
              type="button"
              onClick={handleCreateProject}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700"
            >
              Новый проект
            </button>
          )}
        </header>

        {deleteError && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3">
            {deleteError}
          </div>
        )}

        {isLoading && (
          <div className="bg-white rounded-lg border p-6 text-center text-gray-500">
            Загружаем проекты…
          </div>
        )}

        {error && !isLoading && (
          <div className="bg-white rounded-lg border p-6 text-center text-red-500">
            Не удалось загрузить проекты.
          </div>
        )}

        {!isLoading && !error && projects.length === 0 && (
          <div className="bg-white rounded-lg border p-6 text-center text-gray-500">
            Пока нет проектов, к которым у вас есть доступ.
          </div>
        )}

        {!isLoading && !error && projects.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((p) => (
              <div
                key={p.deal_id}
                className="w-full bg-white rounded-lg border p-4 hover:border-blue-500 hover:shadow-sm transition flex flex-col gap-2"
              >
                <div className="flex items-center justify-between mb-1">
                  <h2 className="text-base font-semibold text-gray-900">
                    {p.deal_name}
                  </h2>
                  <span className="text-xs px-2 py-1 rounded bg-gray-100 text-gray-700">
                    {p.role}
                  </span>
                </div>

                {p.contact_person && (
                  <p className="text-xs text-gray-500">
                    Контактное лицо: {p.contact_person}
                  </p>
                )}

                <p className="text-xs text-gray-500">
                  deal_id: {p.deal_id}
                </p>

                <div className="mt-2 flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => handleOpenProject(p.deal_id)}
                    className="flex-1 px-3 py-1.5 text-xs rounded border border-blue-600 text-blue-600 hover:bg-blue-50"
                  >
                    Открыть
                  </button>

                  {globalRole === "superadmin" && (
                    <button
                      type="button"
                      onClick={() =>
                        handleDeleteProject(p.deal_id, p.deal_name)
                      }
                      disabled={deletingId === p.deal_id}
                      className="px-3 py-1.5 text-xs rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-60"
                    >
                      {deletingId === p.deal_id
                        ? "Удаляем…"
                        : "Удалить"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DashboardPage;
