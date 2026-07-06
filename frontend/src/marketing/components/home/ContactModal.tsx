// src/marketing/components/home/ContactModal.tsx
import React from "react";
import { ArrowRight, Mail, X } from "lucide-react";
import { landingContent } from "../../content/landingContent";

interface ContactModalProps {
  open: boolean;
  email: string;
  message: string;
  onEmailChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

const DEMO_STEPS = [
  "Обсудим сценарий: M&A, DD, contract review или внутренний аудит.",
  "Покажем document flow: загрузка, checks, source-linked results и export.",
  "При необходимости разберём security model, local-first режим и архитектуру.",
] as const;

const ContactModal: React.FC<ContactModalProps> = ({
  open,
  email,
  message,
  onEmailChange,
  onMessageChange,
  onClose,
  onSubmit,
}) => {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[#1A1917]/60 px-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="relative w-full max-w-5xl overflow-hidden rounded-2xl border border-[#E8E4DD] bg-[#FAF8F5]">
        <button
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute right-4 top-4 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#E8E4DD] bg-white text-[#78756F] transition-colors hover:text-[#1A1917]"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="grid lg:grid-cols-[0.95fr_1.05fr]">
          {/* Левая панель */}
          <div className="border-b border-[#E8E4DD] bg-[#F3F0EB] p-8 lg:border-b-0 lg:border-r lg:p-10">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#A8A29E]">
              Запрос enterprise-демо
            </p>

            <h3 className="mt-5 max-w-md font-serif text-3xl leading-tight tracking-[-0.03em] text-[#1A1917]">
              {landingContent.finalCta.title}
            </h3>

            <p className="mt-4 max-w-md text-sm leading-7 text-[#78756F] lg:text-base">
              Расскажи о типах документов, playbooks и текущем процессе review —
              так демо можно сделать предметным, а не общим.
            </p>

            <div className="mt-7 rounded-xl border border-[#E8E4DD] bg-white p-5">
              <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#A8A29E]">
                Как пройдёт демо
              </p>

              <div className="mt-4 space-y-2.5">
                {DEMO_STEPS.map((item, index) => (
                  <div
                    key={item}
                    className="rounded-lg border border-[#E8E4DD] bg-[#FAF8F5] px-4 py-3.5"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#1A1917] text-[11px] font-medium text-white">
                        0{index + 1}
                      </div>
                      <p className="text-sm leading-6 text-[#78756F]">{item}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Правая панель — форма */}
          <div className="p-8 lg:p-10">
            <div className="max-w-xl">
              <div className="inline-flex items-center gap-2 text-sm text-[#78756F]">
                <Mail className="h-4 w-4" />
                Ответ придёт на указанный рабочий email
              </div>

              <form onSubmit={onSubmit} className="mt-7 space-y-4">
                <div>
                  <label className="mb-2 block text-[11px] font-medium uppercase tracking-[0.14em] text-[#A8A29E]">
                    Рабочий email
                  </label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    placeholder="name@company.com"
                    className="input-base"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-[11px] font-medium uppercase tracking-[0.14em] text-[#A8A29E]">
                    Сценарий, типы документов, объём
                  </label>
                  <textarea
                    required
                    rows={6}
                    value={message}
                    onChange={(e) => onMessageChange(e.target.value)}
                    placeholder="Например: DD для пакета SPA / SHA / NDA, 300+ документов, нужен source-linked результат и экспорт в Excel."
                    className="input-base resize-none"
                  />
                </div>

                <div className="rounded-lg border border-[#C86B52]/20 bg-[#F5EBE7] px-4 py-3 text-xs leading-relaxed text-[#C86B52]">
                  Если у тебя чувствительный сценарий, можно сразу указать требования
                  к local-first обработке, ограничения по cloud LLM и ожидания по security review.
                </div>

                <div className="flex flex-col gap-2.5 pt-1 sm:flex-row sm:items-center">
                  <button
                    type="submit"
                    className="cta-primary"
                  >
                    Отправить запрос
                    <ArrowRight className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={onClose}
                    className="inline-flex items-center justify-center rounded-full border border-[#E8E4DD] bg-white px-5 py-3 text-sm text-[#78756F] transition-colors hover:text-[#1A1917]"
                  >
                    Закрыть
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContactModal;


