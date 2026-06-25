// src/components/marketing/marketingTheme.ts

export const marketingTheme = {
  container: {
    // max-w-[1280px] везде — бриф
    hero:    "mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-10 xl:px-12",
    section: "mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-10 xl:px-12",
    prose:   "mx-auto w-full max-w-[800px]  px-4 sm:px-6 lg:px-8",
  },

  section: {
    base:    "py-20 lg:py-28",
    compact: "py-14 lg:py-20",
    relaxed: "py-24 lg:py-32",
  },

  surface: {
    subtle:   "bg-white border border-[#E5E2DA]",
    soft:     "bg-[#F8F7F4] border border-[#E5E2DA]",
    strong:   "bg-[#F1EFEA] border border-[#E5E2DA]",
    // "elevated" — без тени, только граница; elevation через surface-shift, не shadow
    elevated: "bg-white border border-[#E5E2DA]",
    // тёмные карточки для Security / Architecture / CTA секций
    dark:     "bg-[#111827] border border-white/8",
  },

  radius: {
    sm:   "rounded-xl",        // 12px — мелкие элементы: badges, chips
    md:   "rounded-2xl",       // 16px — инпуты, мелкие карточки
    lg:   "rounded-[24px]",    // 24px — основной радиус карточек (бриф)
    xl:   "rounded-[28px]",    // 28px — обёртки секций, крупные блоки
    hero: "rounded-[32px]",    // 32px — зарезервирован, использовать редко
    pill: "rounded-full",
  },

  text: {
    eyebrow:    "text-[11px] uppercase tracking-[0.22em] font-medium text-stone-500",
    // Заголовки секций — font-serif, без font-semibold
    title:      "font-serif text-4xl tracking-[-0.04em] leading-[1.05] text-stone-950 lg:text-5xl",
    subtitle:   "mt-4 text-base leading-8 text-stone-600 lg:text-[1.05rem]",
    body:       "text-sm leading-7 text-stone-600",
    bodyLg:     "text-base leading-8 text-stone-600",
    // cardTitle — font-medium, не font-semibold (бриф: избегать 700+)
    cardTitle:  "text-base font-medium tracking-[-0.01em] text-stone-950",
    cardTitleLg: "font-serif text-2xl tracking-[-0.03em] text-stone-950",
    // Тёмный фон
    eyebrowDark: "text-[11px] uppercase tracking-[0.22em] font-medium text-white/35",
    bodyDark:    "text-sm leading-7 text-white/50",
    titleDark:   "font-serif text-4xl tracking-[-0.04em] leading-[1.05] text-white lg:text-5xl",
  },

  grid: {
    two:   "grid gap-4 md:grid-cols-2",
    three: "grid gap-4 md:grid-cols-3",
    four:  "grid gap-3 sm:grid-cols-2 xl:grid-cols-4",
  },

  button: {
    // Primary — зелёный, только для ссылок и tertiary CTA (не для главных CTA)
    primary:
      "inline-flex items-center justify-center rounded-full bg-[#2F5A4A] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#3F735F]",
    // Secondary — белая с бордером
    secondary:
      "inline-flex items-center justify-center rounded-full border border-[#E5E2DA] bg-white px-5 py-2.5 text-sm font-medium text-stone-700 transition-colors hover:border-stone-300 hover:text-stone-950",
    // Tertiary — текстовая ссылка с зелёным акцентом
    tertiary:
      "inline-flex items-center gap-1.5 text-sm font-medium text-[#2F5A4A] transition-colors hover:text-[#3F735F]",
    // Dark — для CTA-секций на #111827 фоне (главный CTA лендинга)
    dark:
      "inline-flex items-center justify-center rounded-full bg-white px-6 py-3 text-sm font-medium text-stone-950 transition-colors hover:bg-stone-100",
    // Nav CTA — тёмная pill кнопка в хедере
    nav:
      "inline-flex items-center gap-2 rounded-full bg-[#111827] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1f2937]",
  },

  badge: {
    base:
      "inline-flex items-center rounded-full border border-[#E5E2DA] bg-white px-3 py-1.5 text-[11px] font-medium text-stone-500",
    success:
      "inline-flex items-center rounded-full border border-[#2F5A4A]/20 bg-[#2F5A4A]/8 px-3 py-1.5 text-[11px] font-medium text-[#2F5A4A]",
    dark:
      "inline-flex items-center rounded-full border border-white/12 bg-white/8 px-3 py-1.5 text-[11px] font-medium text-white/60",
  },

  input: {
    base:
      "w-full rounded-[16px] border border-[#E5E2DA] bg-white px-4 py-3 text-sm text-stone-950 outline-none transition-colors placeholder:text-stone-400 focus:border-stone-300",
    label:
      "mb-2 block text-[11px] uppercase tracking-[0.14em] font-medium text-stone-400",
  },

  divider: "border-[#E5E2DA]",
} as const;

