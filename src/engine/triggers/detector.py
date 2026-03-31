# src/engine/triggers/detector.py

"""
Trigger detector: использует Stage 7 relations/families и YAML trigger_definitions.

Назначение:
- Определить, какие триггеры ДЕЙСТВИТЕЛЬНО сработали для конкретного документа.
- Работает на основе:
  1) Семейных связей документа (Stage 7 relations/families, RunnerRepository).
  2) Текстового содержимого документа (чанки через DocumentContentService).
  3) YAML-инструкций по типу документа (trigger_definitions в DocumentTypeConfig).

Важно:
- Сами триггеры (их идентификаторы и правила) описываются в YAML-файлах типов
  документов в блоке trigger_definitions.
- Этот класс НИЧЕГО не «знает» про конкретные триггеры (mortgage_related,
  residential_property и т.п.) — он только применяет общие правила:
    * family_*  — условия по семье документов,
    * any_keywords / text_any — условия по тексту (чанкам),
    * (в будущем) другие виды условий (по структуре, ролям сторон и т.д.).

Профиль документа:
- Классификатор (HybridClassifier) определяет doc_type и базовый набор
  applicable_triggers по YAML-конфигу типа.
- TriggerDetector дополняет applicable_triggers, проверяя:
    * семейный контекст (relations/families),
    * фактический текст документа (по чанкам).
- В итоге пара (doc_type, applicable_triggers) образует «профиль документа».
- Этот профиль затем использует CheckRunner, чтобы выбрать, какие проверки
  запускать для документа (ипотека, маткапитал, судебные торги и т.п.).

Контракт:
- На вход получает ORM Document (как минимум с полями id и doc_type).
- На выход возвращает список строк-триггеров (их ID из trigger_definitions),
  которые нашли подтверждение по правилам.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

from classifiers.yaml_registry import YAMLRegistry
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from engine.content.document_content_service import (
    ClauseTreeStorageClient,
    DocumentContentService,
)

logger = get_logger(__name__)


class TriggerDetector:
    """
    Определяет applicable_triggers документа на основе:
    - семей документов (Stage 7 relations/families, RunnerRepository),
    - текстового содержимого (чанки),
    - правил из YAML trigger_definitions.

    Для непрофессионального программиста:
    - Сюда не «зашиты» конкретные типы триггеров.
    - Все конкретные триггеры (mortgage_related, residential_property и т.п.)
      описываются в YAML, а этот класс просто применяет общие правила
      (по семье и по тексту).

    Роль в профиле документа:
    - Классификатор задаёт базовый список applicable_triggers для doc_type
      (какие сценарии В ПРИНЦИПЕ возможны для этого типа).
    - TriggerDetector проверяет, какие из этих триггеров реально проявляются
      в конкретном документе (по семье и тексту) и возвращает фактически
      сработавшие триггеры.
    - В совокупности doc_type и итоговый applicable_triggers составляют
      «профиль документа», которым дальше пользуются CheckRunner и UI.
    """

    def __init__(self, uow) -> None:
        """
        uow: твой UnitOfWork с async Session (db_uow()).

        Мы сохраняем:
        - uow.session   → для работы с базой через RunnerRepository,
        - YAMLRegistry  → чтобы читать конфиг типа документа из YAML,
        - DocumentContentService → чтобы получать чанки текста документа.
        """
        self.uow = uow
        self.repo = RunnerRepository(uow.session)
        self.registry = YAMLRegistry.get_instance()
        self.content_service = DocumentContentService(
            uow.session,
            ClauseTreeStorageClient(),
        )

    async def detect_triggers(self, doc) -> List[str]:
        """
        Определить список триггеров для документа.

        Args:
            doc: ORM Document (из uow.documents). Ожидается, что у него есть:
                 - id       : UUID/str,
                 - doc_type : строка с кодом типа документа (может быть пустой).

        Returns:
            Отсортированный список уникальных строк-триггеров (их ID из YAML).
        """
        triggers: List[str] = []

        # 1. Определяем конфигурацию типа документа из YAMLRegistry.
        doc_type = getattr(doc, "doc_type", "") or ""
        cfg = self.registry.get_config(doc_type) if doc_type else None

        if not cfg or not getattr(cfg, "trigger_definitions", None):
            # Если для типа нет trigger_definitions, считаем, что триггеры
            # по YAML не применимы. Логи оставляем, чтобы было видно в отладке.
            logger.debug(
                "TriggerDetector: no trigger_definitions for doc_type",
                doc_id=str(doc.id),
                doc_type=doc_type,
            )
            unique = sorted(set(triggers))
            logger.debug("Triggers detected", doc_id=str(doc.id), triggers=unique)
            return unique

        trigger_defs: Dict[str, Any] = cfg.trigger_definitions or {}

        # 2. Получаем семейный контекст документа (relations/families).
        #    Раньше здесь был хардкод для mortgage_related,
        #    теперь эта логика описывается в YAML через family_* условия.
        family = await self.repo.get_document_family(doc.id) or []

        # Для удобства соберём множество doc_type членов семьи.
        family_types: Set[str] = {
            getattr(m, "doc_type", "") or "" for m in family
        }

        # 3. Получаем текст документа в виде чанков через DocumentContentService.
        #    Для непрофессионального программиста:
        #    - Чанк — это логический кусочек текста (параграф, клауза и т.п.),
        #      который уже используется в CheckRunner и HybridDetector.
        #    - Здесь нам важно просто иметь список текстов, по которым можно
        #      искать ключевые слова/regex из trigger_definitions.
        try:
            chunks: List[Dict[str, Any]] = await self.content_service.get_sized_chunks(
                doc.id
            )
        except Exception as e:
            logger.warning(
                "TriggerDetector: failed to fetch chunks, falling back to empty text",
                doc_id=str(doc.id),
                error=str(e),
            )
            chunks = []

        # Важно: не переводим текст в lower здесь, потому что regex из YAML
        # уже могут содержать (?i) и другие флаги, которые сами управляют
        # чувствительностью к регистру.
        chunk_texts: List[str] = [
            ch.get("text") or "" for ch in (chunks or []) if ch.get("text")
        ]

        # 4. Применяем правила trigger_definitions к семье и чанкам.
        triggers.extend(
            self._detect_triggers_from_yaml(
                trigger_defs=trigger_defs,
                family_types=family_types,
                chunk_texts=chunk_texts,
            )
        )

        unique = sorted(set(triggers))
        logger.debug("Triggers detected", doc_id=str(doc.id), triggers=unique)
        return unique

    def _detect_triggers_from_yaml(
        self,
        trigger_defs: Dict[str, Any],
        family_types: Set[str],
        chunk_texts: List[str],
    ) -> List[str]:
        """
        Пробегает по trigger_definitions и проверяет, какие триггеры сработали.

        Ожидаемый базовый формат trigger_definitions в YAML (с учётом твоего файла):

            trigger_definitions:
              residential_property:
                any_keywords:
                  - "(?i)квартир[аеиу]"
                  - "(?i)жил[оаые]\\s+дом"
                  - "(?i)комнат[аеиу]"
                  - "(?i)жилое\\s+помещени[еи]"

              land_plot_sale:
                any_keywords:
                  - "(?i)земельн[а-я\\s]*участ"
                  - "(?i)категор(ия|ии)\\s+земел"
                  - "(?i)вид\\s+разрешенн[оа\\s]*использовани[ея]"
                  - "(?i)\\bВРИ\\b"

              mortgage_related:
                family_doc_types_any:
                  - "MORTGAGE_AGREEMENT"
                  - "PLEDGE"
                any_keywords:
                  - "(?i)ипотек[аеи]"
                  - "(?i)залог"
                  - "(?i)закладн(ая|ой)"
                  - "(?i)обременен[ияи]"

        Для непрофессионального программиста:
        - Для каждого trigger_id мы смотрим, выполняются ли условия:
            * family_doc_types_any: хотя бы один doc_type из семьи совпадает,
            * any_keywords / text_any: хотя бы один regex нашёл совпадение
              в каком-либо чанке текста.
        - Если условия выполняются, триггер считается «сработавшим» и
          добавляется в список.
        """
        matched: List[str] = []

        for trig_id, spec in (trigger_defs or {}).items():
            spec = spec or {}

            # --- 1. Семейные условия: family_doc_types_any ---
            fam_any: Iterable[str] = spec.get("family_doc_types_any") or []
            fam_any_clean = {str(t).strip() for t in fam_any if str(t).strip()}
            if fam_any_clean:
                # Если в семье есть хотя бы один doc_type из fam_any_clean,
                # считаем триггер сработавшим.
                if family_types.intersection(fam_any_clean):
                    matched.append(trig_id)
                    # Для простоты: если семейное условие выполнилось,
                    # дальше текстовые условия можно не проверять.
                    continue

            # --- 2. Текстовые условия: any_keywords / text_any (по чанкам) ---
            # Поддерживаем оба ключа:
            # - any_keywords  — фактический формат, который у тебя уже есть;
            # - text_any      — алиас на будущее, если захочешь переименовать.
            text_patterns: Iterable[str] = (
                spec.get("text_any") or spec.get("any_keywords") or []
            )

            if text_patterns:
                if self._matches_any_pattern_in_chunks(text_patterns, chunk_texts, trig_id):
                    matched.append(trig_id)
                    continue

            # В будущем здесь можно добавить дополнительные типы условий:
            # - all_of   : требуется несколько ключевых слов одновременно,
            # - clause_kind: искать только в определённом типе клауз,
            # - min_hits : минимальное количество совпадений и т.п.

        return matched

    @staticmethod
    def _matches_any_pattern_in_chunks(
        patterns: Iterable[str],
        chunk_texts: List[str],
        trig_id: str,
    ) -> bool:
        """
        Проверка: есть ли хотя бы одно совпадение regex-паттерна в каком-либо чанке.

        Для непрофессионального программиста:
        - Мы берем список строк из YAML (patterns).
        - Каждую строку воспринимаем как регулярное выражение (regex):
          например, "(?i)квартир[аеиу]" или "(?i)земельн[а-я\\s]*участ".
        - Пытаемся скомпилировать эти строки через re.compile().
        - Для каждого успешно скомпилированного regex ищем совпадения
          в тексте каждого чанка через regex.search().
        - Если хотя бы один regex нашёл совпадение хотя бы в одном чанке —
          условие выполнено.
        - Если regex некорректный (ошибка компиляции) — логируем предупреждение,
          но не падаем, чтобы один кривой паттерн не ломал весь сервис.
        """
        compiled_patterns: List[re.Pattern] = []

        for raw in patterns or []:
            s = str(raw or "").strip()
            if not s:
                continue
            try:
                # Важно: не добавляем здесь флаги (IGNORECASE и т.п.),
                # потому что они могут быть уже встроены в сам паттерн
                # через (?i) и другие inline-флаги.
                compiled_patterns.append(re.compile(s))
            except re.error as e:
                logger.warning(
                    "TriggerDetector: invalid regex pattern in trigger_definitions",
                    trigger_id=trig_id,
                    pattern=s,
                    error=str(e),
                )

        if not compiled_patterns or not chunk_texts:
            return False

        for text in chunk_texts:
            if text is None:
                continue
            for regex in compiled_patterns:
                try:
                    if regex.search(text):
                        return True
                except re.error as e:
                    # На всякий случай защищаемся от редких ошибок выполнения regex.
                    logger.warning(
                        "TriggerDetector: regex search error",
                        trigger_id=trig_id,
                        pattern=getattr(regex, "pattern", ""),
                        error=str(e),
                    )

        return False