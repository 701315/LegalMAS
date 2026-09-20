import React, { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useContactModal } from "../../context/ContactModalContext";

const PremiumFinalCtaSection: React.FC = () => {
  const { t, i18n } = useTranslation("marketing");
  const { openContactModal } = useContactModal();
  const isRTL = i18n.language === "ar";

  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.2 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const fadeIn = (delay: number): React.CSSProperties => ({
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(16px)",
    transition: `opacity 0.8s cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 0.8s cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
  });

  // Получаем данные из i18n
  const title = t("home.finalCta.title");
  const description = t("home.finalCta.description");
  const primaryLabel = t("home.finalCta.primary");
  const secondaryLabel = t("home.finalCta.secondary");

  // Разбиваем заголовок по переносу строки
  const titleParts = title.split("\n");

  const handlePrimaryClick = () => {
    openContactModal();
  };

  const handleSecondaryClick = () => {
    // Плавный скролл к секции сценариев (ApplicationSection)
    const el = document.getElementById("application");
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <section
      ref={ref}
      className="relative flex items-center justify-center border-t border-[var(--border-color)] bg-[var(--bg-surface)]"
      style={{ minHeight: 480 }}
      data-header-theme="light"
    >
      {/* Subtle radial glow — warm terracotta */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 55% at 50% 50%, rgba(200,107,82,0.08) 0%, transparent 70%)",
        }}
      />

      <div
        className="relative mx-auto flex flex-col items-center px-6 py-20 text-center lg:px-8 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* Декоративный граф — рандомно внутри блока, под текстом */}
        {/* RTL FIX: left-20 заменен на start-20 для корректного позиционирования в арабском */}
        <div
          className="pointer-events-none absolute start-20 top-16 z-0"
          style={{ width: "30%", maxWidth: "380px", opacity: 0.35 }}
          aria-hidden="true"
        >
          <svg viewBox="0 0 520 420" fill="none" className="h-full w-full">
            <circle cx="260" cy="210" r="6" fill="#C86B52" opacity="1" />
            <circle cx="140" cy="130" r="4" fill="#C86B52" opacity="0.9" />
            <circle cx="380" cy="130" r="4" fill="#C86B52" opacity="0.9" />
            <circle cx="100" cy="290" r="3.5" fill="#C86B52" opacity="0.8" />
            <circle cx="420" cy="290" r="3.5" fill="#C86B52" opacity="0.8" />
            <circle cx="200" cy="340" r="3.5" fill="#C86B52" opacity="0.75" />
            <circle cx="320" cy="340" r="3.5" fill="#C86B52" opacity="0.75" />
            <line x1="260" y1="210" x2="140" y2="130" stroke="#C86B52" strokeWidth="1" opacity="0.85" />
            <line x1="260" y1="210" x2="380" y2="130" stroke="#C86B52" strokeWidth="1" opacity="0.85" />
            <line x1="260" y1="210" x2="100" y2="290" stroke="#C86B52" strokeWidth="0.9" opacity="0.75" />
            <line x1="260" y1="210" x2="420" y2="290" stroke="#C86B52" strokeWidth="0.9" opacity="0.75" />
            <line x1="260" y1="210" x2="200" y2="340" stroke="#C86B52" strokeWidth="0.8" opacity="0.7" />
            <line x1="260" y1="210" x2="320" y2="340" stroke="#C86B52" strokeWidth="0.8" opacity="0.7" />
            <line x1="140" y1="130" x2="380" y2="130" stroke="#C86B52" strokeWidth="0.5" opacity="0.5" />
            <line x1="100" y1="290" x2="420" y2="290" stroke="#C86B52" strokeWidth="0.5" opacity="0.5" />
          </svg>
        </div>

        <div className="relative z-10 flex flex-col items-center">
          {/* ИСПРАВЛЕНО: Использован семантический класс text-h1 вместо инлайн-стилей */}
          <h2
            className="mt-6 text-display max-w-4xl mx-auto"
            style={{
              maxWidth: 720,
              ...fadeIn(100),
            }}
          >
            {titleParts[0]}
            <br />
            {titleParts[1] || ""}
          </h2>

          {/* ИСПРАВЛЕНО: Использован семантический класс text-body вместо дублирующих классов */}
          <p
            className="mt-5 text-body"
            style={{ maxWidth: 560, ...fadeIn(200) }}
          >
            {description}
          </p>

          {/* CTA Кнопки */}
          <div
            className="mt-10 flex flex-col gap-3 sm:flex-row"
            style={fadeIn(300)}
          >
            <button
              type="button"
              onClick={handlePrimaryClick}
              className="cta-primary"
            >
              {primaryLabel}
              <ArrowRight
                className="h-4 w-4"
                style={{
                  transform: isRTL ? "rotate(180deg)" : "none",
                  transition: "transform 0.2s ease",
                }}
              />
            </button>

            <button
              type="button"
              onClick={handleSecondaryClick}
              className="cta-secondary"
            >
              {secondaryLabel}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PremiumFinalCtaSection;