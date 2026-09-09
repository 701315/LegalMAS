// src/marketing/components/home/ConceptTagsSection.tsx
import React from "react";
import Marquee from "react-fast-marquee";
import { useTranslation } from "react-i18next";

function Tag({ label }: { label: string }) {
  return (
    <span className="mx-3 inline-flex items-center whitespace-nowrap rounded-full border border-[var(--border-color)] bg-white px-6 py-3 text-body-sm font-medium tracking-tight text-[var(--text-secondary)] transition-all duration-300 hover:border-[#D6D0C7] hover:text-[var(--text-primary)]">
      {label}
    </span>
  );
}

const ConceptTagsSection: React.FC = () => {
  const { t, i18n } = useTranslation("marketing");

  // Получаем данные из i18n
  const eyebrow = t("home.conceptTags.eyebrow");
  const title = t("home.conceptTags.title");
  const description = t("home.conceptTags.description");
  const row1 = t("home.conceptTags.row1", { returnObjects: true }) as string[];
  const row2 = t("home.conceptTags.row2", { returnObjects: true }) as string[];

  // RTL: инвертируем направление Marquee для естественного восприятия
  const isRTL = i18n.language === "ar";
  const marqueeDirection1 = isRTL ? "right" : "left";
  const marqueeDirection2 = isRTL ? "left" : "right";

  return (
    <section className="overflow-hidden border-b border-[var(--border-color)] bg-[var(--bg-base)] py-20 lg:py-28">
      <div
        className="mx-auto mb-16 flex w-full flex-col items-center px-6 text-center lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <span className="eyebrow">{eyebrow}</span>
        <h2 className="section-title !mt-2 max-w-3xl whitespace-pre-line text-balance text-[var(--text-primary)]">
          {title}
        </h2>
        <p className="section-desc text-center text-[var(--text-secondary)]">
          {description}
        </p>
      </div>

      <div className="relative flex flex-col gap-5">
        {/* Градиентные оверлеи для плавного исчезновения краев */}
        {/* RTL: start-0 вместо left-0, end-0 вместо right-0 */}
        <div className="pointer-events-none absolute inset-y-0 start-0 z-10 w-24 bg-gradient-to-r from-[#FAF8F5] to-transparent sm:w-48" />
        <div className="pointer-events-none absolute inset-y-0 end-0 z-10 w-24 bg-gradient-to-l from-[#FAF8F5] to-transparent sm:w-48" />

        {/* Первый ряд тегов */}
        <div>
          <Marquee
            speed={32}
            gradient={false}
            pauseOnHover
            direction={marqueeDirection1}
          >
            {row1.map((tag, index) => (
              <Tag key={`row1-${index}`} label={tag} />
            ))}
            {row1.map((tag, index) => (
              <Tag key={`row1-dup-${index}`} label={tag} />
            ))}
          </Marquee>
        </div>

        {/* Второй ряд тегов (движется в противоположном направлении) */}
        <Marquee
          speed={24}
          gradient={false}
          pauseOnHover
          direction={marqueeDirection2}
        >
          {row2.map((tag, index) => (
            <Tag key={`row2-${index}`} label={tag} />
          ))}
          {row2.map((tag, index) => (
            <Tag key={`row2-dup-${index}`} label={tag} />
          ))}
        </Marquee>
      </div>
    </section>
  );
};

export default ConceptTagsSection;