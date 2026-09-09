// src/marketing/components/home/ContactModal.tsx
import React from "react";
import { ArrowRight, Mail, X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface ContactModalProps {
  open: boolean;
  email: string;
  message: string;
  onEmailChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

const ContactModal: React.FC<ContactModalProps> = ({
  open,
  email,
  message,
  onEmailChange,
  onMessageChange,
  onClose,
  onSubmit,
}) => {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // Получаем массив шагов из i18n
  const stepsRaw = t("home.contactModal.steps", { returnObjects: true });
  const demoSteps = Array.isArray(stepsRaw) ? stepsRaw : [];

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[#1A1917]/60 px-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="relative w-full max-w-5xl overflow-hidden rounded-2xl border border-[var(--border-color)] bg-[var(--bg-base)]">
        {/* RTL FIX: right-4 заменен на end-4 */}
        <button
          onClick={onClose}
          aria-label={t("home.contactModal.closeAria")}
          className="absolute end-4 top-4 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-color)] bg-white text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="grid lg:grid-cols-[0.95fr_1.05fr]">
          {/* Левая панель */}
          {/* RTL FIX: lg:border-r заменен на lg:border-e */}
          <div className="border-b border-[var(--border-color)] bg-[var(--bg-surface)] p-8 lg:border-b-0 lg:border-e lg:p-10">
            <p className="text-meta font-medium uppercase text-[var(--text-muted)]">
              {t("home.contactModal.eyebrow")}
            </p>

            <h3 className="mt-5 max-w-md text-h2 text-[var(--text-primary)] whitespace-pre-line">
              {t("home.contactModal.title")}
            </h3>

            <p className="mt-4 max-w-md text-sm leading-7 text-[var(--text-secondary)] lg:text-base">
              {t("home.contactModal.description")}
            </p>

            <div className="mt-7 rounded-xl border border-[var(--border-color)] bg-white p-5">
              <p className="text-meta font-medium uppercase text-[var(--text-muted)]">
                {t("home.contactModal.stepsTitle")}
              </p>

              <div className="mt-4 space-y-2.5">
                {demoSteps.map((item, index) => (
                  <div
                    key={index}
                    className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-base)] px-4 py-3.5"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#1A1917] text-meta font-medium text-white">
                        0{index + 1}
                      </div>
                      <p className="text-sm leading-6 text-[var(--text-secondary)]">{item}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Правая панель — форма */}
          <div className="p-8 lg:p-10">
            <div className="max-w-xl">
              <div className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <Mail className="h-4 w-4" />
                {t("home.contactModal.emailInfo")}
              </div>

              <form onSubmit={onSubmit} className="mt-7 space-y-4">
                <div>
                  <label className="mb-2 block text-meta font-medium uppercase text-[var(--text-muted)]">
                    {t("home.contactModal.emailLabel")}
                  </label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => onEmailChange(e.target.value)}
                    placeholder={t("home.contactModal.emailPlaceholder")}
                    className="input-base"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-meta font-medium uppercase text-[var(--text-muted)]">
                    {t("home.contactModal.scenarioLabel")}
                  </label>
                  <textarea
                    required
                    rows={6}
                    value={message}
                    onChange={(e) => onMessageChange(e.target.value)}
                    placeholder={t("home.contactModal.scenarioPlaceholder")}
                    className="input-base resize-none"
                  />
                </div>

                <div className="rounded-lg border border-[var(--accent-primary)]/20 bg-[#F5EBE7] px-4 py-3 text-xs leading-relaxed text-[var(--accent-primary)]">
                  {t("home.contactModal.securityNote")}
                </div>

                <div className="flex flex-col gap-2.5 pt-1 sm:flex-row sm:items-center">
                  <button type="submit" className="cta-primary">
                    {t("home.contactModal.submit")}
                    {/* RTL FIX: разворот стрелки для арабского языка */}
                    <ArrowRight 
                      className="h-4 w-4" 
                      style={{ 
                        transform: isRTL ? "rotate(180deg)" : "none",
                        transition: "transform 0.2s ease"
                      }} 
                    />
                  </button>

                  <button
                    type="button"
                    onClick={onClose}
                    className="inline-flex items-center justify-center rounded-full border border-[var(--border-color)] bg-white px-5 py-3 text-sm text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                  >
                    {t("home.contactModal.cancel")}
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