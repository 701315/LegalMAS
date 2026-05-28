# src/services/pii_tokenizer.py

"""
PII Tokenizer.

Отвечает за токенизацию PII-сущностей в тексте и построение политики
обработки на основе applicable_triggers, YAML‑конфига и настроек.

Стратегии:
  TOKENIZE  → заменить сущность на стабильный токен (PERSON1, PHONE1, EMAIL1 ...)
  PRESERVE  → оставить как есть (номера, которые нужны LLM в оригинале:
              ИНН, ОГРН, кадастровый номер и т.п.)
  ROLE_MAP  → для имён сторон договора пытаться заменить имя на роль
              (SELLER/BUYER/LESSOR/...), используя словарь ролей

Основные компоненты:
- PIIPolicy — описывает, какие типы PII токенизировать/сохранять/маппить в роль
  и какой словарь ролей использовать (кастомный из YAML или дефолтный).
- TokenizationResult — результат токенизации (sanitized_text, mapping токен→оригинал,
  счётчики по стратегиям).
- PIITokenizer.tokenize(...) — применяет политику к списку сущностей и строит
  заанонимизированный текст + mapping.
- PIITokenizer.build_policy_from_triggers(...) — собирает PIIPolicy из
  applicable_triggers документа, флага preserve_party_roles и словаря ролей
  из YAML (DocumentTypeConfig.party_role_keywords).
"""

from dataclasses import dataclass, field

from core.config import settings
from core.constants import PIIEntityType, PIITokenPolicy
from services.pii_detector import PIIEntity, get_preserve_types

# ═══════════════════════════════════════════════════════════════════════════════
# Party role keywords (дефолтный словарь, если в YAML ничего не задано)
# ═══════════════════════════════════════════════════════════════════════════════

_PARTY_ROLE_KEYWORDS_DEFAULT: dict[str, str] = {
    # Русский
    "продавец": "SELLER",
    "покупатель": "BUYER",
    "арендодатель": "LESSOR",
    "арендатор": "LESSEE",
    "работодатель": "EMPLOYER",
    "работник": "EMPLOYEE",
    "лицензиар": "LICENSOR",
    "лицензиат": "LICENSEE",
    "заказчик": "CUSTOMER",
    "подрядчик": "CONTRACTOR",
    "займодавец": "LENDER",
    "заёмщик": "BORROWER",
    # English
    "seller": "SELLER",
    "buyer": "BUYER",
    "lessor": "LESSOR",
    "lessee": "LESSEE",
    "employer": "EMPLOYER",
    "employee": "EMPLOYEE",
    "licensor": "LICENSOR",
    "licensee": "LICENSEE",
    "customer": "CUSTOMER",
    "contractor": "CONTRACTOR",
    "lender": "LENDER",
    "borrower": "BORROWER",
}


@dataclass
class PIIPolicy:
    """Политика токенизации — строится на основе applicable_triggers и playbook."""

    tokenize_types: set[PIIEntityType] = field(
        default_factory=lambda: {
            PIIEntityType.PERSON_NAME,
            PIIEntityType.PASSPORT,
            PIIEntityType.PHONE,
            PIIEntityType.EMAIL,
            PIIEntityType.ADDRESS,
        }
    )
    preserve_types: set[PIIEntityType] = field(default_factory=lambda: set(get_preserve_types()))
    use_role_map: bool = True  # активируется если applicable_triggers не пуст

    # словарь из YAML playbook: {keyword_lower: ROLE_ID}
    # None = использовать дефолтный словарь
    party_role_keywords: dict[str, str] | None = None

    def get_action(self, entity_type: PIIEntityType) -> PIITokenPolicy:
        """Определить политику для типа сущности."""
        if entity_type in self.preserve_types:
            return PIITokenPolicy.PRESERVE
        if entity_type == PIIEntityType.PERSON_NAME and self.use_role_map:
            return PIITokenPolicy.ROLE_MAP
        return PIITokenPolicy.TOKENIZE


@dataclass
class TokenizationResult:
    """Результат токенизации."""

    sanitized_text: str
    mapping: dict[str, str]  # TOKEN → original_text
    entities_tokenized: int
    entities_preserved: int
    entities_role_mapped: int


class PIITokenizer:
    """Токенизатор PII-сущностей."""

    def tokenize(
        self,
        text: str,
        entities: list[PIIEntity],
        policy: PIIPolicy,
        context_window: str = "",
    ) -> TokenizationResult:
        """
        Токенизировать текст согласно политике.

        Args:
            text: Исходный текст
            entities: Найденные PII-сущности (отсортированы по позиции)
            policy: Политика обработки
            context_window: Первые N символов текста для определения роли

        Returns:
            TokenizationResult
        """
        mapping: dict[str, str] = {}
        counters: dict[str, int] = {}
        result = list(text)
        context_lower = context_window.lower()

        stats = {"tokenized": 0, "preserved": 0, "role_mapped": 0}

        # Обрабатываем с конца, чтобы не сбивать индексы
        for entity in reversed(entities):
            action = policy.get_action(entity.type)

            if action == PIITokenPolicy.PRESERVE:
                stats["preserved"] += 1
                continue

            token: str | None = None

            if action == PIITokenPolicy.ROLE_MAP:
                token = self._detect_party_role(entity.text, context_lower, policy)
                if token:
                    stats["role_mapped"] += 1
                else:
                    # fallback на обычную токенизацию, если роль не определилась
                    action = PIITokenPolicy.TOKENIZE

            if action == PIITokenPolicy.TOKENIZE:
                type_key = entity.type.value.upper().replace("_", "")
                counters[type_key] = counters.get(type_key, 0) + 1
                token = f"{type_key}{counters[type_key]}"
                stats["tokenized"] += 1

            if token:
                mapping[token] = entity.text
                result[entity.start : entity.end] = list(token)

        return TokenizationResult(
            sanitized_text="".join(result),
            mapping=mapping,
            entities_tokenized=stats["tokenized"],
            entities_preserved=stats["preserved"],
            entities_role_mapped=stats["role_mapped"],
        )

    @staticmethod
    def _detect_party_role(name: str, context_lower: str, policy: PIIPolicy) -> str | None:
        """
        Найти роль стороны в контексте рядом с именем.

        Приоритет:
        1) словарь из PIIPolicy.party_role_keywords (из YAML essential_elements.party_roles)
        2) дефолтный _PARTY_ROLE_KEYWORDS_DEFAULT

        ИСПРАВЛЕНО: пустой dict {} теперь корректно fallback на дефолт
        """
        # Используем кастомные keywords только если они заданы И не пустые
        if policy.party_role_keywords:
            keywords = policy.party_role_keywords
        else:
            keywords = _PARTY_ROLE_KEYWORDS_DEFAULT

        for keyword, role in keywords.items():
            if keyword in context_lower:
                return role
        return None

    @staticmethod
    def build_policy_from_triggers(
        applicable_triggers: list[str] | None,
        preserve_party_roles: bool | None = None,
        party_role_keywords: dict[str, str] | None = None,
    ) -> PIIPolicy:
        """
        Построить PIIPolicy на основе applicable_triggers из классификатора
        и словаря ролей из YAML (party_role_keywords).

        Args:
            applicable_triggers: Список триггеров из Document.applicable_triggers
            preserve_party_roles: Использовать ROLE_MAP. None = из settings.PII_PRESERVE_PARTY_ROLES
            party_role_keywords: {keyword_lower: ROLE_ID} из DocumentTypeConfig.party_role_keywords
                                 None или {} = использовать дефолтный словарь
        """
        # Читаем из settings если не передано явно
        if preserve_party_roles is None:
            preserve_party_roles = settings.PII_PRESERVE_PARTY_ROLES

        use_role_map = bool(applicable_triggers) and preserve_party_roles

        # Нормализуем party_role_keywords: пустой dict → None (чтобы использовался дефолт)
        normalized_keywords = party_role_keywords if party_role_keywords else None

        return PIIPolicy(
            use_role_map=use_role_map,
            party_role_keywords=normalized_keywords,
        )
