// src/components/marketing/landing/SecuritySection.tsx

import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Shield, Lock, Eye, FileCheck } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";

const PILLARS = [
  {
    icon: Lock,
    label: "Local-first",
    text: "Документы не покидают контур без явного решения администратора. Local-first по умолчанию.",
  },
  {
    icon: Shield,
    label: "PII Gateway",
    text: "Перед обращением к внешним моделям данные проходят через санацию. Чувствительное — не уходит.",
  },
  {
    icon: Eye,
    label: "Role-based access",
    text: "Разделение ролей для загрузки, запуска проверок и доступа к выводам. Контроль на каждом уровне.",
  },
  {
    icon: FileCheck,
    label: "Audit trail",
    text: "Source-linked outputs и прозрачный trail для review, внутреннего контроля и security-опросников.",
  },
];

const SecuritySection: React.FC = () => {
  const header = useScrollReveal(0);
  const pillars = useScrollReveal(120);

  return (
    <section
      id="security"
      className="relative flex min-h-screen items-center overflow-hidden scroll-mt-0 py-20"
    >
      <video
        autoPlay muted loop playsInline aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        style={{ opacity: 0.18 }}
      >
        <source src="/video/security-bg.mp4" type="video/mp4" />
      </video>

      <div aria-hidden="true" className="absolute inset-0 bg-[#0D1117]" style={{ opacity: 0.92 }} />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 60% 50% at 15% 80%, rgba(47,90,74,0.20) 0%, transparent 65%)" }}
      />

      <div className="relative mx-auto w-full max-w-[1280px] px-6 lg:px-10 xl:px-12">
        <div className="grid items-start gap-16 lg:grid-cols-2">

          {/* Левая — текст */}
          <div ref={header.ref as React.Ref<HTMLDivElement>} style={header.style}>
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-white/40">
              Безопасность
            </div>
            <h2 className="mt-5 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-white lg:text-[3.5rem]">
              Контроль доступа,
              <br />
              границы данных
              <br />
              и доказуемость.
            </h2>
            <p className="mt-6 max-w-md text-base leading-8 text-white/55">
              Steloom проектировался так, чтобы выдерживать вопросы не только
              юристов, но и CISO. Где хранятся документы, как используется AI,
              кто получает доступ к результатам — всё это прозрачно и задокументировано.
            </p>

            <div className="mt-8 flex flex-wrap gap-2">
              {["Local-first processing", "PII sanitization", "Role-based access", "Audit trail"].map((b) => (
                <span
                  key={b}
                  className="rounded-full border border-[#2F5A4A]/40 bg-[#2F5A4A]/12 px-3.5 py-1.5 text-xs font-medium text-[#6BAF95]"
                >
                  {b}
                </span>
              ))}
            </div>

            <Link
              to="/security"
              className="mt-10 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/8 px-5 py-2.5 text-sm font-medium text-white/70 transition-all hover:border-white/30 hover:text-white"
            >
              Подробнее об архитектуре безопасности
              <ArrowUpRight size={14} />
            </Link>
          </div>

          {/* Правая — четыре столпа */}
          <div
            ref={pillars.ref as React.Ref<HTMLDivElement>}
            style={pillars.style}
            className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          >
            {PILLARS.map((p, i) => {
              const Icon = p.icon;
              return (
                <div
                  key={p.label}
                  className="flex flex-col rounded-[24px] border border-white/8 bg-white/[0.04] p-6 backdrop-blur-sm transition-all duration-300 hover:border-white/15 hover:bg-white/[0.07]"
                  style={{ transitionDelay: `${i * 40}ms` }}
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                    <Icon size={16} strokeWidth={1.5} className="text-[#6BAF95]" />
                  </div>
                  <div className="mt-4 text-[11px] font-medium uppercase tracking-[0.18em] text-white/35">
                    {p.label}
                  </div>
                  <p className="mt-2 text-sm leading-7 text-white/55">{p.text}</p>
                </div>
              );
            })}

            <div className="col-span-full rounded-[24px] border border-white/8 bg-white/[0.03] p-5">
              <div className="flex items-center gap-4">
                <div className="h-2 w-2 rounded-full bg-[#6BAF95]" />
                <p className="text-sm leading-7 text-white/50">
                  Продукт проходит enterprise security review и используется
                  в сценариях с NDA-чувствительными документами.
                </p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default SecuritySection;


