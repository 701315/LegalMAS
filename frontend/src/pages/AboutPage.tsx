import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Shield, Users, Scale, FileText, Lock } from "lucide-react";

import photoVladimir from "../components/marketing/photo/vladimir.jpg";
import photoAnna from "../components/marketing/photo/anna.jpg";
import photoDmitry from "../components/marketing/photo/dmitry.jpg";
import photoIrina from "../components/marketing/photo/irina.jpg";
import photoPavel from "../components/marketing/photo/pavel.jpg";
import photoElena from "../components/marketing/photo/elena.jpg";
import photoMaxim from "../components/marketing/photo/maxim.jpg";
import photoOlga from "../components/marketing/photo/olga.jpg";
import photoSergey from "../components/marketing/photo/sergey.jpg";

const AboutPage: React.FC = () => {
  const cards = [
    {
      icon: <Scale className="h-5 w-5 text-amber-200" />,
      title: "Юридическая логика",
      text:
        "LegalMAS проектируется вокруг playbooks, review-процессов и реальных требований due diligence, а не вокруг одного промпта.",
    },
    {
      icon: <FileText className="h-5 w-5 text-amber-200" />,
      title: "Document pipeline",
      text:
        "Мы строим управляемый контур обработки документов: загрузка, разбор, извлечение, проверка и сборка source-linked выводов.",
    },
    {
      icon: <Lock className="h-5 w-5 text-amber-200" />,
      title: "Privacy-first подход",
      text:
        "Для чувствительных документов важны локальный контур, контролируемое подключение моделей и прозрачность обработки данных.",
    },
  ];

  const team = [
    {
      name: "Vladimir Gorelov",
      role: "Founder & Product / Engineering Lead",
      description:
        "Отвечает за продуктовую логику LegalMAS, архитектуру document pipeline и интеграцию AI в юридические сценарии.",
      linkedin: "https://www.linkedin.com/in/example-vladimir",
      photo: photoVladimir,
    },
    {
      name: "Anna Kuznetsova",
      role: "Head of Legal Workflows",
      description:
        "Конструирует юридические playbooks для M&A, VC и корпоративных сценариев, чтобы выводы LegalMAS были пригодны для review.",
      linkedin: "https://www.linkedin.com/in/example-anna",
      photo: photoAnna,
    },
    {
      name: "Dmitry Morozov",
      role: "Lead ML / NLP Engineer",
      description:
        "Разрабатывает модели для извлечения сущностей, связки выводов с источниками и анализа больших массивов договоров.",
      linkedin: "https://www.linkedin.com/in/example-dmitry",
      photo: photoDmitry,
    },
    {
      name: "Irina Sokolova",
      role: "Document Processing Engineer",
      description:
        "Отвечает за стабильный пайплайн загрузки, OCR, нормализации и разметки документов в Data Room.",
      linkedin: "https://www.linkedin.com/in/example-irina",
      photo: photoIrina,
    },
    {
      name: "Pavel Kravchenko",
      role: "Security & Infrastructure",
      description:
        "Проектирует privacy-first архитектуру, модели доступа и контролируемое подключение облачных LLM.",
      linkedin: "https://www.linkedin.com/in/example-pavel",
      photo: photoPavel,
    },
    {
      name: "Elena Novikova",
      role: "Product & UX Design",
      description:
        "Делает интерфейс LegalMAS пригодным для длительной работы юристов и аналитиков, а не только демо.",
      linkedin: "https://www.linkedin.com/in/example-elena",
      photo: photoElena,
    },
    {
      name: "Maxim Sergeev",
      role: "Customer Success",
      description:
        "Помогает командам интегрировать LegalMAS в их процессы, запускать пилоты и масштабировать сценарии.",
      linkedin: "https://www.linkedin.com/in/example-maxim",
      photo: photoMaxim,
    },
    {
      name: "Olga Petrova",
      role: "Data Analyst",
      description:
        "Собирает и анализирует метрики использования, помогает улучшать качество проверок и выводов.",
      linkedin: "https://www.linkedin.com/in/example-olga",
      photo: photoOlga,
    },
    {
      name: "Sergey Ivanov",
      role: "Backend Engineer",
      description:
        "Разрабатывает backend LegalMAS, API для document pipeline и интеграцию с внешними системами.",
      linkedin: "https://www.linkedin.com/in/example-sergey",
      photo: photoSergey,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl supports-[backdrop-filter]:bg-slate-950/70">
        <div className="mx-auto flex h-16 w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:h-[72px] lg:px-10 xl:px-12">
          <Link to="/" className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white text-slate-950 shadow-lg shadow-black/20">
              <Shield className="h-5 w-5" />
            </div>

            <div className="min-w-0">
              <div className="truncate text-sm font-semibold tracking-tight text-white">
                LegalMAS
              </div>
              <div className="hidden truncate text-[11px] text-slate-500 sm:block">
                Enterprise legal AI infrastructure
              </div>
            </div>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.08]"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            На главную
          </Link>
        </div>
      </header>

      <main className="relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(71,85,105,0.20),transparent_28%),radial-gradient(circle_at_78%_18%,rgba(245,158,11,0.10),transparent_30%),linear-gradient(180deg,#020617_0%,#020617_100%)]" />

        <div className="relative mx-auto w-full max-w-[1480px] px-4 pb-20 pt-16 sm:px-6 lg:px-10 lg:pt-24 xl:px-12">
          <div className="max-w-4xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-slate-400">
              <Users className="h-3.5 w-3.5 text-amber-300" />
              О проекте
            </div>

            <h1 className="mt-6 max-w-5xl text-5xl font-semibold tracking-tight text-white sm:text-6xl lg:text-[5.2rem] lg:leading-[0.96]">
              Команда, которая строит LegalMAS
              <span className="block text-slate-400">
                как enterprise product, а не как AI-обёртку
              </span>
            </h1>

            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-slate-300 lg:text-xl">
              LegalMAS создаётся как инфраструктурный продукт для юридического анализа
              документов, Data Room и due diligence-сценариев, где важны не только скорость,
              но и проверяемость выводов, управляемость пайплайна и аккуратная работа с
              чувствительными данными.
            </p>

            <p className="mt-4 max-w-3xl text-base leading-relaxed text-slate-400 lg:text-lg">
              Мы соединяем product engineering, document processing, legal workflows
              и privacy-first архитектуру, чтобы команды могли получать результат,
              пригодный для review, внутреннего согласования и реальной сделки.
            </p>
          </div>

          <div className="mt-12 grid gap-4 lg:grid-cols-3">
            {cards.map((card) => (
              <div
                key={card.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-amber-400/50 bg-slate-950/90 shadow-[0_10px_30px_rgba(0,0,0,0.45)]">
                  {card.icon}
                </div>

                <h2 className="mt-5 text-xl font-semibold tracking-tight text-white">
                  {card.title}
                </h2>

                <p className="mt-3 text-sm leading-relaxed text-slate-300 lg:text-[15px]">
                  {card.text}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-12 rounded-[32px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur-sm lg:p-8">
            <h2 className="text-2xl font-semibold tracking-tight text-white">
              Что для нас важно
            </h2>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <h3 className="text-lg font-semibold text-white">
                  Юридическая пригодность результата
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Каждый вывод должен быть привязан к источнику, понятен для review
                  и пригоден для обсуждения внутри команды, с клиентом или в сделке.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <h3 className="text-lg font-semibold text-white">
                  Контроль над архитектурой
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Локальный контур, controlled cloud usage и чувствительные документы
                  должны сосуществовать без потери управляемости и безопасности.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <h3 className="text-lg font-semibold text-white">
                  Инженерная зрелость
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Продукт должен выглядеть и работать как серьёзная система:
                  с понятной логикой, прозрачным пайплайном и устойчивым UX.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <h3 className="text-lg font-semibold text-white">
                  Фокус на реальных сценариях
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Мы строим платформу под Data Room, due diligence, corporate legal review
                  и другие сценарии, где ошибка в выводе стоит дорого.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-14">
            <h2 className="text-2xl font-semibold tracking-tight text-white">
              Команда проекта
            </h2>

            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">
              Живые люди, которые собирают LegalMAS как инструмент для реальной работы,
              а не показательную демонстрацию.
            </p>

            <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {team.map((member) => (
                <div
                  key={member.name}
                  className="group overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] shadow-2xl shadow-black/30 backdrop-blur-sm"
                >
                  <div className="relative h-52 w-full overflow-hidden">
                    <img
                      src={member.photo}
                      alt={member.name}
                      className="h-full w-full object-cover transition-opacity duration-300 group-hover:opacity-0"
                      loading="lazy"
                    />

                    <div className="absolute inset-0 flex flex-col justify-between bg-slate-950/90 px-4 py-4 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
                      <div className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-300">
                        Роль в LegalMAS
                      </div>

                      <div>
                        <p className="text-sm leading-relaxed text-slate-100">
                          {member.description}
                        </p>

                        <a
                          href={member.linkedin}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-3 inline-flex items-center text-xs font-medium text-sky-300 underline-offset-2 hover:underline"
                        >
                          Профиль в LinkedIn
                        </a>
                      </div>
                    </div>
                  </div>

                  <div className="px-4 py-4">
                    <p className="truncate text-sm font-semibold text-white sm:text-base">
                      {member.name}
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-slate-400 sm:text-sm">
                      {member.role}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default AboutPage;



