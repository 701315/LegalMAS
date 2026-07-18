"""
Unit-тесты для RetrievalEngine._compute_metadata_scores().

Проверяет устранение double-loop bug:
  Раньше переменные meta/text во внутреннем цикле всегда указывали
  на последний чанк из-за лишнего цикла выше основного.
  После исправления каждый чанк получает независимый score.

Стратегия изоляции:
- Патчим settings.RUNNER_EMBEDDINGS_ENABLED через атрибут модуля engine,
  а НЕ через Pydantic Settings (setattr на Pydantic-модели падает
  для незадекларированных полей).
- Scoring-константы (KIND_BONUS и др.) НЕ патчим — движок читает их
  через getattr(settings, "...", default), дефолты заданы прямо в engine.py.
  Тесты опираются на эти дефолты (0.3, 0.1 и т.д.).
- Чанки передаются как простые dict.
- _compute_metadata_scores() вызывается напрямую на экземпляре.
- Никаких БД, Celery, FastAPI импортов.
"""

from __future__ import annotations

import pytest
import numpy as np


# ===========================================================================
# Helpers
# ===========================================================================


def _make_chunk(
    chunk_id: str,
    text: str = "некий текст договора",
    kind: str = "",
    section_title: str = "",
    position_ratio: float | None = None,
    unit_type: str = "",
    clause_function: str = "",
    citability_band: str = "",
) -> dict:
    """
    Фабрика dict-чанков для тестов.
    Формат совместим с RetrievalEngine.chunks (после нормализации в __init__).
    """
    return {
        "id": chunk_id,
        "text": text,
        "metadata": {
            "chunk_kind": kind,
            "section_title": section_title,
            "position_ratio": position_ratio,
            "unit_type": unit_type,
            "clause_function": clause_function,
            "citability_band": citability_band,
        },
    }


def _make_engine(chunks: list[dict], **kwargs):
    """
    Создать RetrievalEngine с отключёнными эмбеддингами.

    Патчим settings.RUNNER_EMBEDDINGS_ENABLED через объект settings
    напрямую (object.__setattr__), обходя Pydantic-валидацию.
    Восстанавливаем после создания движка — движок уже сохранил
    emb_vectors=None в __init__, дальнейший патч не нужен.
    """
    from core.config import settings as _settings
    from engine.retrieval.engine import RetrievalEngine

    # Читаем текущее значение чтобы восстановить после
    original = _settings.RUNNER_EMBEDDINGS_ENABLED
    try:
        # object.__setattr__ обходит Pydantic __setattr__
        object.__setattr__(_settings, "RUNNER_EMBEDDINGS_ENABLED", False)
        engine = RetrievalEngine(chunks=chunks, **kwargs)
    finally:
        object.__setattr__(_settings, "RUNNER_EMBEDDINGS_ENABLED", original)

    return engine


# Дефолтные значения констант из engine.py (getattr fallback)
# Тесты опираются именно на эти значения — не патчим Settings
_KIND_BONUS = 0.3       # RUNNER_METADATA_KIND_BONUS_SUBCLAUSE
_SECTION_PENALTY = 0.1  # RUNNER_METADATA_KIND_PENALTY_SECTION
_CITABILITY_HIGH = 0.25 # RUNNER_METADATA_CITABILITY_HIGH_BOOST
_CITABILITY_LOW = 0.08  # RUNNER_METADATA_CITABILITY_LOW_PENALTY
_SECTION_TITLE_BOOST = 1.0  # RUNNER_METADATA_SECTION_TITLE_BOOST
_NEG_KW_PENALTY = 0.8   # RUNNER_METADATA_NEGATIVE_KEYWORD_PENALTY


# ===========================================================================
# Тесты double-loop bug fix
# ===========================================================================


class TestDoubleLoopBugFix:
    """
    Проверяет что исправление double-loop bug работает корректно.

    Суть старого бага:
      Был лишний цикл `for ch in self.chunks:` перед основным
      `for idx, ch in enumerate(...)`. Из-за него переменные meta и text
      (объявленные вне enumerate-цикла) всегда ссылались на ПОСЛЕДНИЙ
      чанк в списке.
      Итог: все чанки получали metadata-score последнего чанка.

    Проверка:
      Создаём чанки с разными kind → ожидаем разные scores.
      При старом баге все score были бы одинаковы (= score последнего).
    """

    def test_each_chunk_gets_independent_score(self):
        """
        Три чанка с разными kind → три разных score.
        При double-loop bug все три score равны score последнего чанка.
        """
        chunks = [
            _make_chunk("c1", kind="legal_unit"),  # +0.3 (kind bonus)
            _make_chunk("c2", kind=""),             # +0.0 (нейтральный)
            _make_chunk("c3", kind="section"),      # -0.1 (penalty)
        ]

        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        assert scores.shape == (3,)
        # legal_unit получает бонус — должен быть выше нейтрального
        assert scores[0] > scores[1], (
            f"legal_unit score ({scores[0]:.4f}) должен быть > "
            f"neutral ({scores[1]:.4f})"
        )
        # section получает штраф — должен быть ниже нейтрального
        assert scores[1] > scores[2], (
            f"neutral score ({scores[1]:.4f}) должен быть > "
            f"section ({scores[2]:.4f})"
        )

    def test_no_double_loop_bug_all_scores_differ(self):
        """
        Регрессионный тест на конкретный bug.

        При старом баге: scores[0] == scores[1] == scores[2] == score_of_last_chunk.
        После исправления: scores строго различаются (3 разных kind).
        """
        chunks = [
            _make_chunk("first",  kind="legal_unit"),
            _make_chunk("middle", kind=""),
            _make_chunk("last",   kind="section"),
        ]

        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        # Проверяем что НЕ все одинаковы (что было бы при баге)
        assert not (scores[0] == scores[1] == scores[2]), (
            "Все три score одинаковы — double-loop bug не устранён!"
        )

        # Ключевая проверка: first chunk (legal_unit) НЕ должен
        # иметь score последнего (section) — что происходило при баге
        assert scores[0] != scores[2], (
            f"score[0]={scores[0]:.4f} равен score[2]={scores[2]:.4f} — "
            "подозрение на double-loop bug (last chunk перетирает all)"
        )

    def test_kind_bonus_applied_to_correct_chunk(self):
        """
        kind_bonus применяется ТОЛЬКО к чанку с kind=legal_unit,
        а не ко всем чанкам (что происходило при double-loop bug,
        если последний чанк имел kind=legal_unit).
        """
        chunks = [
            _make_chunk("plain_1", kind=""),            # нейтральный
            _make_chunk("bonus",   kind="legal_unit"),  # ЭТОТ должен получить бонус
            _make_chunk("plain_2", kind=""),            # нейтральный
        ]

        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        # Только средний чанк получил kind_bonus
        assert scores[1] > scores[0], (
            f"Чанк с legal_unit (score={scores[1]:.4f}) должен превышать "
            f"нейтральный чанк[0] (score={scores[0]:.4f})"
        )
        assert scores[1] > scores[2], (
            f"Чанк с legal_unit (score={scores[1]:.4f}) должен превышать "
            f"нейтральный чанк[2] (score={scores[2]:.4f})"
        )
        # Два нейтральных чанка без kind и без других сигналов — равны
        assert scores[0] == pytest.approx(scores[2], abs=1e-5), (
            f"Два нейтральных чанка должны иметь одинаковый score: "
            f"{scores[0]:.4f} vs {scores[2]:.4f}"
        )


# ===========================================================================
# Тесты отдельных scoring-сигналов
# ===========================================================================


class TestScoringSignals:

    def test_section_kind_gets_penalty(self):
        """kind=section → score ниже чем у нейтрального чанка."""
        chunks = [
            _make_chunk("neutral", kind=""),
            _make_chunk("section", kind="section"),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        assert scores[0] > scores[1], (
            f"neutral ({scores[0]:.4f}) должен быть > section ({scores[1]:.4f})"
        )

    def test_citability_high_boost(self):
        """citability_band=high → score выше чем у чанка без citability."""
        chunks = [
            _make_chunk("no_cit",   citability_band=""),
            _make_chunk("high_cit", citability_band="high"),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        assert scores[1] > scores[0], (
            f"high_cit ({scores[1]:.4f}) должен быть > no_cit ({scores[0]:.4f})"
        )

    def test_citability_low_penalty(self):
        """citability_band=low → score ниже чем у нейтрального чанка."""
        chunks = [
            _make_chunk("no_cit",  citability_band=""),
            _make_chunk("low_cit", citability_band="low"),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        assert scores[0] > scores[1], (
            f"no_cit ({scores[0]:.4f}) должен быть > low_cit ({scores[1]:.4f})"
        )

    def test_section_title_boost_for_matching_term(self):
        """
        Чанк с section_title содержащим important_term получает boost.
        Чанк без совпадения — нет.
        """
        chunks = [
            _make_chunk("no_match",   section_title="общие положения"),
            _make_chunk("with_match", section_title="ответственность сторон"),
        ]
        engine = _make_engine(
            chunks,
            important_terms=["ответственность"],
        )
        scores = engine._compute_metadata_scores()

        assert scores[1] > scores[0], (
            f"with_match ({scores[1]:.4f}) должен быть > "
            f"no_match ({scores[0]:.4f})"
        )

    def test_negative_keyword_penalty_isolated(self):
        """
        negative_keyword совпадает только в одном чанке → только он получает штраф.
        Остальные чанки не должны пострадать.
        """
        chunks = [
            _make_chunk("clean",  text="обычный текст договора"),
            _make_chunk("dirty",  section_title="реклама и маркетинг"),
            _make_chunk("clean2", text="ещё обычный текст"),
        ]
        engine = _make_engine(
            chunks,
            negative_keywords=["реклама"],
        )
        scores = engine._compute_metadata_scores()

        # dirty чанк должен получить штраф относительно clean
        assert scores[1] < scores[0], (
            f"dirty ({scores[1]:.4f}) должен быть < clean ({scores[0]:.4f})"
        )
        assert scores[1] < scores[2], (
            f"dirty ({scores[1]:.4f}) должен быть < clean2 ({scores[2]:.4f})"
        )

    def test_empty_chunks_returns_empty_array(self):
        """Пустой список чанков → пустой массив, без исключений."""
        engine = _make_engine([])
        scores = engine._compute_metadata_scores()

        assert isinstance(scores, np.ndarray)
        assert scores.shape == (0,)

    def test_single_chunk_returns_single_score(self):
        """
        Один чанк с kind=legal_unit → массив из одного элемента.
        Значение равно KIND_BONUS (0.3) — единственный применённый сигнал.
        """
        chunks = [_make_chunk("only", kind="legal_unit")]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()

        assert scores.shape == (1,)
        assert float(scores[0]) == pytest.approx(_KIND_BONUS, abs=1e-5), (
            f"Ожидался kind_bonus={_KIND_BONUS}, получено {scores[0]:.6f}"
        )

        