import React from "react";
import { ArrowRight } from "lucide-react";
import Reveal from "../../motion/Reveal";
import { CTA_CONTENT } from "./content/platformContent";
import { useContactModal } from "../../context/ContactModalContext";

/**

PlatformCTASection — финальная CTA-секция (упрощена).
Изменения:
• Убрана кнопка «Связаться с командой» — оставлена только primary
• В мета-строке убрано «Формат: онлайн или очно» — оставлено только время
Композиция без изменений:
• Белый фон (#FAF8F5), крупные вертикальные отступы
• Центрированный контент, max-width 720px
• Тонкая линия-якорь сверху → h2 → 2 абзаца → 1 кнопка → мета
*/
const PlatformCTASection: React.FC = () => {
const { openContactModal } = useContactModal();

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

text

        {/* Заголовок */}
        <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">          {CTA_CONTENT.title}
        </h2>

        {/* Абзацы */}
        <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
          {CTA_CONTENT.paragraphs.map((p, i) => (
            <p
              key={i}
              className="text-[1.0625rem] leading-[1.75] text-[#78756F]"
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
            {CTA_CONTENT.cta.primaryLabel}
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Мета-строка (сокращённая) */}
        <p className="mt-8 text-[0.8125rem] leading-[1.6] text-[#A8A29E]">
          {CTA_CONTENT.meta}
        </p>
      </div>
    </Reveal>
  </div>
</section>
);
};

export default PlatformCTASection;


