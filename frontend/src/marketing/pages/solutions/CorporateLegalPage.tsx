// src/marketing/pages/solutions/CorporateLegalPage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  FileSearch,
  TrendingUp,
  Layers,
  CheckCircle2,
  ShieldCheck,
} from "lucide-react";

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const CorporateLegalPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection />
        <PressureSection />
        <OutcomesSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default CorporateLegalPage;

function HeroSection() {
  const prefersReduced = useReducedMotion();

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5]">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <RevealItem>
            <PathCrumb root="Сценарий использования" leaf="Корпоративные юристы" />
          </RevealItem>

          <div className="mt-12 grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-10 lg:gap-12 items-start">
            <RevealItem>
              <motion.div
                initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
                animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: 0.2, ease }}
                className="overflow-hidden rounded-none border border-[#E8E4DD] bg-white shadow-sm"
              >
                <img
                  src="/in-1.jpg"
                  alt="Corporate legal team workspace"
                  className="block w-full h-full min-h-[420px] lg:min-h-[540px] object-cover"
                />
              </motion.div>
            </RevealItem>

            <div className="flex flex-col justify-start">
              <RevealItem>
                <p className="text-[1.0625rem] leading-[1.75] text-[var(--text-secondary)] font-light">
                  Корпоративный юридический департамент должен успевать за бизнесом:
                  быстрее отвечать внутренним заказчикам, удерживать единый стандарт
                  проверки и не терять контроль над риском по мере роста массива договоров.
                </p>
              </RevealItem>

              <RevealItem>
                <p className="mt-6 text-[1.0625rem] leading-[1.75] text-[var(--text-secondary)] font-light">
                  Steloom берёт на себя первичную обработку документов: применяет
                  корпоративные playbooks, выявляет отклонения, структурирует findings
                  и связывает каждый вывод с конкретным фрагментом источника.
                </p>
              </RevealItem>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function PressureSection() {
  const items = [
    {
      title: "Бизнес ждёт быстрее, чем растёт команда",
      text: "Продажи, закупки, HR и продуктовые команды ожидают быстрых согласований. Объём запросов растёт быстрее, чем юридический департамент успевает масштабироваться.",
    },
    {
      title: "Разный уровень анализа",
      text: "Даже сильная команда по-разному оценивает одинаковые положения договора. Без единого playbook качество зависит от конкретного исполнителя.",
    },
    {
      title: "Сложно удержать полный контроль",
      text: "Когда договоров много, выборочная проверка становится нормой. Это создаёт риск пропущенных отклонений, обязательств и нестандартных клаузул.",
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <RevealItem>
              <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                Где возникает перегрузка
              </p>
            </RevealItem>
          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <RevealItem key={item.title}>
                <div className="flex flex-col h-full">
                  <div className="pt-0">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function OutcomesSection() {
  const outcomes = [
    {
      image: "/lf-1-1.png",
      title: "Скорость для внутренних заказчиков",
      text: "Юридический департамент быстрее отвечает бизнесу, потому что рутинный первичный скрининг и сверка с playbook выполняются автоматически.",
    },
    {
      image: "/lf-1-2.png",
      title: "Единый стандарт по всем договорам",
      text: "Одни и те же правила применяются ко всем документам - независимо от исполнителя, загрузки команды и типа контрагента.",
    },
    {
      image: "/lf-1-3.png",
      title: "Прослеживаемые findings",
      text: "Каждый вывод связан с конкретным абзацем источника. Это упрощает согласование с бизнесом, руководством, аудиторами и комплаенсом.",
    },
    {
      image: "/lf-1-4.png",
      title: "100% охват массива",
      text: "Steloom проверяет весь массив документов, а не выборку. Команда получает более полную картину отклонений и рисков.",
    },
    {
      image: "/lf-1-5.png",
      title: "Больше времени на стратегию",
      text: "Юристы меньше тратят времени на механическую вычитку и больше - на переговоры, оценку риска и правовую позицию бизнеса.",
    },
    {
      image: "/lf-1-6.png",
      title: "Меньше зависимости от ручного процесса",
      text: "Проверка становится воспроизводимой и управляемой: проще делегировать, масштабировать и поддерживать качество при росте нагрузки.",
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <RevealItem>
              <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                Что получает юридический департамент
              </p>
            </RevealItem>
          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {outcomes.slice(0, 3).map((item) => (
              <RevealItem key={item.title}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-[#E8E4DD]/40 bg-[var(--bg-surface)]">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>

          <div className="mt-24 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {outcomes.slice(3).map((item) => (
              <RevealItem key={item.title}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-[#E8E4DD]/40 bg-[var(--bg-surface)]">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function ScenariosSection() {
  const scenarios = [
    {
      title: "Поток входящих договоров",
      text: "Продажи, закупки и партнёрские команды отправляют документы в департамент, а Steloom помогает быстро выделять отклонения от корпоративных стандартов и выносить на ручную оценку только спорные места.",
    },
    {
      title: "Комплаенс и обновление политик",
      text: "При изменениях внутренних требований и регуляторики платформа помогает проверять, где в портфеле договоров уже есть отклонения и какие документы требуют внимания.",
    },
    {
      title: "Портфельный аудит договоров",
      text: "Если нужно быстро понять, какие обязательства, ограничения и риски распределены по массиву документов, Steloom структурирует данные и выводит проблемные зоны в одном потоке.",
    },
    {
      title: "Подготовка к руководству и контролю",
      text: "Структурированные findings с привязкой к первоисточнику дают понятную и доказуемую основу для обсуждения с CFO, procurement, internal audit и compliance.",
    },
  ];

  return (
    <section
      data-header-theme="dark"
      className="relative overflow-hidden border-t border-white/10 text-white"
    >
      <div
        className="absolute inset-0 bg-center bg-cover bg-no-repeat"
        style={{ backgroundImage: 'url("/in-1-4.png")' }}
      />
      <div className="absolute inset-0 bg-[#111111]/78" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-black/35 to-black/55" />

      <div
        className="relative mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-white/55 font-medium mb-4">
            Сценарии применения
          </p>

          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] tracking-[-0.02em] text-white mb-16">
            Где Steloom ускоряет работу департамента
          </h2>

          <div className="space-y-0">
            {scenarios.map((item) => (
              <RevealItem key={item.title}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-white/12">
                  <div className="md:col-span-4">
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-white italic">
                      {item.title}
                    </h3>
                  </div>
                  <div className="md:col-span-8">
                    <p className="text-[0.9375rem] leading-[1.7] text-white/72 font-light max-w-2xl">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CapabilitiesSection() {
  const capabilities = [
    {
      icon: Layers,
      title: "Структурирование массива",
      bullets: [
        "Автоматическая классификация договоров и связанных документов",
        "Единое представление массива для юридического департамента",
        "Снижение хаоса при росте количества запросов",
      ],
    },
    {
      icon: ShieldCheck,
      title: "Применение playbooks",
      bullets: [
        "Сопоставление документов с внутренними стандартами компании",
        "Выявление отклонений и нестандартных формулировок",
        "Единая логика проверки по всей команде",
      ],
    },
    {
      icon: FileSearch,
      title: "Прослеживаемость выводов",
      bullets: [
        "Каждый finding связан с конкретным абзацем источника",
        "Понятная база для согласования с бизнесом и контролем",
        "Доказуемость выводов для внутренних обсуждений",
      ],
    },
    {
      icon: TrendingUp,
      title: "Экономика департамента",
      bullets: [
        "Меньше ручной рутины - больше времени на стратегические вопросы",
        "Масштабирование без эквивалентного роста headcount",
        "Более предсказуемая и управляемая юридическая функция",
      ],
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
            Что автоматизирует Steloom
          </p>
          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] tracking-[-0.02em] text-[#1A1917] mb-16 max-w-none">
            Ключевые задачи департамента - в едином потоке анализа
          </h2>

          <div className="mt-16">
            {capabilities.map((item) => (
              <RevealItem key={item.title}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4 flex items-center gap-4">
                    <item.icon className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                    <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917] italic">
                      {item.title}
                    </h3>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-3">
                      {item.bullets.map((bullet) => (
                        <li key={bullet} className="flex items-start gap-3">
                          <CheckCircle2 className="mt-1 h-4 w-4 text-[var(--color-accent)] opacity-50" />
                          <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                            {bullet}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CTASection({ onDemo }: { onDemo: () => void }) {
  return (
    <section
      data-header-theme="light"
      className="bg-[#FAF8F5] py-28 lg:py-40 border-t border-[#E8E4DD]"
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
              Меньше ручной рутины - <br />
              <span className="italic font-light opacity-60 text-[var(--color-accent)]">
                больше времени на правовую позицию бизнеса
              </span>
            </h2>
            <div className="mt-7 space-y-5 text-[1.0625rem] leading-[1.75] text-[#78756F]">
              <p>
                Steloom помогает корпоративному юридическому департаменту быстрее
                отвечать внутренним заказчикам, удерживать единый стандарт проверки
                и не терять контроль при росте объёма документов.
              </p>
              <p>
                Загрузите массив документов - платформа применит ваши playbooks,
                выделит отклонения и сформирует прослеживаемые findings для
                принятия решения.
              </p>
            </div>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                Запросить демонстрацию <ArrowRight className="h-3.5 w-3.5" />
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
