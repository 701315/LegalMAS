import React from "react";
import Reveal from "../../motion/Reveal";
import { METHODOLOGY_CONTENT } from "./content/platformContent";

/**
 * PlatformMethodologySection — Иммерсивная темная версия.
 * 
 * Параметры:
 *   • Фон секции: Глубокий черный (#1A1917).
 *   • Картинка: /platform-1-1.png на ВСЮ площадь (fullscreen background).
 *   • Оверлей: Градиентный переход от черного слева к прозрачному справа.
 */

const PlatformMethodologySection: React.FC = () => {
  return (
    <section
      className="relative overflow-hidden bg-[#1A1917]"
      data-header-theme="dark"
    >
      
      {/* ── Background Layer: Картинка на всю площадь секции ────────── */}
      <div className="absolute inset-0 z-0">
        <img 
          src="/platform-1-1.png" 
          alt="" 
          className="h-full w-full object-cover object-center opacity-40 lg:opacity-50"
          aria-hidden="true"
        />
        {/* Радиально-линейный градиент для фокуса на тексте слева */}
        <div 
          className="absolute inset-0" 
          style={{
            background: 'linear-gradient(90deg, #1A1917 0%, rgba(26,25,23,0.85) 30%, rgba(26,25,23,0.2) 60%, transparent 100%)'
          }} 
        />
      </div>

      {/* ── Content Layer: Текст поверх изображения ─────────────────── */}
      <div
        className="relative z-10 mx-auto w-full px-6 py-32 lg:px-8 lg:py-48"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-16 lg:grid-cols-12 lg:gap-20">
          <Reveal className="lg:col-span-7">
            <div className="max-w-2xl">
              
              {/* Eyebrow */}
              <div className="eyebrow !text-[var(--color-accent)] brightness-110">
                {METHODOLOGY_CONTENT.eyebrow}
              </div>

              {/* Заголовок — Off-white */}
              <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#FAF8F5]">
                {METHODOLOGY_CONTENT.title}
              </h2>

              {/* Lead-in — Serif Italic */}
              <p
                className="mt-6 font-serif text-[1.25rem] italic leading-[1.5] text-[#FAF8F5]/90"
                style={{ maxWidth: 560 }}
              >
                {METHODOLOGY_CONTENT.leadIn}
              </p>

              {/* Основной текст — Muted Grey для темной темы */}
              <div className="mt-8 space-y-6" style={{ maxWidth: 620 }}>
                {METHODOLOGY_CONTENT.paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-[1.0625rem] leading-[1.75] text-[#A8A29E]"
                  >
                    {p}
                  </p>
                ))}
              </div>
            </div>
          </Reveal>

          {/* Правая колонка остается свободной для визуального баланса */}
          <div className="hidden lg:block lg:col-span-5" />
        </div>
      </div>
    </section>
  );
};

export default PlatformMethodologySection;


