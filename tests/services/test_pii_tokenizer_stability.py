"""
Тесты стабильности токенизации PII через документ.

Ключевой инвариант: одна и та же PII-сущность должна получать
один и тот же токен во всех элементах документа.

Тесты написаны ДО патча чтобы зафиксировать реальное поведение.
"""

import pytest
from core.constants import PIIEntityType, PIITokenPolicy
from services.pii_detector import PIIEntity
from services.pii_tokenizer import PIIPolicy, PIITokenizer


@pytest.fixture
def tokenizer():
    return PIITokenizer()


@pytest.fixture
def policy():
    """Базовая политика: токенизировать имена, preserve ИНН."""
    return PIIPolicy(
        tokenize_types={
            PIIEntityType.PERSON_NAME,
            PIIEntityType.PASSPORT,
            PIIEntityType.PHONE,
            PIIEntityType.EMAIL,
            PIIEntityType.ADDRESS,
        },
        preserve_types=set(),
        use_role_map=False,
    )


def make_entity(
    text: str,
    entity_type: PIIEntityType = PIIEntityType.PERSON_NAME,
    start: int = 0,
) -> PIIEntity:
    return PIIEntity(
        type=entity_type,
        start=start,
        end=start + len(text),
        text=text,
        confidence=1.0,
        source="regex",
    )


# ─── Класс 1: стабильность через несколько вызовов tokenize() ────────────────


class TestTokenStabilityAcrossCalls:
    """
    ГЛАВНЫЙ ТЕСТ ПАТЧА.
    Одна и та же сущность должна получить один токен через несколько
    вызовов tokenize() — как это происходит в _process_elements().
    """

    def test_same_name_same_token_across_elements(self, tokenizer, policy):
        """
        "Иванов И.И." в двух элементах layout → один токен в обоих.
        ДО патча: два разных токена (PERSONNAME1 в каждом).
        ПОСЛЕ патча: один токен PERSONNAME1 в обоих.
        """
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        name = "Иванов И.И."

        entity1 = make_entity(name, PIIEntityType.PERSON_NAME, start=0)
        result1 = tokenizer.tokenize(
            text=f"{name} подписал договор",
            entities=[entity1],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        entity2 = make_entity(name, PIIEntityType.PERSON_NAME, start=10)
        result2 = tokenizer.tokenize(
            text=f"Подписант: {name}",
            entities=[entity2],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        token1 = list(result1.mapping.keys())[0]
        token2 = list(result2.mapping.keys())[0]

        assert token1 == token2, (
            f"Same entity got different tokens: '{token1}' vs '{token2}'. "
            "value_to_token not shared across calls."
        )

    def test_different_names_get_different_tokens(self, tokenizer, policy):
        """Разные имена → разные токены."""
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        entity_ivanov = make_entity("Иванов И.И.", PIIEntityType.PERSON_NAME, 0)
        entity_petrov = make_entity("Петров П.П.", PIIEntityType.PERSON_NAME, 0)

        result1 = tokenizer.tokenize(
            text="Иванов И.И. подписал",
            entities=[entity_ivanov],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )
        result2 = tokenizer.tokenize(
            text="Петров П.П. подписал",
            entities=[entity_petrov],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        token1 = list(result1.mapping.keys())[0]
        token2 = list(result2.mapping.keys())[0]
        assert token1 != token2

    def test_token_index_monotonically_increases(self, tokenizer, policy):
        """Индексы токенов растут монотонно через все элементы."""
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        names = ["Иванов И.И.", "Петров П.П.", "Сидоров С.С."]
        tokens = []

        for name in names:
            entity = make_entity(name, PIIEntityType.PERSON_NAME, 0)
            result = tokenizer.tokenize(
                text=f"{name} подписал",
                entities=[entity],
                policy=policy,
                value_to_token=value_to_token,
                counters=doc_counters,
            )
            tokens.append(list(result.mapping.keys())[0])

        # PERSONNAME1, PERSONNAME2, PERSONNAME3 — строго возрастающие
        assert tokens == ["PERSONNAME1", "PERSONNAME2", "PERSONNAME3"], (
            f"Expected monotonic token indices, got: {tokens}"
        )

    def test_reused_token_not_counted_as_new_tokenization(self, tokenizer, policy):
        """
        Переиспользование токена для уже видевшейся сущности
        не должно увеличивать entities_tokenized.
        """
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        name = "Иванов И.И."
        entity = make_entity(name, PIIEntityType.PERSON_NAME, 0)

        result1 = tokenizer.tokenize(
            text=f"{name} подписал",
            entities=[entity],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )
        result2 = tokenizer.tokenize(
            text=f"Подписант: {name}",
            entities=[make_entity(name, PIIEntityType.PERSON_NAME, 10)],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        # Первый вызов: 1 новая токенизация
        assert result1.entities_tokenized == 1
        # Второй вызов: переиспользование — не новая токенизация
        assert result2.entities_tokenized == 0

    def test_case_insensitive_normalization(self, tokenizer, policy):
        """
        "Иванов" и "иванов" (разный регистр) → один токен.
        Нормализация через .strip().lower().
        """
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        entity1 = make_entity("Иванов", PIIEntityType.PERSON_NAME, 0)
        entity2 = make_entity("иванов", PIIEntityType.PERSON_NAME, 0)

        result1 = tokenizer.tokenize(
            text="Иванов подписал",
            entities=[entity1],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )
        result2 = tokenizer.tokenize(
            text="иванов подписал",
            entities=[entity2],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        token1 = list(result1.mapping.keys())[0]
        token2 = list(result2.mapping.keys())[0]
        assert token1 == token2

    def test_global_mapping_no_collision(self, tokenizer, policy):
        """
        global_mapping.update() при переиспользовании токена не создаёт коллизию.
        Маппинг TOKEN → original должен быть консистентен.
        """
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}
        global_mapping: dict[str, str] = {}

        name = "Иванов И.И."

        for i, text in enumerate([
            f"{name} подписал договор",
            f"Представитель: {name}",
            f"Подпись: {name}",
        ]):
            start = text.index(name)
            entity = make_entity(name, PIIEntityType.PERSON_NAME, start)
            result = tokenizer.tokenize(
                text=text,
                entities=[entity],
                policy=policy,
                value_to_token=value_to_token,
                counters=doc_counters,
            )
            global_mapping.update(result.mapping)

        # Должен быть ровно один токен для "Иванов И.И."
        person_tokens = {k: v for k, v in global_mapping.items() if "PERSONNAME" in k}
        assert len(person_tokens) == 1, (
            f"Expected 1 token for same person, got {len(person_tokens)}: {person_tokens}"
        )
        token, original = next(iter(person_tokens.items()))
        assert original == name


# ─── Класс 2: backward compatibility — вызов без shared state ────────────────


class TestTokenizerBackwardCompatibility:
    """
    Вызов tokenize() без value_to_token / counters должен работать
    как раньше (локальный scope).
    """

    def test_tokenize_without_shared_state_works(self, tokenizer, policy):
        """Вызов без value_to_token → не падает, работает как раньше."""
        entity = make_entity("Иванов И.И.", PIIEntityType.PERSON_NAME, 0)
        result = tokenizer.tokenize(
            text="Иванов И.И. подписал",
            entities=[entity],
            policy=policy,
        )
        assert result.entities_tokenized == 1
        assert len(result.mapping) == 1

    def test_two_independent_calls_without_shared_state(self, tokenizer, policy):
        """
        Два независимых вызова без shared state ведут себя независимо.
        Это ожидаемое поведение для backward compatibility.
        """
        entity = make_entity("Иванов И.И.", PIIEntityType.PERSON_NAME, 0)

        result1 = tokenizer.tokenize(
            text="Иванов И.И. подписал",
            entities=[entity],
            policy=policy,
        )
        result2 = tokenizer.tokenize(
            text="Иванов И.И. подписал",
            entities=[entity],
            policy=policy,
        )

        # Без shared state — оба дают PERSONNAME1 (локальный счётчик с нуля)
        assert list(result1.mapping.keys()) == ["PERSONNAME1"]
        assert list(result2.mapping.keys()) == ["PERSONNAME1"]


# ─── Класс 3: mixed types через документ ─────────────────────────────────────


class TestMixedTypesAcrossDocument:
    """Несколько типов PII-сущностей через весь документ."""

    def test_phone_and_name_independent_counters(self, tokenizer, policy):
        """Счётчики для разных типов независимы: PERSONNAME1 и PHONE1."""
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        entity_name = make_entity("Иванов И.И.", PIIEntityType.PERSON_NAME, 0)
        entity_phone = make_entity("+7 999 123-45-67", PIIEntityType.PHONE, 0)

        result1 = tokenizer.tokenize(
            text="Иванов И.И. подписал",
            entities=[entity_name],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )
        result2 = tokenizer.tokenize(
            text="+7 999 123-45-67 позвонил",
            entities=[entity_phone],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        tokens = {**result1.mapping, **result2.mapping}
        assert "PERSONNAME1" in tokens
        assert "PHONE1" in tokens

    def test_same_phone_in_two_elements_gets_same_token(self, tokenizer, policy):
        """Один номер телефона в двух элементах → один токен."""
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        phone = "+7 999 123-45-67"

        entity1 = make_entity(phone, PIIEntityType.PHONE, 0)
        result1 = tokenizer.tokenize(
            text=f"Тел: {phone}",
            entities=[entity1],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        entity2 = make_entity(phone, PIIEntityType.PHONE, 5)
        result2 = tokenizer.tokenize(
            text=f"Факс: {phone}",
            entities=[entity2],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        token1 = list(result1.mapping.keys())[0]
        token2 = list(result2.mapping.keys())[0]
        assert token1 == token2


# ─── Класс 4: sanitized text корректность ────────────────────────────────────


class TestSanitizedTextCorrectness:
    """Проверяем что sanitized_text корректен при переиспользовании токенов."""

    def test_sanitized_text_contains_token_not_original(self, tokenizer, policy):
        """Sanitized text содержит токен, а не оригинальное значение."""
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        name = "Иванов"
        text = f"{name} подписал договор"
        entity = make_entity(name, PIIEntityType.PERSON_NAME, 0)

        result = tokenizer.tokenize(
            text=text,
            entities=[entity],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        assert name not in result.sanitized_text
        assert "PERSONNAME1" in result.sanitized_text

    def test_reused_token_in_sanitized_text(self, tokenizer, policy):
        """
        При переиспользовании токена sanitized_text второго элемента
        содержит тот же токен (PERSONNAME1), что и первый.
        """
        value_to_token: dict[str, str] = {}
        doc_counters: dict[str, int] = {}

        name = "Иванов"

        result1 = tokenizer.tokenize(
            text=f"{name} подписал договор",
            entities=[make_entity(name, PIIEntityType.PERSON_NAME, 0)],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )
        result2 = tokenizer.tokenize(
            text=f"Представитель: {name}",
            entities=[make_entity(name, PIIEntityType.PERSON_NAME, 15)],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        token_in_result1 = list(result1.mapping.keys())[0]
        token_in_result2 = list(result2.mapping.keys())[0]

        assert token_in_result1 == token_in_result2
        assert token_in_result1 in result1.sanitized_text
        assert token_in_result2 in result2.sanitized_text
        assert name not in result1.sanitized_text
        assert name not in result2.sanitized_text


        