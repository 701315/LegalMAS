# src/services/run_summary_validator.py

"""
Deterministic validation + auto-correction claims-плана (Pass A).

LLM не проверяет саму себя. Фактическая корректность контролируется
детерминированными правилами поверх evidence package:

1. claims — валидный JSON нужной структуры;
2. каждый check_id в claims существует в evidence material_checks
   (несуществующие — отбрасываются, claim сохраняется только если остались check_ids);
3. severity в claims НЕ эскалируется относительно evidence
   (эскалация автокорректируется до evidence-значения, факт логируется);
4. все critical checks из evidence упомянуты в claims (полнота);
5. при неполном покрытии limitations обязательны (раскрытие ограничений);
6. нет юридических рекомендаций вне данных (эвристика по стоп-словам).

Политика: корректировать и принимать, а не отклонять. Пользователь
видит резюме даже если LLM сделала мелкие нарушения. Жёсткий отказ —
только если текст принципиально сломан (нет overall / нет risk_claims).
"""

from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2}

_PROHIBITED_PHRASES = (
    "рекомендуется расторгнуть",
    "необходимо отказаться от сделки",
    "сделка безопасна",
    "рисков нет",
)


def validate_claims(
    claims: Any,
    evidence: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Валидировать и автокорректировать claims-план.

    Возвращает (passed, issues_log). passed=False только если
    структура принципиально сломана.

    Автокоррекции:
    - unknown check_id — удаляется из list;
    - severity escalated — принудительно снижается до evidence-значения;
    - пустой claim после удаления check_ids — удаляется из risk_claims.
    """
    issues: list[str] = []

    if not isinstance(claims, dict):
        return False, ["claims is not a JSON object"]

    # ── Структура ─────────────────────────────────────────────────────
    overall = claims.get("overall_assessment")
    if not isinstance(overall, str) or not overall.strip():
        return False, ["overall_assessment missing or empty"]

    risk_claims = claims.get("risk_claims")
    if not isinstance(risk_claims, list):
        return False, ["risk_claims missing or not a list"]

    # ── Evidence reference map ────────────────────────────────────────
    material = {
        c["check_id"]: c for c in evidence.get("material_checks", [])
    }
    critical_ids = {
        cid for cid, c in material.items() if c["severity"] == "critical"
    }
    seen_ids: set[str] = set()

    # ── Auto-correction loop ──────────────────────────────────────────
    corrected: list[dict[str, Any]] = []

    for idx, claim in enumerate(risk_claims):
        if not isinstance(claim, dict):
            issues.append(f"risk_claims[{idx}] skipped: not an object")
            continue

        text = claim.get("text")
        if not isinstance(text, str) or not text.strip():
            issues.append(f"risk_claims[{idx}] skipped: empty text")
            continue

        ids = claim.get("check_ids")
        if not isinstance(ids, list) or not ids:
            issues.append(f"risk_claims[{idx}] skipped: no check_ids")
            continue

        # Фильтруем неизвестные check_ids
        valid_ids: list[str] = []
        for cid in ids:
            if cid not in material:
                issues.append(
                    f"risk_claims[{idx}]: dropped unknown check_id '{cid}'"
                )
                continue
            valid_ids.append(cid)

        if not valid_ids:
            issues.append(
                f"risk_claims[{idx}] skipped: all check_ids unknown"
            )
            continue

        # Автокоррекция severity: берём ХУДШУЮ среди упомянутых evidence,
        # но не позволяем LLM эскалировать.
        worst_evidence_severity = min(
            valid_ids,
            key=lambda cid: _SEVERITY_ORDER.get(material[cid]["severity"], 99),
        )
        worst_sev = material[worst_evidence_severity]["severity"]

        claim_sev = (claim.get("severity") or "").lower()
        if claim_sev != worst_sev and _SEVERITY_ORDER.get(
            claim_sev, 99
        ) < _SEVERITY_ORDER.get(worst_sev, 99):
            issues.append(
                f"risk_claims[{idx}]: severity auto-corrected "
                f"'{claim_sev}' → '{worst_sev}' for {valid_ids}"
            )
            claim_sev = worst_sev

        # Запрещённые юридические выводы
        lowered = text.lower()
        for phrase in _PROHIBITED_PHRASES:
            if phrase in lowered:
                issues.append(
                    f"risk_claims[{idx}]: prohibited phrase '{phrase}' — kept claim "
                    f"but flagged"
                )

        # Записываем скорректированный claim
        corrected_claim = dict(claim)
        corrected_claim["check_ids"] = valid_ids
        corrected_claim["severity"] = claim_sev if claim_sev in _SEVERITY_ORDER else worst_sev
        corrected.append(corrected_claim)
        seen_ids.update(valid_ids)

    claims["risk_claims"] = corrected

    # ── Полнота по critical ───────────────────────────────────────────
    missing_critical = critical_ids - seen_ids
    if missing_critical:
        issues.append(
            f"critical checks not covered: {sorted(missing_critical)} — "
            f"claim generation accepted with gap"
        )

    # ── Раскрытие ограничений покрытия ────────────────────────────────
    coverage = evidence.get("coverage", {})
    incomplete = (
        coverage.get("failed", 0) > 0
        or coverage.get("quarantine", 0) > 0
        or coverage.get("pending_review", 0) > 0
    )
    limitations = claims.get("limitations")
    if incomplete and (not isinstance(limitations, list) or not limitations):
        # Автоматически вставляем limitation из evidence open_items
        auto_limits = evidence.get("open_items", [])
        if auto_limits:
            claims["limitations"] = auto_limits
            issues.append(
                "limitations auto-populated from evidence open_items"
            )
        else:
            issues.append(
                "limitations empty despite incomplete coverage — accepted"
            )

    if issues:
        logger.warning(
            "Run summary claims validated with issues",
            issue_count=len(issues),
            issues=issues[:20],
        )

    return True, issues


    