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

Профиль документа:
  - Под «профилем документа» мы понимаем пару:
      (doc_type, applicable_triggers).
  - doc_type задаёт базовый тип (например, "contract_1.6_real_estate").
  - applicable_triggers описывает сценарии, которые актуальны для этого документа:
      ипотека, маткапитал, судебная продажа, сельхозземля, наследственный титул и т.п.
  - Именно профиль документа потом использует движок проверок (CheckRunner),
    чтобы выбрать, какие проверки запускать и как формировать DD Grid.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.constants import ClassificationLevel


@dataclass
class ClassificationResult:
    """
    Результат работы одного уровня классификации (L1–L4).

    Для непрофессионального программиста:
    - Классификация идёт по уровням (L1, L2, L3, L4).
    - Каждый уровень возвращает свой промежуточный результат, который
      агрегируется в финальное решение (HybridClassifier).

    Поля:
    - doctype          : код типа документа (например, "contract_1.6_real_estate" или "UNKNOWN").
    - confidence       : уверенность уровня в диапазоне 0.0–1.0.
    - level            : уровень каскада (L1, L2, L3, L4).
    - method           : человекочитаемое описание метода (например, "filename", "header_pattern").
    - language         : предполагаемый язык документа (по умолчанию "ru").
    - jurisdiction     : предполагаемая юрисдикция (по умолчанию "RU").
    - evidence         : текстовая «улика»/объяснение (паттерн, cosine_sim и т.п.).
    - alternative_types: альтернативные типы с более низкой уверенностью (опционально).
    - extra            : произвольный словарь с дополнительными данными уровня.

    applicable_triggers:
    - Список триггеров, которые уровень считает релевантными данному типу.
    - Обычно наполняется на этапе финальной агрегации (HybridClassifier),
      используя YAML trigger_definitions для выбранного doc_type.
    - В сумме с doc_type эти триггеры участвуют в формировании общего
      профиля документа.
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
    applicable_triggers: list = field(default_factory=list)


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

    Структура details/candidates (см. HybridClassifier.classify_document):

      {
        "levels_tried": ["L1", "L2", "L3", "L4"],
        "L1": {
          "type": "contract.real_estate",
          "confidence": 0.8,
          "method": "filename",
          "details": {...}
        },
        "L2": {...},
        "L3": {...},
        "L4": {...},  # если L4 вызывался
        "voting": {
          "strategy": "L1_L2_AGREE" | "L2_STRONG_WINS" | "HYBRID",
          "type": "contract.real_estate",
          "confidence": 0.82
        },
        "voting_override": {
          "strategy": "L1_OVERRIDE_L3",
          "original_voted": {...}
        },
        "candidates": [
          {
            "type_code": "contract.real_estate",
            "confidence": 0.82,
            "level": "L2",
            "method": "header_pattern"
          },
          ...
        ],
        "confidence_zone": "confident" | "low" | "unknown",
        "requires_manual_review": true | false
      }

    applicable_triggers:
      - Управляют маршрутизацией в Runner:
        по этому списку выбираются проверки из каталога, которые надо запускать
        для конкретного документа (например, проверки для ипотеки, маткапитала,
        наследственного титула и т.п.).
      - Строятся на основе trigger_definitions в YAML-конфиге типа документа
        через YAMLRegistry / DocumentTypeConfig и фактических срабатываний
        TriggerDetector (семья, текст).
      - В паре с doctype образуют «профиль документа», который дальнейший
        движок проверок использует для выбора рисков и формирования DD Grid.
    """

    doctype: str
    confidence: float
    level: ClassificationLevel
    language: str
    jurisdiction: str
    details: dict
    applicable_triggers: list = field(default_factory=list)


@dataclass
class HybridClassificationCandidate:
    """
    Один кандидат из агрегированного списка candidates HybridClassifier.

    Структура соответствует элементу из HybridClassifier.classify_document(...):

        {
            "doctype": "contract_1.6_real_estate",
            "confidence": 0.91,
            "level": "L2",
            "method": "header_keyword_high",
            "evidence": "...",
            # опционально:
            # "language": "ru",
            # "jurisdiction": "RU",
            # "raw_similarity": 0.82,
        }

    Для непрофессионального программиста:
    - Это просто «строчка» в длинном списке возможных типов документов.
    - Финальное решение выбирает один тип (final_type), но все кандидаты
      сохраняются в details для прозрачности и отладки.
    """

    doctype: str
    confidence: float
    level: str  # "L1", "L2", "L3", "L4"
    method: str | None = None
    evidence: str | None = None
    language: str | None = None
    jurisdiction: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HybridClassificationResultDTO:
    """
    Формальный DTO для результата HybridClassifier.classify_document().

    ВАЖНО:
    - HybridClassifier по-прежнему возвращает обычный dict.
    - Структура этого dict должна соответствовать этому dataclass-у.
    - Используется как контракт между classifier worker, Runner и API.

    Профиль документа:
        Пара (final_type, applicable_triggers) — это «профиль документа».

        final_type:
          - строковый код типа документа (например, "contract_1.6_real_estate");
          - None или "UNKNOWN" означает, что тип не определён.

        applicable_triggers:
          - список идентификаторов триггеров из YAML (trigger_definitions);
          - учитывает и «теоретически возможные» триггеры по типу,
            и реально сработавшие триггеры из TriggerDetector;
          - используется DocTypeCheckLoader/Runner для выбора checks.

    Зоны уверенности (details["confidence_zone"]):
        - "confident" : final_confidence >= CLASSIFIER_ACCEPT_THRESHOLD
        - "low"       : UNKNOWN_THRESHOLD < final_confidence < ACCEPT_THRESHOLD
        - "unknown"   : final_confidence <= UNKNOWN_THRESHOLD

    requires_manual_review (details["requires_manual_review"]):
        - True, если зона "low" или "unknown";
        - False, если зона "confident".

    Структура details:
        {
            "L1": {...},               # результат L1 (если запускался)
            "L2": {...},               # результат L2
            "L3": {...},               # результат L3
            "L4": {                     # результат L4/LLM (если вызывался)
                "type": "contract_1.6_real_estate" | "UNKNOWN",
                "confidence": 0.72,
                "method": "llm" | "llm_error",
                "reasoning": "краткое объяснение",
                "parse_success": true | false,
                "raw": {
                    "provider": "llamacpp" | "openai" | "...",
                    "model": "...",
                    "tokens_used": 123,
                    "parse_success": true | false,
                    "error_type": null | "parse_error" | "unexpected_exception",
                    "error_message": null | "текст ошибки",
                    "response_text": "... сырой текст ответа LLM ...",
                    "parsed_json": {        # если парсинг JSON удался
                        "type_code": "contract_1.6_real_estate" | "UNKNOWN" | null,
                        "confidence": 0.72,
                        "reasoning": "краткое объяснение"
                    } | null
                }
            },
            "MASTERCOPY": {...},       # если решение скопировано из master-документа
            "voting": {...},           # детали голосования L1/L2/L3
            "voting_override": {...},  # если был override (например, L1_OVERRIDE_L3)
            "candidates": [...],       # список кандидатов (дублирует верхнеуровневое поле)
            "confidence_zone": "confident" | "low" | "unknown",
            "requires_manual_review": true | false
        }
    """

    final_type: str | None = None
    final_confidence: float = 0.0
    level: str | None = None  # "L1","L2","L3","L4","HYBRID","COPIED",None
    language: str | None = None
    jurisdiction: str | None = None
    applicable_triggers: list[str] = field(default_factory=list)
    levels_tried: list[str] = field(default_factory=list)
    candidates: list[HybridClassificationCandidate] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


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
