// src/marketing/components/home/KnowledgeGrowthSection/contract-texts.ts

import type { Fragment, FragmentBucket } from "./types";

/**
 * Фрагменты юридического текста на русском.
 * Разделены по длине, чтобы движок мог подобрать
 * подходящий фрагмент под ширину сегмента силуэта.
 *
 * isKey: true — клоз, который будет подсвечен в фазе Meaning.
 */

const MICRO: Fragment[] = [
  { text: "Сторона", type: "reference", isKey: false },
  { text: "Стороны", type: "reference", isKey: false },
  { text: "Договор", type: "reference", isKey: false },
  { text: "Раздел 7.4", type: "reference", isKey: false },
  { text: "пункт 3.2", type: "reference", isKey: false },
  { text: "статья 12", type: "reference", isKey: false },
  { text: "в порядке", type: "reference", isKey: false },
  { text: "в силу", type: "reference", isKey: false },
  { text: "далее", type: "reference", isKey: false },
  { text: "именуемый", type: "reference", isKey: false },
  { text: "Закрытие", type: "concept", isKey: true },
  { text: "Гарантии", type: "warranty", isKey: true },
  { text: "Заверения", type: "warranty", isKey: true },
  { text: "Расторжение", type: "termination", isKey: true },
  { text: "MAC", type: "mac", isKey: true },
  { text: "due diligence", type: "concept", isKey: true },
  { text: "good faith", type: "concept", isKey: true },
  { text: "force majeure", type: "concept", isKey: true },
  { text: "indemnity", type: "indemnity", isKey: true },
];

const SHORT: Fragment[] = [
  { text: "Существенное неблагоприятное изменение", type: "mac", isKey: true },
  { text: "Ограничение ответственности", type: "liability", isKey: true },
  { text: "Смена контроля", type: "control", isKey: true },
  { text: "Конфиденциальная информация", type: "confidentiality", isKey: true },
  { text: "Обязательства по возмещению", type: "indemnity", isKey: true },
  { text: "Заверения и гарантии", type: "warranty", isKey: true },
  { text: "Расторжение по существенному нарушению", type: "termination", isKey: true },
  { text: "Применимое право", type: "jurisdiction", isKey: true },
  { text: "Material Adverse Change", type: "mac", isKey: true },
  { text: "Limitation of Liability", type: "liability", isKey: true },
  { text: "Change of Control", type: "control", isKey: true },
  { text: "Confidential Information", type: "confidentiality", isKey: true },
  { text: "Governing Law", type: "jurisdiction", isKey: true },
  { text: "Termination for Cause", type: "termination", isKey: true },
  { text: "Дата Закрытия Сделки", type: "concept", isKey: false },
  { text: "Срок действия Договора", type: "termination", isKey: false },
  { text: "Уведомление в письменной форме", type: "reference", isKey: false },
  { text: "Существенные условия", type: "concept", isKey: false },
  { text: "Заверения Продавца", type: "warranty", isKey: false },
  { text: "Обязательства Покупателя", type: "general", isKey: false },
  { text: "Гарантийный депозит", type: "general", isKey: false },
  { text: "Право преимущественной покупки", type: "control", isKey: false },
];

const MEDIUM: Fragment[] = [
  { text: "Продавец заверяет и гарантирует, что...", type: "warranty", isKey: false },
  { text: "Если иное не предусмотрено настоящим Договором...", type: "general", isKey: false },
  { text: "Настоящий Договор прекращается при наступлении...", type: "termination", isKey: false },
  { text: "Покупатель направляет письменное уведомление...", type: "reference", isKey: false },
  { text: "Стороны признают и соглашаются, что...", type: "general", isKey: false },
  { text: "Компания обязуется возместить убытки...", type: "indemnity", isKey: false },
  { text: "В соответствии с разделом 7.4 настоящего Договора...", type: "reference", isKey: false },
  { text: "Никакие изменения не имеют силы, если...", type: "general", isKey: false },
  { text: "Каждый Акционер настоящим безотзывно отказывается...", type: "warranty", isKey: false },
  { text: "Дата Закрытия определяется в соответствии с...", type: "concept", isKey: false },
  { text: "Настоящий Договор представляет собой полное соглашение...", type: "general", isKey: false },
  { text: "По письменному уведомлению другой Стороне...", type: "reference", isKey: false },
  { text: "В соответствии с применимым правом и регулированием...", type: "jurisdiction", isKey: false },
  { text: "Покупатель возмещает, защищает и освобождает...", type: "indemnity", isKey: false },
  { text: "Ни одна из Сторон не несёт ответственности за...", type: "liability", isKey: false },
  { text: "Все заверения и гарантии сохраняют силу...", type: "warranty", isKey: false },
  { text: "Обязательства, предусмотренные разделом 3...", type: "general", isKey: false },
  { text: "Несмотря на вышеизложенные положения...", type: "general", isKey: false },
  { text: "Настоящий Договор регулируется правом...", type: "jurisdiction", isKey: false },
  { text: "Срок действия настоящего Договора начинается с...", type: "termination", isKey: false },
  { text: "Каждая Сторона заверяет и гарантирует, что...", type: "warranty", isKey: false },
  { text: "В случае существенного нарушения настоящего...", type: "termination", isKey: false },
  { text: "Стороны прилагают коммерчески разумные усилия...", type: "general", isKey: false },
  { text: "Настоящий Раздел сохраняет силу после прекращения...", type: "termination", isKey: false },
  { text: "В соответствии с условиями, изложенными в...", type: "reference", isKey: false },
  { text: "Обязательства по возмещению Продавца ограничены...", type: "indemnity", isKey: false },
  { text: "Любые споры по настоящему Договору подлежат...", type: "jurisdiction", isKey: false },
  { text: "Заверения, содержащиеся в настоящем разделе...", type: "warranty", isKey: false },
  { text: "Время является существенным условием в отношении...", type: "general", isKey: false },
  { text: "Продавец передаёт Покупателю при Закрытии...", type: "concept", isKey: false },
];

const LONG: Fragment[] = [
  { 
    text: "Несмотря на любые противоречащие положения настоящего Договора, ответственность Продавца ограничивается...", 
    type: "liability", 
    isKey: false 
  },
  { 
    text: "Заверения и гарантии Сторон, изложенные в Статье IV, сохраняют силу в течение...", 
    type: "warranty", 
    isKey: false 
  },
  { 
    text: "В случае, если какое-либо положение настоящего Договора будет признано недействительным...", 
    type: "general", 
    isKey: false 
  },
  { 
    text: "Покупатель обязуется возместить, защитить и освободить от ответственности Продавца и его аффилированных лиц...", 
    type: "indemnity", 
    isKey: false 
  },
  { 
    text: "Существенное неблагоприятное изменение означает любое событие, обстоятельство или изменение, которое...", 
    type: "mac", 
    isKey: false 
  },
  { 
    text: "Каждая Сторона признаёт и соглашается с тем, что денежной компенсации может быть недостаточно для...", 
    type: "general", 
    isKey: false 
  },
  { 
    text: "Настоящий Договор регулируется и толкуется в соответствии с законодательством, применимым в...", 
    type: "jurisdiction", 
    isKey: false 
  },
  { 
    text: "Стороны соглашаются добросовестно сотрудничать в целях исполнения настоящего Договора и достижения...", 
    type: "general", 
    isKey: false 
  },
];

export const CONTRACT_TEXTS: FragmentBucket = {
  micro: MICRO,
  short: SHORT,
  medium: MEDIUM,
  long: LONG,
};

/**
 * Выбирает подходящий фрагмент под ширину сегмента силуэта.
 * Использует моноширинную метрику: ~0.6 * fontSize на символ.
 */
export function pickFragmentForWidth(
  widthPx: number,
  fontSize: number
): Fragment {
  const maxChars = Math.floor(widthPx / (fontSize * 0.6));

  let pool: Fragment[];
  if (maxChars < 12) pool = CONTRACT_TEXTS.micro;
  else if (maxChars < 32) pool = CONTRACT_TEXTS.short;
  else if (maxChars < 70) pool = CONTRACT_TEXTS.medium;
  else pool = CONTRACT_TEXTS.long;

  const candidates = pool.filter((f) => f.text.length <= maxChars);
  if (candidates.length === 0) {
    return pool[Math.floor(Math.random() * pool.length)];
  }
  return candidates[Math.floor(Math.random() * candidates.length)];
}

