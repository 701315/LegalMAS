// src/marketing/components/home/PremiumHeroSection.tsx
import React, { useEffect, useState } from "react";
import { landingContent } from "../../content/landingContent";

const PremiumHeroSection: React.FC = () => {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 60);
    return () => clearTimeout(t);
  }, []);

  const fadeIn = (delayMs: number): React.CSSProperties => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? "translateY(0)" : "translateY(12px)",
    transition: `opacity 0.6s ease-out ${delayMs}ms, transform 0.6s ease-out ${delayMs}ms`,
  });

  const { hero } = landingContent;

  return (
    <section
      className="relative flex min-h-screen overflow-hidden bg-[#1A1917]"
      data-header-theme="dark"
    >
      {/* Видео на всю ширину */}
      <video
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 h-full w-full object-cover"
        style={{
          filter: "sepia(0.25) saturate(0.75) hue-rotate(-10deg) brightness(0.9)",
        }}
      >
        <source src="/video/hero-bg.mp4" type="video/mp4" />
      </video>

      {/* Тёмный оверлей для читаемости текста */}
      <div
        aria-hidden="true"
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(135deg, rgba(26, 25, 23, 0.8) 0%, rgba(26, 25, 23, 0.6) 100%)",
        }}
      />

      {/* Subtle radial glow — terracotta */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(200,107,82,0.15) 0%, transparent 70%)",
        }}
      />

      {/* Контент — текст по центру экрана */}
      <div
        className="relative z-10 mx-auto flex w-full items-center px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)", minHeight: "100vh" }}
      >
        <div className="grid w-full grid-cols-12 items-center gap-8">
          
          {/* Левая колонка — Заголовок (по центру) */}
          <div className="col-span-12 lg:col-span-6" style={fadeIn(0)}>
            <h1 className="font-serif text-[clamp(2.5rem,5vw,4.5rem)] leading-[1.05] tracking-[-0.03em] text-[#FAF8F5]">
              {hero.title.split("\n")[0]}
              <br />
              <span style={{ color: "#E8B4A0" }}>
                {hero.title.split("\n")[1]}
              </span>
            </h1>
          </div>

          {/* Правая колонка — Граф + Описание (по центру) */}
          <div className="col-span-12 lg:col-span-6 lg:ml-auto" style={fadeIn(200)}>
            {/* SVG-граф над текстом */}
            <div className="relative mb-[-3rem] h-[280px] w-full opacity-0.7">
              <svg viewBox="0 0 520 420" fill="none" className="h-full w-full" aria-hidden="true">
                <circle cx="260" cy="210" r="5.5" fill="#C86B52" opacity="1" />
                <circle cx="140" cy="130" r="3.5" fill="#C86B52" opacity="0.85" />
                <circle cx="380" cy="130" r="3.5" fill="#C86B52" opacity="0.85" />
                <circle cx="100" cy="290" r="3" fill="#C86B52" opacity="0.7" />
                <circle cx="420" cy="290" r="3" fill="#C86B52" opacity="0.7" />
                <circle cx="200" cy="340" r="3" fill="#C86B52" opacity="0.65" />
                <circle cx="320" cy="340" r="3" fill="#C86B52" opacity="0.65" />
                <line x1="260" y1="210" x2="140" y2="130" stroke="#C86B52" strokeWidth="0.8" opacity="0.75" />
                <line x1="260" y1="210" x2="380" y2="130" stroke="#C86B52" strokeWidth="0.8" opacity="0.75" />
                <line x1="260" y1="210" x2="100" y2="290" stroke="#C86B52" strokeWidth="0.7" opacity="0.65" />
                <line x1="260" y1="210" x2="420" y2="290" stroke="#C86B52" strokeWidth="0.7" opacity="0.65" />
                <line x1="260" y1="210" x2="200" y2="340" stroke="#C86B52" strokeWidth="0.6" opacity="0.6" />
                <line x1="260" y1="210" x2="320" y2="340" stroke="#C86B52" strokeWidth="0.6" opacity="0.6" />
                <line x1="140" y1="130" x2="380" y2="130" stroke="#C86B52" strokeWidth="0.4" opacity="0.4" />
                <line x1="100" y1="290" x2="420" y2="290" stroke="#C86B52" strokeWidth="0.4" opacity="0.4" />
              </svg>
            </div>

            {/* Описание */}
            <p className="max-w-md text-[1.0625rem] leading-[1.7] text-[#D6D0C7]">
              {hero.description}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PremiumHeroSection;