# src/engine/checks/planning/context.py

"""
Immutable value objects для checks planning pipeline.

Что живёт в этом модуле:
- CheckContext — универсальный контекст для подбора checks (document или segment scope).
- SegmentInfo — компактный carrier-object с данными сегмента.

Что НЕ живёт в этом модуле:
- DocumentCheckSnapshot / DocumentSnapshot — shared read-model contract,
  который переиспользуется всеми orchestration/worker/engine слоями.
  Живёт в core.pipeline_snapshots.DocumentSnapshot.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

CheckScope = Literal["document", "segment"]


@dataclass(frozen=True)
class CheckContext:
    """
    Универсальный контекст для подбора checks.

    Для непрофессионального программиста:
    - scope показывает, работаем ли мы с целым документом или с отдельным сегментом.
    - В document-режиме важен document_type.
    - В segment-режиме важны segment_id и segment_doc_type.
    - triggers — это набор "флагов", по которым YAML и playbook решают,
      какие проверки нужно запускать.

    Архитектурный смысл:
    - Это immutable value object для planner / runner пайплайна.
    - Контекст создаётся один раз и дальше не должен мутировать.
    """

    scope: CheckScope

    document_id: uuid.UUID
    document_version_id: uuid.UUID | None

    # document-level профиль
    document_type: str | None

    # segment-level профиль
    segment_id: str | None
    segment_doc_type: str | None

    # применимые триггеры (doc- или segment-level)
    triggers: frozenset[str]

    @property
    def effective_doc_type(self) -> str | None:
        """
        Вернуть фактический doc_type, по которому надо подбирать checks.

        Для непрофессионального программиста:
        - Для scope="document" это document_type.
        - Для scope="segment" это segment_doc_type.
        """
        if self.scope == "segment":
            return self.segment_doc_type
        return self.document_type

    @property
    def is_document_scope(self) -> bool:
        """Удобный helper: контекст относится к целому документу."""
        return self.scope == "document"

    @property
    def is_segment_scope(self) -> bool:
        """Удобный helper: контекст относится к отдельному сегменту."""
        return self.scope == "segment"


@dataclass(frozen=True)
class SegmentInfo:
    """
    Краткая информация о сегменте для построения контекста.

    Для непрофессионального программиста:
    - segment_id — строковый идентификатор логического документа внутри файла.
    - segment_doc_type — тип сегмента, такой же, как doc_type для всего документа.
    - triggers — триггеры, которые classifier нашёл именно для этого сегмента.

    Архитектурный смысл:
    - Это компактный immutable carrier-object.
    - Нужен, чтобы planner не зависел от ORM/DTO конкретной реализации сегментов.
    """

    segment_id: str
    segment_doc_type: str | None
    triggers: tuple[str, ...]

    @property
    def has_doc_type(self) -> bool:
        """Есть ли у сегмента определённый segment_doc_type."""
        return bool(self.segment_doc_type)
