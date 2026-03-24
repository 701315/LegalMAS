# src/classifiers/base.py

"""
Базовые классы для каскада классификации документов.

Каскад состоит из четырёх уровней:
  L1 — rule-based: имя файла, путь к папке, простые паттерны.
  L2 — header/keywords: заголовок и ключевые слова/regex из YAML.
  L3 — semantic: эмбеддинги и косинусное сходство с прототипами типов.
  L4 — LLM: крупная языковая модель, используется только как резервный вариант.

applicable_triggers:
  - Список идентификаторов триггеров, актуальных для найденного типа документа.
  - Загружается из блока trigger_definitions в YAML-конфиге типа.
  - Используется Runner’ом (Stage 8), чтобы решать, какие проверки из каталога
    запускать для данного документа (условная маршрутизация проверок).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.constants import ClassificationLevel


@dataclass
class ClassificationResult:
    """
    Результат работы одного уровня классификации (L1–L4).

    Поля:
    - doctype   : код типа документа (например, "contract_1.6_real_estate" или "UNKNOWN").
    - confidence: уверенность уровня в диапазоне 0.0–1.0.
    - level     : уровень каскада (L1, L2, L3, L4).
    - method    : человекочитаемое описание метода (например, "filename", "header_pattern").
    - language  : предполагаемый язык документа (по умолчанию "ru").
    - jurisdiction: предполагаемая юрисдикция (по умолчанию "RU").
    - evidence  : текстовая «улика»/объяснение (паттерн, cosine_sim и т.п.).
    - alternative_types: альтернативные типы с более низкой уверенностью (опционально).
    """

    doctype: str
    confidence: float
    level: ClassificationLevel
    method: str
    language: str = "ru"
    jurisdiction: str = "RU"
    evidence: str | None = None
    alternative_types: list = field(default_factory=list)
    extra: dict | None = None


@dataclass
class FinalClassification:
    """
    Финальный результат классификации после прохождения всего каскада.

    Эти поля сохраняются в сущность Document в базе данных:

      - doctype             → Document.doctype
      - confidence          → Document.classification_confidence
      - level               → Document.classification_level
      - language            → Document.language
      - jurisdiction        → Document.jurisdiction_guess
      - details             → Document.classification_details
      - applicable_triggers → Document.applicable_triggers

    applicable_triggers:
      - Управляют маршрутизацией в Runner:
        по этому списку выбираются проверки из каталога, которые надо запускать
        для конкретного документа (например, проверки для ипотеки, маткапитала,
        наследственного титула и т.п.).
    """

    doctype: str
    confidence: float
    level: ClassificationLevel
    language: str
    jurisdiction: str
    details: dict
    applicable_triggers: list = field(default_factory=list)


class BaseClassifier(ABC):
    """
    Базовый интерфейс для классификаторов уровней L1–L3.

    Все реализации должны:
    - иметь свойство level (возвращает ClassificationLevel),
    - реализовать асинхронный метод classify(...) и возвращать ClassificationResult.
    """

    @property
    @abstractmethod
    def level(self) -> ClassificationLevel:
        """Уровень каскада, к которому относится классификатор (L1, L2 или L3)."""
        pass

    @abstractmethod
    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        """
        Выполнить классификацию на конкретном уровне.

        Параметры:
        - text          : текст документа или его часть, с которой работает уровень.
        - filename      : имя файла (может учитываться на L1/L2/L3 по усмотрению реализации).
        - folder_path   : путь к папке (для L1/L2).
        - text_sanitized: очищенный текст (для L4/облачных провайдеров, здесь обычно не нужен).
        - metadata      : доп. данные от других уровней (по необходимости).

        Возвращает:
        - объект ClassificationResult с итогом работы данного уровня.
        """
        pass


class BaseLLMClassifier(BaseClassifier):
    """
    Базовый интерфейс для L4‑классификаторов на базе LLM.

    Реализации:
    - LocalLLMClassifier (локальная GGUF‑модель),
    - OpenAIClassifier (облачный провайдер),
    - AnthropicClassifier (облачный провайдер).

    Требования к безопасности:
    - Облачные провайдеры ДОЛЖНЫ получать только очищенный текст (text_sanitized),
      без персональных данных и чувствительной информации.
    - Локальные провайдеры МОГУТ работать с сырым текстом, так как модель крутится
      на контролируемом окружении и не отправляет данные наружу.
    """

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L4_LLM

    @abstractmethod
    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        """
        Выполнить классификацию документа на уровне L4 (через LLM).

        Конкретная реализация сама решает:
        - использовать ли text или text_sanitized,
        - как формировать промпт для LLM,
        - как парсить ответ и преобразовывать его в ClassificationResult.
        """
        pass
