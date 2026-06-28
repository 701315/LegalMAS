// src/components/marketing/landing/SolutionsSection.tsx

import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Handshake, Building2, Scale } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";

const ROLES = [
  {
    icon: Handshake,
    eyebrow: "M&A-команды",
    headline: "Скорость и контроль в data room.",
    body: "Steloom обрабатывает data room против вашего playbook — каждое положение, риск и перекрёстная ссылка структурированы за часы, а не недели. Ни одно условие не теряется на странице 47.",
    tags: ["Due Diligence", "Data Room", "Risk Extraction", "Playbook Review"],
    accent: "#2F5A4A",
    accentBg: "rgba(47,90,74,0.06)",
  },
  {
    icon: Building2,
    eyebrow: "Legal Ops",
    headline: "Повторяемость, прозрачность и масштабирование.",
    body: "Стандартизированный процесс review, который не зависит от конкретного юриста. Steloom фиксирует методологию команды в playbook и воспроизводит её на каждом новом документном массиве.",
    tags: ["Process Standardization", "Audit Trail", "Workflow Automation"],
    accent: "#4A6A8A",
    accentBg: "rgba(74,106,138,0.06)",
  },
  {
    icon: Scale,
    eyebrow: "General Counsel",
    headline: "Управляемый риск и доказуемость выводов.",
    body: "Каждый вывод привязан к источнику. Решения принимаются на основе проверяемых данных, а не пересказа. Steloom даёт ясность для управленческих решений и снижает цену пропущенного риска.",
    tags: ["Risk Management", "Decision Support", "Explainable Outputs"],
    accent: "#7A5A3A",
    accentBg: "rgba(122,90,58,0.06)",
  },
];

const SolutionsSection: React.FC = () => {
  const [activeRole, setActiveRole] = useState<number | null>(null);
  const header = useScrollReveal(0);
  const cards = useScrollReveal(100);

  return (
    <section
      id="solutions"
      className="flex min-h-screen items-center bg-white scroll-mt-0 py-20"
    >
      <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 xl:px-12">

        <div
          ref={header.ref as React.Ref<HTMLDivElement>}
          style={header.style}
          className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between"
        >
          <div className="max-w-xl">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Сценарии
            </div>
            <h2 className="mt-4 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-950 lg:text-[3.5rem]">
              Одна платформа
              <br />
              для ключевых контуров
              <br />
              юридической работы
            </h2>
          </div>
          <p className="max-w-sm text-base leading-8 text-stone-500 lg:pb-2">
            Steloom релевантен нескольким ключевым ролям в юрфункции —
            не одному узкому пользователю.
          </p>
        </div>

        <div
          ref={cards.ref as React.Ref<HTMLDivElement>}
          style={cards.style}
          className="mt-14 grid gap-4 lg:grid-cols-3"
        >
          {ROLES.map((role, i) => {
            const Icon = role.icon;
            const isActive = activeRole === i;

            return (
              <div
                key={role.eyebrow}
                onMouseEnter={() => setActiveRole(i)}
                onMouseLeave={() => setActiveRole(null)}
                className="group flex flex-col rounded-[28px] border border-[#E5E2DA] p-8 transition-all duration-300 cursor-default"
                style={{
                  background: isActive ? role.accentBg : "#F8F7F4",
                  borderColor: isActive ? "transparent" : "#E5E2DA",
                  boxShadow: isActive ? "0 8px 32px rgba(0,0,0,0.07)" : "none",
                  transform: isActive ? "translateY(-4px)" : "translateY(0)",
                }}
              >
                <div
                  className="flex h-11 w-11 items-center justify-center rounded-2xl border transition-colors duration-300"
                  style={{
                    borderColor: isActive ? `${role.accent}30` : "#E5E2DA",
                    background: isActive ? `${role.accent}10` : "white",
                  }}
                >
                  <Icon
                    size={18}
                    strokeWidth={1.5}
                    style={{ color: isActive ? role.accent : "#78716c" }}
                  />
                </div>

                <div
                  className="mt-6 text-[11px] font-medium uppercase tracking-[0.18em] transition-colors duration-300"
                  style={{ color: isActive ? role.accent : "#a8a29e" }}
                >
                  {role.eyebrow}
                </div>

                <h3 className="mt-2 font-serif text-2xl leading-snug tracking-[-0.02em] text-stone-950">
                  {role.headline}
                </h3>

                <div
                  className="overflow-hidden transition-all duration-300"
                  style={{
                    maxHeight: isActive ? 200 : 0,
                    opacity: isActive ? 1 : 0,
                    marginTop: isActive ? 12 : 0,
                  }}
                >
                  <p className="text-sm leading-7 text-stone-600">{role.body}</p>
                </div>

                <div
                  className="mt-3 transition-all duration-300"
                  style={{ opacity: isActive ? 0 : 1, maxHeight: isActive ? 0 : 100, overflow: "hidden" }}
                >
                  <p className="text-sm leading-7 text-stone-500 line-clamp-2">{role.body}</p>
                </div>

                <div className="mt-auto pt-6 flex flex-wrap gap-2">
                  {role.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border px-3 py-1 text-[11px] font-medium transition-colors duration-300"
                      style={{
                        borderColor: isActive ? `${role.accent}25` : "#E5E2DA",
                        color: isActive ? role.accent : "#a8a29e",
                        background: isActive ? `${role.accent}08` : "transparent",
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-10">
          <Link
            to="/solutions"
            className="inline-flex items-center gap-2 rounded-full border border-[#E5E2DA] bg-[#F8F7F4] px-5 py-2.5 text-sm font-medium text-stone-700 transition-all hover:border-stone-300 hover:text-stone-950"
          >
            Подробнее о сценариях
            <ArrowUpRight size={14} />
          </Link>
        </div>

      </div>
    </section>
  );
};

export default SolutionsSection;

