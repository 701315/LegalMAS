# src/engine/checks/planning/context.py

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import FrozenSet, Literal


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
    """

    scope: Literal["document", "segment"]

    document_id: uuid.UUID
    document_version_id: uuid.UUID | None

    # document-level профиль
    document_type: str | None

    # segment-level профиль
    segment_id: str | None
    segment_doc_type: str | None

    # применимые триггеры (doc- или segment-level)
    triggers: FrozenSet[str]


@dataclass(frozen=True)
class SegmentInfo:
    """
    Краткая информация о сегменте для построения контекста.

    Для непрофессионального программиста:
    - segment_id — строковый идентификатор логического документа внутри файла.
    - segment_doc_type — тип сегмента, такой же, как doc_type для всего документа.
    - triggers — триггеры, которые classifier нашёл именно для этого сегмента.
    """

    segment_id: str
    segment_doc_type: str | None
    triggers: tuple[str, ...]

