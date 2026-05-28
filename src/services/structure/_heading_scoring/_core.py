# src/services/structure/_heading_scoring/_core.py

"""Основной процесс скоринга кандидата в заголовки."""

from __future__ import annotations

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
    _looks_too_long_for_heading,
    _normalize_element_type,
    level_from_uid,
)


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
    # 1. Нормализация
    rt = normalize_spaces(raw_text)
    u = normalize_spaces(uid)
    lvl = level_from_uid(u) if u else 1
    t = _normalize_title(normalize_spaces(title), uid_depth=lvl)
    el_type_norm = _normalize_element_type(element_type)
    is_rec_toc = _is_recoverable_toc_like_element_type(el_type_norm)
    is_strong = _is_strong_heading_element_type(el_type_norm)

    accept_reasons, reject_reasons, legal_neg = [], [], []

    # 1a-c. Ранние сигналы
    cls_sem = str(semantic_element_type or "").strip().lower()
    if cls_sem == SEMANTIC_TYPE_DEFINITION_ITEM:
        legal_neg.append("semantic_type_definition_item_by_classifier")
    if cls_sem == SEMANTIC_TYPE_SIGNATURE_BLOCK:
        legal_neg.append("semantic_type_signature_block_by_classifier")
    if cls_sem == SEMANTIC_TYPE_APPENDIX_HEADING:
        legal_neg.append("semantic_type_appendix_heading_by_classifier")

    cont_bonus, cont_reasons = _compute_continuity_bonus(continuity_signals)
    u_cont = build_numeric_uid_continuity(
        prev_uid=prev_heading_uid, current_uid=u, next_uid=next_heading_uid
    )
    if any(u_cont.values()):
        accept_reasons.append("uid_monotonic_series")

    # 2. TOC и пустые данные
    if looks_like_toc_line(rt):
        t_bonus, t_type, t_reasons = _toc_match_bonus(toc_match)
        if is_rec_toc:
            sc = _clamp_score(
                0.34
                + (0.08 if t_type == "exact" else min(t_bonus, 0.05))
                + (0.04 if is_strong else 0)
            )
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "toc_like_line_recoverable",
                accept_reasons + t_reasons,
                ["toc_like_line", "recoverable_toc_like_element_type"],
                t_bonus,
                t_type,
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED, 0.0, "toc_like_line", [], ["toc_like_line"], t_bonus, t_type
        )

    if not u or not t:
        return HeadingScoreResult(
            CandidateStatus.REJECTED, 0.0, "empty_uid_or_title", [], ["empty_uid_or_title"]
        )
    if _is_effectively_empty_title(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "empty_or_punct_only_title",
            [],
            ["empty_or_punct_only_title"],
        )
    if len(t) <= 2 and not has_letters(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.0,
            "too_short_non_textual_title",
            [],
            ["too_short_non_textual_title"],
        )
    if not has_letters(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED, 0.05, "title_without_letters", [], ["title_without_letters"]
        )
    if is_garbage_heading_title(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED, 0.0, "garbage_heading_title", [], ["garbage_heading_title"]
        )
    if is_bad_heading_title(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED, 0.05, "bad_heading_title", [], ["bad_heading_title"]
        )

    # 3. UID Plausibility
    is_num = _is_strict_numeric_uid(u)
    if is_num:
        if not uid_is_plausible(u):
            return HeadingScoreResult(
                CandidateStatus.REJECTED,
                0.05,
                "implausible_numeric_uid",
                [],
                ["implausible_numeric_uid"],
            )
        accept_reasons.append("plausible_numeric_uid")
    elif roman_uid_is_plausible(u):
        accept_reasons.append("plausible_roman_uid")
    elif alpha_uid_is_plausible(u):
        accept_reasons.append("plausible_alpha_uid")
    else:
        return HeadingScoreResult(
            CandidateStatus.REJECTED, 0.05, "unsupported_uid_format", [], ["unsupported_uid_format"]
        )

    if digit_uid_without_textual_title(u, t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.05,
            "digit_uid_without_textual_title",
            accept_reasons.copy(),
            ["digit_uid_without_textual_title"],
        )

    # 4. Блок AMBIGUOUS (Definitions, Body, Substantive) - ВОССТАНОВЛЕНО
    t_bonus, t_type, t_reasons = _toc_match_bonus(toc_match)

    # 4.1 Definitions
    if starts_with_quoted_term(t) or looks_like_definition_term_title(t):
        if is_num and lvl >= 2:
            sc = _clamp_score(
                0.42 + min(t_bonus, 0.03) - (0.08 if is_rec_toc else 0) + (0.03 if is_strong else 0)
            )
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "definition_like_title",
                accept_reasons + t_reasons,
                ["definition_like_title"],
                min(t_bonus, 0.03),
                t_type,
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.10,
            "definition_like_title",
            accept_reasons.copy(),
            ["definition_like_title"],
        )

    # 4.2 Lowercase continuation
    if looks_like_lowercase_continuation(t):
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.08,
            "lowercase_continuation_title",
            accept_reasons.copy(),
            ["lowercase_continuation_title"],
        )

    # 4.3 Substantive clause / Too long
    if _looks_too_long_for_heading(t, level=lvl) or looks_like_substantive_clause_line(t):
        if is_num and lvl >= 2:
            sc = _clamp_score(
                0.46 + min(t_bonus, 0.03) - (0.08 if is_rec_toc else 0) + (0.03 if is_strong else 0)
            )
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "substantive_clause_like_title",
                accept_reasons + t_reasons,
                ["substantive_clause_like_title"],
                min(t_bonus, 0.03),
                t_type,
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.12,
            "substantive_clause_like_title",
            accept_reasons.copy(),
            ["substantive_clause_like_title"],
        )

    # 4.4 Body sentence
    if looks_like_body_sentence_title(u, t):
        if is_num and lvl >= 2:
            sc = _clamp_score(
                0.45 + min(t_bonus, 0.03) - (0.08 if is_rec_toc else 0) + (0.03 if is_strong else 0)
            )
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "body_like_sentence_title",
                accept_reasons + t_reasons,
                ["body_like_sentence_title"],
                min(t_bonus, 0.03),
                t_type,
            )
        return HeadingScoreResult(
            CandidateStatus.REJECTED,
            0.10,
            "body_like_sentence_title",
            accept_reasons.copy(),
            ["body_like_sentence_title"],
        )

    # 5. Legal Negative Guards (Appendix, Definition Item, Signatures) - ВОССТАНОВЛЕНО
    if looks_like_appendix_heading(rt):
        sc = _clamp_score(0.60 + min(t_bonus, 0.03) + cont_bonus)
        return HeadingScoreResult(
            CandidateStatus.AMBIGUOUS,
            sc,
            "appendix_heading",
            accept_reasons + t_reasons,
            ["appendix_heading"],
            t_bonus,
            t_type,
            str(SEMANTIC_TYPE_APPENDIX_HEADING),
            cont_bonus,
            legal_neg + ["looks_like_appendix_heading_by_scorer"],
        )

    if looks_like_definition_item(rt) or looks_like_definition_item(t):
        legal_neg.append("looks_like_definition_item_by_scorer")
        if is_num and lvl >= 2:
            sc = _clamp_score(0.40 + min(t_bonus, 0.03) + cont_bonus - (0.08 if is_rec_toc else 0))
            return HeadingScoreResult(
                CandidateStatus.AMBIGUOUS,
                sc,
                "definition_item_by_legal_rules",
                accept_reasons + t_reasons,
                ["definition_item_by_legal_rules"],
                t_bonus,
                t_type,
                str(SEMANTIC_TYPE_DEFINITION_ITEM),
                cont_bonus,
                legal_neg,
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
        )

    # 6. Финальное решение по уровням
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
            sc = _clamp_score(
                0.90
                + (0.03 if is_strong else 0)
                - (0.05 if is_rec_toc else 0)
                + t_bonus
                + cont_bonus
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
            )
        if lvl == 2:
            sc = _clamp_score(
                0.78
                + (0.04 if is_strong else 0)
                - (0.06 if is_rec_toc else 0)
                + t_bonus
                + cont_bonus
            )
            st = CandidateStatus.ACCEPTED if sc >= 0.86 else CandidateStatus.AMBIGUOUS
            return HeadingScoreResult(
                st,
                sc,
                "accepted"
                if st == CandidateStatus.ACCEPTED
                else "nested_numeric_heading_needs_confirmation",
                accept_reasons + ["nested_numeric_heading"],
                reject_reasons,
                t_bonus,
                t_type,
                res_sem,
                cont_bonus,
                legal_neg,
            )
        if lvl == 3:
            sc = _clamp_score(
                0.68
                + (0.04 if is_strong else 0)
                - (0.06 if is_rec_toc else 0)
                + t_bonus
                + cont_bonus
            )
            st = CandidateStatus.ACCEPTED if sc >= 0.82 else CandidateStatus.AMBIGUOUS
            return HeadingScoreResult(
                st,
                sc,
                "accepted"
                if st == CandidateStatus.ACCEPTED
                else "deep_numeric_heading_needs_confirmation",
                accept_reasons + ["deep_numeric_heading_l3"],
                reject_reasons,
                t_bonus,
                t_type,
                res_sem,
                cont_bonus,
                legal_neg,
            )
        sc = min(1.0, 0.58 + t_bonus)
        return HeadingScoreResult(
            CandidateStatus.AMBIGUOUS,
            sc,
            "very_deep_numeric_heading",
            accept_reasons + ["very_deep_numeric_heading"],
            reject_reasons,
            t_bonus,
            t_type,
            res_sem,
            cont_bonus,
            legal_neg,
        )

    # Fallback для Roman/Alpha
    base = 0.76 if classify_uid_kind(u) == "roman" else 0.60
    sc = min(1.0, base + t_bonus)
    st = CandidateStatus.ACCEPTED if sc >= 0.82 else CandidateStatus.AMBIGUOUS
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
    )
