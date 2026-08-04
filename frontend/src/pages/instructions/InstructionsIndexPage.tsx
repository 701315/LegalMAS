// src/pages/instructions/InstructionsIndexPage.tsx
// Главная страница управления инструкциями для superadmin.
// Точка входа в базовые инструкции платформы, Playbook Studio
// и базовые playbooks.

import React from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, Layers, Shield } from "lucide-react";

// ─────────────────────────────────────────────────────────────
// NavCard — карточка навигации
// Визуально выровнена с ToolCard из AdminMonitoringPage
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
  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              Инструкции
            </h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Управление базовыми инструкциями платформы, playbook studio и
              версиями базовых playbooks. Изменения публикуются через flow
              draft → validate → publish.
            </p>
          </div>
        </header>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Платформа
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Универсальные инструкции и базовые настройки по типам документов,
              которые используются как основа для tenant-override и сборки
              playbooks.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
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

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Studio
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Единая среда для сборки, проверки, предпросмотра и публикации
              версий playbook перед их применением в проектах.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <NavCard
              to="/admin/instructions/playbook-studio"
              title="Playbook Studio"
              description="Templates, version builder, compiled preview, publish и дальнейшее применение в проектах."
              icon={BookOpen}
            />
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Реестр
            </div>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Опубликованные стандартные playbooks платформы, доступные для
              использования в проектах и просмотра их состава.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <NavCard
              to="/admin/instructions/playbooks-registry"
              title="Реестр стандартных playbook"
              description="Просмотр состава опубликованных playbook и экспорт в Excel / Word."
              icon={Layers}
            />
          </div>
        </section>
      </div>
    </div>
  );
};

export default InstructionsIndexPage;


