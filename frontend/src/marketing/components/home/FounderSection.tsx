// src/marketing/components/home/FounderSection.tsx
import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";
import { useTranslation } from "react-i18next";
import photoVladimir from "../assets/photos/vladimir.jpg";

/**
 * FounderSection — сбалансированный портрет + единая цитата.
 * Фотография уменьшена для лучшей пропорции, текст унифицирован.
 */
const FounderSection: React.FC = () => {
  const { t, i18n } = useTranslation("marketing");
  const left = useScrollReveal(0);
  const right = useScrollReveal(120);

  const isRTL = i18n.language === "ar";

  return (
    <section
      id="founder"
      className="relative bg-[var(--bg-base)] py-24 lg:py-36 border-y border-[var(--border-color)]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-16 lg:grid-cols-12 lg:gap-24">
          
          {/* ── Левая колонка: Уменьшенный, сбалансированный портрет ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-4"
          >
            {/* max-w-sm ограничивает физический размер фото на больших экранах */}
            <div className="relative group max-w-sm mx-auto lg:max-w-none">
              <div className="aspect-[4/5] w-full overflow-hidden rounded-[2rem] border border-[var(--border-color)] bg-[var(--bg-surface)] shadow-sm transition-all duration-1000">
                <img
                  src={photoVladimir}
                  alt={t("home.founder.name")}
                  className="h-full w-full object-cover grayscale-[0.3] group-hover:grayscale-0 transition-all duration-1000 scale-[1.02] group-hover:scale-105"
                />
              </div>
              
              {/* Подпись под фото (центрована на мобильных, слева на десктопе) */}
              <div className="mt-8 text-center lg:text-start">
                <div className="text-lg font-serif italic text-[var(--text-primary)]">
                  {t("home.founder.name")}
                </div>
                <div className="mt-1 text-eyebrow uppercase tracking-widest text-[var(--accent-primary)] font-bold">
                  {t("home.founder.role")}
                </div>
              </div>
            </div>
          </div>

          {/* ── Правая колонка: Единая, унифицированная цитата ──────── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="lg:col-span-8"
          >
            {/* RTL FIX: border-l -> border-s, pl -> ps */}
            <div className="relative border-s border-[var(--accent-primary)]/20 ps-8 lg:ps-16">
              <p className="eyebrow mb-8">{t("home.founder.eyebrow")}</p>
              
              <blockquote>
                <p className="text-h2 whitespace-pre-line">
                  {t("home.founder.quote")}
                </p>
              </blockquote>

              <div className="mt-12">
                <Link 
                  to="/about" 
                  className="cta-link group inline-flex items-center gap-2 text-body-sm font-semibold text-[var(--text-primary)]"
                >
                  {t("home.founder.ctaLabel")}
                  {/* RTL FIX: разворот стрелки для арабского */}
                  <ArrowRight 
                    className="h-4 w-4 transition-transform group-hover:translate-x-1" 
                    style={{ transform: isRTL ? "rotate(180deg) translateX(-4px)" : "none" }}
                  />
                </Link>
              </div>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default FounderSection;