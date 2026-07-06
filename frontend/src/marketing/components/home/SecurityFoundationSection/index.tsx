// src/marketing/components/home/SecurityFoundationSection/index.tsx
import React from "react";
import { Link } from "react-router-dom";
import { 
  ArrowRight, 
  ShieldCheck, 
  FileKey, 
  Server, 
  Eye, 
  Lock, 
  Network 
} from "lucide-react";
import { landingContent } from "../../../content/landingContent";

// Расширенная сетка из 6 пунктов безопасности
const CERTIFICATES = [
  {
    title: "ISO 27001 & SOC 2",
    desc: "Steloom полностью сертифицирован по стандарту ISO 27001 и соответствует требованиям SOC 2 Type II для управления данными.",
    icon: <ShieldCheck strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "GDPR & 152-ФЗ",
    desc: "Полное соответствие строжайшим стандартам конфиденциальности данных для безопасной работы с резидентами РФ и ЕС.",
    icon: <FileKey strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "Zero Data Training",
    desc: "AI-модели никогда не дообучаются на ваших данных. Вся обработка происходит в read-only режиме для моделей.",
    icon: <Lock strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "Изоляция контуров",
    desc: "Каждая сделка живёт в собственном физически изолированном контуре. Доступ строго контролируется RBAC-политиками.",
    icon: <Network strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "Гибридная архитектура LLM",
    desc: "Платформа настроена как на работу с локальными LLM в закрытом контуре, так и на облачные модели через строгий PII sanitization gateway.",
    icon: <Server strokeWidth={1.5} className="h-6 w-6" />
  },
  {
    title: "100% Аудит и прозрачность",
    desc: "Полный аудит исходных данных для работы LLM и сделанных ею выводов. Абсолютная прозрачность для пользователя без «чёрных ящиков».",
    icon: <Eye strokeWidth={1.5} className="h-6 w-6" />
  }
];

const SecurityFoundationSection: React.FC = () => {
  const content = landingContent.security;

  return (
    <section
      id="security"
      className="relative flex items-center bg-[#FAF8F5] py-20 lg:py-28 scroll-mt-0 border-y border-[#E8E4DD]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-start gap-16 lg:grid-cols-12 lg:gap-20">
          
          {/* ── Левая колонка: Сетка сертификатов (6 карточек) ── */}
          <div className="lg:col-span-7">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-10">
              {CERTIFICATES.map((cert, i) => (
                <div 
                  key={i} 
                  className="flex flex-col border-t border-[#E8E4DD] pt-6"
                >
                  <h3 className="text-[0.9375rem] font-medium text-[#1A1917] tracking-tight mb-3">
                    {cert.title}
                  </h3>
                  <p className="text-[0.9375rem] leading-[1.6] text-[#78756F] mb-8 flex-grow pr-4">
                    {cert.desc}
                  </p>
                  
                  {/* Иконка-бейджик */}
                  <div className="mt-auto inline-flex h-14 w-14 items-center justify-center rounded-full border border-[#E8E4DD] text-[#A8A29E] bg-white">
                    {cert.icon}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Правая колонка: Текст ── */}
          <div className="flex flex-col justify-center lg:col-span-5 lg:sticky lg:top-32">
            <span className="eyebrow">{content.eyebrow}</span>

            <h2 className="section-title !mt-2 whitespace-pre-line text-[#1A1917]">
              {content.title}
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              <p className="text-[1.0625rem] leading-[1.7] text-[#78756F]">
                {content.description}
              </p>
              
              <ul className="mt-2 space-y-4">
                {content.badges.map((badge, idx) => (
                  <li key={idx} className="flex items-start gap-4 text-[#78756F]">
                    <span className="mt-2.5 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[#C86B52]" />
                    <span className="text-[1.0625rem] leading-[1.7]">{badge}</span>
                  </li>
                ))}
              </ul>
            </div>

            <Link to="/security" className="cta-link mt-12">
              {content.linkLabel}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
};

export default SecurityFoundationSection;


