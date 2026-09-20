// src/marketing/components/home/KnowledgeGrowthSection/index.tsx
import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";  
import { useScrollReveal } from "../../../../hooks/useScrollReveal";
import { useTranslation } from "react-i18next";
import KnowledgeTree from "./KnowledgeTree";

const KnowledgeGrowthSection: React.FC = () => {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

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

  // Получаем данные из i18n
  const eyebrow = t("home.knowledgeGrowth.eyebrow");
  const title = t("home.knowledgeGrowth.title");
  const ctaLabel = t("home.knowledgeGrowth.ctaLabel");
  
  // БЕЗОПАСНОЕ получение массива абзацев:
  // Если ключ не найден или возвращает строку, мы принудительно оборачиваем его в массив,
  // чтобы .map() не падал с ошибкой.
  const paragraphsRaw = t("home.knowledgeGrowth.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) 
    ? paragraphsRaw 
    : [t("home.knowledgeGrowth.paragraphs")];

  return (
    <section
      ref={sectionRef}
      id="knowledge"
      className="relative flex min-h-screen items-center bg-[var(--bg-base)] py-20 lg:py-28 scroll-mt-0"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-16">
          
          {/* ── Левая колонка: Дерево ── */}
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

          {/* ── Правая колонка: Концепция ── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="flex flex-col justify-center lg:col-span-4"
          >
            <span className="eyebrow">{eyebrow}</span>

            {/* whitespace-pre-line сохраняет перенос строки \n из JSON */}
            <h2 className="text-h1 !mt-2 max-w-3xl text-[var(--text-primary)] whitespace-pre-line">
              {title.split("\n")[0]}
              <br />
              <em className="not-italic text-[var(--accent-primary)]">
                {title.split("\n")[1] || ""}
              </em>
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              {paragraphs.map((paragraph, index) => (
                <p 
                  key={index} 
                  className="text-body leading-relaxed text-[var(--text-secondary)]"
                >
                  {paragraph}
                </p>
              ))}
            </div>

            <Link to="/capabilities" className="cta-link mt-12 inline-flex items-center gap-2">
              {ctaLabel}
              {/* RTL FIX: разворот стрелки для арабского языка */}
              <ArrowRight 
                className="h-3.5 w-3.5" 
                style={{ 
                  transform: isRTL ? "rotate(180deg)" : "none",
                  transition: "transform 0.2s ease"
                }} 
              />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default KnowledgeGrowthSection;