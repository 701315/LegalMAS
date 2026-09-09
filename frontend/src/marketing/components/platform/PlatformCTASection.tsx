import React from "react";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

/**
 * PlatformCTASection — финальная CTA-секция.
 * 
 * Композиция:
 * • Белый фон (#FAF8F5), крупные вертикальные отступы
 * • Центрированный контент, max-width 720px
 * • Тонкая линия-якорь сверху → h2 → 2 абзаца → 1 кнопка → мета
 */
const PlatformCTASection: React.FC = () => {
  const { openContactModal } = useContactModal();
  
  // RTL FIX: Инициализация i18n и определение направления письма
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const paragraphsRaw = t("platform.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section
      className="relative"
      style={{ background: "#FAF8F5" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            {/* Верхний тонкий якорь */}
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

            {/* Заголовок */}
            <h2 className="mt-10 text-h1">
              {t("platform.cta.title")}
            </h2>

            {/* Абзацы */}
            <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
              {paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="text-body leading-[1.75] text-[var(--text-secondary)]"
                >
                  {p}
                </p>
              ))}
            </div>

            {/* Одна CTA-кнопка */}
            <div className="mt-10 flex items-center justify-center">
              <button
                type="button"
                onClick={openContactModal}
                className="cta-primary"
              >
                {t("platform.cta.ctaButton.primaryLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ 
                    transform: isRTL ? "rotate(180deg)" : "none",
                    transition: "transform 0.2s ease"
                  }} 
                />
              </button>
            </div>

            {/* Мета-строка (сокращённая) */}
            <p className="mt-8 text-eyebrow leading-[1.6] text-[var(--text-muted)]">
              {t("platform.cta.meta")}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default PlatformCTASection;