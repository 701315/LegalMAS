// src/marketing/components/home/KnowledgeGrowthSection/contract-texts.ts
import type { Fragment, FragmentBucket } from "./types";

// ============================================================================
// RUSSIAN (Original)
// ============================================================================
const MICRO_RU: Fragment[] = [
  { text: "Сторона", type: "reference", isKey: false },
  { text: "Договор", type: "reference", isKey: false },
  { text: "Раздел 7.4", type: "reference", isKey: false },
  { text: "Закрытие", type: "concept", isKey: true },
  { text: "Гарантии", type: "warranty", isKey: true },
  { text: "Расторжение", type: "termination", isKey: true },
  { text: "MAC", type: "mac", isKey: true },
  { text: "indemnity", type: "indemnity", isKey: true },
];

const SHORT_RU: Fragment[] = [
  { text: "Существенное неблагоприятное изменение", type: "mac", isKey: true },
  { text: "Ограничение ответственности", type: "liability", isKey: true },
  { text: "Смена контроля", type: "control", isKey: true },
  { text: "Конфиденциальная информация", type: "confidentiality", isKey: true },
  { text: "Обязательства по возмещению", type: "indemnity", isKey: true },
  { text: "Расторжение по существенному нарушению", type: "termination", isKey: true },
  { text: "Применимое право", type: "jurisdiction", isKey: true },
  { text: "Дата Закрытия Сделки", type: "concept", isKey: false },
  { text: "Существенные условия", type: "concept", isKey: false },
];

const MEDIUM_RU: Fragment[] = [
  { text: "Продавец заверяет и гарантирует, что...", type: "warranty", isKey: false },
  { text: "Если иное не предусмотрено настоящим Договором...", type: "general", isKey: false },
  { text: "Настоящий Договор прекращается при наступлении...", type: "termination", isKey: false },
  { text: "Стороны признают и соглашаются, что...", type: "general", isKey: false },
  { text: "Компания обязуется возместить убытки...", type: "indemnity", isKey: false },
  { text: "В соответствии с разделом 7.4 настоящего Договора...", type: "reference", isKey: false },
  { text: "Никакие изменения не имеют силы, если...", type: "general", isKey: false },
  { text: "Настоящий Договор регулируется правом...", type: "jurisdiction", isKey: false },
  { text: "В случае существенного нарушения настоящего...", type: "termination", isKey: false },
];

const LONG_RU: Fragment[] = [
  { text: "Несмотря на любые противоречащие положения настоящего Договора, ответственность Продавца ограничивается...", type: "liability", isKey: false },
  { text: "Заверения и гарантии Сторон, изложенные в Статье IV, сохраняют силу в течение...", type: "warranty", isKey: false },
  { text: "В случае, если какое-либо положение настоящего Договора будет признано недействительным...", type: "general", isKey: false },
  { text: "Покупатель обязуется возместить, защитить и освободить от ответственности Продавца...", type: "indemnity", isKey: false },
  { text: "Существенное неблагоприятное изменение означает любое событие, обстоятельство или изменение, которое...", type: "mac", isKey: false },
];

// ============================================================================
// ENGLISH
// ============================================================================
const MICRO_EN: Fragment[] = [
  { text: "Party", type: "reference", isKey: false },
  { text: "Agreement", type: "reference", isKey: false },
  { text: "Section 7.4", type: "reference", isKey: false },
  { text: "Closing", type: "concept", isKey: true },
  { text: "Warranties", type: "warranty", isKey: true },
  { text: "Termination", type: "termination", isKey: true },
  { text: "MAC", type: "mac", isKey: true },
  { text: "Indemnity", type: "indemnity", isKey: true },
];

const SHORT_EN: Fragment[] = [
  { text: "Material Adverse Change", type: "mac", isKey: true },
  { text: "Limitation of Liability", type: "liability", isKey: true },
  { text: "Change of Control", type: "control", isKey: true },
  { text: "Confidential Information", type: "confidentiality", isKey: true },
  { text: "Obligations to Indemnify", type: "indemnity", isKey: true },
  { text: "Termination for Cause", type: "termination", isKey: true },
  { text: "Governing Law", type: "jurisdiction", isKey: true },
  { text: "Closing Date", type: "concept", isKey: false },
  { text: "Material Conditions", type: "concept", isKey: false },
];

const MEDIUM_EN: Fragment[] = [
  { text: "Seller represents and warrants that...", type: "warranty", isKey: false },
  { text: "Unless otherwise provided in this Agreement...", type: "general", isKey: false },
  { text: "This Agreement shall terminate upon the occurrence of...", type: "termination", isKey: false },
  { text: "The Parties acknowledge and agree that...", type: "general", isKey: false },
  { text: "The Company undertakes to compensate for any losses...", type: "indemnity", isKey: false },
  { text: "In accordance with Section 7.4 of this Agreement...", type: "reference", isKey: false },
  { text: "No amendments shall be effective unless...", type: "general", isKey: false },
  { text: "This Agreement shall be governed by the laws of...", type: "jurisdiction", isKey: false },
  { text: "In the event of a material breach of this...", type: "termination", isKey: false },
];

const LONG_EN: Fragment[] = [
  { text: "Notwithstanding any conflicting provisions herein, Seller's liability shall be strictly limited to...", type: "liability", isKey: false },
  { text: "The representations and warranties of the Parties set forth in Article IV shall survive for a period of...", type: "warranty", isKey: false },
  { text: "In the event that any provision of this Agreement is held to be invalid or unenforceable...", type: "general", isKey: false },
  { text: "Buyer agrees to indemnify, defend, and hold harmless the Seller and its affiliates from...", type: "indemnity", isKey: false },
  { text: "Material Adverse Change means any event, circumstance, or change that would reasonably be expected to...", type: "mac", isKey: false },
];

// ============================================================================
// TURKISH
// ============================================================================
const MICRO_TR: Fragment[] = [
  { text: "Taraf", type: "reference", isKey: false },
  { text: "Sözleşme", type: "reference", isKey: false },
  { text: "Madde 7.4", type: "reference", isKey: false },
  { text: "Kapanış", type: "concept", isKey: true },
  { text: "Garantiler", type: "warranty", isKey: true },
  { text: "Fesih", type: "termination", isKey: true },
  { text: "MAC", type: "mac", isKey: true },
  { text: "Tazminat", type: "indemnity", isKey: true },
];

const SHORT_TR: Fragment[] = [
  { text: "Önemli Olumsuz Değişiklik", type: "mac", isKey: true },
  { text: "Sorumluluğun Sınırlandırılması", type: "liability", isKey: true },
  { text: "Kontrol Değişikliği", type: "control", isKey: true },
  { text: "Gizli Bilgi", type: "confidentiality", isKey: true },
  { text: "Tazminat Yükümlülükleri", type: "indemnity", isKey: true },
  { text: "Önemli İhlal Nedeniyle Fesih", type: "termination", isKey: true },
  { text: "Uygulanacak Hukuk", type: "jurisdiction", isKey: true },
  { text: "Kapanış Tarihi", type: "concept", isKey: false },
  { text: "Temel Koşullar", type: "concept", isKey: false },
];

const MEDIUM_TR: Fragment[] = [
  { text: "Satıcı, ... olduğunu beyan ve taahhüt eder.", type: "warranty", isKey: false },
  { text: "İşbu Sözleşmede aksi öngörülmedikçe...", type: "general", isKey: false },
  { text: "İşbu Sözleşme, ... durumunda sona erecektir.", type: "termination", isKey: false },
  { text: "Taraflar, ... olduğunu kabul ve beyan eder.", type: "general", isKey: false },
  { text: "Şirket, doğacak zararları tazmin etmeyi taahhüt eder.", type: "indemnity", isKey: false },
  { text: "İşbu Sözleşmenin 7.4. maddesi uyarınca...", type: "reference", isKey: false },
  { text: "Aksi yazılı olarak kararlaştırılmadıkça hiçbir değişiklik...", type: "general", isKey: false },
  { text: "İşbu Sözleşme, ... hukukuna tabi olacaktır.", type: "jurisdiction", isKey: false },
  { text: "İşbu Sözleşmenin önemli bir şekilde ihlali durumunda...", type: "termination", isKey: false },
];

const LONG_TR: Fragment[] = [
  { text: "İşbu Sözleşmedeki herhangi bir çelişkili hükme bakılmaksızın, Satıcının sorumluluğu ... ile sınırlıdır.", type: "liability", isKey: false },
  { text: "IV. Maddede yer alan Tarafların beyan ve garantileri, ... süresi boyunca geçerliliğini koruyacaktır.", type: "warranty", isKey: false },
  { text: "İşbu Sözleşmenin herhangi bir hükmünün geçersiz veya uygulanamaz kabul edilmesi durumunda...", type: "general", isKey: false },
  { text: "Alıcı, Satıcıyı ve bağlı kuruluşlarını her türlü talebe karşı tazmin etmeyi, savunmayı ve zararsız kılmayı kabul eder.", type: "indemnity", isKey: false },
  { text: "Önemli Olumsuz Değişiklik, makul bir şekilde ... beklenen herhangi bir olay, durum veya değişikliği ifade eder.", type: "mac", isKey: false },
];

// ============================================================================
// ARABIC (RTL)
// ============================================================================
const MICRO_AR: Fragment[] = [
  { text: "الطرف", type: "reference", isKey: false },
  { text: "العقد", type: "reference", isKey: false },
  { text: "المادة 7.4", type: "reference", isKey: false },
  { text: "الإغلاق", type: "concept", isKey: true },
  { text: "ضمانات", type: "warranty", isKey: true },
  { text: "فسخ", type: "termination", isKey: true },
  { text: "MAC", type: "mac", isKey: true },
  { text: "تعويض", type: "indemnity", isKey: true },
];

const SHORT_AR: Fragment[] = [
  { text: "تغيير سلبي جوهري", type: "mac", isKey: true },
  { text: "تحديد المسؤولية", type: "liability", isKey: true },
  { text: "تغيير السيطرة", type: "control", isKey: true },
  { text: "معلومات سرية", type: "confidentiality", isKey: true },
  { text: "التزامات التعويض", type: "indemnity", isKey: true },
  { text: "الفسخ بسبب الإخلال الجوهري", type: "termination", isKey: true },
  { text: "القانون الواجب التطبيق", type: "jurisdiction", isKey: true },
  { text: "تاريخ الإغلاق", type: "concept", isKey: false },
  { text: "الشروط الجوهرية", type: "concept", isKey: false },
];

const MEDIUM_AR: Fragment[] = [
  { text: "يقر البائع ويضمن أن...", type: "warranty", isKey: false },
  { text: "ما لم ينص على خلاف ذلك في هذا العقد...", type: "general", isKey: false },
  { text: "ينتهي هذا العقد عند حدوث...", type: "termination", isKey: false },
  { text: "تقر الأطراف وتوافق على أن...", type: "general", isKey: false },
  { text: "تلتزم الشركة بتعويض أي خسائر...", type: "indemnity", isKey: false },
  { text: "وفقاً للمادة 7.4 من هذا العقد...", type: "reference", isKey: false },
  { text: "لا تكون أي تعديلات نافذة إلا إذا...", type: "general", isKey: false },
  { text: "يخضع هذا العقد ويفسر وفقاً لقوانين...", type: "jurisdiction", isKey: false },
  { text: "في حالة الإخلال الجوهري بهذا...", type: "termination", isKey: false },
];

const LONG_AR: Fragment[] = [
  { text: "على الرغم من أي أحكام متضاربة في هذا العقد، تقتصر مسؤولية البائع على...", type: "liability", isKey: false },
  { text: "تحتفظ التصريحات والضمانات الصادرة عن الأطراف والواردة في المادة الرابعة بقوتها لمدة...", type: "warranty", isKey: false },
  { text: "في حال اعتُبر أي حكم من أحكام هذا العقد باطلاً أو غير قابل للتنفيذ...", type: "general", isKey: false },
  { text: "يوافق المشتري على تعويض البائع وشركاته التابعة والدفاع عنهم وحمايتهم من...", type: "indemnity", isKey: false },
  { text: "يعني التغيير السلبي الجوهري أي حدث أو ظرف أو تغيير من شأنه أن...", type: "mac", isKey: false },
];

// ============================================================================
// EXPORTS & LOGIC
// ============================================================================

const ALL_CONTRACT_TEXTS: Record<string, FragmentBucket> = {
  ru: { micro: MICRO_RU, short: SHORT_RU, medium: MEDIUM_RU, long: LONG_RU },
  en: { micro: MICRO_EN, short: SHORT_EN, medium: MEDIUM_EN, long: LONG_EN },
  tr: { micro: MICRO_TR, short: SHORT_TR, medium: MEDIUM_TR, long: LONG_TR },
  ar: { micro: MICRO_AR, short: SHORT_AR, medium: MEDIUM_AR, long: LONG_AR },
};

/**
 * Возвращает пул фрагментов для конкретного языка.
 * Fallback на английский, если язык не найден.
 */
export function getContractTexts(lang: string): FragmentBucket {
  return ALL_CONTRACT_TEXTS[lang] || ALL_CONTRACT_TEXTS["en"];
}

/**
 * Выбирает подходящий фрагмент под ширину сегмента силуэта.
 * ВАЖНО: Теперь требует передачи текущего языка (lang).
 */
export function pickFragmentForWidth(
  widthPx: number,
  fontSize: number,
  lang: string = "ru" // Дефолт для обратной совместимости
): Fragment {
  // Для арабского шрифта визуальная плотность чуть выше, 
  // но 0.6 остается безопасной консервативной оценкой для моноширинного расчета.
  const maxChars = Math.floor(widthPx / (fontSize * 0.6));
  
  const pool = getContractTexts(lang);

  let targetPool: Fragment[];
  if (maxChars < 12) targetPool = pool.micro;
  else if (maxChars < 32) targetPool = pool.short;
  else if (maxChars < 70) targetPool = pool.medium;
  else targetPool = pool.long;

  const candidates = targetPool.filter((f) => f.text.length <= maxChars);
  if (candidates.length === 0) {
    return targetPool[Math.floor(Math.random() * targetPool.length)];
  }
  return candidates[Math.floor(Math.random() * candidates.length)];
}