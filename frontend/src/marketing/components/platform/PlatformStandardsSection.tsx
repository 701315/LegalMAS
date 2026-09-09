import React from "react";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";

const PlatformMethodologySection: React.FC = () => {
  // RTL FIX: Инициализация i18n и определение направления
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const paragraphsRaw = t("platform.methodology.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  // RTL FIX: Зеркалирование градиента для арабского языка.
  // В LTR текст слева, градиент плотный слева (90deg).
  // В RTL текст справа, градиент должен быть плотным справа (270deg).
  const gradientStyle = {
    background: isRTL
      ? "linear-gradient(270deg, #1A1917 0%, rgba(26,25,23,0.85) 30%, rgba(26,25,23,0.2) 60%, transparent 100%)"
      : "linear-gradient(90deg, #1A1917 0%, rgba(26,25,23,0.85) 30%, rgba(26,25,23,0.2) 60%, transparent 100%)",
  };

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
        {/* RTL FIX: Динамический градиент в зависимости от направления письма */}
        <div 
          className="absolute inset-0" 
          style={gradientStyle} 
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
              <div className="eyebrow !text-[var(--accent-primary)] brightness-110 text-start">
                {t("platform.methodology.eyebrow")}
              </div>

              {/* Заголовок — Off-white */}
              <h2 className="mt-4 font-serif text-h1 leading-[1.05] tracking-[-0.03em] text-[var(--text-inverse)] text-start">
                {t("platform.methodology.title")}
              </h2>

              {/* Lead-in — Serif Italic */}
              <p
                className="mt-6 font-serif text-h3 italic leading-[1.5] text-[var(--text-inverse)]/90 text-start"
                style={{ maxWidth: 560 }}
              >
                {t("platform.methodology.leadIn")}
              </p>

              {/* Основной текст — Muted Grey для темной темы */}
              <div className="mt-8 space-y-6" style={{ maxWidth: 620 }}>
                {paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-body leading-[1.75] text-[var(--text-muted)] text-start"
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