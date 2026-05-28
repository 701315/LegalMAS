# src/engine/content/parse_quality.py

"""
parse_quality.py — сбор артефакта качества парсинга документа.

Для непрофессионального программиста:
- После обработки документа система накопила много сигналов о качестве:
  * насколько надёжно был определён TOC;
  * сколько heading candidates прошли как accepted;
  * деградировало ли дерево клауз;
  * сколько units получили known type;
  * сколько cross-references удалось резолвить.
- parse_quality.py собирает все эти сигналы в один артефакт.
- Downstream (detectors, DD grid) читает этот артефакт чтобы отделить:
  * "норма отсутствует в договоре" (legal unclear)
  * "норма есть, но мы не смогли её найти из-за плохого парсинга" (parse unclear)

Архитектурная роль:
- Вызывается после chunking (когда все артефакты уже в MinIO).
- Читает clause_tree, legal_units_snapshot и chunks_manifest.
- Возвращает ParseQualityReport который сохраняется в MinIO.
- Не знает про БД напрямую — работает только с загруженными dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Константы качества
# ---------------------------------------------------------------------------

# Минимальная доля units с known type чтобы считать legal_unit quality "ok"
_MIN_KNOWN_TYPE_RATIO = 0.3

# Максимальная доля best_effort units чтобы считать hierarchy quality "ok"
_MAX_BEST_EFFORT_RATIO = 0.4

# Минимальная доля resolved cross-refs для "ok"
_MIN_CROSS_REF_RESOLVE_RATIO = 0.3


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------


@dataclass
class QualitySignal:
    """
    Один сигнал качества.

    status: "ok" / "weak" / "failed"
    score:  числовая оценка [0.0..1.0]
    reason: человекочитаемое объяснение
    details: дополнительные данные
    """

    status: str  # "ok" / "weak" / "failed"
    score: float  # 0.0 .. 1.0
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass
class ParseQualityReport:
    """
    Отчёт о качестве парсинга одного документа/сегмента.

    Для непрофессионального программиста:
    - Каждое поле — это один аспект качества.
    - overall_status — итоговая оценка: "ok", "weak", или "failed".
    - Детектор читает этот отчёт чтобы решить:
      * если overall_status="failed" — не доверяем структуре, пишем "parse unclear"
      * если overall_status="ok" — можно доверять findings.

    Поля:
    - layout_quality:      качество layout (элементы, страницы)
    - toc_quality:         качество TOC (найден/надёжен/false positives)
    - heading_quality:     качество heading candidates
    - hierarchy_quality:   качество дерева клауз
    - legal_unit_quality:  качество legal units (типизация, coverage)
    - cross_ref_quality:   качество cross-reference резолвинга
    - citation_quality:    качество citation anchors
    - overall_status:      итоговый статус
    - overall_score:       числовая итоговая оценка [0.0..1.0]
    - document_id:         ID документа
    - segment_id:          ID сегмента (если применимо)
    """

    document_id: str = ""
    segment_id: str | None = None

    layout_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )
    toc_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )
    heading_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )
    hierarchy_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )
    legal_unit_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )
    cross_ref_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )
    citation_quality: QualitySignal = field(
        default_factory=lambda: QualitySignal(status="ok", score=1.0)
    )

    overall_status: str = "ok"
    overall_score: float = 1.0

    schema_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "overall_status": self.overall_status,
            "overall_score": round(self.overall_score, 3),
            "layout_quality": self.layout_quality.to_dict(),
            "toc_quality": self.toc_quality.to_dict(),
            "heading_quality": self.heading_quality.to_dict(),
            "hierarchy_quality": self.hierarchy_quality.to_dict(),
            "legal_unit_quality": self.legal_unit_quality.to_dict(),
            "cross_ref_quality": self.cross_ref_quality.to_dict(),
            "citation_quality": self.citation_quality.to_dict(),
        }

    @property
    def is_parse_reliable(self) -> bool:
        """
        True если парсинг достаточно надёжен для retrieval и detection.

        Для непрофессионального программиста:
        - "reliable" = система доверяет своей структуре документа;
        - если False — детектор должен помечать findings как "parse unclear"
          а не "legal unclear".
        """
        return self.overall_status in {"ok", "weak"}

    @property
    def is_parse_failed(self) -> bool:
        return self.overall_status == "failed"


# ---------------------------------------------------------------------------
# ParseQualityBuilder
# ---------------------------------------------------------------------------


class ParseQualityBuilder:
    """
    Строит ParseQualityReport из артефактов документа.

    Использование:
        builder = ParseQualityBuilder()
        report = builder.build(
            document_id="...",
            segment_id="...",
            clause_tree=tree_dict,
            legal_units_snapshot=snapshot_dict,
            chunks_manifest=manifest_dict,
        )
        artifact = report.to_dict()
    """

    def build(
        self,
        *,
        document_id: str,
        segment_id: str | None = None,
        clause_tree: dict[str, Any] | None = None,
        legal_units_snapshot: dict[str, Any] | None = None,
        chunks_manifest: dict[str, Any] | None = None,
    ) -> ParseQualityReport:
        """
        Построить ParseQualityReport из доступных артефактов.

        Все параметры кроме document_id опциональны:
        - если артефакт недоступен — соответствующий signal = "weak" или "failed".
        - это позволяет строить отчёт даже при частичных данных.
        """
        report = ParseQualityReport(
            document_id=str(document_id),
            segment_id=segment_id,
        )

        # Каждый signal строится независимо.
        # Ошибка в одном не ломает остальные.
        try:
            report.layout_quality = self._assess_layout_quality(clause_tree)
        except Exception as e:
            report.layout_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"layout_quality_assessment_failed: {e}",
            )

        try:
            report.toc_quality = self._assess_toc_quality(clause_tree)
        except Exception as e:
            report.toc_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"toc_quality_assessment_failed: {e}",
            )

        try:
            report.heading_quality = self._assess_heading_quality(clause_tree)
        except Exception as e:
            report.heading_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"heading_quality_assessment_failed: {e}",
            )

        try:
            report.hierarchy_quality = self._assess_hierarchy_quality(clause_tree)
        except Exception as e:
            report.hierarchy_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"hierarchy_quality_assessment_failed: {e}",
            )

        try:
            report.legal_unit_quality = self._assess_legal_unit_quality(legal_units_snapshot)
        except Exception as e:
            report.legal_unit_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"legal_unit_quality_assessment_failed: {e}",
            )

        try:
            report.cross_ref_quality = self._assess_cross_ref_quality(legal_units_snapshot)
        except Exception as e:
            report.cross_ref_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"cross_ref_quality_assessment_failed: {e}",
            )

        try:
            report.citation_quality = self._assess_citation_quality(
                legal_units_snapshot, chunks_manifest
            )
        except Exception as e:
            report.citation_quality = QualitySignal(
                status="weak",
                score=0.5,
                reason=f"citation_quality_assessment_failed: {e}",
            )

        # Вычисляем overall
        report.overall_score, report.overall_status = self._compute_overall(report)

        logger.info(
            "ParseQualityBuilder: report built",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "overall_status": report.overall_status,
                "overall_score": report.overall_score,
                "layout_status": report.layout_quality.status,
                "toc_status": report.toc_quality.status,
                "heading_status": report.heading_quality.status,
                "hierarchy_status": report.hierarchy_quality.status,
                "legal_unit_status": report.legal_unit_quality.status,
                "cross_ref_status": report.cross_ref_quality.status,
                "citation_status": report.citation_quality.status,
            },
        )

        return report

    # ── Оценка отдельных аспектов ─────────────────────────────────────────────

    def _assess_layout_quality(
        self,
        clause_tree: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество layout по данным из clause_tree.

        Для непрофессионального программиста:
        - Если clause_tree не пришёл — layout недоступен.
        - Если дерево degraded — layout вероятно имел проблемы.
        - Если есть root nodes — layout достаточно хорош.
        """
        if clause_tree is None:
            return QualitySignal(
                status="failed",
                score=0.0,
                reason="clause_tree_not_available",
            )

        degraded = bool(clause_tree.get("degraded", False))
        root_nodes = clause_tree.get("root") or []
        root_count = len(root_nodes) if isinstance(root_nodes, list) else 0
        structure_confidence = str(clause_tree.get("structure_confidence") or "MEDIUM").upper()

        if root_count == 0:
            return QualitySignal(
                status="failed",
                score=0.1,
                reason="no_root_nodes_in_clause_tree",
                details={"degraded": degraded},
            )

        if degraded:
            return QualitySignal(
                status="weak",
                score=0.5,
                reason="clause_tree_degraded",
                details={
                    "root_count": root_count,
                    "structure_confidence": structure_confidence,
                },
            )

        score_map = {"HIGH": 1.0, "MEDIUM": 0.75, "LOW": 0.4, "FAILED": 0.1}
        score = score_map.get(structure_confidence, 0.75)

        return QualitySignal(
            status="ok" if score >= 0.6 else "weak",
            score=score,
            details={
                "root_count": root_count,
                "structure_confidence": structure_confidence,
            },
        )

    def _assess_toc_quality(
        self,
        clause_tree: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество TOC по diagnostics в clause_tree.
        """
        if clause_tree is None:
            return QualitySignal(status="weak", score=0.5, reason="no_clause_tree")

        diagnostics = clause_tree.get("structure_diagnostics") or {}
        toc_diag = diagnostics.get("toc_diagnostics") or {}

        if not toc_diag:
            # TOC diagnostics не записаны — не знаем ничего, считаем нейтральным
            return QualitySignal(
                status="ok",
                score=0.75,
                reason="toc_diagnostics_not_available",
            )

        toc_detected = bool(toc_diag.get("detected", False))
        confidence_band = str(toc_diag.get("toc_confidence_band") or "none").lower()
        false_positive_count = int(toc_diag.get("toc_false_positive_count") or 0)
        body_recovered = int(toc_diag.get("body_recovered_from_toc") or 0)

        if not toc_detected:
            return QualitySignal(
                status="ok",
                score=0.9,
                reason="toc_not_detected_document_starts_with_body",
            )

        band_scores = {"high": 1.0, "partial": 0.7, "low": 0.4, "none": 0.5}
        score = band_scores.get(confidence_band, 0.6)

        if false_positive_count > 5:
            score = max(0.2, score - 0.2)

        if body_recovered > 0:
            score = max(0.3, score - 0.1)

        status = "ok" if score >= 0.7 else ("weak" if score >= 0.4 else "failed")

        return QualitySignal(
            status=status,
            score=score,
            details={
                "toc_detected": toc_detected,
                "confidence_band": confidence_band,
                "false_positive_count": false_positive_count,
                "body_recovered": body_recovered,
            },
        )

    def _assess_heading_quality(
        self,
        clause_tree: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество heading candidates по diagnostics clause_tree.
        """
        if clause_tree is None:
            return QualitySignal(status="weak", score=0.5, reason="no_clause_tree")

        diagnostics = clause_tree.get("structure_diagnostics") or {}

        # Смотрим на quality_gates из hierarchy builder
        quality_gates = diagnostics.get("quality_gates") or {}
        hierarchy_quality = str(quality_gates.get("hierarchy_quality") or "good").lower()
        structure_confidence = str(quality_gates.get("structure_confidence") or "MEDIUM").upper()

        if hierarchy_quality == "failed":
            return QualitySignal(
                status="failed",
                score=0.1,
                reason="hierarchy_quality_failed",
                details={"structure_confidence": structure_confidence},
            )

        if hierarchy_quality == "partial":
            return QualitySignal(
                status="weak",
                score=0.5,
                reason="hierarchy_quality_partial",
                details={"structure_confidence": structure_confidence},
            )

        conf_score = {"HIGH": 1.0, "MEDIUM": 0.75, "LOW": 0.4}.get(structure_confidence, 0.7)
        return QualitySignal(
            status="ok" if conf_score >= 0.6 else "weak",
            score=conf_score,
            details={"structure_confidence": structure_confidence},
        )

    def _assess_hierarchy_quality(
        self,
        clause_tree: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество дерева клауз.
        """
        if clause_tree is None:
            return QualitySignal(status="failed", score=0.0, reason="no_clause_tree")

        root_nodes = clause_tree.get("root") or []
        root_count = len(root_nodes) if isinstance(root_nodes, list) else 0
        degraded = bool(clause_tree.get("degraded", False))

        diagnostics = clause_tree.get("structure_diagnostics") or {}
        quality_gates = diagnostics.get("quality_gates") or {}

        section_chunking_allowed = bool(quality_gates.get("section_chunking_allowed", True))
        recoverable_hierarchy_used = bool(quality_gates.get("recoverable_hierarchy_used", False))
        total_fallback_blocked = int(quality_gates.get("total_fallback_blocked") or 0)

        if root_count == 0 or degraded:
            return QualitySignal(
                status="failed",
                score=0.1,
                reason="hierarchy_degraded_or_empty",
                details={
                    "root_count": root_count,
                    "degraded": degraded,
                },
            )

        if not section_chunking_allowed:
            return QualitySignal(
                status="weak",
                score=0.4,
                reason="section_chunking_not_allowed",
                details={
                    "recoverable_hierarchy_used": recoverable_hierarchy_used,
                    "total_fallback_blocked": total_fallback_blocked,
                },
            )

        if recoverable_hierarchy_used:
            return QualitySignal(
                status="weak",
                score=0.65,
                reason="recoverable_hierarchy_used",
                details={"root_count": root_count},
            )

        return QualitySignal(
            status="ok",
            score=0.9,
            details={"root_count": root_count},
        )

    def _assess_legal_unit_quality(
        self,
        legal_units_snapshot: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество legal units из snapshot.
        """
        if legal_units_snapshot is None:
            return QualitySignal(
                status="weak",
                score=0.5,
                reason="legal_units_snapshot_not_available",
            )

        stats = legal_units_snapshot.get("stats") or {}
        total_units = int(stats.get("total_units") or 0)
        units_with_known_type = int(stats.get("units_with_known_type") or 0)
        units_heading_only = int(stats.get("units_heading_only") or 0)
        units_best_effort = int(stats.get("units_best_effort") or 0)
        warnings_count = len(stats.get("build_warnings") or [])

        if total_units == 0:
            return QualitySignal(
                status="failed",
                score=0.0,
                reason="no_legal_units_built",
            )

        known_type_ratio = units_with_known_type / total_units
        best_effort_ratio = units_best_effort / total_units
        heading_only_ratio = units_heading_only / total_units

        score = 1.0
        reasons: list[str] = []

        if known_type_ratio < _MIN_KNOWN_TYPE_RATIO:
            score -= 0.3
            reasons.append(f"low_known_type_ratio:{known_type_ratio:.2f}")

        if best_effort_ratio > _MAX_BEST_EFFORT_RATIO:
            score -= 0.2
            reasons.append(f"high_best_effort_ratio:{best_effort_ratio:.2f}")

        if heading_only_ratio > 0.5:
            score -= 0.2
            reasons.append(f"high_heading_only_ratio:{heading_only_ratio:.2f}")

        if warnings_count > 5:
            score -= 0.1
            reasons.append(f"many_build_warnings:{warnings_count}")

        score = round(max(0.0, min(1.0, score)), 3)
        status = "ok" if score >= 0.7 else ("weak" if score >= 0.4 else "failed")

        return QualitySignal(
            status=status,
            score=score,
            reason="; ".join(reasons) if reasons else None,
            details={
                "total_units": total_units,
                "units_with_known_type": units_with_known_type,
                "known_type_ratio": round(known_type_ratio, 3),
                "best_effort_ratio": round(best_effort_ratio, 3),
                "heading_only_ratio": round(heading_only_ratio, 3),
            },
        )

    def _assess_cross_ref_quality(
        self,
        legal_units_snapshot: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество cross-reference резолвинга.
        """
        if legal_units_snapshot is None:
            return QualitySignal(
                status="weak",
                score=0.5,
                reason="legal_units_snapshot_not_available",
            )

        # Считаем статистику cross-refs из units
        units = legal_units_snapshot.get("units") or []
        total_refs = 0
        resolved_refs = 0

        for unit in units:
            if not isinstance(unit, dict):
                continue
            cross_refs = unit.get("cross_refs") or []
            for ref in cross_refs:
                if isinstance(ref, dict):
                    total_refs += 1
                    if bool(ref.get("resolved", False)):
                        resolved_refs += 1

        if total_refs == 0:
            # Нет cross-refs — это нормально для простых документов
            return QualitySignal(
                status="ok",
                score=0.9,
                reason="no_cross_refs_found",
                details={"total_refs": 0},
            )

        resolve_ratio = resolved_refs / total_refs
        score = round(resolve_ratio, 3)

        if resolve_ratio >= _MIN_CROSS_REF_RESOLVE_RATIO:
            status = "ok" if resolve_ratio >= 0.5 else "weak"
        else:
            status = "weak"

        return QualitySignal(
            status=status,
            score=score,
            details={
                "total_refs": total_refs,
                "resolved_refs": resolved_refs,
                "resolve_ratio": round(resolve_ratio, 3),
            },
        )

    def _assess_citation_quality(
        self,
        legal_units_snapshot: dict[str, Any] | None,
        chunks_manifest: dict[str, Any] | None,
    ) -> QualitySignal:
        """
        Оценить качество citation anchors.

        Эвристика: смотрим на coverage — сколько units имеют own_text.
        Если у большинства units есть own_text — citation будет работать хорошо.
        """
        if legal_units_snapshot is None:
            return QualitySignal(
                status="weak",
                score=0.5,
                reason="legal_units_snapshot_not_available",
            )

        units = legal_units_snapshot.get("units") or []
        if not units:
            return QualitySignal(
                status="weak",
                score=0.3,
                reason="no_units_for_citation_assessment",
            )

        units_with_own_text = sum(
            1 for u in units if isinstance(u, dict) and bool((u.get("own_text") or "").strip())
        )
        units_with_text_ratio = units_with_own_text / len(units)

        # Также смотрим на chunks_manifest coverage
        coverage_bonus = 0.0
        if chunks_manifest is not None:
            totals = chunks_manifest.get("totals") or {}
            clause_count = int(totals.get("clause_count") or 0)
            total_leaf_nodes = int(totals.get("total_leaf_nodes") or 0)

            if total_leaf_nodes > 0 and clause_count > 0:
                chunk_coverage = min(1.0, clause_count / total_leaf_nodes)
                coverage_bonus = chunk_coverage * 0.1

        score = round(min(1.0, units_with_text_ratio * 0.9 + coverage_bonus), 3)
        status = "ok" if score >= 0.7 else ("weak" if score >= 0.4 else "failed")

        return QualitySignal(
            status=status,
            score=score,
            details={
                "total_units": len(units),
                "units_with_own_text": units_with_own_text,
                "units_with_text_ratio": round(units_with_text_ratio, 3),
            },
        )

    def _compute_overall(
        self,
        report: ParseQualityReport,
    ) -> tuple[float, str]:
        """
        Вычислить итоговый score и status из отдельных signals.

        Веса компонент:
        - hierarchy_quality: 30% — самое важное, без дерева нет структуры
        - legal_unit_quality: 25% — типизация units
        - heading_quality:    20% — качество heading detection
        - layout_quality:     15% — качество layout
        - toc_quality:         5% — TOC менее критичен
        - cross_ref_quality:   3% — полезен но не критичен
        - citation_quality:    2% — дополнительный сигнал

        Важно: если любой компонент "failed" — overall не может быть "ok".
        Если два и более компонента "failed" — overall = "failed".
        """
        signals = [
            (report.hierarchy_quality, 0.30),
            (report.legal_unit_quality, 0.25),
            (report.heading_quality, 0.20),
            (report.layout_quality, 0.15),
            (report.toc_quality, 0.05),
            (report.cross_ref_quality, 0.03),
            (report.citation_quality, 0.02),
        ]

        weighted_score = sum(signal.score * weight for signal, weight in signals)
        weighted_score = round(min(1.0, max(0.0, weighted_score)), 3)

        # Подсчёт failed компонент
        failed_count = sum(1 for signal, _ in signals if signal.status == "failed")
        weak_count = sum(1 for signal, _ in signals if signal.status == "weak")

        if failed_count >= 2:
            overall_status = "failed"
        elif failed_count == 1 or weak_count >= 3:
            overall_status = "weak"
        elif weak_count >= 1:
            overall_status = "weak" if weighted_score < 0.75 else "ok"
        else:
            overall_status = "ok"

        return weighted_score, overall_status
