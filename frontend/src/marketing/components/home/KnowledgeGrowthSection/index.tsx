// src/marketing/components/home/KnowledgeGrowthSection/index.tsx
import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { useScrollReveal } from "../../../../hooks/useScrollReveal";
import KnowledgeTree from "./KnowledgeTree";
import { landingContent } from "../../../content/landingContent";

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

  // Берем "eyebrow" из контента
  const content = landingContent.capabilities;

  return (
    <section
      ref={sectionRef}
      id="knowledge"
      className="relative flex min-h-screen items-center bg-[#F8F7F4] py-24 sm:py-32 scroll-mt-0"
      data-header-theme="light"
    >
      <div className="mx-auto w-full max-w-[1920px] px-6 lg:px-10 xl:px-12">
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-16">
          
          {/* ── Левая колонка: Дерево ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-7 xl:col-span-8"
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
            className="flex flex-col justify-center lg:col-span-5 xl:col-span-4"
          >
            <span className="eyebrow">{content.eyebrow}</span>

            <h2 className="section-title !mt-2 text-stone-950">
              Растущее
              <br />
              <em className="not-italic text-[#2F5A4A]">знание.</em>
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              <p className="text-[1.05rem] leading-relaxed text-stone-600">
                Steloom собирает тысячи разрозненных положений договора
                в единую живую структуру — не для поиска, а для понимания.
              </p>

              <p className="text-[1.05rem] leading-relaxed text-stone-600">
                Один документ или пакет из десятков — система работает
                одинаково: распознаёт тип (SPA, SHA, NDA, трудовой договор),
                выстраивает структуру и применяет набор рисков, заранее
                определённый юристом под конкретную сделку.
              </p>

              <p className="text-[1.05rem] leading-relaxed text-stone-600">
                Каждый вывод привязан к источнику — конкретному пункту
                в конкретном документе. Без галлюцинаций, без отвязанных
                обобщений.
              </p>
            </div>

            <Link
              to="/capabilities"
              className="mt-12 inline-flex w-fit items-center gap-2 rounded-full border border-stone-300 bg-white px-6 py-3 text-sm font-medium text-stone-700 shadow-sm transition-all hover:border-stone-400 hover:text-stone-950 hover:shadow-md"
            >
              Все возможности платформы
              <ArrowUpRight size={16} />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default KnowledgeGrowthSection;

