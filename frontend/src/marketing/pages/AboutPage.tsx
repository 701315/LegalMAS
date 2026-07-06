// src/marketing/pages/AboutPage.tsx
import React from "react";
import { Scale, FileText, Lock } from "lucide-react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";

import photoVladimir from "../components/assets/photos/vladimir.jpg";
import photoAnna from "../components/assets/photos/anna.jpg";
import photoDmitry from "../components/assets/photos/dmitry.jpg";
import photoIrina from "../components/assets/photos/irina.jpg";
import photoPavel from "../components/assets/photos/pavel.jpg";
import photoElena from "../components/assets/photos/elena.jpg";
import photoMaxim from "../components/assets/photos/maxim.jpg";
import photoOlga from "../components/assets/photos/olga.jpg";
import photoSergey from "../components/assets/photos/sergey.jpg";

const AboutPage: React.FC = () => {
  const cards = [
    {
      icon: <Scale className="h-5 w-5 text-[#78756F]" />,
      title: "Юридическая логика",
      text: "Steloom проектируется вокруг playbooks, review-процессов и реальных требований due diligence, а не вокруг одного промпта.",
    },
    {
      icon: <FileText className="h-5 w-5 text-[#78756F]" />,
      title: "Document pipeline",
      text: "Мы строим управляемый контур обработки документов: загрузка, разбор, извлечение, проверка и сборка source-linked выводов.",
    },
    {
      icon: <Lock className="h-5 w-5 text-[#78756F]" />,
      title: "Privacy-first подход",
      text: "Для чувствительных документов важны локальный контур, контролируемое подключение моделей и прозрачность обработки данных.",
    },
  ];

  const team = [
    {
      name: "Vladimir Gorelov",
      role: "Основатель и руководитель продукта / разработки",
      description: "Отвечает за продуктовую логику Steloom, архитектуру document pipeline и интеграцию AI в юридические сценарии.",
      linkedin: "https://www.linkedin.com/in/example-vladimir",
      photo: photoVladimir,
    },
    {
      name: "Anna Kuznetsova",
      role: "Руководитель legal workflows",
      description: "Конструирует юридические playbooks для M&A, VC и корпоративных сценариев, чтобы выводы Steloom были пригодны для review.",
      linkedin: "https://www.linkedin.com/in/example-anna",
      photo: photoAnna,
    },
    {
      name: "Dmitry Morozov",
      role: "Ведущий ML / NLP инженер",
      description: "Разрабатывает модели для извлечения сущностей, связки выводов с источниками и анализа больших массивов договоров.",
      linkedin: "https://www.linkedin.com/in/example-dmitry",
      photo: photoDmitry,
    },
    {
      name: "Irina Sokolova",
      role: "Инженер document processing",
      description: "Отвечает за стабильный пайплайн загрузки, OCR, нормализации и разметки документов в Data Room.",
      linkedin: "https://www.linkedin.com/in/example-irina",
      photo: photoIrina,
    },
    {
      name: "Pavel Kravchenko",
      role: "Безопасность и инфраструктура",
      description: "Проектирует privacy-first архитектуру, модели доступа и контролируемое подключение облачных LLM.",
      linkedin: "https://www.linkedin.com/in/example-pavel",
      photo: photoPavel,
    },
    {
      name: "Elena Novikova",
      role: "Продукт и UX-дизайн",
      description: "Делает интерфейс Steloom пригодным для длительной работы юристов и аналитиков, а не только демо.",
      linkedin: "https://www.linkedin.com/in/example-elena",
      photo: photoElena,
    },
    {
      name: "Maxim Sergeev",
      role: "Customer Success",
      description: "Помогает командам интегрировать Steloom в их процессы, запускать пилоты и масштабировать сценарии.",
      linkedin: "https://www.linkedin.com/in/example-maxim",
      photo: photoMaxim,
    },
    {
      name: "Olga Petrova",
      role: "Data Analyst",
      description: "Собирает и анализирует метрики использования, помогает улучшать качество проверок и выводов.",
      linkedin: "https://www.linkedin.com/in/example-olga",
      photo: photoOlga,
    },
    {
      name: "Sergey Ivanov",
      role: "Backend инженер",
      description: "Разрабатывает backend Steloom, API для document pipeline и интеграцию с внешними системами.",
      linkedin: "https://www.linkedin.com/in/example-sergey",
      photo: photoSergey,
    },
  ];

  return (
    <MarketingEditorialShell
      title="Команда, которая строит Steloom как enterprise-продукт"
      description="Steloom создаётся как инфраструктурный продукт для юридического анализа документов, Data Room и due diligence-сценариев, где важны проверяемость выводов, управляемость пайплайна и аккуратная работа с чувствительными данными."
    >
      <div className="grid gap-4 lg:grid-cols-3">
        {cards.map((card) => (
          <div
            key={card.title}
            className="rounded-2xl border border-[#E8E4DD] bg-white p-6"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#E8E4DD] bg-[#F3F0EB]">
              {card.icon}
            </div>
            <h2 className="mt-5 text-xl font-semibold tracking-tight text-[#1A1917]">
              {card.title}
            </h2>
            <p className="mt-3 text-sm leading-7 text-[#78756F]">
              {card.text}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-12 rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-6 lg:p-8">
        <h2 className="font-serif text-3xl tracking-[-0.03em] text-[#1A1917] lg:text-4xl">
          Что для нас важно
        </h2>

        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          {[
            [
              "Юридическая пригодность результата",
              "Каждый вывод должен быть привязан к источнику, понятен для review и пригоден для обсуждения внутри команды, с клиентом или в сделке.",
            ],
            [
              "Контроль над архитектурой",
              "Локальный контур, controlled cloud usage и чувствительные документы должны сосуществовать без потери управляемости и безопасности.",
            ],
            [
              "Инженерная зрелость",
              "Мы строим не демо‑слой поверх LLM, а product-grade систему с ingestion, pipeline orchestration и audit-ready логикой.",
            ],
            [
              "Практическое внедрение",
              "Сценарии должны быть применимы в реальном документном потоке, а не только в презентации или пилотном примере.",
            ],
          ].map(([title, text]) => (
            <div
              key={title}
              className="rounded-xl border border-[#E8E4DD] bg-white p-5"
            >
              <h3 className="text-lg font-semibold text-[#1A1917]">{title}</h3>
              <p className="mt-2 text-sm leading-7 text-[#78756F]">{text}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-12">
        <h2 className="font-serif text-3xl tracking-[-0.03em] text-[#1A1917] lg:text-4xl">
          Команда
        </h2>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {team.map((member) => (
            <article
              key={member.name}
              className="overflow-hidden rounded-2xl border border-[#E8E4DD] bg-white"
            >
              <div className="aspect-[4/3] overflow-hidden bg-[#F3F0EB]">
                <img
                  src={member.photo}
                  alt={member.name}
                  className="h-full w-full object-cover"
                />
              </div>
              <div className="p-5">
                <h3 className="text-xl font-semibold text-[#1A1917]">
                  {member.name}
                </h3>
                <p className="mt-1 text-sm font-medium text-[#78756F]">
                  {member.role}
                </p>
                <p className="mt-3 text-sm leading-7 text-[#78756F]">
                  {member.description}
                </p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </MarketingEditorialShell>
  );
};

export default AboutPage;


