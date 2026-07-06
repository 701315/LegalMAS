// src/marketing/components/home/KnowledgeGrowthSection/index.tsx
import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";  
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

  const content = landingContent.capabilities;

  return (
    <section
      ref={sectionRef}
      id="knowledge"
      className="relative flex min-h-screen items-center bg-[#FAF8F5] py-20 lg:py-28 scroll-mt-0"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-16">
          
          {/* ── Левая колонка: Дерево (увеличена в 1.5 раза) ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-8"
          >
            <div
              className="relative mx-auto w-full"
              style={{ maxHeight: "115vh", maxWidth: "115vh" }}
            >
              <KnowledgeTree key={animationKey} active={treeActive} />
            </div>
          </div>

          {/* ── Правая колонка: Концепция (уменьшена, чтобы дать место дереву) ── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="flex flex-col justify-center lg:col-span-4"
          >
            <span className="eyebrow">{content.eyebrow}</span>

            <h2 className="section-title !mt-2 text-[#1A1917]">
              Растущее
              <br />
              <em className="not-italic text-[#C86B52]">знание.</em>
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              <p className="text-[1.0625rem] leading-[1.7] text-[#78756F]">
                Steloom собирает тысячи разрозненных положений договора
                в единую живую структуру — не для поиска, а для понимания.
              </p>

              <p className="text-[1.0625rem] leading-[1.7] text-[#78756F]">
                Один документ или пакет из десятков — система работает
                одинаково: распознаёт тип (SPA, SHA, NDA, трудовой договор),
                выстраивает структуру и применяет набор рисков, заранее
                определённый юристом под конкретную сделку.
              </p>

              <p className="text-[1.0625rem] leading-[1.7] text-[#78756F]">
                Каждый вывод привязан к источнику — конкретному пункту
                в конкретном документе. Без галлюцинаций, без отвязанных
                обобщений.
              </p>
            </div>

            <Link to="/capabilities" className="cta-link mt-12">
              Все возможности платформы
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default KnowledgeGrowthSection;


