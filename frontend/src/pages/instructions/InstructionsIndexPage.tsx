// src/pages/instructions/InstructionsIndexPage.tsx
// Главная страница управления инструкциями для superadmin.
// Точка входа в базовые инструкции платформы, Playbook Studio
// и базовые playbooks.

import React from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, Shield } from "lucide-react";


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
    className="group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
  >
    <div className="flex items-start gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
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
// SectionHeading — заголовок раздела
// Единый стиль для всех трёх разделов страницы.
// ─────────────────────────────────────────────────────────────

const SectionHeading: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
    {children}
  </h2>
);

// ─────────────────────────────────────────────────────────────
// InstructionsIndexPage
// ─────────────────────────────────────────────────────────────

const InstructionsIndexPage: React.FC = () => {
  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">

        {/* ── Заголовок страницы (на фоне) ─────────────────── */}
        <header>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Инструкции
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Управление базовыми инструкциями платформы, playbook studio и
            версиями базовых playbooks. Изменения публикуются через flow
            draft&nbsp;→&nbsp;validate&nbsp;→&nbsp;publish.
          </p>
        </header>

        {/* ── Раздел 1: Базовые инструкции платформы ──────── */}

        {/* ── Раздел 1: Базовые инструкции платформы ──────── */}
        <section className="space-y-3">
          <SectionHeading>Базовые инструкции платформы</SectionHeading>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NavCard
              to="/admin/instructions/global-checks"
              title="Global Instructions"
              description="Универсальные проверки для любых документов: конфиденциальность, применимое право, срок действия и др."
              icon={Shield}
            />
            <NavCard
              to="/admin/instructions/doc-types"
              title="Doc-type Instructions"
              description="Инструкции по типам документов. Базовые настройки extraction, checks, retrieval."
              icon={FileText}
            />
          </div>
        </section>

        {/* ── Раздел 2: Playbook Studio ─────────────────────── */}
        <section className="space-y-3">
          <SectionHeading>Playbook Studio</SectionHeading>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NavCard
              to="/admin/instructions/playbook-studio"
              title="Playbook Studio"
              description="Единая встроенная среда: templates, version builder, compiled preview, publish и дальнейшее применение в проектах."
              icon={BookOpen}
            />
          </div>
        </section>

        {/* ── Раздел 3: Реестр стандартных playbook ─────── */}
        <section className="space-y-3">
          <SectionHeading>Базовые playbooks платформы</SectionHeading>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NavCard
              to="/admin/instructions/playbooks-registry"
              title="Реестр стандартных playbook"
              description="Опубликованные playbook, доступные пользователям в проектах. Просмотр состава и экспорт в Excel / Word."
              icon={BookOpen}
            />
          </div>
        </section>
      </div>
    </div>
  );
};

export default InstructionsIndexPage;



