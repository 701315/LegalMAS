// src/components/marketing/landing/CapabilitiesSection.tsx

import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, CheckCircle2 } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";

function CapabilitiesVisual() {
  const [activeIndex, setActiveIndex] = useState(0);

  const ITEMS = [
    {
      label: "Playbook check",
      status: "done",
      text: "Условие об ограничении ответственности — соответствует стандарту",
      source: "SPA_v3.pdf · §8.2",
    },
    {
      label: "Risk flag",
      status: "risk",
      text: "Change of control clause — отклонение от стандартной позиции",
      source: "SHA_final.pdf · §12.4",
    },
    {
      label: "Obligation",
      status: "done",
      text: "MAC-definition — присутствует, формулировка стандартная",
      source: "SPA_v3.pdf · §1.1",
    },
    {
      label: "Playbook check",
      status: "pending",
      text: "Non-compete scope — требует проверки юриста",
      source: "Employment.pdf · §5",
    },
    {
      label: "Cross-ref",
      status: "done",
      text: "Определение Closing Date согласовано во всех 3 документах",
      source: "SPA / SHA / Disclosure",
    },
  ];

  useEffect(() => {
    const t = setInterval(() => {
      setActiveIndex((i) => (i + 1) % ITEMS.length);
    }, 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-[28px] border border-[#E5E2DA] bg-white">
      <div className="flex items-center gap-2 border-b border-[#F0EDE8] px-5 py-3.5">
        <div className="h-2.5 w-2.5 rounded-full bg-[#F0EDE8]" />
        <div className="h-2.5 w-2.5 rounded-full bg-[#F0EDE8]" />
        <div className="h-2.5 w-2.5 rounded-full bg-[#F0EDE8]" />
        <span className="ml-3 text-[11px] font-medium text-stone-400">
          SPA_DD_Package · Playbook Review
        </span>
      </div>
      <div className="border-b border-[#F0EDE8] px-5 py-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-stone-400">Progress</span>
          <span className="text-[11px] font-medium text-[#2F5A4A]">18 / 24 checks</span>
        </div>
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-[#F0EDE8]">
          <div className="h-full w-3/4 rounded-full bg-[#2F5A4A] transition-all duration-700" />
        </div>
      </div>
      <div className="divide-y divide-[#F8F7F4]">
        {ITEMS.map((item, i) => (
          <div
            key={i}
            className="flex items-start gap-3 px-5 py-3.5 transition-colors duration-300"
            style={{ background: i === activeIndex ? "#F8F7F4" : "white" }}
          >
            <div className="mt-0.5 shrink-0">
              {item.status === "done" && (
                <div className="flex h-4 w-4 items-center justify-center rounded-full bg-[#2F5A4A]/10">
                  <CheckCircle2 size={10} className="text-[#2F5A4A]" />
                </div>
              )}
              {item.status === "risk" && (
                <div className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-50">
                  <div className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                </div>
              )}
              {item.status === "pending" && (
                <div className="flex h-4 w-4 items-center justify-center rounded-full bg-stone-100">
                  <div className="h-1.5 w-1.5 rounded-full bg-stone-400" />
                </div>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-stone-400">
                {item.label}
              </span>
              <p className="mt-0.5 text-xs leading-5 text-stone-700">{item.text}</p>
              <p className="mt-0.5 text-[10px] text-stone-400">{item.source}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-[#F0EDE8] px-5 py-3">
        <p className="text-[10px] text-stone-400">
          Source-linked · Every output traceable to document and clause
        </p>
      </div>
    </div>
  );
}

const BULLETS = [
  "Playbook-driven review по каждому разделу",
  "Извлечение положений с привязкой к источнику",
  "Автоматическое выявление рисков и отклонений",
  "Работа с пакетом документов, а не с одним файлом",
  "Структурированный export-ready результат",
];

const CapabilitiesSection: React.FC = () => {
  const reveal = useScrollReveal(0);

  return (
    <section
      id="capabilities"
      className="flex min-h-screen items-center bg-[#F8F7F4] scroll-mt-0 py-20"
    >
      <div className="mx-auto w-full max-w-[1280px] px-6 lg:px-10 xl:px-12">
        <div
          ref={reveal.ref as React.Ref<HTMLDivElement>}
          style={reveal.style}
          className="grid items-start gap-12 lg:grid-cols-2"
        >
          {/* ── Левая колонка ── */}
          <div className="flex flex-col justify-center">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Возможности
            </div>
            <h2 className="mt-5 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-950 lg:text-[3.5rem]">
              Ключевые операции
              <br />
              поверх документа —
              <br />
              в одной логике.
            </h2>
            <p className="mt-5 max-w-md text-base leading-8 text-stone-600">
              Извлечение положений, навигация по рискам, привязка вывода
              к источнику, review по playbook — единая система, а не набор
              разрозненных AI-фич.
            </p>

            <ul className="mt-7 space-y-2.5">
              {BULLETS.map((b) => (
                <li key={b} className="flex items-start gap-3">
                  <CheckCircle2
                    size={15}
                    className="mt-0.5 shrink-0 text-[#2F5A4A]"
                    strokeWidth={1.75}
                  />
                  <span className="text-sm leading-6 text-stone-700">{b}</span>
                </li>
              ))}
            </ul>

            <Link
              to="/capabilities"
              className="mt-10 inline-flex w-fit items-center gap-2 rounded-full border border-[#E5E2DA] bg-white px-5 py-2.5 text-sm font-medium text-stone-700 transition-all hover:border-stone-300 hover:text-stone-950"
            >
              Все возможности платформы
              <ArrowUpRight size={14} />
            </Link>
          </div>

          {/* ── Правая колонка ── */}
          <div className="h-[580px] lg:h-[640px]">
            <CapabilitiesVisual />
          </div>
        </div>
      </div>
    </section>
  );
};

export default CapabilitiesSection;

