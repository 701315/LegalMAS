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
        value_to_token: dict[str, str] | None = None,
        counters: dict[str, int] | None = None,
    ) -> TokenizationResult:
        """
        Токенизировать текст согласно политике.

        Args:
            text: Исходный текст элемента
            entities: Найденные PII-сущности (отсортированы по позиции)
            policy: Политика обработки
            context_window: Оставлен для backward compatibility, не используется
                в ROLE_MAP — заменён proximity-поиском по full_text + entity.start.
            value_to_token: Разделяемый маппинг normalized_value → token через документ.
                None = локальный scope (backward compatibility).
            counters: Разделяемые счётчики type_key → current_max_index через документ.
                None = локальный scope (backward compatibility).

        Returns:
            TokenizationResult с mapping только для ЭТОГО элемента.
        """
        _value_to_token: dict[str, str] = value_to_token if value_to_token is not None else {}
        _counters: dict[str, int] = counters if counters is not None else {}

        local_mapping: dict[str, str] = {}
        result = list(text)

        stats = {"tokenized": 0, "preserved": 0, "role_mapped": 0}

        # Обрабатываем с конца, чтобы не сбивать индексы при замене
        for entity in reversed(entities):
            action = policy.get_action(entity.type)

            if action == PIITokenPolicy.PRESERVE:
                stats["preserved"] += 1
                continue

            token: str | None = None

            if action == PIITokenPolicy.ROLE_MAP:
                # Proximity-поиск: ближайший keyword слева от entity.start в full text
                token = self._detect_party_role(entity.text, text, entity.start, policy)
                if token:
                    stats["role_mapped"] += 1
                else:
                    # fallback: роль не определена → обычная токенизация
                    action = PIITokenPolicy.TOKENIZE

            if action == PIITokenPolicy.TOKENIZE:
                normalized = entity.text.strip().lower()
                if normalized in _value_to_token:
                    token = _value_to_token[normalized]
                else:
                    type_key = entity.type.value.upper().replace("_", "")
                    _counters[type_key] = _counters.get(type_key, 0) + 1
                    token = f"{type_key}{_counters[type_key]}"
                    _value_to_token[normalized] = token
                    stats["tokenized"] += 1

            if token:
                local_mapping[token] = entity.text
                result[entity.start : entity.end] = list(token)

        return TokenizationResult(
            sanitized_text="".join(result),
            mapping=local_mapping,
            entities_tokenized=stats["tokenized"],
            entities_preserved=stats["preserved"],
            entities_role_mapped=stats["role_mapped"],
        )

    @staticmethod
    def _detect_party_role(
        name: str,
        full_text: str,
        entity_start: int,
        policy: PIIPolicy,
        window: int = 200,
    ) -> str | None:
        """
        Найти роль стороны по ближайшему ключевому слову СЛЕВА от сущности.

        Алгоритм:
        - Берём окно текста длиной window символов непосредственно перед entity_start.
        - Для каждого keyword ищем его последнее вхождение в этом окне (rfind).
        - Побеждает keyword с наименьшим расстоянием до entity_start.
        - Если ни одного keyword не найдено — возвращаем None (fallback на TOKENIZE).

        Почему rfind и левое окно:
        - В юридических документах роль указывается ПЕРЕД именем или сразу после.
        - Поиск в полном тексте давал ложные срабатывания при нескольких сторонах
        в одном элементе: "продавец" стоит первым в словаре и выигрывал
        у "покупателя" даже когда покупатель был ближе к имени.

        Args:
            name: Текст сущности (зарезервирован для future use / logging).
            full_text: Полный текст элемента layout.
            entity_start: Позиция начала сущности в full_text.
            policy: Политика с опциональным кастомным словарём ролей.
            window: Количество символов слева от entity_start для поиска.

        Returns:
            Строка-роль (SELLER, BUYER, LESSOR, ...) или None.
        """
        keywords = policy.party_role_keywords or _PARTY_ROLE_KEYWORDS_DEFAULT

        # Левое окно: window символов до entity_start
        search_start = max(0, entity_start - window)
        left_context = full_text[search_start:entity_start].lower()

        if not left_context:
            return None

        best_role: str | None = None
        best_distance: int | None = None

        for keyword, role in keywords.items():
            idx = left_context.rfind(keyword)
            if idx == -1:
                continue
            # Расстояние: сколько символов от конца keyword до entity_start
            distance = len(left_context) - (idx + len(keyword))
            if best_distance is None or distance < best_distance:
                best_role = role
                best_distance = distance

        return best_role

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
