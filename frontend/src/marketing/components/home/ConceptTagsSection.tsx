// src/marketing/components/home/ConceptTagsSection.tsx

import React from "react";
import Marquee from "react-fast-marquee";
import { useTranslation } from "react-i18next";

function Tag({ label }: { label: string }) {
  return (
    <span className="mx-3 inline-flex items-center whitespace-nowrap rounded-full border border-[var(--border-color)] bg-white px-6 py-3 text-body-sm font-medium text-[var(--text-secondary)] transition-all duration-300 hover:border-[#D6D0C7] hover:text-[var(--text-primary)]">
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

  // Безопасное получение массивов (защита от ошибок рендеринга)
  const rawRow1 = t("home.conceptTags.row1", { returnObjects: true });
  const rawRow2 = t("home.conceptTags.row2", { returnObjects: true });

  const row1: string[] = Array.isArray(rawRow1)
    ? rawRow1.map((item) => String(item))
    : [];
  const row2: string[] = Array.isArray(rawRow2)
    ? rawRow2.map((item) => String(item))
    : [];

  // RTL: инвертируем направление Marquee для арабского языка
  const isRTL = i18n.language === "ar";
  const marqueeDirection1 = isRTL ? "right" : "left";
  const marqueeDirection2 = isRTL ? "left" : "right";

  return (
    <section className="overflow-hidden border-b border-[var(--border-color)] bg-[var(--bg-base)] py-20 lg:py-28">
      <div
        className="mx-auto mb-16 flex w-full flex-col items-center px-6 text-center lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* Надзаголовок (Eyebrow) */}
        <span className="text-eyebrow">{eyebrow}</span>

        {/* ЗАГОЛОВОК СЕКЦИИ — УВЕЛИЧЕН ДО H1 (text-h1 и max-w-4xl) */}
        <h2 className="text-h1 mt-2 max-w-4xl whitespace-pre-line text-balance text-[var(--text-primary)]">
          {title}
        </h2>

        {/* Описание секции */}
        <p className="text-body mt-6 max-w-2xl text-center">
          {description}
        </p>
      </div>

      {/* Бегущие строки (Marquee) */}
      <div className="relative flex flex-col gap-5">
        {/* Градиентные оверлеи для плавного исчезновения краев */}
        <div className="pointer-events-none absolute inset-y-0 start-0 z-10 w-24 bg-gradient-to-r from-[#FAF8F5] to-transparent sm:w-48" />
        <div className="pointer-events-none absolute inset-y-0 end-0 z-10 w-24 bg-gradient-to-l from-[#FAF8F5] to-transparent sm:w-48" />

        {/* Первый ряд тегов */}
        {row1.length > 0 && (
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
        )}

        {/* Второй ряд тегов */}
        {row2.length > 0 && (
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
        )}
      </div>
    </section>
  );
};

export default ConceptTagsSection;