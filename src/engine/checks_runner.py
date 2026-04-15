# src/engine/checks_runner.py

"""
⚠️  ФАСАД ОБРАТНОЙ СОВМЕСТИМОСТИ.

Реальная логика перенесена в:
- engine/checks/check_runner.py       — оркестратор
- engine/checks/planning/             — планирование, скоупинг, чанки
- engine/checks/result_normalizer.py  — нормализация результатов
- engine/checks/result_saver.py       — сохранение в БД

Этот файл сохранён, чтобы НЕ менять импорт в:
  src/workers/check_runner_worker.py
"""

from engine.checks.check_runner import CheckRunner

__all__ = ["CheckRunner"]

