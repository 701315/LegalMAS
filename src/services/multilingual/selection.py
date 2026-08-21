# src/services/multilingual/selection.py

"""
Layer 5: Selection.

Задача:
- проставить visibility флаги на все сегменты в зависимости от target_language;
- ParallelGroup: сегменты target_language visible, остальные hidden с полным контекстом;
- OrphanGroup: visible_orphan_target или visible_orphan_foreign;
- MonolingualGroup: все visible.

НЕ делает:
- не создаёт новых групп;
- не изменяет alignment;
- не изменяет text сегментов.

Ключевой инвариант:
- Никакой сегмент не удаляется физически.
- Скрытые сегменты остаются в списке с флагом visibility="hidden".
- Layer 6 может собрать полный dump (visible + hidden) для аудита,
  и filtered dump (только visible) для передачи в classify_elements.

Hidden сегменты хранят максимальный контекст:
- translation_of - segment_ids партнёров на target_language
- translation_pair_confidence - alignment_confidence из ParallelGroup
- translation_language - язык партнёров
- parallel_group_id - id группы для аудита

Это позволяет:
- LLM использовать hidden как context (перевод visible сегмента)
- Аудитору проверить почему сегмент скрыт
- Recovery если пользователь запросит другой target_language
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger

from services.multilingual.models import (
    Group,
    LanguageSegment,
    MonolingualGroup,
    OrphanGroup,
    ParallelGroup,
    ProcessingWarning,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Константы: display prefixes для orphan_foreign
# ---------------------------------------------------------------------------

# Префиксы для visible_orphan_foreign сегментов.
# Downstream может добавить этот префикс при отображении пользователю.
# Мы НЕ модифицируем text сегмента - это только hint для UI.
_ORPHAN_FOREIGN_PREFIX_BY_TARGET: dict[str, str] = {
    "ru": "[БЕЗ ПЕРЕВОДА]",
    "en": "[NO TRANSLATION]",
    "fr": "[SANS TRADUCTION]",
    "de": "[OHNE ÜBERSETZUNG]",
    "es": "[SIN TRADUCCIÓN]",
    "it": "[SENZA TRADUZIONE]",
    "pt": "[SEM TRADUÇÃO]",
    "tr": "[ÇEVIRISIZ]",
    "ar": "[بدون ترجمة]",
    "he": "[ללא תרגום]",
    "kk": "[АУДАРМАСЫЗ]",
    "uk": "[БЕЗ ПЕРЕКЛАДУ]",
}

# Default fallback если target_language не в маппинге
_DEFAULT_ORPHAN_FOREIGN_PREFIX = "[NO TRANSLATION]"


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def apply_visibility(
    segments: list[LanguageSegment],
    groups: list[Group],
    target_language: str,
) -> tuple[list[LanguageSegment], list[ProcessingWarning]]:
    """
    Layer 5 entry point.

    Проставить visibility флаги на все сегменты в зависимости от target_language
    и результатов Layer 4 alignment.

    Аргументы:
        segments: все LanguageSegments (результат Layer 3)
        groups: все Group (результат Layer 4)
        target_language: целевой язык (ISO 639-1)

    Возвращает:
        (segments, warnings):
        - segments: те же сегменты с обновлёнными visibility полями
        - warnings: список ProcessingWarning для audit

    Мутирует segments in-place (заполняет visibility, hidden_reason,
    translation_of, translation_pair_confidence, translation_language,
    parallel_group_id, is_orphan_target, is_orphan_foreign, is_ambiguous,
    orphan_display_prefix). Возвращает список для удобства.

    Гарантии:
    - все сегменты получают visibility значение (нет default state);
    - никогда не бросает исключений;
    - определизм: один и тот же input даёт тот же output.

    Для непрофессионального программиста:
    Функция берёт результаты alignment и решает какие сегменты показать
    пользователю (visible), а какие скрыть (hidden). Скрытые не удаляются,
    остаются в системе для аудита и LLM context.
    """
    if not segments:
        return [], []

    warnings: list[ProcessingWarning] = []

    # Строим index: segment_id -> segment для быстрого доступа
    segments_by_id: dict[str, LanguageSegment] = {
        seg.segment_id: seg for seg in segments
    }

    # Track какие сегменты обработаны (для отладки)
    processed_ids: set[str] = set()

    # Обрабатываем каждую группу
    for group in groups:
        if isinstance(group, ParallelGroup):
            _apply_visibility_parallel(
                group=group,
                segments_by_id=segments_by_id,
                target_language=target_language,
                warnings=warnings,
                processed_ids=processed_ids,
            )
        elif isinstance(group, OrphanGroup):
            _apply_visibility_orphan(
                group=group,
                segments_by_id=segments_by_id,
                target_language=target_language,
                processed_ids=processed_ids,
            )
        elif isinstance(group, MonolingualGroup):
            _apply_visibility_monolingual(
                group=group,
                segments_by_id=segments_by_id,
                target_language=target_language,
                processed_ids=processed_ids,
            )

    # Проверяем что все сегменты обработаны
    unprocessed = [seg for seg in segments if seg.segment_id not in processed_ids]
    if unprocessed:
        # Fallback: помечаем как visible (fail-safe: лучше показать, чем скрыть)
        for seg in unprocessed:
            _apply_default_visible(seg)
            warnings.append(
                ProcessingWarning(
                    warning_type="segment_not_in_any_group",
                    element_id=seg.source_element_id,
                    page=seg.page,
                    details={
                        "segment_id": seg.segment_id,
                        "fallback": "marked as visible",
                    },
                )
            )

    return segments, warnings


# ---------------------------------------------------------------------------
# ParallelGroup: target visible, остальные hidden
# ---------------------------------------------------------------------------


def _apply_visibility_parallel(
    group: ParallelGroup,
    segments_by_id: dict[str, LanguageSegment],
    target_language: str,
    warnings: list[ProcessingWarning],
    processed_ids: set[str],
) -> None:
    """
    Обработать ParallelGroup.

    Правила:
    - Сегменты на target_language → visible
    - Сегменты на другом языке → hidden с полным контекстом
    - Если target_language отсутствует в группе → warning, все visible ambiguous
    """
    # Собираем segment_ids по языкам
    target_segment_ids: list[str] = list(group.segments_by_language.get(target_language, []))

    # Проверяем есть ли target_language в группе
    if not target_segment_ids:
        # Особый случай: пара без target-языка (например, EN+FR при target=RU)
        # Помечаем все visible с флагом is_ambiguous
        _handle_parallel_without_target(
            group=group,
            segments_by_id=segments_by_id,
            target_language=target_language,
            warnings=warnings,
            processed_ids=processed_ids,
        )
        return

    # Собираем языки НЕ target'а (партнёры для перевода)
    other_languages: list[str] = [
        lang for lang in group.languages if lang != target_language
    ]

    # Обрабатываем target segments — visible
    for seg_id in target_segment_ids:
        seg = segments_by_id.get(seg_id)
        if seg is None:
            continue
        seg.visibility = "visible"
        seg.hidden_reason = None
        seg.parallel_group_id = group.group_id
        # Для visible target сегментов translation_of содержит партнёров
        # (для LLM context access — можно посмотреть как это на другом языке)
        partner_ids: list[str] = []
        for other_lang in other_languages:
            partner_ids.extend(group.get_segment_ids(other_lang))
        seg.translation_of = sorted(partner_ids)
        seg.translation_pair_confidence = group.alignment_confidence
        # translation_language для visible target - список других языков
        # Берём первый (обычно один партнёр-язык в паре)
        seg.translation_language = other_languages[0] if other_languages else None
        processed_ids.add(seg_id)

    # Обрабатываем other language segments — hidden
    for other_lang in other_languages:
        other_seg_ids = group.get_segment_ids(other_lang)
        for seg_id in other_seg_ids:
            seg = segments_by_id.get(seg_id)
            if seg is None:
                continue
            seg.visibility = "hidden"
            seg.hidden_reason = "parallel_translation_available"
            seg.translation_of = sorted(target_segment_ids)
            seg.translation_pair_confidence = group.alignment_confidence
            seg.translation_language = target_language
            seg.parallel_group_id = group.group_id
            processed_ids.add(seg_id)


def _handle_parallel_without_target(
    group: ParallelGroup,
    segments_by_id: dict[str, LanguageSegment],
    target_language: str,
    warnings: list[ProcessingWarning],
    processed_ids: set[str],
) -> None:
    """
    Особый случай: ParallelGroup без target_language.

    Например, найдена пара EN+FR, а пользователь выбрал target=RU.
    Что делать? Мы не можем скрыть один язык — не знаем какой из них
    предпочесть. Стратегия: все visible с флагом is_ambiguous.

    Это редкий случай для типичных RU-EN документов, но возможен для
    многоязычных документов (например, EN+FR+RU где target=RU и есть
    отдельная пара EN+FR).
    """
    all_segment_ids: list[str] = group.all_segment_ids()

    warnings.append(
        ProcessingWarning(
            warning_type="parallel_group_without_target_language",
            page=group.page,
            details={
                "group_id": group.group_id,
                "target_language": target_language,
                "group_languages": group.languages,
                "total_segments": len(all_segment_ids),
                "fallback": "all segments marked visible with is_ambiguous=True",
            },
        )
    )

    for seg_id in all_segment_ids:
        seg = segments_by_id.get(seg_id)
        if seg is None:
            continue
        seg.visibility = "visible_ambiguous"
        seg.is_ambiguous = True
        seg.parallel_group_id = group.group_id
        # translation_of не заполняем - нет target на который ссылаться
        processed_ids.add(seg_id)


# ---------------------------------------------------------------------------
# OrphanGroup: visible_orphan_target или visible_orphan_foreign
# ---------------------------------------------------------------------------


def _apply_visibility_orphan(
    group: OrphanGroup,
    segments_by_id: dict[str, LanguageSegment],
    target_language: str,
    processed_ids: set[str],
) -> None:
    """
    Обработать OrphanGroup.

    Правила:
    - orphan_language == target_language → visible_orphan_target
    - orphan_language != target_language → visible_orphan_foreign
      + orphan_display_prefix для UI
    """
    is_target = group.orphan_language == target_language

    for seg_id in group.segment_ids:
        seg = segments_by_id.get(seg_id)
        if seg is None:
            continue

        if is_target:
            seg.visibility = "visible_orphan_target"
            seg.is_orphan_target = True
            seg.is_orphan_foreign = False
            seg.orphan_display_prefix = None
        else:
            seg.visibility = "visible_orphan_foreign"
            seg.is_orphan_target = False
            seg.is_orphan_foreign = True
            seg.orphan_display_prefix = _get_orphan_foreign_prefix(target_language)

        # Для orphan translation_of пустой - нет партнёра
        seg.translation_of = []
        processed_ids.add(seg_id)


def _get_orphan_foreign_prefix(target_language: str) -> str:
    """
    Получить UI-префикс для orphan_foreign сегмента.

    Возвращает локализованное сообщение "[БЕЗ ПЕРЕВОДА]" или "[NO TRANSLATION]"
    в зависимости от target_language.
    """
    return _ORPHAN_FOREIGN_PREFIX_BY_TARGET.get(
        target_language, _DEFAULT_ORPHAN_FOREIGN_PREFIX
    )


# ---------------------------------------------------------------------------
# MonolingualGroup: все visible
# ---------------------------------------------------------------------------


def _apply_visibility_monolingual(
    group: MonolingualGroup,
    segments_by_id: dict[str, LanguageSegment],
    target_language: str,
    processed_ids: set[str],
) -> None:
    """
    Обработать MonolingualGroup.

    Все сегменты в такой группе — visible.

    Это работает и для bypass (structured_data, neutral),
    и для монолингвальных страниц.
    """
    for seg_id in group.segment_ids:
        seg = segments_by_id.get(seg_id)
        if seg is None:
            continue

        seg.visibility = "visible"
        seg.hidden_reason = None
        seg.translation_of = []
        seg.parallel_group_id = None

        # Для сегментов на target_language не помечаем orphan
        # Для других языков на monolingual page — тоже visible
        # (одноязычный документ по определению не имеет переводов)
        seg.is_orphan_target = False
        seg.is_orphan_foreign = False
        seg.is_ambiguous = False

        processed_ids.add(seg_id)


# ---------------------------------------------------------------------------
# Fallback для сегментов вне групп
# ---------------------------------------------------------------------------


def _apply_default_visible(seg: LanguageSegment) -> None:
    """
    Fallback: сегмент не попал ни в одну группу.

    Помечаем как visible (fail-safe: лучше показать, чем случайно скрыть контент).
    """
    seg.visibility = "visible"
    seg.hidden_reason = None
    seg.translation_of = []
    seg.parallel_group_id = None
    seg.is_orphan_target = False
    seg.is_orphan_foreign = False
    seg.is_ambiguous = False



    