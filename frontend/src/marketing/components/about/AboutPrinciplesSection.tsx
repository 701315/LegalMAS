import React from 'react';
import Reveal from '../../motion/Reveal';

const principles = [
  { title: "Сначала процесс", desc: "Автоматизируем не документ, а реальный workflow юридической команды." },
  { title: "Проверяемость", desc: "Каждое утверждение системы подтверждено прямой ссылкой на источник." },
  { title: "Скрытая сложность", desc: "Чистый интерфейс для оркестрации мощных специализированных моделей." },
  { title: "Предсказуемость", desc: "Единая и прозрачная логика анализа данных в рамках всей организации." }
];

const AboutPrinciples: React.FC = () => {
  return (
    <section className="bg-[var(--bg-base)] py-24 border-t border-[var(--color-border)]">
      <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: 'var(--container-max-width)' }}>
        <Reveal>
          <h2 className="section-title text-3xl mb-16 italic">Принципы создания</h2>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {principles.map((p, i) => (
            <Reveal key={i}>
              <div className="border-l-2 border-[var(--color-border)] pl-6">
                <h4 className="font-serif text-xl italic mb-3 tracking-tight">{p.title}</h4>
                <p className="text-[0.9375rem] leading-[1.6] text-[var(--text-secondary)]">
                  {p.desc}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
};

export default AboutPrinciples;


