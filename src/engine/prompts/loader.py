# src/engine/prompts/loader.py

"""
Prompt Loader.

Задачи:
- Найти корневую папку с промптами (по settings.PROMPTSDIR или ./prompts)
- Загружать .txt шаблоны по имени
- Подставлять переменные в шаблон безопасной replace-подстановкой
- Давать доступ к "сырому" тексту без форматирования
- Кешировать загруженные шаблоны в памяти

Использование:
    from engine.prompts.loader import load_prompt, get_promptloader

    text = load_prompt("detection/genericpresence", {
        "condition_name": "...",
        "legal_base": "...",
        "context": "...",
    })
"""

from __future__ import annotations

import re
from pathlib import Path

from core.config import settings
from core.logging import get_logger

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
        prompts_dir = settings.PROMPTS_DIR  # например, "prompts"
        if not prompts_dir:
            raise ValueError("PROMPTSDIR is empty")

        path = Path(prompts_dir)
        if path.is_absolute():
            return path

        # Относительный путь — считаем от корня проекта (родитель src/)
        # file = этот файл (loader.py)
        file_path = Path(__file__).resolve()
        project_root = (
            file_path.parent.parent.parent.parent
        )  # src/engine/prompts/ -> src/engine -> src -> root
        return project_root / prompts_dir
    except Exception:
        # Fallback: текущая директория + "prompts"
        logger.warning("Failed to resolve PROMPTSDIR, falling back to ./prompts")
        return Path("prompts").resolve()


class PromptLoader:
    """
    Загрузчик промптов (.txt) с поддержкой кеша и подстановки переменных.

    Формат промпта: обычный текст, внутри которого могут быть плейсхолдеры
    вида {variable_name} для безопасной replace-подстановки.
    """

    def __init__(self, prompts_root: Path | None = None) -> None:
        self.root: Path = prompts_root or _get_prompts_root()
        self._cache: dict[str, str] = {}  # normalized_name -> template_text

    # --- публичные методы ---

    def load(self, prompt_name: str, variables: dict[str, object]) -> str:
        """
        Загрузить промпт и безопасно подставить переменные.

        Args:
            prompt_name: имя промпта без .txt, например:
                "detection/genericpresence" или "classification/classifydocument"
            variables:
                словарь переменных, где ключ может быть:
                - "context"
                - "{context}"

        Returns:
            Строка с подставленными переменными.

        Raises:
            FileNotFoundError: если файл промпта не найден

        ВАЖНО:
        Используем последовательный .replace(), а не str.format(),
        потому что промпты могут содержать JSON-примеры с фигурными скобками:
            {"found": true, "evidence": "..."}
        str.format() ломается на таких шаблонах, интерпретируя JSON-ключи
        как Python placeholders.
        """
        template = self._load_template(prompt_name)

        if not variables:
            return template

        result = template
        for key, value in variables.items():
            key_str = str(key)
            placeholder = (
                key_str
                if key_str.startswith("{") and key_str.endswith("}")
                else f"{{{key_str}}}"
            )
            replacement = "" if value is None else str(value)
            result = result.replace(placeholder, replacement)

        return result

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

    def list_prompts(self, category: str | None = None) -> list[str]:
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

        prompts: list[str] = []
        for path in search_root.rglob("*.txt"):
            # относительный путь относительно root
            rel = path.relative_to(self.root)
            # без суффикса .txt
            name = str(rel.with_suffix(""))
            prompts.append(name)

        return sorted(prompts)

    def get_variables(self, prompt_name: str) -> list[str]:
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

        Правила:
        - заменяем обратные слэши на прямые;
        - если имя оканчивается ровно на ".txt" — снимаем только этот суффикс;
        - никаких rstrip(".txt"), потому что он удаляет любые хвостовые
          символы из множества {'.', 't', 'x'}, а не точный суффикс.

        Пример:
            "test_prompt.txt" -> "test_prompt"
            "test_prompt"     -> "test_prompt"
        """
        normalized = prompt_name.replace("\\", "/")
        if normalized.endswith(".txt"):
            return normalized[:-4]
        return normalized


# --- глобальный singleton для удобства ---

_prompt_loader: PromptLoader | None = None


def get_promptloader() -> PromptLoader:
    """
    Вернуть глобальный PromptLoader (singleton).

    Используется, например, в:
        from engine.prompts.loader import get_promptloader

        loader = get_promptloader()
        text = loader.load("detection/genericpresence", {...})
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader


def load_prompt(prompt_name: str, variables: dict[str, object]) -> str:
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
