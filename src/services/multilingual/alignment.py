# src/services/multilingual/alignment.py

"""
Layer 4: Alignment.

Задача:
- найти пары одинакового контента на разных языках (ParallelGroup);
- пометить одинокие сегменты как orphan;
- монолингвальный контент оформить как MonolingualGroup.

Архитектура:
Стратегии применяются КАСКАДОМ по остатку неспаренных сегментов на каждой странице:
1. split_from_single_element (самый надежный сигнал из Layer 2)
2. structural_anchor (по нумерации пунктов)
3. coordinate_columns (относительный column matching по высоте элементов + статистике страницы)
4. stacked_pairs (относительное вертикальное и горизонтальное соседство)
5. positional_sequential (для оставшихся крупных блоков)

ВСЕ геометрии (Y-gap, X-spread, Column alignment) рассчитываются ОТНОСИТЕЛЬНО:
- собственных габаритов элементов (bbox.height / bbox.width)
- статистики страницы (median_line_gap — медианный межстрочный интервал)

ПОЛНЫЙ ОТКАЗ ОТ ФИКСИРОВАННЫХ ЧИСЕЛ (8.0, 12.0, 15.0, 35.0 и т.д.)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.logging import get_logger

from services.multilingual.alignment_helpers import (
    ScopeTracker,
    cross_language_anchor_key,
)
from services.multilingual.models import (
    AlignmentMethod,
    Group,
    LanguageSegment,
    MonolingualGroup,
    OrphanGroup,
    PageLayout,
    ParallelGroup,
    ProcessingWarning,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы уверенности методов
# ---------------------------------------------------------------------------

_CONFIDENCE_SPLIT_SIBLINGS = 1.0
_CONFIDENCE_ANCHOR_HIGH = 0.90
_CONFIDENCE_COORDINATE_COLUMNS = 0.80
_CONFIDENCE_STACKED_PAIRS = 0.80
_CONFIDENCE_POSITIONAL_SEQUENTIAL = 0.60
_POSITIONAL_SEQUENTIAL_MIN_SEGMENTS = 2


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def align_segments(
    segments: list[LanguageSegment],
    page_layouts: dict[int, PageLayout],
    target_language: str,
) -> tuple[list[Group], list[ProcessingWarning]]:
    """
    Layer 4 Entry Point.
    """
    if not segments:
        return [], []

    warnings: list[ProcessingWarning] = []

    # 1. Bypass (структурные данные / нейтральные)
    bypass_groups, non_bypass_segments = _extract_bypass_groups(segments)
    if not non_bypass_segments:
        return bypass_groups, warnings

    # 2. Scope Tracking
    sorted_segments = sorted(
        non_bypass_segments,
        key=lambda s: (s.page, s.bbox.top, s.bbox.x0)
    )
    segments_with_scope = _attach_scope(sorted_segments)

    parallel_groups: list[ParallelGroup] = []

    # 3. Split Siblings Alignment (Самый сильный сигнал)
    split_groups, remaining = _align_split_siblings(segments_with_scope)
    parallel_groups.extend(split_groups)

    # 4. Structural Anchor Alignment
    anchor_groups, remaining = _align_by_anchor(remaining, warnings=warnings)
    parallel_groups.extend(anchor_groups)

    # 5. Каскадное применение геометрических стратегий (per page)
    by_page: dict[int, list[tuple[LanguageSegment, str]]] = defaultdict(list)
    for seg, scope in remaining:
        by_page[seg.page].append((seg, scope))

    all_paired_ids: set[str] = set()

    for page, page_segments in by_page.items():
        layout = page_layouts.get(page)

        # 5.1 Columns Alignment (относительно высоты строк + статистики страницы)
        col_groups, paired = _align_coordinate_columns(page, page_segments)
        parallel_groups.extend(col_groups)
        all_paired_ids.update(paired)
        page_segments = [item for item in page_segments if item[0].segment_id not in paired]

        # 5.2 Stacked Pairs Alignment (относительно высоты, ширины и статистики страницы)
        stacked_groups, paired = _align_stacked_pairs(page, page_segments)
        parallel_groups.extend(stacked_groups)
        all_paired_ids.update(paired)
        page_segments = [item for item in page_segments if item[0].segment_id not in paired]

        # 5.3 Positional Sequential (для блоков, если они есть)
        pos_groups, paired = _align_positional_sequential(page, page_segments, layout)
        parallel_groups.extend(pos_groups)
        all_paired_ids.update(paired)

    remaining = [
        (seg, scope) for seg, scope in remaining
        if seg.segment_id not in all_paired_ids
    ]

    # 6. Финализация (Orphans & Monolingual)
    final_groups: list[Group] = []
    final_groups.extend(bypass_groups)
    final_groups.extend(parallel_groups)

    final_groups.extend(_finalize_remaining_segments(remaining, page_layouts))
    _generate_orphan_warnings(final_groups, warnings)

    return final_groups, warnings


# ---------------------------------------------------------------------------
# Вспомогательные функции стратегий
# ---------------------------------------------------------------------------

def _extract_bypass_groups(
    segments: list[LanguageSegment],
) -> tuple[list[Group], list[LanguageSegment]]:
    bypass_groups: list[Group] = []
    non_bypass: list[LanguageSegment] = []
    counter = 0

    for seg in segments:
        if seg.is_bypass():
            counter += 1
            bypass_groups.append(MonolingualGroup(
                group_id=f"bypass_{counter:04d}",
                page=seg.page,
                segment_ids=[seg.segment_id],
            ))
        else:
            non_bypass.append(seg)

    return bypass_groups, non_bypass


def _attach_scope(
    segments: list[LanguageSegment],
) -> list[tuple[LanguageSegment, str]]:
    tracker = ScopeTracker()
    return [(seg, tracker.update(seg.anchor_uid)) for seg in segments]


def _align_split_siblings(
    segments_with_scope: list[tuple[LanguageSegment, str]],
) -> tuple[list[ParallelGroup], list[tuple[LanguageSegment, str]]]:
    by_source: dict[str, list[tuple[LanguageSegment, str]]] = defaultdict(list)
    for seg, scope in segments_with_scope:
        by_source[seg.source_element_id].append((seg, scope))

    parallel_groups: list[ParallelGroup] = []
    paired_ids: set[str] = set()
    counter = 0

    for source_id, group_items in by_source.items():
        if len(group_items) < 2:
            continue

        by_lang: dict[str, list[str]] = defaultdict(list)
        scripts: set[str] = set()
        included_segment_ids: list[str] = []

        for seg, _scope in group_items:
            by_lang[seg.language].append(seg.segment_id)
            included_segment_ids.append(seg.segment_id)
            if seg.script and seg.script != "other":
                scripts.add(seg.script)

        known_by_lang = {
            lang: sorted(seg_ids) for lang, seg_ids in by_lang.items()
            if lang not in ("unknown", "mixed")
        }
        ambiguous_by_lang = {
            lang: sorted(seg_ids) for lang, seg_ids in by_lang.items()
            if lang in ("unknown", "mixed")
        }

        can_form_group = False
        segments_by_language: dict[str, list[str]] = {}

        if len(known_by_lang) >= 2:
            segments_by_language = {l: sorted(ids) for l, ids in by_lang.items()}
            can_form_group = True
        elif len(known_by_lang) == 1 and ambiguous_by_lang:
            strong_split = all(seg.split_reason != "none" and seg.split_confidence >= 0.90 for seg, _ in group_items)
            if strong_split and len(scripts) >= 2:
                segments_by_language = {l: sorted(ids) for l, ids in by_lang.items()}
                can_form_group = True

        if not can_form_group:
            continue

        counter += 1
        parallel_groups.append(ParallelGroup(
            group_id=f"pair_split_{counter:04d}",
            page=group_items[0][0].page,
            scope=group_items[0][1],
            segments_by_language=segments_by_language,
            alignment_confidence=_CONFIDENCE_SPLIT_SIBLINGS,
            alignment_method="coordinate_columns",
        ))
        paired_ids.update(included_segment_ids)

    remaining = [(s, sc) for s, sc in segments_with_scope if s.segment_id not in paired_ids]
    return parallel_groups, remaining


def _align_by_anchor(
    segments_with_scope: list[tuple[LanguageSegment, str]],
    warnings: list[ProcessingWarning],
) -> tuple[list[ParallelGroup], list[tuple[LanguageSegment, str]]]:
    anchor_index: dict[tuple[str, str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    anchor_pages: dict[tuple[str, str, str], int] = {}

    for seg, scope in segments_with_scope:
        if not seg.anchor_uid or seg.language in ("unknown", "mixed"):
            continue

        key = cross_language_anchor_key(seg.anchor_uid)
        if not key:
            continue

        full_key = (scope, key[0], key[1])
        anchor_index[full_key][seg.language].append(seg.segment_id)
        if full_key not in anchor_pages or seg.page < anchor_pages[full_key]:
            anchor_pages[full_key] = seg.page

    parallel_groups: list[ParallelGroup] = []
    paired_ids: set[str] = set()
    counter = 0

    for (scope, category, number), by_lang in anchor_index.items():
        if len(by_lang) < 2:
            continue

        if any(len(ids) > 1 for ids in by_lang.values()):
            warnings.append(ProcessingWarning(
                warning_type="anchor_matching_ambiguous",
                page=anchor_pages[(scope, category, number)],
                details={"scope": scope, "category": category, "number": number},
            ))
            continue

        counter += 1
        parallel_groups.append(ParallelGroup(
            group_id=f"pair_anchor_{counter:04d}",
            page=anchor_pages[(scope, category, number)],
            scope=scope,
            anchor_uid_normalized=(category, number),
            segments_by_language={l: sorted(ids) for l, ids in by_lang.items()},
            alignment_confidence=_CONFIDENCE_ANCHOR_HIGH,
            alignment_method="structural_anchor",
        ))
        for ids in by_lang.values():
            paired_ids.update(ids)

    remaining = [(s, sc) for s, sc in segments_with_scope if s.segment_id not in paired_ids]
    return parallel_groups, remaining


def _align_coordinate_columns(
    page: int,
    page_segments: list[tuple[LanguageSegment, str]],
) -> tuple[list[ParallelGroup], set[str]]:
    """
    100% ОТНОСИТЕЛЬНЫЙ КОЛОНКОВЫЙ СПАРИВАТЕЛЬ.
    Допуск вычисляется ТОЛЬКО от высоты элементов + статистики страницы.
    """
    if len(page_segments) < 2:
        return [], set()

    all_x = [seg.bbox.x_center for seg, _ in page_segments if not seg.bbox.is_zero]
    if len(all_x) < 2:
        return [], set()

    median_x = sorted(all_x)[len(all_x) // 2]
    left_col, right_col = [], []

    for seg, scope in page_segments:
        if not seg.bbox.is_zero:
            (left_col if seg.bbox.x_center < median_x else right_col).append((seg, scope))

    left_col.sort(key=lambda i: i[0].bbox.top)
    right_col.sort(key=lambda i: i[0].bbox.top)

    # Вычисляем медианный межстрочный интервал на этой странице
    all_tops = sorted([seg.bbox.top for seg, _ in page_segments if not seg.bbox.is_zero])
    line_gaps = [
        all_tops[i+1] - all_tops[i] 
        for i in range(len(all_tops)-1) 
        if all_tops[i+1] - all_tops[i] > 0
    ]
    median_line_gap = sorted(line_gaps)[len(line_gaps) // 2] if line_gaps else 10.0

    groups: list[ParallelGroup] = []
    paired_ids: set[str] = set()
    counter = 0

    for left_seg, left_scope in left_col:
        if left_seg.segment_id in paired_ids:
            continue

        best_right = None
        best_delta = float("inf")

        for right_seg, right_scope in right_col:
            if right_seg.segment_id in paired_ids or left_seg.language == right_seg.language:
                continue
            if left_seg.language in ("unknown", "mixed") or right_seg.language in ("unknown", "mixed"):
                continue

            dy = abs(right_seg.bbox.y_center - left_seg.bbox.y_center)
            
            # УНИВЕРСАЛЬНЫЙ ДОПУСК: 
            # Берём БОЛЬШЕЕ из: (1) высота элемента, (2) медианный интервал строки на странице
            # Умножаем на 2.5 — это покрывает до 2-3 строк текста разной длины
            reference_size = max(left_seg.bbox.height, right_seg.bbox.height, median_line_gap)
            max_allowed_dy = reference_size * 2.5

            if dy <= max_allowed_dy and dy < best_delta:
                best_delta = dy
                best_right = (right_seg, right_scope)

        if best_right:
            right_seg, _ = best_right
            counter += 1
            groups.append(ParallelGroup(
                group_id=f"pair_col_{page:03d}_{counter:03d}",
                page=page,
                scope=left_scope,
                segments_by_language={
                    left_seg.language: [left_seg.segment_id],
                    right_seg.language: [right_seg.segment_id],
                },
                alignment_confidence=_CONFIDENCE_COORDINATE_COLUMNS,
                alignment_method="coordinate_columns",
            ))
            paired_ids.update([left_seg.segment_id, right_seg.segment_id])

    return groups, paired_ids


def _align_stacked_pairs(
    page: int,
    page_segments: list[tuple[LanguageSegment, str]],
) -> tuple[list[ParallelGroup], set[str]]:
    """
    100% ОТНОСИТЕЛЬНЫЙ СТАКИВАТЕЛЬ.
    Все допуски вычисляются от геометрии элементов и статистики страницы.
    """
    if len(page_segments) < 2:
        return [], set()

    sorted_segs = sorted(page_segments, key=lambda i: (i[0].bbox.top, i[0].bbox.x0))
    
    # Вычисляем медианный межстрочный интервал на странице
    all_tops = sorted([seg.bbox.top for seg, _ in sorted_segs if not seg.bbox.is_zero])
    line_gaps = [
        all_tops[i+1] - all_tops[i] 
        for i in range(len(all_tops)-1) 
        if all_tops[i+1] - all_tops[i] > 0
    ]
    median_line_gap = sorted(line_gaps)[len(line_gaps) // 2] if line_gaps else 10.0

    groups: list[ParallelGroup] = []
    paired_ids: set[str] = set()
    counter = 0

    i = 0
    while i < len(sorted_segs) - 1:
        seg_a, scope_a = sorted_segs[i]
        
        if seg_a.segment_id in paired_ids:
            i += 1
            continue

        matched = False
        for j in range(1, 6):
            if i + j >= len(sorted_segs):
                break
                
            seg_b, scope_b = sorted_segs[i + j]
            if seg_b.segment_id in paired_ids:
                continue

            if seg_a.language == seg_b.language or seg_a.language in ("unknown", "mixed") or seg_b.language in ("unknown", "mixed"):
                continue

            # Y-ДОПУСК: Зазор не должен превышать 3 медианных межстрочных интервала
            dy_gap = seg_b.bbox.top - seg_a.bbox.bottom
            max_allowed_gap = median_line_gap * 3.0

            # X-ДОПУСК: Относительно ширины элементов (без фиксированных чисел)
            dx_left = abs(seg_b.bbox.x0 - seg_a.bbox.x0)
            dx_center = abs(seg_b.bbox.x_center - seg_a.bbox.x_center)
            
            min_width = min(seg_a.bbox.width, seg_b.bbox.width)
            max_width = max(seg_a.bbox.width, seg_b.bbox.width)
            
            # Разрешаем сдвиг до 40% ширины (универсально для любого формата)
            is_x_aligned = (dx_left <= min_width * 0.4) or (dx_center <= max_width * 0.4)

            if dy_gap <= max_allowed_gap and is_x_aligned:
                counter += 1
                groups.append(ParallelGroup(
                    group_id=f"pair_stacked_{page:03d}_{counter:03d}",
                    page=page,
                    scope=scope_a,
                    segments_by_language={
                        seg_a.language: [seg_a.segment_id],
                        seg_b.language: [seg_b.segment_id],
                    },
                    alignment_confidence=_CONFIDENCE_STACKED_PAIRS,
                    alignment_method="stacked_cells",
                ))
                paired_ids.update([seg_a.segment_id, seg_b.segment_id])
                matched = True
                break
        
        i += 1

    return groups, paired_ids


def _align_positional_sequential(
    page: int,
    page_segments: list[tuple[LanguageSegment, str]],
    layout: PageLayout | None,
) -> tuple[list[ParallelGroup], set[str]]:
    """
    Позиционное спаривание последовательных языковых блоков.
    """
    if len(page_segments) < _POSITIONAL_SEQUENTIAL_MIN_SEGMENTS:
        return [], set()

    sorted_segs = sorted(page_segments, key=lambda i: (i[0].bbox.top, i[0].bbox.x0))
    
    blocks = []
    if layout and layout.block_boundaries:
        boundaries = sorted(set(layout.block_boundaries))
        for idx, start in enumerate(boundaries):
            end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(sorted_segs)
            if start < len(sorted_segs):
                blocks.append(sorted_segs[start:end])

    if len(blocks) != 2:
        block_a, block_b = [], []
        first_lang = None

        for item in sorted_segs:
            seg = item[0]
            if seg.language in ("unknown", "mixed"):
                continue
            if first_lang is None:
                first_lang = seg.language
                block_a.append(item)
            elif seg.language == first_lang and not block_b:
                block_a.append(item)
            else:
                block_b.append(item)

        if block_a and block_b:
            blocks = [block_a, block_b]

    if len(blocks) != 2:
        return [], set()

    block_a, block_b = blocks[0], blocks[1]
    
    lang_a = _dominant_language(block_a)
    lang_b = _dominant_language(block_b)

    if not lang_a or not lang_b or lang_a == lang_b:
        return [], set()

    groups: list[ParallelGroup] = []
    paired_ids: set[str] = set()
    counter = 0

    for i in range(min(len(block_a), len(block_b))):
        seg_a, scope_a = block_a[i]
        seg_b, scope_b = block_b[i]

        if seg_a.language == lang_a and seg_b.language == lang_b:
            counter += 1
            groups.append(ParallelGroup(
                group_id=f"pair_pos_{page:03d}_{counter:03d}",
                page=page,
                scope=scope_a,
                segments_by_language={
                    seg_a.language: [seg_a.segment_id],
                    seg_b.language: [seg_b.segment_id],
                },
                alignment_confidence=_CONFIDENCE_POSITIONAL_SEQUENTIAL,
                alignment_method="positional_sequential",
            ))
            paired_ids.update([seg_a.segment_id, seg_b.segment_id])

    return groups, paired_ids


def _dominant_language(segments: list[tuple[LanguageSegment, str]]) -> str | None:
    if not segments:
        return None
    counts = defaultdict(int)
    for seg, _ in segments:
        if seg.language not in ("unknown", "mixed"):
            counts[seg.language] += 1
    if not counts:
        return None
    max_lang, max_count = max(counts.items(), key=lambda x: x[1])
    return max_lang if max_count / sum(counts.values()) >= 0.5 else None


def _finalize_remaining_segments(
    remaining: list[tuple[LanguageSegment, str]],
    page_layouts: dict[int, PageLayout],
) -> list[Group]:
    if not remaining:
        return []

    by_page = defaultdict(list)
    for seg, scope in remaining:
        by_page[seg.page].append((seg, scope))

    groups: list[Group] = []
    counter_orphan = counter_mono = 0

    for page, page_segments in by_page.items():
        layout = page_layouts.get(page)

        if layout and layout.layout_type == "monolingual":
            counter_mono += 1
            groups.append(MonolingualGroup(
                group_id=f"mono_{page:03d}_{counter_mono:03d}",
                page=page,
                scope=page_segments[0][1] if page_segments else "",
                segment_ids=sorted([s.segment_id for s, _ in page_segments]),
            ))
        else:
            by_lang = defaultdict(list)
            for seg, scope in page_segments:
                by_lang[seg.language].append((seg, scope))

            for lang, lang_segments in by_lang.items():
                counter_orphan += 1
                
                reason = "no_pair_found"
                if len(lang_segments) == 1:
                    reason = "single_element"
                elif not any(s.anchor_uid for s, _ in lang_segments):
                    reason = "no_anchor_available"

                groups.append(OrphanGroup(
                    group_id=f"orphan_{page:03d}_{counter_orphan:03d}",
                    page=page,
                    orphan_language=lang,
                    scope=lang_segments[0][1] if lang_segments else "",
                    segment_ids=sorted([s.segment_id for s, _ in lang_segments]),
                    orphan_reason=reason,
                ))

    return groups


def _generate_orphan_warnings(groups: list[Group], warnings: list[ProcessingWarning]) -> None:
    orphan_by_page = defaultdict(list)
    for group in groups:
        if isinstance(group, OrphanGroup):
            orphan_by_page[group.page].append(group)

    for page, page_orphans in orphan_by_page.items():
        total = sum(len(g.segment_ids) for g in page_orphans)
        if total >= 5:
            warnings.append(ProcessingWarning(
                warning_type="orphan_cluster",
                page=page,
                details={"orphan_groups_count": len(page_orphans), "total_orphan_segments": total},
            ))


            