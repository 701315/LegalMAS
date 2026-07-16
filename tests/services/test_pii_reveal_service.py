"""
Тесты PIIRevealService.

Проверяем:
1. Корректная обратная подстановка токенов
2. Пустой mapping → layout не изменяется
3. Частичный mapping (не все токены в тексте)
4. Недоступный sanitized layout → PIIRevealError
5. Недоступный pii_mapping → PIIRevealError
6. Повреждённый mapping (не дешифруется) → PIIRevealError
7. Round-trip: encrypt → store → load → decrypt → substitute
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import PermanentError
from services.pii_encryption import PIIEncryptor
from services.pii_reveal_service import PIIRevealError, _substitute_tokens, reveal_document_pii


# ─── Fixtures ────────────────────────────────────────────────────────────────

VALID_KEY = PIIEncryptor.generate_key()
DOC_ID = uuid.uuid4()


def make_layout(*texts: str) -> dict:
    """Создать минимальный layout с заданными текстами."""
    return {
        "elements": [
            {"element_id": f"e{i}", "page": 1, "text": text}
            for i, text in enumerate(texts)
        ]
    }


def make_store(layout: dict | None = None, mapping_bytes: bytes | None = None) -> MagicMock:
    """Создать mock ArtifactStore с заданными данными."""
    store = MagicMock()
    if layout is not None:
        store.get_json.return_value = layout
    if mapping_bytes is not None:
        store.get_file.return_value = mapping_bytes
    return store


# ─── _substitute_tokens unit tests ───────────────────────────────────────────


class TestSubstituteTokens:
    """Unit tests для _substitute_tokens()."""

    def test_basic_substitution(self):
        """Базовая замена: один токен → оригинал."""
        layout = make_layout("PERSONNAME1 подписал договор")
        mapping = {"PERSONNAME1": "Иванов И.И."}
        result = _substitute_tokens(layout, mapping)
        assert result["elements"][0]["text"] == "Иванов И.И. подписал договор"

    def test_multiple_tokens_in_one_element(self):
        """Несколько токенов в одном элементе."""
        layout = make_layout("PERSONNAME1 и PERSONNAME2 заключили договор")
        mapping = {
            "PERSONNAME1": "Иванов И.И.",
            "PERSONNAME2": "Петров П.П.",
        }
        result = _substitute_tokens(layout, mapping)
        assert "Иванов И.И." in result["elements"][0]["text"]
        assert "Петров П.П." in result["elements"][0]["text"]

    def test_tokens_across_multiple_elements(self):
        """Один токен встречается в нескольких элементах."""
        layout = make_layout(
            "Продавец PERSONNAME1",
            "Подпись: PERSONNAME1",
        )
        mapping = {"PERSONNAME1": "Иванов И.И."}
        result = _substitute_tokens(layout, mapping)
        assert result["elements"][0]["text"] == "Продавец Иванов И.И."
        assert result["elements"][1]["text"] == "Подпись: Иванов И.И."

    def test_empty_mapping_returns_layout_unchanged(self):
        """Пустой mapping → layout не изменяется."""
        layout = make_layout("PERSONNAME1 подписал")
        result = _substitute_tokens(layout, {})
        assert result["elements"][0]["text"] == "PERSONNAME1 подписал"

    def test_token_not_present_in_text(self):
        """Токен из mapping не встречается в тексте → текст не меняется."""
        layout = make_layout("обычный текст без токенов")
        mapping = {"PERSONNAME1": "Иванов"}
        result = _substitute_tokens(layout, mapping)
        assert result["elements"][0]["text"] == "обычный текст без токенов"

    def test_does_not_mutate_input_layout(self):
        """_substitute_tokens не мутирует входной layout."""
        original_text = "PERSONNAME1 подписал"
        layout = make_layout(original_text)
        mapping = {"PERSONNAME1": "Иванов И.И."}
        _substitute_tokens(layout, mapping)
        # Оригинал не изменён
        assert layout["elements"][0]["text"] == original_text

    def test_element_without_text_preserved(self):
        """Элемент без поля text сохраняется как есть."""
        layout = {"elements": [{"element_id": "e0", "page": 1}]}
        mapping = {"PERSONNAME1": "Иванов"}
        result = _substitute_tokens(layout, mapping)
        assert result["elements"][0].get("text", "") == ""

    def test_preserves_non_element_fields(self):
        """Поля верхнего уровня (кроме elements) не теряются."""
        layout = {
            "elements": [{"element_id": "e0", "page": 1, "text": "PERSONNAME1"}],
            "metadata": {"language": "ru"},
            "version": "v2",
        }
        mapping = {"PERSONNAME1": "Иванов"}
        result = _substitute_tokens(layout, mapping)
        assert result["metadata"] == {"language": "ru"}
        assert result["version"] == "v2"

    def test_prefix_collision_longer_tokens_replaced_first(self):
        """
        Более длинные токены должны заменяться раньше коротких,
        иначе PERSONNAME10 может частично сломаться через PERSONNAME1.
        """
        layout = make_layout("PERSONNAME10 подписал вместе с PERSONNAME1")
        mapping = {
            "PERSONNAME1": "Иванов И.И.",
            "PERSONNAME10": "Петров П.П.",
        }

        result = _substitute_tokens(layout, mapping)

        assert result["elements"][0]["text"] == (
            "Петров П.П. подписал вместе с Иванов И.И."
        )


# ─── reveal_document_pii integration tests ───────────────────────────────────


class TestRevealDocumentPII:
    """Integration tests для reveal_document_pii()."""

    @pytest.mark.asyncio
    async def test_successful_reveal_roundtrip(self):
        """
        Round-trip: encrypt mapping → store → load → decrypt → substitute.
        Главный тест: confirm что весь reveal-поток работает корректно.
        """
        encryptor = PIIEncryptor(VALID_KEY)
        original_mapping = {
            "PERSONNAME1": "Иванов И.И.",
            "PHONE1": "+7 999 123-45-67",
        }
        encrypted_mapping = encryptor.encrypt_mapping(original_mapping)

        sanitized_layout = make_layout(
            "PERSONNAME1 подписал договор",
            "Тел: PHONE1",
        )

        store = make_store(
            layout=sanitized_layout,
            mapping_bytes=encrypted_mapping,
        )

        result = await reveal_document_pii(
            store=store,
            encryptor=encryptor,
            sanitized_layout_ref="s3://bucket/sanitized.json",
            pii_mapping_ref="s3://bucket/mapping.enc",
            document_id=DOC_ID,
        )

        assert result["elements"][0]["text"] == "Иванов И.И. подписал договор"
        assert result["elements"][1]["text"] == "Тел: +7 999 123-45-67"

    @pytest.mark.asyncio
    async def test_sanitized_layout_not_found_raises_reveal_error(self):
        """Недоступный sanitized layout → PIIRevealError."""
        store = MagicMock()
        store.get_json.side_effect = PermanentError("not found")

        with pytest.raises(PIIRevealError, match="Sanitized layout not found"):
            await reveal_document_pii(
                store=store,
                sanitized_layout_ref="s3://bucket/missing.json",
                pii_mapping_ref="s3://bucket/mapping.enc",
                document_id=DOC_ID,
            )

    @pytest.mark.asyncio
    async def test_pii_mapping_not_found_raises_reveal_error(self):
        """Недоступный PII mapping → PIIRevealError."""
        encryptor = PIIEncryptor(VALID_KEY)
        store = MagicMock()
        store.get_json.return_value = make_layout("text")
        store.get_file.side_effect = PermanentError("not found")

        with pytest.raises(PIIRevealError, match="PII mapping not found"):
            await reveal_document_pii(
                store=store,
                encryptor=encryptor,
                sanitized_layout_ref="s3://bucket/sanitized.json",
                pii_mapping_ref="s3://bucket/missing.enc",
                document_id=DOC_ID,
            )

    @pytest.mark.asyncio
    async def test_corrupted_mapping_raises_reveal_error(self):
        """Повреждённый mapping (не дешифруется) → PIIRevealError."""
        encryptor = PIIEncryptor(VALID_KEY)
        store = MagicMock()
        store.get_json.return_value = make_layout("text")
        store.get_file.return_value = b"not-encrypted-data"

        with pytest.raises(PIIRevealError, match="Failed to decrypt"):
            await reveal_document_pii(
                store=store,
                encryptor=encryptor,
                sanitized_layout_ref="s3://bucket/sanitized.json",
                pii_mapping_ref="s3://bucket/mapping.enc",
                document_id=DOC_ID,
            )

    @pytest.mark.asyncio
    async def test_empty_mapping_returns_layout_unchanged(self):
        """Пустой mapping (нет PII в документе) → layout возвращается как есть."""
        encryptor = PIIEncryptor(VALID_KEY)
        empty_encrypted = encryptor.encrypt_mapping({})
        original_text = "Договор купли-продажи без персональных данных"

        store = make_store(
            layout=make_layout(original_text),
            mapping_bytes=empty_encrypted,
        )

        result = await reveal_document_pii(
            store=store,
            encryptor=encryptor,
            sanitized_layout_ref="s3://bucket/sanitized.json",
            pii_mapping_ref="s3://bucket/mapping.enc",
            document_id=DOC_ID,
        )

        assert result["elements"][0]["text"] == original_text

    @pytest.mark.asyncio
    async def test_dev_mode_plaintext_mapping_works(self):
        """
        Dev-режим: mapping хранится в plaintext (encryptor без ключа).
        Reveal должен работать с plaintext mapping.
        """
        dev_encryptor = PIIEncryptor("")
        mapping = {"PERSONNAME1": "Тестов Т.Т."}
        plaintext_mapping = dev_encryptor.encrypt_mapping(mapping)

        store = make_store(
            layout=make_layout("Подписант: PERSONNAME1"),
            mapping_bytes=plaintext_mapping,
        )

        result = await reveal_document_pii(
            store=store,
            encryptor=dev_encryptor,
            sanitized_layout_ref="s3://bucket/sanitized.json",
            pii_mapping_ref="s3://bucket/mapping.enc",
            document_id=DOC_ID,
        )

        assert result["elements"][0]["text"] == "Подписант: Тестов Т.Т."


        