// =============================================================
// src/pages/AdminTenantNewPage.tsx
// Создание нового клиента (tenant).
// Только для superadmin.
// =============================================================

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useCreateTenant } from "../api/admin";
import type { ApiError } from "../types";
import Button from "../components/ui/Button";

// ─────────────────────────────────────────────────────────────
// Утилиты
// ─────────────────────────────────────────────────────────────

function autoSlug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 50);
}

// ─────────────────────────────────────────────────────────────
// AdminTenantNewPage
// ─────────────────────────────────────────────────────────────

const AdminTenantNewPage: React.FC = () => {
  const { t } = useTranslation("admin");
  const navigate = useNavigate();
  const createMutation = useCreateTenant();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [notes, setNotes] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const handleNameChange = (value: string) => {
    setName(value);
    if (!slug || slug === autoSlug(name)) {
      setSlug(autoSlug(value));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);

    if (!name.trim()) {
      setErrorText(t("tenantNew.errors.nameRequired"));
      return;
    }

    if (!slug.trim()) {
      setErrorText(t("tenantNew.errors.slugRequired"));
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
        t("tenantNew.errors.createFailed");
      setErrorText(String(detail));
    }
  };

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <button
            type="button"
            onClick={() => navigate("/admin")}
            className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {t("tenantNew.back")}
          </button>

          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            {t("tenantNew.title")}
          </h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {t("tenantNew.subtitle")}
          </p>
        </header>

        {/* ── Ошибка ───────────────────────────────────────────── */}
        {errorText && (
          <div className="rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3 text-sm text-[var(--color-error-text)]">
            {errorText}
          </div>
        )}

        {/* ── Форма + подсказки ────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">

          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-1.5">
                <label
                  htmlFor="tenant-name"
                  className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  {t("tenantNew.nameLabel")}
                </label>
                <input
                  id="tenant-name"
                  type="text"
                  value={name}
                  onChange={(e) => handleNameChange(e.target.value)}
                  className="input-base w-full"
                  placeholder={t("tenantNew.namePlaceholder")}
                  autoComplete="off"
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="tenant-slug"
                  className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  {t("tenantNew.slugLabel")}
                </label>
                <input
                  id="tenant-slug"
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  className="input-base w-full font-mono"
                  placeholder={t("tenantNew.slugPlaceholder")}
                  autoComplete="off"
                />
                <p className="text-xs text-[var(--text-muted)]">
                  {t("tenantNew.slugHint")}
                </p>
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="tenant-notes"
                  className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  {t("tenantNew.notesLabel")}
                </label>
                <textarea
                  id="tenant-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="input-base w-full resize-none"
                  rows={3}
                  placeholder={t("tenantNew.notesPlaceholder")}
                />
              </div>

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] pt-4">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate("/admin")}
                >
                  {t("actions.cancel", { ns: "common" })}
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  isLoading={createMutation.isPending}
                >
                  {createMutation.isPending ? t("tenantNew.creating") : t("tenantNew.createButton")}
                </Button>
              </div>
            </form>
          </section>


          {/* Подсказки */}
          <aside className="space-y-4">
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("tenantNew.slugHelp.title")}
              </h2>
              <div className="mt-3 space-y-2 text-xs text-[var(--text-secondary)]">
                <p>
                  {t("tenantNew.slugHelp.p1")}
                </p>
                <p>
                  {t("tenantNew.slugHelp.p2")}{" "}
                  <code className="rounded bg-[var(--bg-elevated-soft)] px-1 font-mono text-[11px] text-[var(--text-primary)]">
                    romashka-legal
                  </code>
                </p>
                <p>
                  {t("tenantNew.slugHelp.p3")}
                </p>
              </div>
            </section>

            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("tenantNew.afterCreation.title")}
              </h2>
              <div className="mt-3 space-y-3">
                <div className="subtle-panel px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    {t("tenantNew.afterCreation.step1Label")}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {t("tenantNew.afterCreation.step1Desc")}
                  </p>
                </div>
                <div className="subtle-panel px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    {t("tenantNew.afterCreation.step2Label")}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {t("tenantNew.afterCreation.step2Desc")}
                  </p>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
};

export default AdminTenantNewPage;


