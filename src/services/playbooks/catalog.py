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
- Доменные сервисы playbook wiring используют индекс и validation helpers из этого файла,
  чтобы проверять, что instruction_code в line items ссылается на реально существующую
  canonical global instruction.
- Фронтенд показывает темы плитками и позволяет администратору выбирать отдельные
  инструкции для включения в PlaybookLine (шаблон плейбука).
"""

from __future__ import annotations

import pathlib

import yaml

from api.schemas.playbooks import PlaybookCheckInfo, PlaybookTopicInfo
from core.config import settings
from core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from db.repositories.global_instruction_version_repo import GlobalInstructionVersionRepository

logger = get_logger(__name__)


def _get_global_checks_root() -> pathlib.Path:
    """
    Возвращает корневую директорию каталога global checks.

    Не кэшируем путь на import-time, чтобы код был устойчивее
    к тестам, hot-reload и смене settings между окружениями.
    """
    return pathlib.Path(settings.BASE_DIR) / "playbooks" / "global_checks"


def _safe_relative_path(path: pathlib.Path, base_dir: pathlib.Path) -> str:
    """
    Вернуть путь относительно BASE_DIR, а если это невозможно —
    вернуть абсолютный/нормализованный путь как строку.

    Это защищает от ValueError в случае нестандартной конфигурации путей.
    """
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _normalize_str(value: object, fallback: str) -> str:
    """
    Нормализовать YAML-значение к непустой строке.
    """
    if value is None:
        return fallback
    normalized = str(value).strip()
    return normalized or fallback

async def load_global_checks_catalog_from_db(
    session: AsyncSession,
) -> list[PlaybookTopicInfo]:
    """
    DB-backed catalog loader for published platform global instructions.

    Fallback:
    - если БД пуста → используем существующий file-based catalog.
    """
    repo = GlobalInstructionVersionRepository(session)
    versions = await repo.list_all_published_platform()

    if not versions:
        logger.warning(
            "No published platform global instructions in DB — falling back to file-based catalog"
        )
        return load_global_checks_catalog()

    topics_map: dict[str, list[PlaybookCheckInfo]] = {}

    for version in versions:
        payload = version.compiled_payload if isinstance(version.compiled_payload, dict) else {}

        topic_code = _normalize_str(
            version.group or payload.get("group") or payload.get("category"),
            "ungrouped",
        )
        title = _normalize_str(
            version.name or payload.get("name"),
            version.instruction_code,
        )

        description_raw = payload.get("description")
        description = None
        if description_raw is not None:
            description = str(description_raw).strip() or None

        item = PlaybookCheckInfo(
            code=version.instruction_code,
            title=title,
            description=description,
            topic_code=topic_code,
            file_path=str(version.source_path or ""),
        )

        topics_map.setdefault(topic_code, []).append(item)

    topics = [
        PlaybookTopicInfo(
            topic_code=topic_code,
            topic_name=topic_code,
            checks=sorted(checks, key=lambda c: c.code),
        )
        for topic_code, checks in sorted(topics_map.items(), key=lambda pair: pair[0])
    ]

    logger.info(
        "Global checks catalog loaded from DB",
        topics=len(topics),
        total_checks=sum(len(t.checks) for t in topics),
    )
    return topics


def load_global_checks_catalog() -> list[PlaybookTopicInfo]:
    topics: dict[str, PlaybookTopicInfo] = {}

    base_dir = pathlib.Path(settings.BASE_DIR)
    global_checks_root = _get_global_checks_root()

    if not global_checks_root.exists():
        logger.warning(
            "global_checks directory not found — catalog will be empty",
            path=str(global_checks_root),
        )
        return []

    if not global_checks_root.is_dir():
        logger.warning(
            "global_checks path exists but is not a directory — catalog will be empty",
            path=str(global_checks_root),
        )
        return []

    for topic_dir in sorted(global_checks_root.iterdir()):
        if not topic_dir.is_dir():
            continue

        topic_code = topic_dir.name
        checks: list[PlaybookCheckInfo] = []

        for file in sorted(topic_dir.glob("*.yaml")):
            try:
                with file.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                logger.warning(
                    "Failed to parse global check YAML — skipping",
                    file=_safe_relative_path(file, base_dir),
                    error=str(exc),
                )
                continue
            except OSError as exc:
                logger.warning(
                    "Failed to read global check YAML — skipping",
                    file=_safe_relative_path(file, base_dir),
                    error=str(exc),
                )
                continue
            except Exception as exc:
                logger.warning(
                    "Unexpected error while loading global check YAML — skipping",
                    file=_safe_relative_path(file, base_dir),
                    error=str(exc),
                )
                continue

            if not isinstance(data, dict) or not data:
                logger.warning(
                    "Empty or non-object YAML file in global_checks — skipping",
                    file=_safe_relative_path(file, base_dir),
                )
                continue

            code = _normalize_str(data.get("id"), file.stem)
            title = _normalize_str(data.get("name"), code)

            description_raw = data.get("description")
            description = None
            if description_raw is not None:
                description = str(description_raw).strip() or None

            checks.append(
                PlaybookCheckInfo(
                    code=code,
                    title=title,
                    description=description,
                    topic_code=topic_code,
                    file_path=_safe_relative_path(file, base_dir),
                )
            )

        if not checks:
            logger.debug(
                "No checks found in topic directory — skipping",
                topic=topic_code,
            )
            continue

        topics[topic_code] = PlaybookTopicInfo(
            topic_code=topic_code,
            topic_name=topic_code,
            checks=sorted(checks, key=lambda c: c.code),
        )

    logger.info(
        "Global checks catalog loaded",
        topics=len(topics),
        total_checks=sum(len(t.checks) for t in topics.values()),
    )
    return sorted(topics.values(), key=lambda t: t.topic_code)

def load_global_checks_index() -> dict[str, PlaybookCheckInfo]:
    """
    Построить индекс global checks по canonical instruction code.

    Нужен доменным сервисам, которые валидируют instruction_code
    в составе playbook line items и при сборке версии из from_line_id.
    """
    index: dict[str, PlaybookCheckInfo] = {}
    for topic in load_global_checks_catalog():
        for check in topic.checks:
            index[check.code] = check
    return index


def get_unknown_global_check_codes(codes: list[str]) -> list[str]:
    """
    Вернуть отсортированный список instruction_code, которых нет
    в текущем canonical global checks catalog.
    """
    index = load_global_checks_index()
    normalized_codes = {
        str(code).strip()
        for code in codes
        if code is not None and str(code).strip()
    }
    return sorted(code for code in normalized_codes if code not in index)



