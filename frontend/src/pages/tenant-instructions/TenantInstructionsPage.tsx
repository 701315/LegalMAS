import React from "react";
import { useNavigate } from "react-router-dom";
import {
  BookOpen,
  FileText,
  GitBranch,
  Globe,
  Layers,
  Shield,
} from "lucide-react";

interface NavCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}

const NavCard: React.FC<NavCardProps> = ({
  icon,
  title,
  description,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      "group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm",
      "transition-all duration-200",
      "hover:border-[var(--border-strong)] hover:shadow-md",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35",
      "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]",
    ].join(" ")}
  >
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
          {title}
        </p>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          {description}
        </p>
      </div>
    </div>
  </button>
);

const TenantInstructionsPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* HEADER */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              Инструкции
            </h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Базовые инструкции платформы, playbook studio и переопределения
              для вашей организации.
            </p>
          </div>
        </header>

        {/* 2 COLUMNS */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">

          {/* LEFT COLUMN */}
          <div className="space-y-4">

            {/* Платформа */}
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Платформа
                </div>
                <h2 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                  Базовые инструкции платформы
                </h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  Управляются superadmin. Доступны вам для просмотра и как основа
                  для создания overrides.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <NavCard
                  icon={<Shield className="h-4 w-4" aria-hidden="true" />}
                  title="Базовые Global Instructions"
                  description="Универсальные проверки, применимые к любым документам."
                  onClick={() =>
                    navigate("/tenant-admin/instructions/base-global-checks")
                  }
                />
                <NavCard
                  icon={<FileText className="h-4 w-4" aria-hidden="true" />}
                  title="Базовые Doc-Type Instructions"
                  description="Инструкции для конкретных типов документов."
                  onClick={() =>
                    navigate("/tenant-admin/instructions/base-doc-types")
                  }
                />
              </div>
            </section>

            {/* Studio */}
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Studio
                </div>
                <h2 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                  Playbook Studio
                </h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  Сборка playbooks из базовых инструкций и подготовка версий для применения.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2">
                <NavCard
                  icon={<BookOpen className="h-4 w-4" aria-hidden="true" />}
                  title="Playbook Studio"
                  description="Создание шаблонов и сборка версий."
                  onClick={() =>
                    navigate("/tenant-admin/instructions/playbook-studio")
                  }
                />
              </div>
            </section>

            {/* Организация */}
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Организация
                </div>
                <h2 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                  Переопределения вашей организации
                </h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  Настройки уровня tenant. Overrides применяются поверх базовых версий.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <NavCard
                  icon={<Globe className="h-4 w-4" aria-hidden="true" />}
                  title="Global Overrides"
                  description="Переопределения базовых global instructions."
                  onClick={() =>
                    navigate("/tenant-admin/instructions/overrides?tab=global")
                  }
                />
                <NavCard
                  icon={<GitBranch className="h-4 w-4" aria-hidden="true" />}
                  title="Doc-Type Overrides"
                  description="Переопределения doc-type instructions."
                  onClick={() =>
                    navigate("/tenant-admin/instructions/overrides?tab=doc-type")
                  }
                />
                <NavCard
                  icon={<Layers className="h-4 w-4" aria-hidden="true" />}
                  title="Playbooks организации"
                  description="Собственные playbooks вашей организации."
                  onClick={() =>
                    navigate("/tenant-admin/instructions/my-playbooks")
                  }
                />
              </div>
            </section>

          </div>

          {/* RIGHT COLUMN — EDITORIAL VISUAL */}
          <div className="hidden xl:block">
            <div className="relative h-full w-full overflow-hidden rounded-2xl">
              <img
                src="/instrcutionpicture.png"
                alt=""
                aria-hidden="true"
                className="h-full w-full object-cover"
              />
              {/* subtle gradient */}
              <div className="absolute inset-0 bg-gradient-to-t from-[var(--bg-base)]/10 to-transparent" />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default TenantInstructionsPage;


