"""MVP PromptLoader без кэша (Stage 8)"""

from pathlib import Path

from core.config import settings


def load_prompt(prompt_name: str, **variables) -> str:
    """Загрузить промпт из prompts/{prompt_name}.txt"""
    project_root = Path(__file__).parent.parent.parent.parent
    prompts_dir = project_root / getattr(settings, "PROMPTS_DIR", "prompts")

    path = prompts_dir / f"{prompt_name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")

    template = path.read_text(encoding="utf-8").strip()
    return template.format(**variables)
