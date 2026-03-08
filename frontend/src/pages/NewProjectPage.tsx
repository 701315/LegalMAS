// =============================================================
// src/pages/NewProjectPage.tsx
// Создание нового проекта (доступно только для superadmin).
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../hooks/useAuth";

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

  // Если вдруг пользователь не superadmin — вернём его на дашборд
  if (globalRole !== "superadmin") {
    navigate("/dashboard");
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

      const res = await client.post<DealResponse>(
        "/api/v1/deals",
        payload,
      );

      const dealId = res.data.id;
      // После создания сразу переходим на страницу загрузки документов проекта
      navigate(`/projects/${dealId}/upload`);
    } catch (err: any) {
      setErrorText(
        err?.detail || "Не удалось создать проект. Попробуйте позже.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    navigate("/dashboard");
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-xl mx-auto bg-white rounded-lg border shadow-sm p-6">
        <h1 className="text-xl font-bold text-gray-900 mb-4">
          Новый проект
        </h1>
        <p className="text-sm text-gray-500 mb-4">
          Укажите основные данные проекта. Остальные настройки можно будет задать позже.
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          {/* Название проекта */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Название проекта
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Например: DD по покупке ООО «Ромашка»"
            />
          </div>

          {/* Контактное лицо */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Контактное лицо
            </label>
            <input
              type="text"
              value={contactPerson}
              onChange={(e) => setContactPerson(e.target.value)}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="ФИО или e-mail ответственного"
            />
          </div>

          {/* Ошибка */}
          {errorText && (
            <p className="text-sm text-red-600">
              {errorText}
            </p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleCancel}
              className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 hover:bg-gray-50"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
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
