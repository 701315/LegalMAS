"""
Unit-тесты для @model_validator(_sync_llm_context_limit) в Settings.

Используем model_validate() напрямую — Settings() является синглтоном,
поэтому для тестов создаём экземпляры через model_validate, минуя __new__.
"""
import logging
import pytest
from src.core.config import Settings


def _make_settings(**overrides) -> Settings:
    """
    Создаёт изолированный экземпляр Settings через model_validate,
    обходя синглтон и не читая .env (используем _env_file=None через extra).
    """
    # Передаём минимально необходимые поля + overrides
    # Остальные поля берут дефолты из класса
    return Settings.model_validate(
        {
            "LLM_PROVIDER": "llamacpp",
            "LLM_LOCAL_N_CTX": 8192,
            "LLM_CONTEXT_LIMIT": 8192,
            **overrides,
        }
    )


class TestSyncLlmContextLimit:

    def test_llamacpp_syncs_when_out_of_sync(self):
        """Рассинхрон: LLM_CONTEXT_LIMIT=4096, LLM_LOCAL_N_CTX=8192 → авто-исправление."""
        s = _make_settings(LLM_CONTEXT_LIMIT=4096, LLM_LOCAL_N_CTX=8192)
        assert s.LLM_CONTEXT_LIMIT == 8192

    def test_llamacpp_no_change_when_already_synced(self):
        """Нет рассинхрона → поле остаётся нетронутым."""
        s = _make_settings(LLM_CONTEXT_LIMIT=8192, LLM_LOCAL_N_CTX=8192)
        assert s.LLM_CONTEXT_LIMIT == 8192

    def test_llamacpp_syncs_custom_n_ctx(self):
        """Кастомный n_ctx=4096 в .env → LLM_CONTEXT_LIMIT тоже должен стать 4096."""
        s = _make_settings(
            LLM_CONTEXT_LIMIT=8192,  # дефолт в коде
            LLM_LOCAL_N_CTX=4096,    # переопределено в .env
        )
        assert s.LLM_CONTEXT_LIMIT == 4096

    def test_openai_context_limit_not_touched(self):
        """Для openai validator не трогает LLM_CONTEXT_LIMIT."""
        s = _make_settings(
            LLM_PROVIDER="openai",
            LLM_CONTEXT_LIMIT=4096,
            LLM_LOCAL_N_CTX=8192,
        )
        assert s.LLM_CONTEXT_LIMIT == 4096  # не изменился

    def test_ollama_context_limit_not_touched(self):
        """Для ollama validator не трогает LLM_CONTEXT_LIMIT."""
        s = _make_settings(
            LLM_PROVIDER="ollama",
            LLM_CONTEXT_LIMIT=2048,
            LLM_LOCAL_N_CTX=8192,
        )
        assert s.LLM_CONTEXT_LIMIT == 2048

    def test_warning_logged_on_desync(self, caplog):
        """При рассинхроне в лог пишется WARNING с обоими значениями."""
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            _make_settings(LLM_CONTEXT_LIMIT=4096, LLM_LOCAL_N_CTX=8192)
        assert "auto-syncing" in caplog.text
        assert "4096" in caplog.text
        assert "8192" in caplog.text

    def test_no_warning_when_synced(self, caplog):
        """При синхронизированных значениях WARNING не пишется."""
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            _make_settings(LLM_CONTEXT_LIMIT=8192, LLM_LOCAL_N_CTX=8192)
        assert "auto-syncing" not in caplog.text


        