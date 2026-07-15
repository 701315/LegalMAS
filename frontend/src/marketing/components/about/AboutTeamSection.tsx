import React from 'react';
import Reveal from '../../motion/Reveal';

const teamBlocks = [
  {
    title: "Наш опыт",
    image: "/photo 1.jpg",
    description: "Наш путь начался в разных индустриях - от M&A и инвестиционного банкинга до разработки высоконагруженных систем. Мы объединили эти знания, чтобы создать продукт, который устраняет системные боли в работе с информацией."
  },
  {
    title: "Наша политика",
    image: "/photo 2.jpg",
    description: "Мы проектируем Steloom для людей, а не для алгоритмов. Наш приоритет - интуитивный интерфейс и удобство, понятное каждому эксперту. Это инструмент для профессионала, а не для «диджитал-гика»."
  },
  {
    title: "Наш продукт",
    image: "/photo 3.jpg",
    description: "В основе платформы лежат прозрачность и доказуемость результатов. Мы обеспечиваем предсказуемость каждого шага, открытость процессов и исключительное удобство в ежедневной эксплуатации."
  },
  {
    title: "Наши операции",
    image: "/photo 4.jpg",
    description: "Мы непрерывно развиваем платформу, адаптируясь к вызовам рынка и запросам пользователей. Мы верим в пользу нашего продукта и движем его вперед, меняя стандарты работы с данными."
  }
];

const AboutTeamSection: React.FC = () => {
  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32 border-t border-[var(--color-border)]">
      <div 
        className="mx-auto w-full px-6 lg:px-8" 
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <div className="grid grid-cols-1 gap-16 lg:grid-cols-12 lg:gap-24">
          
          {/* ── Левая колонка: Заголовок и вводный текст ────────────────── */}
          <div className="lg:col-span-4 lg:sticky lg:top-32 h-fit">
            <Reveal>
              <h2 className="font-serif text-[2.5rem] leading-tight tracking-tight text-[var(--text-primary)]">
                Команда
              </h2>
              <p className="mt-6 text-[1.0625rem] leading-[1.6] text-[var(--text-secondary)] max-w-sm">
                Мы - группа экспертов из сфер финансов, права, промышленности и технологий, 
                объединившая накопленные знания и опыт в продукт, решающий реальные задачи пользователей.
              </p>
            </Reveal>
          </div>

          {/* ── Правая колонка: Сетка 2x2 ──────────────────────────────── */}
          <div className="lg:col-span-8">
            <div className="grid grid-cols-1 gap-x-12 gap-y-16 md:grid-cols-2 lg:gap-x-16">
              {teamBlocks.map((block, i) => (
                <Reveal key={block.title} delay={i * 0.1}>
                  <div className="flex flex-col items-start">
                    {/* 
                        Изображение: 
                        - уменьшен max-width до 380px
                        - изменен aspect на 3/2 (более узкий горизонтальный формат)
                    */}
                    <div className="w-full max-w-[380px] aspect-[3/2] overflow-hidden rounded-[2rem] bg-[var(--bg-surface)] border border-[var(--color-border)]">
                      <img 
                        src={block.image} 
                        alt={block.title}
                        className="h-full w-full object-cover grayscale-[0.2] hover:grayscale-0 transition-all duration-700"
                      />
                    </div>
                    
                    {/* Заголовок блока */}
                    <h3 className="mt-8 font-serif text-[1.75rem] leading-none tracking-tight text-[var(--text-primary)]">
                      {block.title}
                    </h3>
                    
                    {/* Описание — ограничено по ширине для лучшей читаемости рядом с картинкой */}
                    <p className="mt-4 text-[0.9375rem] leading-[1.6] text-[var(--text-secondary)] max-w-[380px]">
                      {block.description}
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default AboutTeamSection;