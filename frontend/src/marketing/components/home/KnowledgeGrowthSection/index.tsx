// src/marketing/components/home/KnowledgeGrowthSection/index.tsx

import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { useScrollReveal } from "../../../../hooks/useScrollReveal";
import KnowledgeTree from "./KnowledgeTree";

const KnowledgeGrowthSection: React.FC = () => {
  const left = useScrollReveal(0);
  const right = useScrollReveal(150);
  const sectionRef = useRef<HTMLElement>(null);
  const [treeActive, setTreeActive] = useState(false);
  const [animationKey, setAnimationKey] = useState(0);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setAnimationKey((k) => k + 1);
          setTreeActive(true);
        } else {
          setTreeActive(false);
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
      id="knowledge"
      className="relative flex min-h-screen items-center bg-[#F8F7F4] py-4 scroll-mt-0"
    >
      <div className="mx-auto w-full max-w-[1920px] px-4 lg:px-6 xl:px-10">
        <div className="grid items-center gap-6 lg:grid-cols-12 lg:gap-8">
          {/* ── Левая колонка: Дерево ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-8"
          >
            <div
              className="relative mx-auto w-full"
              style={{ maxHeight: "85vh", maxWidth: "85vh" }}
            >
              <KnowledgeTree key={animationKey} active={treeActive} />
            </div>
          </div>

          {/* ── Правая колонка: Концепция ── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="flex flex-col justify-center lg:col-span-4"
          >
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Возможности
            </div>

            <h2 className="mt-5 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-950 lg:text-[3.75rem]">
              Растущее
              <br />
              <em className="not-italic" style={{ color: "#2F5A4A" }}>
                знание.
              </em>
            </h2>

            <p className="mt-6 max-w-md text-base leading-8 text-stone-600 lg:text-[1.05rem] lg:leading-9">
              Steloom собирает тысячи разрозненных положений договора
              в единую живую структуру — не для поиска, а для понимания.
            </p>

            <p className="mt-5 max-w-md text-base leading-8 text-stone-600 lg:text-[1.05rem] lg:leading-9">
              Один документ или пакет из десятков — система работает
              одинаково: распознаёт тип (SPA, SHA, NDA, трудовой договор),
              выстраивает структуру и применяет набор рисков, заранее
              определённый юристом под конкретную сделку.
            </p>

            <p className="mt-5 max-w-md text-base leading-8 text-stone-600 lg:text-[1.05rem] lg:leading-9">
              Каждый вывод привязан к источнику — конкретному пункту
              в конкретном документе. Без галлюцинаций, без отвязанных
              обобщений.
            </p>

            <Link
              to="/platform"
              className="mt-10 inline-flex w-fit items-center gap-2 rounded-full border border-[#E5E2DA] bg-white px-5 py-2.5 text-sm font-medium text-stone-700 transition-all hover:border-stone-300 hover:text-stone-950"
            >
              Все возможности платформы
              <ArrowUpRight size={14} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default KnowledgeGrowthSection;


