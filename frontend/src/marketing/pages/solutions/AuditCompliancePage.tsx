import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  FolderSearch,
  CheckCircle2,
  AlertTriangle,
  Scale,
  ClipboardCheck,
  BarChart3,
  ListChecks,
  FileWarning,
  ScanSearch,
} from "lucide-react";

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const AuditPage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion() ?? false;

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} prefersReduced={prefersReduced} />
        <AuditRoutinesIntroSection />
        <VisualCardsSection />
        <CapabilitiesSection />
        <SignalsSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default AuditPage;

function HeroSection({
  onDemo,
  prefersReduced,
}: {
  onDemo: () => void;
  prefersReduced: boolean;
}) {
  return (
    <section
      className="relative flex min-h-[68dvh] items-center overflow-hidden bg-[#1A1917]"
      data-header-theme="dark"
    >
      <div className="absolute inset-0 z-0">
        <motion.img
          src="/in-1-4.png"
          alt="Среда внутреннего аудита и контроля"
          className="h-full w-full object-cover object-center opacity-35 lg:opacity-55"
          initial={prefersReduced ? undefined : { scale: 1.02, opacity: 0 }}
          animate={prefersReduced ? undefined : { scale: 1, opacity: 0.55 }}
          transition={{ duration: 1.5, ease }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, #1A1917 0%, rgba(26,25,23,0.96) 28%, rgba(26,25,23,0.58) 62%, transparent 100%)",
          }}
        />
      </div>

      <div
        className="relative z-10 mx-auto w-full px-6 py-20 lg:px-8 lg:py-24"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-7 xl:col-span-6">
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <div className="flex items-center gap-2 text-[0.75rem] uppercase tracking-[0.14em]">
                <span className="text-white/70">Сценарий использования</span>
                <span className="text-white/40" aria-hidden="true">
                  /
                </span>
                <span className="text-white/70">Внутренний аудит</span>
              </div>
            </motion.div>

            <motion.h1
              className="mt-10 font-serif text-[clamp(2rem,4vw,3.05rem)] leading-[1.08] tracking-[-0.03em] text-[#FAF8F5]"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.22, ease }}
            >
              Аудиторский след, который не нужно собирать вручную - <br />
              <span className="italic font-light text-[var(--color-accent)] brightness-125">
                от вывода системы до абзаца в первоисточнике
              </span>
            </motion.h1>

            <motion.p
              className="mt-8 max-w-xl text-[1rem] leading-[1.75] text-white/72 font-light"
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.38, ease }}
            >
              Steloom помогает внутреннему аудиту применять единые правила ко всему
              договорному массиву, фиксировать основания выводов и готовить
              доказательную базу для повторной проверки и отчётности.
            </motion.p>

            <motion.div
              className="mt-10"
              initial={prefersReduced ? undefined : { opacity: 0 }}
              animate={prefersReduced ? undefined : { opacity: 1 }}
              transition={{ delay: 0.52 }}
            >
              <button onClick={onDemo} className="cta-primary">
                Запросить демонстрацию
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AuditRoutinesIntroSection() {
  return (
    <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-12 lg:gap-16">
            <div className="lg:col-span-5">
              <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                Что забирает время у аудитора
              </p>
              <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-[1.15] tracking-[-0.02em] text-[#1A1917]">
                Рутинные процедуры аудита - <br />
                <span className="italic font-light text-[var(--color-accent)]">
                  в едином потоке анализа
                </span>
              </h2>
            </div>

            <div className="lg:col-span-7">
              <div className="space-y-6 text-[1rem] leading-[1.8] text-[#78756F] font-light">
                <p>
                  Структурирование массива, проверка по чек-листам, формирование
                  доказательной базы и сравнение между периодами — это рутинные
                  процедуры, которые поглощают время аудитора и перегружают команду
                  ручной работой.
                </p>
                <p>
                  Steloom автоматизирует эти этапы: применяет единые правила ко
                  всему массиву, выделяет документы и отклонения, требующие
                  профессионального суждения, и формирует прослеживаемый
                  аудиторский след — от вывода системы до конкретного абзаца
                  первоисточника.
                </p>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function VisualCardsSection() {
  const cards = [
    {
      title: "Единый чек-лист",
      text: "Единые правила проверки применяются ко всему массиву — ни один документ не выпадает из аудита. Снижается зависимость от выборочного подхода и человеческих ошибок при анализе тысяч договоров одновременно.",
      image: "/ia-1-1.png",
      alt: "Единый чек-лист проверки договорного массива",
    },
    {
      title: "Аудиторский след",
      text: "Каждое замечание связано с конкретным пунктом документа. Заключение оформляется с указанием изученных вопросов, выявленных отклонений и оснований — как готовая доказательная база для внутреннего и внешнего контроля.",
      image: "/ia-1-2.png",
      alt: "Аудиторский след и привязка вывода к документу",
    },
    {
      title: "Сравнение периодов",
      text: "Результаты прошлых проверок остаются доступными для сопоставления. Можно сравнивать массивы между периодами, видеть динамику и быстрее выявлять новые зоны риска, требующие внимания команды.",
      image: "/ia-1-3.png",
      alt: "Сравнение результатов между периодами аудита",
    },
  ];

  return (
    <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-20 lg:px-8 lg:py-24"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3 lg:gap-10 items-stretch">
          {cards.map((card, index) => (
            <Reveal key={card.title} delay={index * 0.08}>
              <article className="group h-full">
                <div className="flex h-full flex-col overflow-hidden border border-[#E8E4DD]/50 bg-[var(--bg-surface)]">
                  <div className="relative aspect-[4/3] overflow-hidden bg-[#EFEAE2]">
                    <img
                      src={card.image}
                      alt={card.alt}
                      className="h-full w-full object-cover object-center transition-transform duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-[1.03]"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-[#1A1917]/12 via-transparent to-transparent" />
                  </div>

                  <div className="flex flex-1 flex-col px-6 py-7 lg:px-7 lg:py-8 bg-[var(--bg-surface)]">
                    <h3 className="font-serif text-[1.35rem] tracking-tight text-[#1A1917] italic">
                      {card.title}
                    </h3>
                    <p className="mt-4 text-[0.9375rem] leading-[1.7] text-[#78756F] font-light">
                      {card.text}
                    </p>
                  </div>
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function CapabilitiesSection() {
  const capabilities = [
    {
      icon: FolderSearch,
      title: "Структурирование массива",
      bullets: [
        "Автоматическая классификация по типам, датам, контрагентам и риск-категориям",
        "Исключение ручной сортировки и предварительной фильтрации документов",
        "Единое представление разнородных форматов — сканов, PDF и Word — в структурированном виде",
      ],
    },
    {
      icon: ListChecks,
      title: "Проверка по чек-листам",
      bullets: [
        "Применение единых правил ко всем документам — 100% охват вместо выборочного аудита",
        "Выявление пропущенных обязательных условий, отклонений от типовых форм и внутренних политик",
        "Флаггирование документов, требующих профессионального суждения аудитора",
      ],
    },
    {
      icon: ClipboardCheck,
      title: "Аудиторский след и доказательность",
      bullets: [
        "Каждое заключение сопровождается ссылкой на конкретный абзац первоисточника",
        "Полная история: что загружено, какие правила применены и какие отклонения выявлены",
        "Экспортируемые отчёты для внутреннего аудита и внешних проверок",
      ],
    },
    {
      icon: Scale,
      title: "Единая логика проверки",
      bullets: [
        "Сопоставление всех документов с единым набором контрольных критериев",
        "Снижение зависимости от ручной вариативности и различий в подходе между аудиторами",
        "Более воспроизводимая методология для последующего контроля и защиты результатов",
      ],
    },
    {
      icon: AlertTriangle,
      title: "Выявление исключений и зон риска",
      bullets: [
        "Выделение документов с отклонениями, которые требуют отдельного анализа",
        "Определение исключений для эскалации, follow-up и дополнительной проверки",
        "Более удобная приоритизация работы команды по риску и значимости отклонений",
      ],
    },
    {
      icon: BarChart3,
      title: "Отчётность для руководства",
      bullets: [
        "Сводная картина типовых отклонений, зон риска и документов, требующих внимания",
        "Основа для обсуждения с руководством, комитетом по аудиту и второй линией контроля",
        "Более понятная коммуникация результатов внутреннего аудита на уровне функций и периодов",
      ],
    },
  ];

  return (
    <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50" data-header-theme="light">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl mb-16">
            <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
              Что автоматизирует Steloom
            </p>
            <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-[1.15] tracking-[-0.02em] text-[#1A1917]">
              Рутинные процедуры аудита - <br />
              <span className="italic font-light text-[var(--color-accent)]">
                в едином потоке анализа
              </span>
            </h2>
          </div>
        </Reveal>

        <div className="mt-16">
          {capabilities.map((item, index) => (
            <Reveal key={item.title} delay={index * 0.05}>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                <div className="md:col-span-4">
                  <div className="flex items-center gap-3">
                    <item.icon className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                    <h3 className="font-serif text-[1.35rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                  </div>
                </div>

                <div className="md:col-span-8">
                  <ul className="space-y-4">
                    {item.bullets.map((bullet) => (
                      <li key={bullet} className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          {bullet}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function SignalsSection() {
  const signals = [
    "Пропущенные обязательные условия и оговорки, которые должны присутствовать по внутренним политикам.",
    "Отклонения от типовых форм, шаблонов и утверждённых договорных конструкций.",
    "Нестандартные или рискованные формулировки в ключевых положениях договора.",
    "Документы, где отсутствуют нужные согласования, подтверждения или обязательные элементы контроля.",
    "Изменения в договорном массиве между периодами, требующие повторной проверки.",
    "Повторяющиеся типы отклонений, которые указывают на системную проблему процесса.",
    "Документы, требующие эскалации аудитору из-за уровня риска или неоднозначности формулировок.",
    "Основания для follow-up проверки и контроля корректирующих мероприятий.",
  ];

  return (
    <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-16">
            <div className="lg:col-span-4">
              <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                Какие сигналы выявляет система
              </p>
              <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-[1.15] tracking-[-0.02em] text-[#1A1917]">
                Что именно попадает в фокус проверки
              </h2>
              <p className="mt-5 text-[0.95rem] leading-[1.75] text-[#78756F] font-light max-w-md">
                Этот блок нужен для быстрой ориентации: что именно Steloom может
                выделять в договорном массиве, чтобы команда внутреннего аудита
                переходила от ручного просмотра к более прицельному анализу.
              </p>
            </div>

            <div className="lg:col-span-8">
              <div className="grid gap-x-10 gap-y-6 md:grid-cols-2">
                {signals.map((item, index) => (
                  <RevealItem key={item}>
                    <div className="flex items-start gap-3 border-t border-[#E8E4DD]/60 pt-5">
                      {index % 2 === 0 ? (
                        <FileWarning className="h-4 w-4 text-[var(--color-accent)] opacity-60 flex-shrink-0 mt-1" />
                      ) : (
                        <ScanSearch className="h-4 w-4 text-[var(--color-accent)] opacity-60 flex-shrink-0 mt-1" />
                      )}
                      <p className="text-[0.9375rem] leading-[1.7] text-[#78756F] font-light">
                        {item}
                      </p>
                    </div>
                  </RevealItem>
                ))}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CTASection({ onDemo }: { onDemo: () => void }) {
  return (
    <section
      className="relative bg-[#FAF8F5] py-28 lg:py-40 border-t border-[#E8E4DD]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

            <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
              Steloom помогает внутреннему аудиту работать на основе доказательств <br />
              <span className="italic font-light opacity-60 text-[var(--color-accent)]">
                а не на ручной сборке материалов и выборочном анализе
              </span>
            </h2>

            <div className="mt-7 space-y-5 text-[1.0625rem] leading-[1.75] text-[#78756F]">
              <p>
                Платформа структурирует договорный массив, проверяет документы по
                единым правилам, связывает выводы с источниками и помогает готовить
                материалы для внутреннего и внешнего контроля.
              </p>
              <p>
                Загрузите документы — Steloom выделит отклонения, сформирует
                прослеживаемую доказательную базу и сократит объём рутинной работы
                для сотрудников департамента внутреннего аудита.
              </p>
            </div>

            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                Запросить демонстрацию
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            <p className="mt-8 text-[0.8125rem] leading-[1.6] text-[#A8A29E]">
              Обычно мы отвечаем в течение одного рабочего дня.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


