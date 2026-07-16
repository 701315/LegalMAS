"""
Тесты дефолтного поведения ROLE_MAP.

Ключевой инвариант после Patch 4.1:
- По умолчанию PII-слой токенизирует ФИО как PERSONNAME1, не как SELLER/BUYER.
- ROLE_MAP — explicit opt-in через PII_PRESERVE_PARTY_ROLES=True.
- Primary goal: privacy. Role resolution: downstream semantic layer.

Тесты написаны ДО правки чтобы зафиксировать ожидаемое поведение.
"""

import pytest
from unittest.mock import patch
from core.constants import PIIEntityType
from services.pii_detector import PIIEntity
from services.pii_tokenizer import PIIPolicy, PIITokenizer


@pytest.fixture
def tokenizer():
    return PIITokenizer()


def make_name_entity(text: str, full_text: str) -> PIIEntity:
    start = full_text.index(text)
    return PIIEntity(
        type=PIIEntityType.PERSON_NAME,
        start=start,
        end=start + len(text),
        text=text,
        confidence=0.9,
        source="ner",
    )


# ─── Класс 1: дефолты PIIPolicy ───────────────────────────────────────────────


class TestPIIPolicyDefaults:
    """Дефолтное состояние PIIPolicy без явных аргументов."""

    def test_default_use_role_map_is_false(self):
        """
        PIIPolicy() без аргументов → use_role_map=False.
        ROLE_MAP — opt-in, не opt-out.
        """
        policy = PIIPolicy()
        assert policy.use_role_map is False, (
            f"Expected use_role_map=False by default, got {policy.use_role_map}. "
            "ROLE_MAP must be explicit opt-in, not default behavior."
        )

    def test_default_person_name_action_is_tokenize(self):
        """
        По умолчанию PERSON_NAME → TOKENIZE, не ROLE_MAP.
        """
        policy = PIIPolicy()
        action = policy.get_action(PIIEntityType.PERSON_NAME)
        from core.constants import PIITokenPolicy
        assert action == PIITokenPolicy.TOKENIZE, (
            f"Expected TOKENIZE for PERSON_NAME by default, got {action}. "
            "Default must be privacy (tokenize), not role assignment."
        )


# ─── Класс 2: build_policy_from_triggers дефолты ─────────────────────────────


class TestBuildPolicyFromTriggersDefaults:
    """
    build_policy_from_triggers() с дефолтными settings.
    """

    def test_default_settings_give_no_role_map(self):
        """
        build_policy_from_triggers() с PII_PRESERVE_PARTY_ROLES=False
        → use_role_map=False даже при наличии triggers.
        """
        with patch("services.pii_tokenizer.settings") as mock_settings:
            mock_settings.PII_PRESERVE_PARTY_ROLES = False

            policy = PIITokenizer.build_policy_from_triggers(
                applicable_triggers=["parties_authority_cluster"],
            )

        assert policy.use_role_map is False, (
            f"Expected use_role_map=False when PII_PRESERVE_PARTY_ROLES=False, "
            f"got {policy.use_role_map}"
        )

    def test_no_triggers_gives_no_role_map_regardless_of_setting(self):
        """
        Нет triggers → use_role_map=False даже при PII_PRESERVE_PARTY_ROLES=True.
        Семантика: role map имеет смысл только когда есть классификационный контекст.
        """
        with patch("services.pii_tokenizer.settings") as mock_settings:
            mock_settings.PII_PRESERVE_PARTY_ROLES = True

            policy = PIITokenizer.build_policy_from_triggers(
                applicable_triggers=[],
            )

        assert policy.use_role_map is False

    def test_none_triggers_gives_no_role_map(self):
        """None triggers → use_role_map=False."""
        with patch("services.pii_tokenizer.settings") as mock_settings:
            mock_settings.PII_PRESERVE_PARTY_ROLES = True

            policy = PIITokenizer.build_policy_from_triggers(
                applicable_triggers=None,
            )

        assert policy.use_role_map is False

    def test_explicit_opt_in_with_triggers_enables_role_map(self):
        """
        Явный opt-in: PII_PRESERVE_PARTY_ROLES=True + triggers → use_role_map=True.
        Это документирует что opt-in всё ещё работает.
        """
        with patch("services.pii_tokenizer.settings") as mock_settings:
            mock_settings.PII_PRESERVE_PARTY_ROLES = True

            policy = PIITokenizer.build_policy_from_triggers(
                applicable_triggers=["parties_authority_cluster"],
            )

        assert policy.use_role_map is True

    def test_explicit_preserve_party_roles_false_overrides_setting(self):
        """
        Явный preserve_party_roles=False в аргументе → use_role_map=False,
        независимо от settings.
        """
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=["parties_authority_cluster"],
            preserve_party_roles=False,
        )
        assert policy.use_role_map is False


# ─── Класс 3: runtime поведение токенизатора по умолчанию ────────────────────


class TestDefaultTokenizationBehavior:
    """
    По умолчанию person names токенизируются как PERSONNAMEn,
    даже если рядом есть роль.
    """

    def test_person_name_becomes_personname_not_seller_by_default(
        self, tokenizer
    ):
        """
        ГЛАВНЫЙ ТЕСТ PATCH 4.1.
        Рядом с именем есть 'Продавец', но по умолчанию роль не назначается.
        Имя → PERSONNAME1, а не SELLER.
        """
        text = "именуемый Продавец, Иванов И.И."
        name = "Иванов И.И."
        entity = make_name_entity(name, text)

        # Дефолтная политика — без явного use_role_map=True
        policy = PIIPolicy()

        result = tokenizer.tokenize(
            text=text,
            entities=[entity],
            policy=policy,
        )

        assert "PERSONNAME1" in result.mapping, (
            "Expected PERSONNAME1 in mapping by default"
        )
        assert "SELLER" not in result.mapping, (
            f"SELLER should not appear in default mode. "
            f"Got mapping: {result.mapping}"
        )
        assert result.entities_role_mapped == 0
        assert result.entities_tokenized == 1

    def test_two_parties_both_get_personname_by_default(self, tokenizer):
        """
        Два участника — оба получают PERSONNAMEn, не SELLER/BUYER.
        Downstream может сам определить роли.
        """
        text = "Продавец Иванов И.И. и Покупатель Петров П.П."

        entity_ivanov = make_name_entity("Иванов И.И.", text)
        entity_petrov = make_name_entity("Петров П.П.", text)

        policy = PIIPolicy()
        value_to_token: dict = {}
        doc_counters: dict = {}

        result1 = tokenizer.tokenize(
            text="Продавец Иванов И.И.",
            entities=[make_name_entity("Иванов И.И.", "Продавец Иванов И.И.")],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )
        result2 = tokenizer.tokenize(
            text="Покупатель Петров П.П.",
            entities=[make_name_entity("Петров П.П.", "Покупатель Петров П.П.")],
            policy=policy,
            value_to_token=value_to_token,
            counters=doc_counters,
        )

        all_tokens = {**result1.mapping, **result2.mapping}

        assert "SELLER" not in all_tokens
        assert "BUYER" not in all_tokens
        assert "PERSONNAME1" in all_tokens
        assert "PERSONNAME2" in all_tokens

    def test_role_words_stay_in_sanitized_text(self, tokenizer):
        """
        Слова ролей (Продавец, Покупатель) НЕ удаляются из текста.
        Они не PII. Downstream их читает для определения ролей.
        """
        text = "Продавец Иванов И.И. передаёт право"
        name = "Иванов И.И."
        entity = make_name_entity(name, text)
        policy = PIIPolicy()

        result = tokenizer.tokenize(
            text=text,
            entities=[entity],
            policy=policy,
        )

        assert "Продавец" in result.sanitized_text, (
            "Role word 'Продавец' should remain in sanitized text — it is not PII"
        )
        assert name not in result.sanitized_text
        assert "PERSONNAME1" in result.sanitized_text


# ─── Класс 4: opt-in всё ещё работает ────────────────────────────────────────


class TestRoleMapOptIn:
    """
    Явный opt-in через use_role_map=True сохраняет поведение.
    Это regression guard: proximity tests не должны сломаться.
    """

    def test_explicit_role_map_still_assigns_seller(self, tokenizer):
        """Явный opt-in → SELLER назначается как раньше."""
        text = "именуемый Продавец, Иванов И.И."
        name = "Иванов И.И."
        entity = make_name_entity(name, text)

        policy = PIIPolicy(use_role_map=True)

        result = tokenizer.tokenize(
            text=text,
            entities=[entity],
            policy=policy,
        )

        assert "SELLER" in result.mapping
        assert result.entities_role_mapped == 1

    def test_default_false_does_not_affect_explicit_true(self, tokenizer):
        """
        Смена дефолта не влияет на явный use_role_map=True.
        Backward compatible для кода, который явно включает opt-in.
        """
        policy_default = PIIPolicy()
        policy_explicit = PIIPolicy(use_role_map=True)

        assert policy_default.use_role_map is False
        assert policy_explicit.use_role_map is True


        