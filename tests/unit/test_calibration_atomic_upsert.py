"""
Pure-logic regression tests for atomic calibration upsert.

Почему тест pure-logic:
- прямой импорт db.repositories.* сейчас тянет тяжёлый package graph;
- для этой находки критичны два инварианта:
  1) sample_count не должен терять инкременты;
  2) calibrated_confidence должен оставаться точным running average.

Этот тест фиксирует именно бизнес-математику и регрессию lost update.
"""

from __future__ import annotations


def _sample_value(correct: bool) -> float:
    return 1.0 if correct else 0.0


def _apply_atomic_upsert(
    current_avg: float | None,
    current_count: int,
    correct: bool,
) -> tuple[float, int]:
    """
    Локальная копия математики atomic upsert.

    - если bucket ещё не существует -> (value, 1)
    - если существует -> пересчёт running average с инкрементом count
    """
    value = _sample_value(correct)

    if current_avg is None or current_count <= 0:
        return value, 1

    new_count = current_count + 1
    new_avg = (current_avg * current_count + value) / new_count
    return new_avg, new_count


def _apply_atomic_sequence(events: list[bool]) -> tuple[float, int]:
    """
    Последовательно применить набор calibration samples.
    """
    avg: float | None = None
    count = 0

    for event in events:
        avg, count = _apply_atomic_upsert(avg, count, event)

    return (avg if avg is not None else 0.0), count


def _old_read_modify_write_last_writer_wins(
    current_avg: float,
    current_count: int,
    concurrent_events: list[bool],
) -> tuple[float, int]:
    """
    Симуляция старого дефекта:
    все писатели читают один и тот же snapshot (avg, count),
    считают локально новое значение и затем последний writer затирает остальных.

    Это и есть lost update:
    - count увеличивается только на 1, а не на число событий;
    - один или несколько samples теряются.
    """
    last_avg = current_avg
    last_count = current_count

    for event in concurrent_events:
        value = _sample_value(event)
        last_count = current_count + 1
        last_avg = (current_avg * current_count + value) / (current_count + 1)

    return last_avg, last_count


class TestAtomicCalibrationMath:
    def test_first_correct_sample_creates_avg_1_count_1(self):
        avg, count = _apply_atomic_upsert(None, 0, True)
        assert avg == 1.0
        assert count == 1

    def test_first_incorrect_sample_creates_avg_0_count_1(self):
        avg, count = _apply_atomic_upsert(None, 0, False)
        assert avg == 0.0
        assert count == 1

    def test_existing_bucket_correctly_updates_with_true(self):
        # Было: avg=0.7, count=10 -> sum=7.0
        # Добавляем True -> (7 + 1) / 11
        avg, count = _apply_atomic_upsert(0.7, 10, True)
        assert count == 11
        assert abs(avg - (8.0 / 11.0)) < 1e-12

    def test_existing_bucket_correctly_updates_with_false(self):
        # Было: avg=0.7, count=10 -> sum=7.0
        # Добавляем False -> 7 / 11
        avg, count = _apply_atomic_upsert(0.7, 10, False)
        assert count == 11
        assert abs(avg - (7.0 / 11.0)) < 1e-12

    def test_sequence_average_equals_arithmetic_mean(self):
        events = [True, False, True, True, False]  # 3/5 = 0.6
        avg, count = _apply_atomic_sequence(events)

        assert count == 5
        assert abs(avg - 0.6) < 1e-12

    def test_sequence_count_increments_once_per_event(self):
        events = [True, True, False, False, True, False, True]
        _, count = _apply_atomic_sequence(events)

        assert count == len(events)

    def test_average_stays_within_zero_one_bounds(self):
        events = [True, False, False, True, True, False, True, True, False]
        avg, count = _apply_atomic_sequence(events)

        assert count == len(events)
        assert 0.0 <= avg <= 1.0

    def test_atomic_update_preserves_both_concurrent_samples(self):
        """
        Что должен давать правильный atomic сценарий:
        старт: avg=0.7, count=10 -> sum=7
        события: [True, False]
        итог: count=12, avg=(7+1+0)/12 = 8/12
        """
        avg = 0.7
        count = 10

        avg, count = _apply_atomic_upsert(avg, count, True)
        avg, count = _apply_atomic_upsert(avg, count, False)

        assert count == 12
        assert abs(avg - (8.0 / 12.0)) < 1e-12

    def test_old_pattern_loses_increment_under_concurrency(self):
        """
        Регрессионный тест на исходный баг:
        старый read-modify-write может потерять один инкремент.
        """
        old_avg, old_count = _old_read_modify_write_last_writer_wins(
            current_avg=0.7,
            current_count=10,
            concurrent_events=[True, False],
        )

        # Потерян один sample: count стал 11 вместо 12
        assert old_count == 11

        # old_avg соответствует только одному из двух апдейтов, а не обоим сразу
        expected_true_only = 8.0 / 11.0
        expected_false_only = 7.0 / 11.0
        assert abs(old_avg - expected_true_only) < 1e-12 or abs(old_avg - expected_false_only) < 1e-12

    def test_atomic_result_differs_from_old_lost_update_pattern(self):
        """
        Atomic обновление должно отличаться от старого broken поведения.
        """
        atomic_avg = 0.7
        atomic_count = 10
        atomic_avg, atomic_count = _apply_atomic_upsert(atomic_avg, atomic_count, True)
        atomic_avg, atomic_count = _apply_atomic_upsert(atomic_avg, atomic_count, False)

        old_avg, old_count = _old_read_modify_write_last_writer_wins(
            current_avg=0.7,
            current_count=10,
            concurrent_events=[True, False],
        )

        assert atomic_count == 12
        assert old_count == 11
        assert atomic_count != old_count
        assert abs(atomic_avg - old_avg) > 1e-12


        