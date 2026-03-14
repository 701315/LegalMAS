# src/services/playbooks/catalog.py

"""
Каталог глобальных чеков для конструктора плейбуков.

Назначение:
- Построить в памяти «каталог» всех доступных глобальных проверок (global_checks),
  который будет использоваться админской страницей для сборки шаблонов плейбуков.
- Каталог собирается из файловой системы: playbooks/global_checks/<topic>/*.yaml.

Что делает:
- Проходит по директории playbooks/global_checks и всем её подпапкам-темам
  (например: coc, confidentiality, cyber).
- Для каждой темы читает все *.yaml файлы-инструкции.
- Из каждого YAML берёт id, name и description и формирует объект проверки:
  code (id), title (name), description, topic_code и относительный путь к файлу.
- Группирует проверки по темам и возвращает список PlaybookTopicInfo:
  одна запись на тему, внутри — список PlaybookCheckInfo для инструкций этой темы.

Как используется:
- Эндпоинт API (например, GET /api/v1/playbooks/catalog) вызывает load_global_checks_catalog()
  и отдаёт результат фронтенду.
- Фронтенд показывает темы плитками и позволяет администратору выбирать отдельные
  инструкции для включения в PlaybookLine (шаблон плейбука).
"""


import pathlib
from typing import List, Dict

import yaml

from api.schemas.playbooks import PlaybookTopicInfo, PlaybookCheckInfo

# жёстко прописанный корень проекта
BASE_DIR = pathlib.Path("/home/vladi/projects/LegalMAS")
GLOBAL_CHECKS_ROOT = BASE_DIR / "playbooks" / "global_checks"


def load_global_checks_catalog() -> List[PlaybookTopicInfo]:
    topics: Dict[str, PlaybookTopicInfo] = {}

    if not GLOBAL_CHECKS_ROOT.exists():
        return []

    for topic_dir in GLOBAL_CHECKS_ROOT.iterdir():
        if not topic_dir.is_dir():
            continue

        topic_code = topic_dir.name
        checks: list[PlaybookCheckInfo] = []

        for file in topic_dir.glob("*.yaml"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                # TODO: залогировать, но не падать
                continue

            code = data.get("id") or file.stem
            title = data.get("name") or code
            description = data.get("description")

            checks.append(
                PlaybookCheckInfo(
                    code=code,
                    title=title,
                    description=description,
                    topic_code=topic_code,
                    file_path=str(file.relative_to(BASE_DIR)),
                )
            )

        if not checks:
            continue

        topics[topic_code] = PlaybookTopicInfo(
            topic_code=topic_code,
            topic_name=topic_code,  # позже можно замапить в красивое имя
            checks=sorted(checks, key=lambda c: c.code),
        )

    return sorted(topics.values(), key=lambda t: t.topic_code)
