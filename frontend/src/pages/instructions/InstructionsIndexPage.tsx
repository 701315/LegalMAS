// src/pages/instructions/InstructionsIndexPage.tsx
// Главная страница управления инструкциями для superadmin.
// Точка входа в базовые инструкции платформы, Playbook Studio
// и базовые playbooks.

import React from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, Layers, Shield } from "lucide-react";

// ─────────────────────────────────────────────────────────────
// NavCard — карточка навигации
// ─────────────────────────────────────────────────────────────

interface NavCardProps {
  to: string;
  title: string;
  description: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const NavCard: React.FC<NavCardProps> = ({
  to,
  title,
  description,
  icon: Icon,
}) => (
  <NavLink
    to={to}
    className={[
      "group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm",
      "transition-all duration-200",
      "hover:border-[var(--border-strong)] hover:shadow-md",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35",
      "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]",
    ].join(" ")}
  >
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
          {title}
        </h3>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          {description}
        </p>
      </div>
    </div>
  </NavLink>
);

// ─────────────────────────────────────────────────────────────
// InstructionsIndexPage
// ─────────────────────────────────────────────────────────────

const InstructionsIndexPage: React.FC = () => {
  const { t } = useTranslation("admin");

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {t("instructionsHub.title")}
            </h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              {t("instructionsHub.subtitle")}
            </p>
          </div>
        </header>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("instructionsHub.groups.platform")}
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              {t("instructionsHub.groups.platformDesc")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <NavCard
              to="/admin/instructions/global-checks"
              title={t("instructionsHub.cards.globalTitle")}
              description={t("instructionsHub.cards.globalDesc")}
              icon={Shield}
            />
            <NavCard
              to="/admin/instructions/doc-types"
              title={t("instructionsHub.cards.docTypeTitle")}
              description={t("instructionsHub.cards.docTypeDesc")}
              icon={FileText}
            />
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("instructionsHub.groups.studio")}
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              {t("instructionsHub.groups.studioDesc")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <NavCard
              to="/admin/instructions/playbook-studio"
              title={t("instructionsHub.cards.studioTitle")}
              description={t("instructionsHub.cards.studioDesc")}
              icon={BookOpen}
            />
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("instructionsHub.groups.registry")}
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              {t("instructionsHub.groups.registryDesc")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <NavCard
              to="/admin/instructions/playbooks-registry"
              title={t("instructionsHub.cards.registryTitle")}
              description={t("instructionsHub.cards.registryDesc")}
              icon={Layers}
            />
          </div>
        </section>

      </div>
    </div>
  );
};

export default InstructionsIndexPage;


