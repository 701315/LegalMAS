// =============================================================
// src/pages/NewProjectPage.tsx
// Создание нового проекта (доступно только для superadmin).
// =============================================================

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../hooks/useAuth";
import type { ApiError } from "../types";

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

  const [name, setName] = useState("");
  const [contactPerson, setContactPerson] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (globalRole !== "superadmin") {
      navigate("/dashboard", { replace: true });
    }
  }, [globalRole, navigate]);

  if (globalRole !== "superadmin") {
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
    <div className="min-h-screen bg-gray-50 px-4 py-6 text-gray-900">
      <div className="mx-auto max-w-xl rounded-lg border border-gray-200 bg-white p-6 text-gray-900 shadow-sm">
        <h1 className="mb-4 text-xl font-bold text-gray-900">
          Новый проект
        </h1>
        <p className="mb-4 text-sm text-gray-500">
          Укажите основные данные проекта. Остальные настройки можно будет
          задать позже.
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Название проекта
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder='Например: DD по покупке ООО «Ромашка»'
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Контактное лицо
            </label>
            <input
              type="text"
              value={contactPerson}
              onChange={(e) => setContactPerson(e.target.value)}
              className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="ФИО или e-mail ответственного"
            />
          </div>

          {errorText && (
            <p className="text-sm text-red-600">{errorText}</p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {isSubmitting ? "Создаём..." : "Создать проект"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default NewProjectPage;


