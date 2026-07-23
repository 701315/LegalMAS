// =============================================================
// src/pages/NewProjectPage.tsx
// Создание нового проекта (доступно только для superadmin).
// Визуально согласовано с текущим DashboardPage.
// =============================================================

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useUIStore } from "../stores/uiStore";
import type { ApiError } from "../types";
import Button from "../components/ui/Button";

interface CreateDealInput {
  name: string;
  metadata_?: {
    contact_person?: string | null;
  };
}

interface DealResponse {
  id: string;
}

const NewProjectPage: React.FC = () => {
  const navigate = useNavigate();
  const { globalRole } = useAuth();
  const setProjectRole = useUIStore((s) => s.setProjectRole);

  const [name, setName] = useState("");
  const [contactPerson, setContactPerson] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canCreate =
    globalRole === "superadmin" || globalRole === "tenant_admin";

  useEffect(() => {
    if (!canCreate) {
      navigate("/dashboard", { replace: true });
    }
  }, [canCreate, navigate]);

  if (!canCreate) {
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);

    if (!name.trim()) {
      setErrorText("Укажите название проекта.");
      return;
    }

    setIsSubmitting(true);

    try {
      const payload: CreateDealInput = {
        name: name.trim(),
        metadata_: {
          contact_person: contactPerson.trim() || null,
        },
      };

      const res = await client.post<DealResponse>("/api/v1/deals", payload);
      const dealId = res.data.id;

      // Сразу записываем роль "admin" в store.
      // Backend только что создал membership с этой ролью.
      // Обновляем frontend store чтобы ProjectRouteGuard и
      // useDealPermissions сразу видели корректные права
      // без ожидания следующей загрузки user-info из API.
      setProjectRole(dealId, "admin");

      navigate(`/projects/${dealId}/upload`);
    } catch (err: unknown) {
      let detailFromResponse: string | undefined;
      let detailFromApiError: string | undefined;
      let messageFromError: string | undefined;

      if (typeof err === "object" && err !== null) {
        if ("response" in err) {
          const resp = (err as { response?: { data?: ApiError } }).response;
          detailFromResponse = resp?.data?.detail;
        }

        if (
          "detail" in err &&
          typeof (err as { detail?: unknown }).detail === "string"
        ) {
          detailFromApiError = (err as { detail?: string }).detail;
        }

        if (
          "message" in err &&
          typeof (err as { message?: unknown }).message === "string"
        ) {
          messageFromError = (err as { message?: string }).message;
        }
      }

      const msg =
        detailFromApiError ??
        detailFromResponse ??
        messageFromError ??
        "Не удалось создать проект. Попробуйте позже.";

      setErrorText(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    navigate("/dashboard");
  };

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6 md:px-6">
      <div className="mx-auto max-w-6xl animate-fadein space-y-5">
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-col gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Новый проект
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Создайте новый проект и задайте базовые параметры рабочего
                пространства. Все дополнительные настройки можно будет изменить
                позже.
              </p>
            </div>
          </div>
        </header>

        {errorText && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {errorText}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-1.5">
                <label
                  htmlFor="project-name"
                  className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  Название проекта
                </label>
                <input
                  id="project-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input-base"
                  placeholder='Например: DD по покупке ООО «Ромашка»'
                  autoComplete="off"
                />
                <p className="text-xs text-[var(--text-muted)]">
                  Лучше использовать короткое рабочее название, которое будет
                  понятно в dashboard, списке проектов и внутри рабочего
                  пространства.
                </p>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="contact-person"
                  className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  Контактное лицо
                </label>
                <input
                  id="contact-person"
                  type="text"
                  value={contactPerson}
                  onChange={(e) => setContactPerson(e.target.value)}
                  className="input-base"
                  placeholder="ФИО или e-mail ответственного"
                  autoComplete="off"
                />
                <p className="text-xs text-[var(--text-muted)]">
                  Необязательное поле. Можно указать внутреннего координатора,
                  ответственного юриста или основной контакт по проекту.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] pt-4">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleCancel}
                >
                  Отмена
                </Button>

                <Button
                  type="submit"
                  variant="secondary"
                  size="sm"
                  isLoading={isSubmitting}
                >
                  {isSubmitting ? "Создаём…" : "Создать проект"}
                </Button>
              </div>
            </form>
          </section>

          <aside className="space-y-4">
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                Что произойдёт дальше
              </h2>

              <div className="mt-4 space-y-3">
                <div className="subtle-panel px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Шаг 1
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-primary)]">
                    Создастся карточка проекта
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    Проект появится в рабочем списке и будет готов к
                    дальнейшей настройке.
                  </p>
                </div>

                <div className="subtle-panel px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Шаг 2
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-primary)]">
                    Откроется загрузка документов
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    Сразу после создания можно перейти к наполнению data room и
                    первичному импорту материалов.
                  </p>
                </div>

                <div className="subtle-panel px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Шаг 3
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-primary)]">
                    Настройка команды и workflow
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    Позже можно назначить участников, выбрать playbook и
                    настроить review-процесс.
                  </p>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                Подсказки по заполнению
              </h2>

              <div className="mt-4 space-y-3 text-sm text-[var(--text-secondary)]">
                <p>
                  Обязательное поле только одно — название проекта. Если детали
                  ещё не согласованы, этого уже достаточно для старта.
                </p>
                <p>
                  Название и контактное лицо можно изменить позже, поэтому
                  сейчас не нужно добиваться финальной формулировки.
                </p>
                <p>
                  Для удобства лучше использовать короткое рабочее название,
                  которое команда быстро узнает в списке проектов.
                </p>
              </div>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default NewProjectPage;




