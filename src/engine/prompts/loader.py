"""
Prompt Loader.

Задачи:
- Найти корневую папку с промптами (по settings.PROMPTSDIR или ./prompts)
- Загружать .txt шаблоны по имени
- Подставлять переменные в шаблон через .format(**variables)
- Давать доступ к "сырому" тексту без форматирования
- Кешировать загруженные шаблоны в памяти

Использование:
    from src.engine.prompts.loader import load_prompt, get_promptloader

    text = load_prompt("detection/genericpresence", {
        "condition_name": "...",
        "legal_base": "...",
        "context": "...",
    })
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def _get_prompts_root() -> Path:
    """
    Определить корневую директорию с промптами.

    Правила:
    - Если settings.PROMPTSDIR — абсолютный путь, используем его как есть.
    - Если относительный — интерпретируем относительно корня проекта (родителя src/).
    - Если что-то пошло не так — fallback в ./prompts от текущей рабочей директории.
    """
    try:
        prompts_dir = settings.PROMPTSDIR  # например, "prompts"
        if not prompts_dir:
            raise ValueError("PROMPTSDIR is empty")

        path = Path(prompts_dir)
        if path.is_absolute():
            return path

        # Относительный путь — считаем от корня проекта (родитель src/)
        # file = этот файл (loader.py)
        file_path = Path(__file__).resolve()
        project_root = file_path.parent.parent.parent.parent  # src/engine/prompts/ -> src/engine -> src -> root
        return project_root / prompts_dir
    except Exception:
        # Fallback: текущая директория + "prompts"
        logger.warning("Failed to resolve PROMPTSDIR, falling back to ./prompts")
        return Path("prompts").resolve()


class PromptLoader:
    """
    Загрузчик промптов (.txt) с поддержкой кеша и подстановки переменных.

    Формат промпта: обычный текст, внутри которого могут быть плейсхолдеры
    вида {variable_name} для .format(**variables).
    """

    def __init__(self, prompts_root: Optional[Path] = None) -> None:
        self.root: Path = prompts_root or _get_prompts_root()
        self._cache: Dict[str, str] = {}  # normalized_name -> template_text

    # --- публичные методы ---

    def load(self, prompt_name: str, variables: Dict[str, object]) -> str:
        """
        Загрузить промпт и подставить переменные.

        Args:
            prompt_name: имя промпта без .txt, например:
                "detection/genericpresence" или "classification/classifydocument"
            variables: словарь для .format(**variables)

        Returns:
            Строка с подставленными переменными.

        Raises:
            FileNotFoundError: если файл промпта не найден
            KeyError: если в шаблоне есть плейсхолдер, которого нет в variables
        """
        template = self._load_template(prompt_name)

        if not variables:
            return template

        try:
            return template.format(**variables)
        except KeyError as e:
            missing = str(e).strip("'")
            raise KeyError(
                f"Prompt '{prompt_name}' requires variable '{missing}', "
                f"but it was not provided. Provided: {list(variables.keys())}"
            ) from e

    def load_raw(self, prompt_name: str) -> str:
        """
        Загрузить промпт без подстановки переменных (сырой шаблон).
        """
        return self._load_template(prompt_name)

    def exists(self, prompt_name: str) -> bool:
        """
        Проверить, существует ли файл промпта.
        """
        path = self._resolve_path(prompt_name)
        return path.exists()

    def list_prompts(self, category: Optional[str] = None) -> List[str]:
        """
        Перечислить все доступные промпты.

        Args:
            category: подкаталог внутри root (например, "detection", "classification").
                      Если None — ищем по всему дереву.

        Returns:
            Список имён промптов без .txt, относительно корня prompts.
            Например: ["detection/genericpresence", "classification/classifydocument"]
        """
        search_root = self.root / category if category else self.root
        if not search_root.exists():
            return []

        prompts: List[str] = []
        for path in search_root.rglob("*.txt"):
            # относительный путь относительно root
            rel = path.relative_to(self.root)
            # без суффикса .txt
            name = str(rel.with_suffix(""))
            prompts.append(name)

        return sorted(prompts)

    def get_variables(self, prompt_name: str) -> List[str]:
        """
        Вернуть список имён переменных, используемых в шаблоне.

        Выделяет плейсхолдеры вида {variable}.
        """
        template = self._load_template(prompt_name)
        # Простая регулярка по фигурным скобкам
        variables = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", template)
        # Сохраняем порядок появления и убираем дубли
        seen = {}
        for v in variables:
            if v not in seen:
                seen[v] = True
        return list(seen.keys())

    def reload_cache(self) -> None:
        """
        Очистить кеш промптов, чтобы в dev-режиме подтягивались свежие изменения файлов.
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info("Prompt cache cleared", cleared_count=count)

    # --- внутренние методы ---

    def _load_template(self, prompt_name: str) -> str:
        """
        Загрузить текст шаблона (с кешированием).
        """
        normalized = self._normalize_name(prompt_name)

        if normalized in self._cache:
            return self._cache[normalized]

        path = self._resolve_path(normalized)
        if not path.exists():
            available = self.list_prompts()
            raise FileNotFoundError(
                f"Prompt file not found: {path}\n"
                f"Expected: '{normalized}.txt'\n"
                f"Available prompts:\n" + "\n".join(f" - {p}" for p in available)
            )

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Prompt file is empty: {path}")

        self._cache[normalized] = text
        logger.debug(
            "Prompt loaded from file",
            prompt=normalized,
            length=len(text),
            path=str(path),
        )
        return text

    def _resolve_path(self, prompt_name: str) -> Path:
        """
        Построить путь до файла .txt по имени промпта.
        """
        name = prompt_name
        if not name.endswith(".txt"):
            name = f"{name}.txt"
        return self.root / name

    @staticmethod
    def _normalize_name(prompt_name: str) -> str:
        """
        Нормализовать имя промпта для использования в кеше.

        Сейчас просто заменяем обратные слэши на прямые.
        """
        return prompt_name.replace("\\", "/").rstrip(".txt")


# --- глобальный singleton для удобства ---

_prompt_loader: Optional[PromptLoader] = None


def get_promptloader() -> PromptLoader:
    """
    Вернуть глобальный PromptLoader (singleton).

    Используется, например, в:
        from src.engine.prompts.loader import get_promptloader

        loader = get_promptloader()
        text = loader.load("detection/genericpresence", {...})
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader


def load_prompt(prompt_name: str, variables: Dict[str, object]) -> str:
    """
    Утилитарная функция для одноразовой загрузки промпта.

    Пример:
        text = load_prompt("detection/genericpresence", {
            "condition_name": "...",
            "legal_base": "...",
            "context": "...",
        })
    """
    return get_promptloader().load(prompt_name, variables)
