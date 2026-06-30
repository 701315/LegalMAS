// =============================================================
// src/pages/AdminTenantNewPage.tsx
// Создание нового клиента (tenant).
// Только для superadmin.
// =============================================================

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateTenant } from "../api/admin";
import type { ApiError } from "../types";
import Button from "../components/ui/Button";

const AdminTenantNewPage: React.FC = () => {
  const navigate = useNavigate();
  const createMutation = useCreateTenant();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [notes, setNotes] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const handleNameChange = (value: string) => {
    setName(value);
    // Автогенерация slug из названия
    if (!slug || slug === autoSlug(name)) {
      setSlug(autoSlug(value));
    }
  };

  function autoSlug(value: string): string {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .trim()
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .slice(0, 50);
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);

    if (!name.trim()) {
      setErrorText("Укажите название клиента.");
      return;
    }

    if (!slug.trim()) {
      setErrorText("Укажите slug.");
      return;
    }

    try {
      const tenant = await createMutation.mutateAsync({
        name: name.trim(),
        slug: slug.trim(),
        notes: notes.trim() || null,
      });

      navigate(`/admin/tenants/${tenant.id}`);
    } catch (err: unknown) {
      const apiErr = err as ApiError | { message?: string } | null;
      const detail =
        (apiErr as ApiError)?.detail ??
        (apiErr as { message?: string })?.message ??
        "Не удалось создать клиента. Попробуйте позже.";
      setErrorText(String(detail));
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-base)] px-4 py-6 md:px-6">
      <div className="mx-auto max-w-2xl animate-fadein space-y-5">
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Новый клиент
          </h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Создайте нового клиента системы. После создания можно будет
            добавить его пользователей.
          </p>
        </header>

        {errorText && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {errorText}
          </div>
        )}

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label
                htmlFor="tenant-name"
                className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
              >
                Название клиента *
              </label>
              <input
                id="tenant-name"
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                className="input-base w-full"
                placeholder="Например: Ромашка Лигал"
                autoComplete="off"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="tenant-slug"
                className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
              >
                Slug *
              </label>
              <input
                id="tenant-slug"
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="input-base w-full font-mono"
                placeholder="romashka-legal"
                autoComplete="off"
              />
              <p className="text-xs text-[var(--text-muted)]">
                Только строчные латинские буквы, цифры и дефис.
                Генерируется автоматически из названия.
              </p>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="tenant-notes"
                className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
              >
                Заметки
              </label>
              <textarea
                id="tenant-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="input-base w-full resize-none"
                rows={3}
                placeholder="Произвольные заметки администратора..."
              />
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] pt-4">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => navigate("/admin")}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                isLoading={createMutation.isPending}
              >
                {createMutation.isPending ? "Создаём…" : "Создать клиента"}
              </Button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
};

export default AdminTenantNewPage;


