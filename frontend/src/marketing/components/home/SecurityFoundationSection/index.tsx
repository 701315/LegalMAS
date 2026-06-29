// src/components/marketing/landing/SecurityFoundationSection/index.tsx

import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { useScrollReveal } from "../../../../hooks/useScrollReveal";
import RootsTree from "./RootsTree";

type Principle = {
  id: string;
  body: string;
};

const PRINCIPLES: Principle[] = [
  {
    id: "isolation",
    body: "Каждая сделка живёт в собственном контуре. Между проектами нет проходных каналов — ни для пользователей, ни для модели.",
  },
  {
    id: "audit",
    body: "Каждое действие в системе записывается. Кто открыл документ, кто запустил анализ, какая версия playbook применялась, какой источник лежит в основе вывода.",
  },
  {
    id: "control",
    body: "AI работает внутри вашего периметра по вашим правилам. Никаких скрытых вызовов, никаких утечек через third-party провайдеров.",
  },
  {
    id: "compliance",
    body: "Steloom соответствует ISO 27001 и требованиям российского законодательства о персональных данных.",
  },
];

const SecurityFoundationSection: React.FC = () => {
  const left = useScrollReveal(0);
  const right = useScrollReveal(150);
  const sectionRef = useRef<HTMLElement>(null);
  const [active, setActive] = useState(false);
  const [animationKey, setAnimationKey] = useState(0);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setAnimationKey((k) => k + 1);
          setActive(true);
        } else {
          setActive(false);
        }
      },
      { threshold: 0.35 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      id="security"
      className="relative flex min-h-screen items-center bg-[#F8F7F4] py-4 scroll-mt-0"
    >
      <div className="mx-auto w-full max-w-[1920px] px-4 lg:px-6 xl:px-10">
        <div className="grid items-center gap-6 lg:grid-cols-12 lg:gap-8">

          {/* ── Левая колонка: Корни (соразмерно дереву) ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-8"
          >
            <div
              className="relative mx-auto w-full"
              style={{ maxHeight: "85vh", maxWidth: "85vh" }}
            >
              <RootsTree key={animationKey} active={active} />
            </div>
          </div>

          {/* ── Правая колонка: Заголовок + 4 абзаца без титулов ── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="flex flex-col justify-center lg:col-span-4"
          >
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Безопасность
            </div>

            <h2 className="mt-5 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-950 lg:text-[3.75rem]">
              Основание,
              <br />
              <em className="not-italic" style={{ color: "#2F5A4A" }}>
                на котором держится безопасность.
              </em>
            </h2>

            {/* ── 4 абзаца без заголовков ── */}
            <div className="mt-8 flex flex-col gap-5 max-w-md">
              {PRINCIPLES.map((p) => (
                <p
                  key={p.id}
                  className="text-base leading-8 text-stone-600 lg:text-[1.05rem] lg:leading-9"
                >
                  {p.body}
                </p>
              ))}
            </div>

            <Link
              to="/security"
              className="mt-10 inline-flex w-fit items-center gap-2 rounded-full border border-[#E5E2DA] bg-white px-5 py-2.5 text-sm font-medium text-stone-700 transition-all hover:border-stone-300 hover:text-stone-950"
            >
              Подробнее о безопасности
              <ArrowUpRight size={14} />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default SecurityFoundationSection;