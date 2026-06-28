// src/components/marketing/landing/SecurityFoundationSection/infrastructure-texts.ts
//
// Тексты для корневой системы безопасности.
//
// Концепция: корни — это инфраструктура, которая поддерживает
// "дерево знания" сверху. Содержит:
//   - юридические якоря (Source, Evidence) — переход от мира юриста
//   - операционные понятия (Audit, Workspace, Versioning)
//   - технические протоколы (AES-256, TLS 1.3, SHA-256)
//   - атомы кода (hash(), verify(), encrypt())
//
// Распределение по глубине корней:
//   верх (близко к стволу)   = юридические якоря + операционные
//   середина                  = технологии + протоколы
//   глубже                    = низкоуровневые термины + код
//
// Длина сегмента определяет тип фразы (короткие в тонких корнях,
// длинные в основании).

import type { Fragment } from "./types";

// ─── Короткие фрагменты (для самых тонких корешков) ─────────
const MICRO: Fragment[] = [
  { text: "AES-256", type: "concept", isKey: true },
  { text: "SHA-256", type: "concept", isKey: true },
  { text: "TLS 1.3", type: "concept", isKey: true },
  { text: "JWT", type: "concept", isKey: true },
  { text: "RBAC", type: "concept", isKey: true },
  { text: "UUID", type: "reference", isKey: false },
  { text: "OAuth2", type: "concept", isKey: false },
  { text: "X.509", type: "reference", isKey: false },
  { text: "HMAC", type: "concept", isKey: false },
  { text: "PBKDF2", type: "concept", isKey: false },
  { text: "ECDSA", type: "concept", isKey: false },
  { text: "RSA-4096", type: "concept", isKey: false },
  { text: "FIPS 140-2", type: "concept", isKey: false },
  { text: "ISO 27001", type: "concept", isKey: true },
  { text: "SOC 2", type: "concept", isKey: true },
  { text: "GDPR", type: "concept", isKey: true },
  { text: "152-ФЗ", type: "concept", isKey: true },
  { text: "hash()", type: "reference", isKey: false },
  { text: "verify()", type: "reference", isKey: false },
  { text: "encrypt()", type: "reference", isKey: false },
  { text: "decrypt()", type: "reference", isKey: false },
  { text: "commit()", type: "reference", isKey: false },
  { text: "sign()", type: "reference", isKey: false },
  { text: "freeze()", type: "reference", isKey: false },
  { text: "lock()", type: "reference", isKey: false },
  { text: "audit()", type: "reference", isKey: false },
  { text: "trace()", type: "reference", isKey: false },
  { text: "validate()", type: "reference", isKey: false },
  { text: "isolate()", type: "reference", isKey: false },
  { text: "salt", type: "reference", isKey: false },
  { text: "nonce", type: "reference", isKey: false },
  { text: "Sandbox", type: "concept", isKey: true },
  { text: "Zero Trust", type: "concept", isKey: true },
  { text: "Immutable", type: "concept", isKey: true },
  { text: "Audit Trail", type: "concept", isKey: true },
  { text: "RLS", type: "concept", isKey: false },
  { text: "SSO", type: "concept", isKey: false },
  { text: "MFA", type: "concept", isKey: false },
  { text: "SAML", type: "concept", isKey: false },
];

// ─── Средние фрагменты (для средних корней) ─────────────────
const SHORT: Fragment[] = [
  { text: "Source Reference", type: "reference", isKey: true },
  { text: "Evidence Chain", type: "concept", isKey: true },
  { text: "Document Hash", type: "concept", isKey: false },
  { text: "Access Policy", type: "concept", isKey: true },
  { text: "Audit Log", type: "concept", isKey: true },
  { text: "Encrypted Storage", type: "concept", isKey: true },
  { text: "Signed Output", type: "concept", isKey: true },
  { text: "Detached Workspace", type: "concept", isKey: true },
  { text: "Private Cloud", type: "concept", isKey: true },
  { text: "Local LLM", type: "concept", isKey: true },
  { text: "PII Detection", type: "concept", isKey: false },
  { text: "Tenant Isolation", type: "concept", isKey: true },
  { text: "Version Control", type: "concept", isKey: false },
  { text: "Token Expiry", type: "reference", isKey: false },
  { text: "Session Lock", type: "reference", isKey: false },
  { text: "Encryption at Rest", type: "concept", isKey: true },
  { text: "Encryption in Transit", type: "concept", isKey: true },
  { text: "Key Rotation", type: "concept", isKey: false },
  { text: "Workspace Isolation", type: "concept", isKey: true },
  { text: "Immutable Storage", type: "concept", isKey: true },
  { text: "Access Control", type: "concept", isKey: true },
  { text: "Data Residency", type: "concept", isKey: true },
  { text: "Penetration Test", type: "concept", isKey: false },
  { text: "Threat Model", type: "concept", isKey: false },
  { text: "Compliance Audit", type: "concept", isKey: true },
  { text: "152-ФЗ persistence", type: "concept", isKey: false },
  { text: "Sandboxed Execution", type: "concept", isKey: true },
  { text: "Permission Matrix", type: "reference", isKey: false },
  { text: "Signed Commit", type: "reference", isKey: false },
  { text: "audit.write(event)", type: "reference", isKey: false },
  { text: "hash(document)", type: "reference", isKey: false },
  { text: "verify(signature)", type: "reference", isKey: false },
  { text: "encrypt(payload)", type: "reference", isKey: false },
  { text: "workspace.lock()", type: "reference", isKey: false },
  { text: "policy.apply()", type: "reference", isKey: false },
  { text: "evidence.link()", type: "reference", isKey: false },
];

// ─── Длинные фрагменты (для основания корней — где толстые ветви) ───
const MEDIUM: Fragment[] = [
  { text: "Каждый документ имеет неизменяемый SHA-256 хэш...", type: "concept", isKey: false },
  { text: "Workspace для каждой сделки физически изолирован...", type: "concept", isKey: false },
  { text: "Все операции записываются в неперезаписываемый журнал...", type: "concept", isKey: false },
  { text: "Доступ к данным контролируется через RBAC-политики...", type: "concept", isKey: false },
  { text: "AI-модель работает в изолированном sandbox-окружении...", type: "concept", isKey: false },
  { text: "Каждый вывод системы подписан криптографической подписью...", type: "concept", isKey: false },
  { text: "Данные шифруются ключами клиента, хранимыми в KMS...", type: "concept", isKey: false },
  { text: "Соединение защищено TLS 1.3 с perfect forward secrecy...", type: "concept", isKey: false },
  { text: "Аудит-трейл хранится в immutable-режиме навечно...", type: "concept", isKey: false },
  { text: "Каждое утверждение модели имеет verifiable source link...", type: "concept", isKey: false },
  { text: "Tenant isolation на уровне базы данных через RLS...", type: "concept", isKey: false },
  { text: "Multi-factor authentication обязательна для всех ролей...", type: "concept", isKey: false },
  { text: "Ключи шифрования ротируются каждые 90 дней автоматически...", type: "concept", isKey: false },
  { text: "Доступ к prod-окружению только через bastion с MFA...", type: "concept", isKey: false },
  { text: "Регулярный penetration testing третьей стороной...", type: "concept", isKey: false },
  { text: "Все исходящие вызовы проходят через egress whitelist...", type: "concept", isKey: false },
  { text: "PII обнаруживается и маскируется до отправки в модель...", type: "concept", isKey: false },
  { text: "Данные никогда не покидают периметр клиента...", type: "concept", isKey: false },
  { text: "Соответствие 152-ФЗ о персональных данных РФ...", type: "concept", isKey: false },
  { text: "ISO 27001 сертификация подтверждается ежегодно...", type: "concept", isKey: false },
  { text: "SOC 2 Type II audit проводится независимым аудитором...", type: "concept", isKey: false },
  { text: "GDPR-compliant обработка данных пользователей ЕС...", type: "concept", isKey: false },
];

// ─── Очень длинные (для самых широких участков воротника) ────
const LONG: Fragment[] = [
  {
    text: "Каждый шаг pipeline записывается в immutable audit log с timestamp, user_id и hash источника...",
    type: "concept",
    isKey: false,
  },
  {
    text: "Workspace каждого клиента изолирован на уровне инфраструктуры — отдельные ключи, отдельная БД, отдельный namespace...",
    type: "concept",
    isKey: false,
  },
  {
    text: "Модель никогда не дообучается на данных клиента — все запросы выполняются в read-only mode...",
    type: "concept",
    isKey: false,
  },
  {
    text: "При каждом ответе AI возвращается verifiable evidence chain — какие документы, какие пункты, какой playbook...",
    type: "concept",
    isKey: false,
  },
  {
    text: "Доступ к каждому документу проверяется по RBAC-политикам в реальном времени, на каждый запрос...",
    type: "concept",
    isKey: false,
  },
];

// ─── Bucket-структура и helper ──────────────────────────────
type FragmentBucket = {
  micro: Fragment[];
  short: Fragment[];
  medium: Fragment[];
  long: Fragment[];
};

export const INFRASTRUCTURE_TEXTS: FragmentBucket = {
  micro: MICRO,
  short: SHORT,
  medium: MEDIUM,
  long: LONG,
};

// Helper для выбора фрагмента под ширину сегмента
// (та же логика что в contract-texts.ts дерева, чтобы engine работал одинаково)
export function pickFragmentForWidth(widthPx: number, fontSize: number): Fragment {
  const maxChars = Math.floor(widthPx / (fontSize * 0.6));

  let pool: Fragment[];
  if (maxChars < 12) pool = INFRASTRUCTURE_TEXTS.micro;
  else if (maxChars < 32) pool = INFRASTRUCTURE_TEXTS.short;
  else if (maxChars < 70) pool = INFRASTRUCTURE_TEXTS.medium;
  else pool = INFRASTRUCTURE_TEXTS.long;

  const candidates = pool.filter((f) => f.text.length <= maxChars);
  if (candidates.length === 0) {
    return pool[Math.floor(Math.random() * pool.length)];
  }
  return candidates[Math.floor(Math.random() * candidates.length)];
}
