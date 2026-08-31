# src/services/structure/_heading_scoring/_core.py

"""Основной процесс скоринга кандидата в заголовки."""

from __future__ import annotations

import re
from typing import Any

from services.structure._models._constants import (
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING as SEMANTIC_TYPE_APPENDIX_HEADING,
)
from services.structure._models._constants import (
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM as SEMANTIC_TYPE_DEFINITION_ITEM,
)
from services.structure._models._constants import (
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK as SEMANTIC_TYPE_SIGNATURE_BLOCK,
)
from services.structure.heading_features import (
    alpha_uid_is_plausible,
    classify_uid_kind,
    digit_uid_without_textual_title,
    has_letters,
    is_bad_heading_title,
    is_garbage_heading_title,
    looks_like_body_sentence_title,
    looks_like_definition_term_title,
    looks_like_lowercase_continuation,
    looks_like_numeric_amount_continuation,
    looks_like_reference_led_clause_continuation,
    looks_like_substantive_clause_line,
    looks_like_toc_line,
    roman_uid_is_plausible,
    starts_with_quoted_term,
    uid_is_plausible,

)
from services.structure.heading_patterns import _normalize_title, normalize_spaces
from services.structure.legal_heading_rules import (
    build_numeric_uid_continuity,
    looks_like_appendix_heading,
    looks_like_definition_item,
    looks_like_signature_or_requisites_heading,
)

from ._logic import _compute_continuity_bonus, _resolve_semantic_type_in_scorer, _toc_match_bonus
from ._types import CandidateStatus, HeadingScoreResult
from ._utils import (
    _clamp_score,
    _is_effectively_empty_title,
    _is_recoverable_toc_like_element_type,
    _is_strict_numeric_uid,
    _is_strong_heading_element_type,
    _looks_like_appendix_uid,
    _looks_like_root_numeric_uid,
    _looks_too_long_for_heading,
    _normalize_element_type,
    level_from_uid,
)


def _has_strong_toc_confirmation(toc_match_type: str | None, toc_bonus: float) -> bool:
    """Strong TOC confirmation: exact match или сильный fuzzy match.

    Phase 13.5:
    fuzzy threshold снижен до 0.03, потому что _toc_match_bonus()
    возвращает для fuzzy максимум 0.04. Старый порог 0.08 был недостижим.
    """
    if toc_match_type == "exact":
        return True
    if toc_match_type == "fuzzy" and toc_bonus >= 0.03:
        return True
    return False


def _has_structural_confirmation(
    *,
    strong_toc_confirmation: bool,
    cont_bonus: float,
    u_cont: dict[str, Any] | None = None,
) -> bool:
    if strong_toc_confirmation:
        return True
    if cont_bonus >= 0.03:
        return True
    if u_cont and any(bool(v) for v in u_cont.values()):
        return True
    return False


def _has_strong_structural_confirmation(
    *,
    strong_toc_confirmation: bool,
    cont_bonus: float,
    u_cont: dict[str, Any] | None = None,
    uid: str | None = None,
    level: int = 1,
) -> bool:
    if strong_toc_confirmation and cont_bonus >= 0.02:
        return True
    if strong_toc_confirmation and u_cont and any(bool(v) for v in u_cont.values()):
        return True
    if level >= 2 and cont_bonus >= 0.04 and u_cont and any(bool(v) for v in u_cont.values()):
        return True
    if uid and _looks_like_root_numeric_uid(uid) and (strong_toc_confirmation or cont_bonus >= 0.03):
        return True
    
    # Универсальное правило: подразделы с явной нумерацией (1.1, 1.1.1, 2.8...)
    # имеют структурное подтверждение даже без TOC match
    # Работает для любых языков и форматов нумерации
    if level >= 2 and uid:
        # Числовая иерархия: 1.1, 1.1.1, 2.8...
        if re.match(r'^\d+(?:\.\d+)+$', uid):
            if cont_bonus >= 0.02 or (u_cont and any(bool(v) for v in u_cont.values())):
                return True
        # Буквенная иерархия: (a), (b), a), b)...
        elif re.match(r'^\(?[a-zA-Zа-яА-Я]\)?$', uid) and level >= 2:
            if cont_bonus >= 0.02:
                return True
    
    return False


def _top_level_numeric_base_score(
    *,
    is_strong: bool,
    is_rec_toc: bool,
    t_bonus: float,
    cont_bonus: float,
    strong_toc_confirmation: bool,
) -> float:
    score = 0.90
    if is_strong:
        score += 0.03
    if is_rec_toc:
        score -= 0.05
    score += t_bonus
    score += cont_bonus
    if strong_toc_confirmation:
        score += 0.03
    return _clamp_score(score)


def _nested_numeric_base_score(
    *,
    level: int,
    is_strong: bool,
    is_rec_toc: bool,
    t_bonus: float,
    cont_bonus: float,
    strong_toc_confirmation: bool,
) -> float:
    if level == 2:
        score = 0.84
        if is_strong:
            score += 0.04
        if is_rec_toc:
            score -= 0.04
        score += t_bonus
        score += cont_bonus
        if strong_toc_confirmation:
            score += 0.05
        return _clamp_score(score)

    if level == 3:
        score = 0.76
        if is_strong:
            score += 0.04
        if is_rec_toc:
            score -= 0.04
        score += t_bonus
        score += cont_bonus
        if strong_toc_confirmation:
            score += 0.06
        return _clamp_score(score)

    score = 0.64 + t_bonus + min(cont_bonus, 0.07)
    if is_strong:
        score += 0.03
    if is_rec_toc:
        score -= 0.03
    if strong_toc_confirmation:
        score += 0.05
    return _clamp_score(score)


def _accepted_status_for_numeric_level(
    *,
    level: int,
    score: float,
    strong_structural_confirmation: bool,
) -> CandidateStatus:
    if level == 1:
        return CandidateStatus.ACCEPTED
    if level == 2:
        if score >= 0.80:
            return CandidateStatus.ACCEPTED
        if score >= 0.72 and strong_structural_confirmation:
            return CandidateStatus.ACCEPTED
        return CandidateStatus.AMBIGUOUS
    if level == 3:
        if score >= 0.74:
            return CandidateStatus.ACCEPTED
        if score >= 0.68 and strong_structural_confirmation:
            return CandidateStatus.ACCEPTED
        return CandidateStatus.AMBIGUOUS
    if score >= 0.70 and strong_structural_confirmation:
        return CandidateStatus.ACCEPTED
    return CandidateStatus.AMBIGUOUS


def _guarded_numeric_recovery_score(
    *,
    base: float,
    t_bonus: float,
    cont_bonus: float,
    is_rec_toc: bool,
    is_strong: bool,
    u_cont: dict[str, Any] | None,
    strong_structural_confirmation: bool,
) -> float:
    score = (
        base
        + min(t_bonus, 0.05)
        - (0.04 if is_rec_toc else 0)
        + (0.03 if is_strong else 0)
        + cont_bonus
        + (0.02 if u_cont and any(u_cont.values()) else 0)
        + (0.03 if strong_structural_confirmation else 0)
    )
    return _clamp_score(score)


def score_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict[str, Any] | None = None,
    element_type: str | None = None,
    semantic_element_type: str | None = None,
    continuity_signals: dict[str, Any] | None = None,
    prev_heading_uid: str | None = None,
    next_heading_uid: str | None = None,
) -> HeadingScoreResult:
    rt = normalize_spaces(raw_text)
    u = normalize_spaces(uid)
    lvl = level_from_uid(u) if u else 1
    t = _normalize_title(normalize_spaces(title), uid_depth=lvl)
    el_type_norm = _normalize_element_type(element_type)
    is_rec_toc = _is_recoverable_toc_like_element_type(el_type_norm)
    is_strong = _is_strong_heading_element_type(el_type_norm)

    accept_reasons: list[str] = []
    reject_reasons: list[str] = []
    legal_neg: list[str] = []

    cls_sem = str(semantic_element_type or "").strip().lower()
    if cls_sem == SEMANTIC_TYPE_DEFINITION_ITEM:
        legal_neg.append("semantic_type_definition_item_by_classifier")
    if cls_sem == SEMANTIC_TYPE_SIGNATURE_BLOCK:
        legal_neg.append("semantic_type_signature_block_by_classifier")
    if cls_sem == SEMANTIC_TYPE_APPENDIX_HEADING:
        accept_reasons.append("semantic_type_appendix_heading_by_classifier")

    cont_bonus, cont_reasons = _compute_continuity_bonus(continuity_signals)
    u_cont = build_numeric_uid_continuity(
        prev_uid=prev_heading_uid,
        current_uid=u,
        next_uid=next_heading_uid,
    )
    if any(u_cont.values()):
        accept_reasons.append("uid_monotonic_series")

    t_bonus, t_type, t_reasons = _toc_match_bonus(toc_match)
    strong_toc_confirmation = _has_strong_toc_confirmation(t_type, t_bonus)
    structural_confirmation = _has_structural_confirmation(
        strong_toc_confirmation=strong_toc_confirmation,
        cont_bonus=cont_bonus,
        u_cont=u_cont,
    )
    strong_structural_confirmation = _has_strong_structural_confirmation(
        strong_toc_confirmation=strong_toc_confirmation,
        cont_bonus=cont_bonus,
        u_cont=u_cont,
        uid=u,
        level=lvl,
    )

    if looks_like_toc_line(rt):
        if is_rec_toc:
            sc = _clamp_score(
                0.34
                + (0.08 if t_type == "exact" else min(t_bonus, 0.05))
                + (0.04 if is_strong else 0)
                + (0.03 if _looks_like_root_numeric_uid(u) and strong_toc_confirmation else 0)
                + (0.02 if _looks_like_appendix_uid(u) and strong_toc_confirmation else 0)
                + (0.03 if strong_structural_confirmation else 0)
            )
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "toc_like_line_recoverable",
                accept_reasons + t_reasons,
                ["toc_like_line", "recoverable_toc_like_element_type"],
                t_bonus,
                t_type,
                semantic_element_type=cls_sem or None,
                continuity_bonus=cont_bonus,
                legal_negative_signals=legal_neg,
                structural_evidence={
                    "strong_toc_confirmation": strong_toc_confirmation,
                    "structural_confirmation": structural_confirmation,
                    "strong_structural_confirmation": strong_structural_confirmation,
                    "is_root_numeric_uid": _looks_like_root_numeric_uid(u),
                    "is_appendix_uid": _looks_like_appendix_uid(u),
                },
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "toc_like_line",
            [],
            ["toc_like_line"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={
                "strong_toc_confirmation": strong_toc_confirmation,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
            },
        )

    if not u or not t:
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "empty_uid_or_title",
            [],
            ["empty_uid_or_title"],
            structural_evidence={},
        )
    if _is_effectively_empty_title(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "empty_or_punct_only_title",
            [],
            ["empty_or_punct_only_title"],
            structural_evidence={},
        )
    if len(t) <= 2 and not has_letters(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "too_short_non_textual_title",
            [],
            ["too_short_non_textual_title"],
            structural_evidence={},
        )
    if not has_letters(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.05,
            "title_without_letters",
            [],
            ["title_without_letters"],
            structural_evidence={},
        )
    if is_garbage_heading_title(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "garbage_heading_title",
            [],
            ["garbage_heading_title"],
            structural_evidence={},
        )
    if is_bad_heading_title(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.05,
            "bad_heading_title",
            [],
            ["bad_heading_title"],
            structural_evidence={},
        )

    is_num = _is_strict_numeric_uid(u)
    uid_kind = classify_uid_kind(u)

    if is_num:
        if not uid_is_plausible(u):
            return HeadingScoreResult(
                CandidateStatus.REJECTED,
                0.05,
                "implausible_numeric_uid",
                [],
                ["implausible_numeric_uid"],
                t_bonus,
                t_type,
                semantic_element_type=cls_sem or None,
                continuity_bonus=cont_bonus,
                legal_negative_signals=legal_neg,
                structural_evidence={
                    "uid_kind": uid_kind,
                },
            )
        accept_reasons.append("plausible_numeric_uid")
    elif roman_uid_is_plausible(u):
        accept_reasons.append("plausible_roman_uid")
    elif alpha_uid_is_plausible(u):
        accept_reasons.append("plausible_alpha_uid")
    elif u.startswith("S-"):
        accept_reasons.append("synthetic_caps_uid")
        uid_kind = "synthetic_caps"
    else:
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.05,
            "unsupported_uid_format",
            [],
            ["unsupported_uid_format"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
            },
        )

    if digit_uid_without_textual_title(u, t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.05,
            "digit_uid_without_textual_title",
            accept_reasons.copy(),
            ["digit_uid_without_textual_title"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
            },
        )

    numeric_amount_continuation = bool(
        is_num and looks_like_numeric_amount_continuation(t)
    )
    reference_led_clause_continuation = bool(
        is_num and lvl >= 2 and looks_like_reference_led_clause_continuation(t)
    )

    if numeric_amount_continuation:
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.05,
            "numeric_amount_continuation_title",
            accept_reasons.copy(),
            ["numeric_amount_continuation_title"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg + ["numeric_amount_continuation"],
            structural_evidence={
                "uid_kind": uid_kind,
                "uid_level": lvl,
                "strong_toc_confirmation": strong_toc_confirmation,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
            },
        )

    if reference_led_clause_continuation and not strong_toc_confirmation:
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.08,
            "reference_led_clause_continuation",
            accept_reasons.copy(),
            ["reference_led_clause_continuation"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg + ["reference_led_clause_continuation"],
            structural_evidence={
                "uid_kind": uid_kind,
                "uid_level": lvl,
                "strong_toc_confirmation": strong_toc_confirmation,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "uid_continuity": u_cont,
            },
        )

    if starts_with_quoted_term(t) or looks_like_definition_term_title(t):
        if (
            is_num
            and lvl >= 2
            and structural_confirmation
            and not reference_led_clause_continuation
            and not numeric_amount_continuation
        ):
            sc = _guarded_numeric_recovery_score(
                base=0.55,
                t_bonus=t_bonus,
                cont_bonus=cont_bonus,
                is_rec_toc=is_rec_toc,
                is_strong=is_strong,
                u_cont=u_cont,
                strong_structural_confirmation=strong_structural_confirmation,
            )
            status = CandidateStatus.ACCEPTED if strong_structural_confirmation and sc >= 0.67 else CandidateStatus.AMBIGUOUS
            return HeadingScoreResult(
                status,
                sc,
                "definition_like_title_recovered" if status == CandidateStatus.ACCEPTED else "definition_like_title",
                accept_reasons + t_reasons,
                ["definition_like_title"],
                min(t_bonus, 0.05),
                t_type,
                semantic_element_type=cls_sem or None,
                continuity_bonus=cont_bonus,
                legal_negative_signals=legal_neg,
                structural_evidence={
                    "uid_kind": uid_kind,
                    "strong_toc_confirmation": strong_toc_confirmation,
                    "structural_confirmation": structural_confirmation,
                    "strong_structural_confirmation": strong_structural_confirmation,
                    "uid_continuity": u_cont,
                },
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.10,
            "definition_like_title",
            accept_reasons.copy(),
            ["definition_like_title"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "uid_continuity": u_cont,
            },
        )

    if looks_like_lowercase_continuation(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.08,
            "lowercase_continuation_title",
            accept_reasons.copy(),
            ["lowercase_continuation_title"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={},
        )

    if _looks_too_long_for_heading(t, level=lvl) or looks_like_substantive_clause_line(t):
        # Patch 3 (final):
        # Для legal docs clause-like substantive sentence после numeric uid
        # НЕ должен автоматически жёстко reject'иться.
        #
        # Ключевой practical case:
        #   2.1 В соответствии с Договором...
        #   6.3 В случае нарушения...
        # где:
        #   - extractor raw_type = heading
        #   - classifier element_type = heading_candidate
        #   - classifier semantic_element_type = subsection_heading
        # но structural_confirmation ещё не успевает сработать.
        #
        # Поэтому разрешаем recovery не только через structural_confirmation,
        # но и через сильный classifier/extractor consensus.

        classifier_says_nested_heading = (
            str(element_type or "").strip().lower() == "heading_candidate"
            and str(cls_sem or "").strip().lower() == "subsection_heading"
        )

        recoverable_legal_clause = (
            is_num
            and lvl >= 2
            and not reference_led_clause_continuation
            and not numeric_amount_continuation
            and (
                structural_confirmation
                or classifier_says_nested_heading
            )
        )

        if recoverable_legal_clause:
            sc = _guarded_numeric_recovery_score(
                base=0.60,
                t_bonus=t_bonus,
                cont_bonus=cont_bonus,
                is_rec_toc=is_rec_toc,
                is_strong=is_strong,
                u_cont=u_cont,
                strong_structural_confirmation=strong_structural_confirmation,
            )

            # Дополнительный буст, если classifier уже уверен что это nested heading.
            if classifier_says_nested_heading:
                sc = _clamp_score(sc + 0.08)

            status = (
                CandidateStatus.ACCEPTED
                if sc >= 0.70 and (strong_structural_confirmation or classifier_says_nested_heading)
                else CandidateStatus.AMBIGUOUS
            )

            return HeadingScoreResult(
                status,
                sc,
                (
                    "substantive_clause_like_title_recovered"
                    if status == CandidateStatus.ACCEPTED
                    else "substantive_clause_like_title"
                ),
                accept_reasons + t_reasons,
                ["substantive_clause_like_title"],
                min(t_bonus, 0.05),
                t_type,
                semantic_element_type=cls_sem or None,
                continuity_bonus=cont_bonus,
                legal_negative_signals=legal_neg,
                structural_evidence={
                    "uid_kind": uid_kind,
                    "strong_toc_confirmation": strong_toc_confirmation,
                    "structural_confirmation": structural_confirmation,
                    "strong_structural_confirmation": strong_structural_confirmation,
                    "classifier_says_nested_heading": classifier_says_nested_heading,
                    "uid_continuity": u_cont,
                },
            )

        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.12,
            "substantive_clause_like_title",
            accept_reasons.copy(),
            ["substantive_clause_like_title"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "classifier_says_nested_heading": classifier_says_nested_heading,
                "uid_continuity": u_cont,
            },
        )

    if looks_like_body_sentence_title(u, t):
        if (
            is_num
            and lvl >= 2
            and structural_confirmation
            and not reference_led_clause_continuation
            and not numeric_amount_continuation
        ):
            sc = _guarded_numeric_recovery_score(
                base=0.57,
                t_bonus=t_bonus,
                cont_bonus=cont_bonus,
                is_rec_toc=is_rec_toc,
                is_strong=is_strong,
                u_cont=u_cont,
                strong_structural_confirmation=strong_structural_confirmation,
            )
            status = CandidateStatus.ACCEPTED if strong_structural_confirmation and sc >= 0.68 else CandidateStatus.AMBIGUOUS
            return HeadingScoreResult(
                status,
                sc,
                "body_like_sentence_title_recovered" if status == CandidateStatus.ACCEPTED else "body_like_sentence_title",
                accept_reasons + t_reasons,
                ["body_like_sentence_title"],
                min(t_bonus, 0.05),
                t_type,
                semantic_element_type=cls_sem or None,
                continuity_bonus=cont_bonus,
                legal_negative_signals=legal_neg,
                structural_evidence={
                    "uid_kind": uid_kind,
                    "strong_toc_confirmation": strong_toc_confirmation,
                    "structural_confirmation": structural_confirmation,
                    "strong_structural_confirmation": strong_structural_confirmation,
                    "uid_continuity": u_cont,
                },
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.10,
            "body_like_sentence_title",
            accept_reasons.copy(),
            ["body_like_sentence_title"],
            t_bonus,
            t_type,
            semantic_element_type=cls_sem or None,
            continuity_bonus=cont_bonus,
            legal_negative_signals=legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "uid_continuity": u_cont,
            },
        )

    if looks_like_appendix_heading(rt):
        sc = _clamp_score(
            0.72
            + min(t_bonus, 0.06)
            + cont_bonus
            + (0.03 if is_strong else 0)
            + (0.04 if strong_toc_confirmation else 0)
            + (0.03 if strong_structural_confirmation else 0)
        )
        return HeadingScoreResult(
            CandidateStatus.ACCEPTED if sc >= 0.78 else CandidateStatus.AMBIGUOUS,
            sc,
            "appendix_heading",
            accept_reasons + t_reasons + ["appendix_heading"],
            reject_reasons,
            t_bonus,
            t_type,
            str(SEMANTIC_TYPE_APPENDIX_HEADING),
            cont_bonus,
            legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
                "strong_toc_confirmation": strong_toc_confirmation,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "is_appendix_uid": _looks_like_appendix_uid(u),
            },
        )

    if looks_like_definition_item(rt) or looks_like_definition_item(t):
        legal_neg.append("looks_like_definition_item_by_scorer")
        if is_num and lvl >= 2 and strong_structural_confirmation:
            sc = _clamp_score(
                0.50
                + min(t_bonus, 0.04)
                + cont_bonus
                - (0.04 if is_rec_toc else 0)
                + (0.02 if any(u_cont.values()) else 0)
                + 0.03
            )
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "definition_item_by_legal_rules_recoverable",
                accept_reasons + t_reasons,
                ["definition_item_by_legal_rules"],
                t_bonus,
                t_type,
                str(SEMANTIC_TYPE_DEFINITION_ITEM),
                cont_bonus,
                legal_neg,
                structural_evidence={
                    "uid_kind": uid_kind,
                    "strong_toc_confirmation": strong_toc_confirmation,
                    "structural_confirmation": structural_confirmation,
                    "strong_structural_confirmation": strong_structural_confirmation,
                    "uid_continuity": u_cont,
                },
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.08,
            "definition_item_by_legal_rules",
            accept_reasons,
            ["definition_item_by_legal_rules"],
            0.0,
            None,
            str(SEMANTIC_TYPE_DEFINITION_ITEM),
            cont_bonus,
            legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "uid_continuity": u_cont,
            },
        )

    if looks_like_signature_or_requisites_heading(rt):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "signature_or_requisites_block",
            accept_reasons,
            ["signature_or_requisites_block"],
            0.0,
            None,
            str(SEMANTIC_TYPE_SIGNATURE_BLOCK),
            cont_bonus,
            legal_neg + ["looks_like_signature_or_requisites_by_scorer"],
            structural_evidence={
                "uid_kind": uid_kind,
            },
        )

    accept_reasons.extend(t_reasons)
    if cont_reasons:
        accept_reasons.extend(r for r in cont_reasons if not r.startswith("continuity_next"))
        reject_reasons.extend(r for r in cont_reasons if r.startswith("continuity_next"))

    res_sem = _resolve_semantic_type_in_scorer(
        uid=u,
        title=t,
        raw_text=rt,
        element_type=element_type,
        classifier_semantic_type=cls_sem or None,
    )

    if is_num:
        if lvl == 1:
            sc = _top_level_numeric_base_score(
                is_strong=is_strong,
                is_rec_toc=is_rec_toc,
                t_bonus=t_bonus,
                cont_bonus=cont_bonus,
                strong_toc_confirmation=strong_toc_confirmation,
            )
            return HeadingScoreResult(
                CandidateStatus.ACCEPTED,
                sc,
                "accepted",
                accept_reasons + ["top_level_numeric_heading"],
                reject_reasons,
                t_bonus,
                t_type,
                res_sem,
                cont_bonus,
                legal_neg,
                structural_evidence={
                    "uid_kind": uid_kind,
                    "uid_level": lvl,
                    "strong_toc_confirmation": strong_toc_confirmation,
                    "structural_confirmation": structural_confirmation,
                    "strong_structural_confirmation": strong_structural_confirmation,
                    "is_root_numeric_uid": _looks_like_root_numeric_uid(u),
                    "uid_continuity": u_cont,
                },
            )

        sc = _nested_numeric_base_score(
            level=lvl,
            is_strong=is_strong,
            is_rec_toc=is_rec_toc,
            t_bonus=t_bonus,
            cont_bonus=cont_bonus,
            strong_toc_confirmation=strong_toc_confirmation,
        )
        st = _accepted_status_for_numeric_level(
            level=lvl,
            score=sc,
            strong_structural_confirmation=strong_structural_confirmation,
        )

        if lvl == 2:
            reason = "accepted" if st == CandidateStatus.ACCEPTED else "nested_numeric_heading_needs_confirmation"
            accept_tag = "nested_numeric_heading"
        elif lvl == 3:
            reason = "accepted" if st == CandidateStatus.ACCEPTED else "deep_numeric_heading_needs_confirmation"
            accept_tag = "deep_numeric_heading_l3"
        else:
            reason = "accepted" if st == CandidateStatus.ACCEPTED else "very_deep_numeric_heading"
            accept_tag = "very_deep_numeric_heading"

        return HeadingScoreResult(
            st,
            sc,
            reason,
            accept_reasons + [accept_tag],
            reject_reasons,
            t_bonus,
            t_type,
            res_sem,
            cont_bonus,
            legal_neg,
            structural_evidence={
                "uid_kind": uid_kind,
                "uid_level": lvl,
                "strong_toc_confirmation": strong_toc_confirmation,
                "structural_confirmation": structural_confirmation,
                "strong_structural_confirmation": strong_structural_confirmation,
                "uid_continuity": u_cont,
            },
        )

    base = 0.76 if uid_kind == "roman" else 0.60
    sc = _clamp_score(
        base
        + t_bonus
        + min(cont_bonus, 0.06)
        + (0.03 if is_strong else 0)
        + (0.03 if strong_toc_confirmation else 0)
        + (0.02 if strong_structural_confirmation else 0)
    )
    st = CandidateStatus.ACCEPTED if sc >= 0.82 or (sc >= 0.76 and strong_structural_confirmation and uid_kind == "roman") else CandidateStatus.AMBIGUOUS
    return HeadingScoreResult(
        st,
        sc,
        "accepted" if st == CandidateStatus.ACCEPTED else "roman_alpha_needs_conf",
        accept_reasons,
        reject_reasons,
        t_bonus,
        t_type,
        res_sem,
        cont_bonus,
        legal_neg,
        structural_evidence={
            "uid_kind": uid_kind,
            "uid_level": lvl,
            "strong_toc_confirmation": strong_toc_confirmation,
            "structural_confirmation": structural_confirmation,
            "strong_structural_confirmation": strong_structural_confirmation,
            "uid_continuity": u_cont,
        },
    )


    