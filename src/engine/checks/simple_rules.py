# src/engine/checks/simple_rules.py (LEGACY: rules-only executor, не используется в текущем пайплайне)

"""
Простой executor одного check из PlaybookVersion.compiled_checks.

Назначение:
- взять конфиг одного чека (из compiled_checks["checks"]);
- по elements (layout) и clause_tree документа решить:
  сработал чек или нет (пока по ключевым словам);
- вернуть dict в формате, совместимом с CheckExecutor / CheckRunner (legacy rules-only executor).

Важно:
- это упрощённый rules-only executor (без LLM), чтобы быстро перейти
  от хардкода CoC к плейбуку;
- позже сюда можно добавить:
  * поддержку LLM;
  * более сложные правила;
  * работу с clause_tree/structured_data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def execute_check_for_document(
    check_cfg: Dict[str, Any],
    *,
    document_id: str,
    elements: List[dict],
    clause_tree: Optional[dict] = None,
    doc_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Выполняет один check по конфигу и возвращает dict для CheckResult.

    Вход:
      - check_cfg: один элемент из compiled_checks["checks"];
      - document_id: строковый UUID документа;
      - elements: список элементов layout (как в text_layout_raw["elements"]);
      - clause_tree: дерево пунктов договора (пока можем не использовать);
      - doc_type: тип документа (для фильтрации по doc_types в check_cfg).

    Выход:
      dict с ключами:
        - check_id, check_name, result, severity, value_text,
          evidence_snippet, evidence_page, confidence,
          detector_used, quality_flags, structured_data,
          conditional_check_triggered, trigger_name.

    Сейчас логика очень простая:
      1) если в check_cfg есть doc_types и текущий doc_type туда не входит —
         возвращаем PASS (чек "не применим");
      2) ищем любые keywords из check_cfg["rules"]["keywords"] в elements[*]["text"];
      3) если нашли хотя бы одно совпадение — result = "fail", иначе "pass".
    """
    check_id = check_cfg.get("id") or "unknown_check"
    check_name = check_cfg.get("name") or check_id
    severity = check_cfg.get("severity") or "medium"
    detector_type = check_cfg.get("detector_type") or "rules"

    # 1. Фильтрация по doc_types (если указаны в конфиге)
    cfg_doc_types = check_cfg.get("doc_types") or []
    if cfg_doc_types and doc_type and doc_type not in cfg_doc_types:
        # Чек не применим к этому типу документа — считаем, что он "pass"
        return {
            "check_id": check_id,
            "check_name": check_name,
            "result": "pass",
            "severity": severity,
            "value_text": f"Check not applicable for doc_type={doc_type}",
            "evidence_snippet": None,
            "evidence_page": None,
            "confidence": 1.0,
            "detector_used": detector_type,
            "quality_flags": {"source": check_cfg.get("source", "global_playbook")},
            "structured_data": None,
            "conditional_check_triggered": False,
            "trigger_name": None,
        }

    # 2. Rules-only: ищем keywords в тексте элементов
    rules_cfg = check_cfg.get("rules") or {}
    keywords = rules_cfg.get("keywords") or []

    matched_element = None
    matched_keyword = None

    for el in elements:
        text_piece = (el.get("text") or "").lower()
        if not text_piece:
            continue
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in text_piece:
                matched_element = el
                matched_keyword = kw
                break
        if matched_element:
            break

    quality_flags: Dict[str, Any] = {"source": check_cfg.get("source", "global_playbook")}

    if matched_element:
        # Чек "сработал": нашли ключевое слово
        snippet = (matched_element.get("text") or "")[:300]
        page = matched_element.get("page")
        value_text = f"Matched keyword: '{matched_keyword}'"

        return {
            "check_id": check_id,
            "check_name": check_name,
            "result": "fail",
            "severity": severity,
            "value_text": value_text,
            "evidence_snippet": snippet,
            "evidence_page": page,
            "confidence": 0.8,
            "detector_used": detector_type,
            "quality_flags": quality_flags,
            "structured_data": None,
            "conditional_check_triggered": False,
            "trigger_name": None,
        }

    # Если совпадений нет — чек прошёл (pass)
    return {
        "check_id": check_id,
        "check_name": check_name,
        "result": "pass",
        "severity": severity if severity != "critical" else "pass",
        "value_text": "No matches found for check.",
        "evidence_snippet": None,
        "evidence_page": None,
        "confidence": 0.9,
        "detector_used": detector_type,
        "quality_flags": quality_flags,
        "structured_data": None,
        "conditional_check_triggered": False,
        "trigger_name": None,
    }
