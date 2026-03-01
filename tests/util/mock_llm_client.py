from typing import Optional

from src.engine.llm.client import LLMResponse


class MockLLMClient:
    """
    Простейший LLM-клиент-заглушка для тестов CheckRunner.

    - is_available() всегда возвращает False,
      поэтому LLMDetector просто не используется.
    - call(...) никогда не вызывается в таком режиме, но
      оставлен для совместимости интерфейса.
    """

    def __init__(self) -> None:
        self._available = False

    def is_available(self) -> bool:
        return self._available

    def call(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> Optional[LLMResponse]:
        # В этом mock-е мы не обращаемся к реальному LLM.
        # Возвращаем None, чтобы LLMDetector пропустил LLM-ветку.
        return None
