import React from 'react';
import { ArrowRight } from 'lucide-react';
import Reveal from '../../motion/Reveal';
import { useContactModal } from '../../context/ContactModalContext';

/**
 * AboutCTASection — финальная CTA-секция страницы «О нас».
 * Выполнена в строгом соответствии с паттерном SecurityCTASection.
 */

const AboutCTASection: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <section
      className="relative"
      style={{ background: '#FAF8F5' }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            {/* Верхний тонкий якорь (как в Security) */}
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

            {/* ✅ Заголовок — унифицированная шкала clamp */}
            <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
              Давайте покажем Steloom <br /> на ваших документах
            </h2>

            {/* Абзацы — шрифт 1.0625rem / ведущий 1.75 */}
            <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
              <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                Мы готовы провести персональную демонстрацию платформы, 
                используя примеры ваших рабочих документов, чтобы вы могли 
                оценить точность и скорость подготовки информации.
              </p>
              <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                Забронируйте встречу с нашей командой, чтобы обсудить ваши 
                текущие задачи и увидеть Steloom в действии.
              </p>
            </div>

            {/* Одна главная CTA-кнопка со стрелкой */}
            <div className="mt-10 flex items-center justify-center">
              <button
                type="button"
                onClick={openContactModal}
                className="cta-primary"
              >
                Запросить демонстрацию
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Мета-строка — приглушенный шрифт 0.8125rem */}
            <p className="mt-8 text-[0.8125rem] leading-[1.6] text-[#A8A29E]">
              Обычно мы отвечаем и назначаем встречу в течение одного рабочего дня.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default AboutCTASection;