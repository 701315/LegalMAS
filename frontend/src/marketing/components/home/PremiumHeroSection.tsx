// src/marketing/components/home/PremiumHeroSection.tsx

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

const DEFAULT_TITLE = "Преобразуйте документы\nв структуру и знание";
const DEFAULT_DESCRIPTION = [
  "Steloom переводит массивы юридических документов в связанную, проверяемую и пригодную для работы интеллектуальную систему.",
  "Команда тратит меньше времени на поиск и сверку — больше на выводы и решения.",
];

const PremiumHeroSection: React.FC = () => {
  const { t } = useTranslation("marketing");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 60);
    return () => clearTimeout(timer);
  }, []);

  const fadeIn = (delayMs: number): React.CSSProperties => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? "translateY(0)" : "translateY(12px)",
    transition: `opacity 0.6s ease-out ${delayMs}ms, transform 0.6s ease-out ${delayMs}ms`,
  });

  const rawTitle = t("home.hero.title", { defaultValue: DEFAULT_TITLE });
  const title = typeof rawTitle === "string" && !rawTitle.startsWith("home.") ? rawTitle : DEFAULT_TITLE;
  const titleParts = title.split("\n");

  const rawDesc = t("home.hero.description", { returnObjects: true });
  const description: string[] = Array.isArray(rawDesc) && rawDesc.length > 0
    ? rawDesc.map((item) => String(item))
    : DEFAULT_DESCRIPTION;

  return (
    <section
      id="landing-hero"
      data-theme="dark"
      data-header-theme="dark"
      data-nav-theme="dark"
      data-header-transparent="true"
      className="relative flex min-h-screen overflow-hidden bg-[#1A1917] -mt-16 lg:-mt-20 pt-16 lg:pt-20"
    >
      {/* 1. Видео */}
      <video
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 h-full w-full object-cover z-0"
        style={{ filter: "sepia(0.2) saturate(0.8) hue-rotate(-5deg) brightness(0.85)" }}
      >
        <source src="/video/hero-bg.mp4" type="video/mp4" />
      </video>

      {/* 2. Оверлей */}
      <div
        aria-hidden="true"
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: "linear-gradient(135deg, rgba(26, 25, 23, 0.75) 0%, rgba(26, 25, 23, 0.55) 100%)",
        }}
      />

      {/* 3. Контент */}
      <div
        className="relative z-30 mx-auto flex w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)", minHeight: "100vh", paddingTop: "28vh" }}
      >
        <div className="grid w-full grid-cols-12 items-start gap-8">
          
          {/* Левая колонка — Заголовок (Используем text-display) */}
          <div className="col-span-12 lg:col-span-6" style={fadeIn(0)}>
            {/* ИСПОЛЬЗУЕМ СИСТЕМНЫЙ КЛАСС text-display и принудительно !text-white для темного фона */}
            <h1 className="text-display !text-white">
              {titleParts[0]}
              {titleParts.length > 1 && (
                <>
                  <br />
                  <span className="text-[#E8B4A0]">{titleParts[1]}</span>
                </>
              )}
            </h1>
          </div>

          {/* Правая колонка — Описание (Используем text-body) */}
          <div className="col-span-12 lg:col-span-6 lg:ml-auto relative" style={fadeIn(200)}>
            {/* Граф */}
            <div className="absolute bottom-full mb-[-3rem] h-[280px] w-full opacity-70 z-20 pointer-events-none">
               {/* Ваш SVG граф (оставляю без изменений для экономии места) */}
               <svg viewBox="0 0 520 420" fill="none" className="h-full w-full"><circle cx="260" cy="210" r="5.5" fill="#C86B52" /><circle cx="140" cy="130" r="3.5" fill="#C86B52" opacity="0.85" /><circle cx="380" cy="130" r="3.5" fill="#C86B52" opacity="0.85" /><circle cx="100" cy="290" r="3" fill="#C86B52" opacity="0.7" /><circle cx="420" cy="290" r="3" fill="#C86B52" opacity="0.7" /><circle cx="200" cy="340" r="3" fill="#C86B52" opacity="0.65" /><circle cx="320" cy="340" r="3" fill="#C86B52" opacity="0.65" /><line x1="260" y1="210" x2="140" y2="130" stroke="#C86B52" strokeWidth="0.8" opacity="0.75" /><line x1="260" y1="210" x2="380" y2="130" stroke="#C86B52" strokeWidth="0.8" opacity="0.75" /><line x1="260" y1="210" x2="100" y2="290" stroke="#C86B52" strokeWidth="0.7" opacity="0.65" /><line x1="260" y1="210" x2="420" y2="290" stroke="#C86B52" strokeWidth="0.7" opacity="0.65" /><line x1="260" y1="210" x2="200" y2="340" stroke="#C86B52" strokeWidth="0.6" opacity="0.6" /><line x1="260" y1="210" x2="320" y2="340" stroke="#C86B52" strokeWidth="0.6" opacity="0.6" /><line x1="140" y1="130" x2="380" y2="130" stroke="#C86B52" strokeWidth="0.4" opacity="0.4" /><line x1="100" y1="290" x2="420" y2="290" stroke="#C86B52" strokeWidth="0.4" opacity="0.4" /></svg>
            </div>

            {/* ИСПОЛЬЗУЕМ СИСТЕМНЫЙ КЛАСС text-body. Цвета переопределяем явно (т.к. фон тёмный) */}
            <div className="max-w-md text-body !text-[#D6D0C7]">
              {description.map((paragraph, idx) => (
                <p key={idx} className={idx > 0 ? "mt-4" : ""}>
                  {paragraph}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PremiumHeroSection;