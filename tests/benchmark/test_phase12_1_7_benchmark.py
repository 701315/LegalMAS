"""
Phase 12.1.7 — Offline Benchmark для semantic enrichment quality.

Структура:
1. BenchmarkLoader         — загружает clauses_gold.json
2. BenchmarkEvaluator      — вычисляет метрики против gold labels
3. Unit тесты (без LLM)    — проверяют инфраструктуру benchmark
4. Mock-LLM тесты          — проверяют полный pipeline с идеальным LLM
5. llm_integration тесты   — реальный LLM (только с -m llm_integration)
6. Standalone runner       — вызывается напрямую python ... для отчёта

Метрики:
- unit_type_accuracy       — точность классификации типа
- clause_function_accuracy — точность классификации функции
- topic_recall             — доля gold topics найденных LLM
- topic_precision          — доля LLM topics присутствующих в gold
- delta_vs_baseline        — улучшение vs rule-based baseline

Запуск unit части:
    pytest tests/benchmark/test_phase12_1_7_benchmark.py -v

Запуск с живым LLM:
    pytest tests/benchmark/test_phase12_1_7_benchmark.py -m llm_integration -v

Standalone отчёт:
    python tests/benchmark/test_phase12_1_7_benchmark.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BENCHMARK_DIR = Path(__file__).parent
FIXTURES_DIR = BENCHMARK_DIR / "fixtures"
GOLD_FILE = FIXTURES_DIR / "clauses_gold.json"

# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class GoldClause:
    """Один элемент curated evaluation set."""

    id: str
    language: str
    category: str
    title: str
    own_text: str
    gold_unit_type: str
    gold_clause_function: str
    gold_topic_tags: list[str]
    baseline_unit_type: str
    notes: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoldClause":
        return cls(
            id=str(data["id"]),
            language=str(data["language"]),
            category=str(data["category"]),
            title=str(data["title"]),
            own_text=str(data["own_text"]),
            gold_unit_type=str(data["gold_unit_type"]),
            gold_clause_function=str(data["gold_clause_function"]),
            gold_topic_tags=list(data["gold_topic_tags"]),
            baseline_unit_type=str(data["baseline_unit_type"]),
            notes=str(data.get("notes", "")),
        )


@dataclass
class ClauseEvalResult:
    """Результат оценки одного clause."""

    clause_id: str
    language: str
    category: str

    # Gold
    gold_unit_type: str
    gold_clause_function: str
    gold_topic_tags: list[str]

    # Baseline (rule-based)
    baseline_unit_type: str

    # LLM enrichment result
    enrichment_status: str
    effective_unit_type: str
    effective_clause_function: str
    effective_topic_tags: list[str]

    # Метрики
    unit_type_correct: bool
    clause_function_correct: bool
    topic_recall: float      # gold topics найденные LLM / всего gold topics
    topic_precision: float   # LLM topics совпавшие с gold / всего LLM topics
    baseline_type_correct: bool  # был ли baseline уже правильным

    @property
    def topic_f1(self) -> float:
        if self.topic_recall + self.topic_precision == 0:
            return 0.0
        return round(
            2 * self.topic_recall * self.topic_precision
            / (self.topic_recall + self.topic_precision),
            3,
        )


@dataclass
class BenchmarkReport:
    """Агрегированный отчёт по всему evaluation set."""

    total_clauses: int
    evaluated_clauses: int  # статус APPLIED или обработанные
    skipped_clauses: int

    # Метрики (по evaluated)
    unit_type_accuracy: float
    clause_function_accuracy: float
    avg_topic_recall: float
    avg_topic_precision: float
    avg_topic_f1: float

    # Delta vs baseline
    baseline_unit_type_accuracy: float
    delta_unit_type: float  # enrichment - baseline

    # По категориям
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_language: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Детальные результаты
    results: list[ClauseEvalResult] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            "=" * 60,
            "Phase 12.1.7 Benchmark Report",
            "=" * 60,
            f"Total clauses:          {self.total_clauses}",
            f"Evaluated:              {self.evaluated_clauses}",
            f"Skipped:                {self.skipped_clauses}",
            "-" * 60,
            f"unit_type_accuracy:     {self.unit_type_accuracy:.1%}",
            f"clause_function_acc:    {self.clause_function_accuracy:.1%}",
            f"avg_topic_recall:       {self.avg_topic_recall:.1%}",
            f"avg_topic_precision:    {self.avg_topic_precision:.1%}",
            f"avg_topic_f1:           {self.avg_topic_f1:.1%}",
            "-" * 60,
            f"baseline_type_acc:      {self.baseline_unit_type_accuracy:.1%}",
            f"delta_unit_type:        {self.delta_unit_type:+.1%}",
            "=" * 60,
        ]
        if self.by_category:
            lines.append("By category:")
            for cat, metrics in sorted(self.by_category.items()):
                lines.append(
                    f"  {cat:<20} type={metrics.get('unit_type_accuracy', 0):.0%}"
                    f"  recall={metrics.get('avg_topic_recall', 0):.0%}"
                    f"  n={metrics.get('count', 0)}"
                )
        if self.by_language:
            lines.append("By language:")
            for lang, metrics in sorted(self.by_language.items()):
                lines.append(
                    f"  {lang:<10} type={metrics.get('unit_type_accuracy', 0):.0%}"
                    f"  recall={metrics.get('avg_topic_recall', 0):.0%}"
                    f"  n={metrics.get('count', 0)}"
                )
        return lines


# ---------------------------------------------------------------------------
# BenchmarkLoader
# ---------------------------------------------------------------------------


class BenchmarkLoader:
    """Загружает и валидирует curated gold evaluation set."""

    def __init__(self, gold_file: Path = GOLD_FILE) -> None:
        self.gold_file = gold_file

    def load(self) -> list[GoldClause]:
        if not self.gold_file.exists():
            raise FileNotFoundError(
                f"Gold evaluation set not found: {self.gold_file}"
            )
        raw = json.loads(self.gold_file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Gold file must contain a JSON array")
        clauses = [GoldClause.from_dict(item) for item in raw]
        self._validate(clauses)
        return clauses

    def _validate(self, clauses: list[GoldClause]) -> None:
        """Проверяет консистентность gold labels."""
        from services.structure.legal_unit_models import ClauseFunction, LegalUnitType
        from services.structure.topic_tagger import KNOWN_TOPICS

        ids_seen: set[str] = set()
        errors: list[str] = []

        for clause in clauses:
            # Уникальность ID
            if clause.id in ids_seen:
                errors.append(f"Duplicate id: {clause.id}")
            ids_seen.add(clause.id)

            # Валидность unit_type
            try:
                LegalUnitType(clause.gold_unit_type)
            except ValueError:
                errors.append(
                    f"{clause.id}: invalid gold_unit_type={clause.gold_unit_type!r}"
                )

            try:
                LegalUnitType(clause.baseline_unit_type)
            except ValueError:
                errors.append(
                    f"{clause.id}: invalid baseline_unit_type={clause.baseline_unit_type!r}"
                )

            # Валидность clause_function
            try:
                ClauseFunction(clause.gold_clause_function)
            except ValueError:
                errors.append(
                    f"{clause.id}: invalid gold_clause_function="
                    f"{clause.gold_clause_function!r}"
                )

            # Все topics из KNOWN_TOPICS
            for topic in clause.gold_topic_tags:
                if topic not in KNOWN_TOPICS:
                    errors.append(
                        f"{clause.id}: topic {topic!r} not in KNOWN_TOPICS"
                    )

            # Текст достаточный для enrichment
            if len(clause.own_text) < 40:
                errors.append(
                    f"{clause.id}: own_text too short ({len(clause.own_text)} chars)"
                )

        if errors:
            raise ValueError(
                f"Gold evaluation set has {len(errors)} validation error(s):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


# ---------------------------------------------------------------------------
# BenchmarkEvaluator
# ---------------------------------------------------------------------------


class BenchmarkEvaluator:
    """
    Запускает enrichment pipeline на gold clauses и вычисляет метрики.
    """

    def __init__(self) -> None:
        from services.structure.semantic_enrichment._policy import (
            SemanticEnrichmentPolicy,
        )
        self.policy = SemanticEnrichmentPolicy(
            min_confidence_fill_missing=0.72,
            min_confidence_add_topics=0.72,
            min_confidence_override_existing=0.92,
            allow_override_existing_type=False,
            allow_override_existing_clause_function=False,
            allow_add_topics_to_existing=True,
            max_topics_from_llm=8,
            min_text_chars=40,
        )

    def _make_legal_unit(self, clause: GoldClause) -> Any:
        """Строит LegalUnit из GoldClause."""
        from services.structure.legal_unit_models import (
            CitabilityMetrics,
            ClauseFunction,
            LegalUnit,
            LegalUnitType,
        )

        try:
            unit_type = LegalUnitType(clause.baseline_unit_type)
        except ValueError:
            unit_type = LegalUnitType.UNKNOWN

        return LegalUnit(
            unit_id=clause.id,
            raw_uid=f"raw_{clause.id}",
            scope="main",
            title=clause.title,
            level=2,
            unit_type=unit_type,
            clause_function=ClauseFunction.UNKNOWN,
            segment_id="benchmark_seg",
            segment_type="main_contract",
            page_start=1,
            page_end=1,
            own_text=clause.own_text,
            subtree_text=None,
            topic_tags=[],
            citability=CitabilityMetrics(
                citability_score=0.85,
                citability_band="high",
                has_own_text=True,
                has_subtree_text=False,
                is_heading_only=False,
            ),
        )

    def _compute_topic_metrics(
        self,
        effective_topics: list[str],
        gold_topics: list[str],
    ) -> tuple[float, float]:
        """Возвращает (recall, precision)."""
        gold_set = set(gold_topics)
        eff_set = set(effective_topics)

        if not gold_set:
            recall = 1.0
        else:
            recall = len(gold_set & eff_set) / len(gold_set)

        if not eff_set:
            precision = 1.0 if not gold_set else 0.0
        else:
            precision = len(gold_set & eff_set) / len(eff_set)

        return round(recall, 3), round(precision, 3)

    def evaluate_clause(
        self,
        clause: GoldClause,
        enrichment: Any,
    ) -> ClauseEvalResult:
        """Оценивает один clause на основе enrichment результата."""
        effective_unit_type = enrichment.effective_unit_type.value
        effective_clause_function = enrichment.effective_clause_function.value
        effective_topic_tags = list(enrichment.effective_topic_tags)

        unit_type_correct = effective_unit_type == clause.gold_unit_type
        clause_function_correct = effective_clause_function == clause.gold_clause_function
        baseline_type_correct = clause.baseline_unit_type == clause.gold_unit_type

        topic_recall, topic_precision = self._compute_topic_metrics(
            effective_topic_tags, clause.gold_topic_tags
        )

        return ClauseEvalResult(
            clause_id=clause.id,
            language=clause.language,
            category=clause.category,
            gold_unit_type=clause.gold_unit_type,
            gold_clause_function=clause.gold_clause_function,
            gold_topic_tags=clause.gold_topic_tags,
            baseline_unit_type=clause.baseline_unit_type,
            enrichment_status=enrichment.status.value,
            effective_unit_type=effective_unit_type,
            effective_clause_function=effective_clause_function,
            effective_topic_tags=effective_topic_tags,
            unit_type_correct=unit_type_correct,
            clause_function_correct=clause_function_correct,
            topic_recall=topic_recall,
            topic_precision=topic_precision,
            baseline_type_correct=baseline_type_correct,
        )

    def run(self, clauses: list[GoldClause]) -> BenchmarkReport:
        """
        Запускает полный benchmark.

        Вызывает enrich_single_unit() для каждого clause
        и агрегирует метрики.
        """
        from services.structure.semantic_enrichment._enricher import (
            enrich_single_unit,
        )

        results: list[ClauseEvalResult] = []
        skipped = 0

        for clause in clauses:
            unit = self._make_legal_unit(clause)
            try:
                enrichment = enrich_single_unit(
                    unit=unit,
                    previous_unit=None,
                    next_unit=None,
                    all_units=None,
                    policy=self.policy,
                    document_id="benchmark",
                )
            except Exception as exc:
                print(
                    f"  WARNING: enrich_single_unit failed for {clause.id}: {exc}",
                    file=sys.stderr,
                )
                skipped += 1
                continue

            result = self.evaluate_clause(clause, enrichment)
            results.append(result)

        return self._aggregate(results, total=len(clauses), skipped=skipped)

    def _aggregate(
        self,
        results: list[ClauseEvalResult],
        total: int,
        skipped: int,
    ) -> BenchmarkReport:
        """Агрегирует ClauseEvalResult в BenchmarkReport."""
        evaluated = len(results)

        if evaluated == 0:
            return BenchmarkReport(
                total_clauses=total,
                evaluated_clauses=0,
                skipped_clauses=skipped,
                unit_type_accuracy=0.0,
                clause_function_accuracy=0.0,
                avg_topic_recall=0.0,
                avg_topic_precision=0.0,
                avg_topic_f1=0.0,
                baseline_unit_type_accuracy=0.0,
                delta_unit_type=0.0,
                results=results,
            )

        unit_type_acc = sum(r.unit_type_correct for r in results) / evaluated
        func_acc = sum(r.clause_function_correct for r in results) / evaluated
        avg_recall = sum(r.topic_recall for r in results) / evaluated
        avg_precision = sum(r.topic_precision for r in results) / evaluated
        avg_f1 = sum(r.topic_f1 for r in results) / evaluated
        baseline_acc = sum(r.baseline_type_correct for r in results) / evaluated
        delta = unit_type_acc - baseline_acc

        # По категориям
        by_category: dict[str, dict[str, Any]] = {}
        for r in results:
            cat = r.category
            if cat not in by_category:
                by_category[cat] = {
                    "count": 0,
                    "unit_type_correct": 0,
                    "topic_recall_sum": 0.0,
                }
            by_category[cat]["count"] += 1
            by_category[cat]["unit_type_correct"] += int(r.unit_type_correct)
            by_category[cat]["topic_recall_sum"] += r.topic_recall

        for cat, data in by_category.items():
            n = data["count"]
            data["unit_type_accuracy"] = data["unit_type_correct"] / n
            data["avg_topic_recall"] = data["topic_recall_sum"] / n

        # По языку
        by_language: dict[str, dict[str, Any]] = {}
        for r in results:
            lang = r.language
            if lang not in by_language:
                by_language[lang] = {
                    "count": 0,
                    "unit_type_correct": 0,
                    "topic_recall_sum": 0.0,
                }
            by_language[lang]["count"] += 1
            by_language[lang]["unit_type_correct"] += int(r.unit_type_correct)
            by_language[lang]["topic_recall_sum"] += r.topic_recall

        for lang, data in by_language.items():
            n = data["count"]
            data["unit_type_accuracy"] = data["unit_type_correct"] / n
            data["avg_topic_recall"] = data["topic_recall_sum"] / n

        return BenchmarkReport(
            total_clauses=total,
            evaluated_clauses=evaluated,
            skipped_clauses=skipped,
            unit_type_accuracy=round(unit_type_acc, 3),
            clause_function_accuracy=round(func_acc, 3),
            avg_topic_recall=round(avg_recall, 3),
            avg_topic_precision=round(avg_precision, 3),
            avg_topic_f1=round(avg_f1, 3),
            baseline_unit_type_accuracy=round(baseline_acc, 3),
            delta_unit_type=round(delta, 3),
            by_category=by_category,
            by_language=by_language,
            results=results,
        )


# ---------------------------------------------------------------------------
# Unit тесты — инфраструктура (всегда запускаются)
# ---------------------------------------------------------------------------


class TestBenchmarkLoader:
    """Тесты инфраструктуры загрузки gold set."""

    def test_gold_file_exists(self):
        assert GOLD_FILE.exists(), f"Gold file not found: {GOLD_FILE}"

    def test_gold_file_loads(self):
        loader = BenchmarkLoader()
        clauses = loader.load()
        assert len(clauses) > 0

    def test_gold_file_has_expected_count(self):
        loader = BenchmarkLoader()
        clauses = loader.load()
        assert len(clauses) == 24

    def test_all_clause_ids_unique(self):
        loader = BenchmarkLoader()
        clauses = loader.load()
        ids = [c.id for c in clauses]
        assert len(ids) == len(set(ids))

    def test_language_distribution(self):
        loader = BenchmarkLoader()
        clauses = loader.load()
        langs = {c.language for c in clauses}
        assert "en" in langs
        assert "ru" in langs
        assert "mixed" in langs

    def test_category_distribution(self):
        loader = BenchmarkLoader()
        clauses = loader.load()
        categories = {c.category for c in clauses}
        expected = {
            "payment", "warranty", "definitions",
            "liability", "governing_law", "notices",
            "termination", "appendix", "confidentiality",
            "dispute_resolution", "indemnification",
        }
        assert expected.issubset(categories)

    def test_gold_labels_are_valid(self):
        """Вся валидация gold labels проходит без ошибок."""
        loader = BenchmarkLoader()
        clauses = loader.load()  # если есть ошибки — выбросит ValueError

        from services.structure.topic_tagger import KNOWN_TOPICS
        from services.structure.legal_unit_models import LegalUnitType, ClauseFunction

        for clause in clauses:
            LegalUnitType(clause.gold_unit_type)
            ClauseFunction(clause.gold_clause_function)
            for topic in clause.gold_topic_tags:
                assert topic in KNOWN_TOPICS, (
                    f"{clause.id}: {topic!r} not in KNOWN_TOPICS"
                )

    def test_all_texts_long_enough_for_enrichment(self):
        loader = BenchmarkLoader()
        clauses = loader.load()
        for clause in clauses:
            assert len(clause.own_text) >= 40, (
                f"{clause.id}: text too short ({len(clause.own_text)} chars)"
            )


class TestBenchmarkEvaluator:
    """Тесты метрик evaluator (без LLM)."""

    def _make_mock_enrichment(
        self,
        unit_type: str = "payment_term",
        clause_function: str = "obligations",
        topic_tags: list[str] | None = None,
        status: str = "applied",
    ) -> Any:
        from services.structure.legal_unit_models import ClauseFunction, LegalUnitType
        from services.structure.semantic_enrichment._types import (
            LegalUnitEnrichment,
            SemanticEnrichmentStatus,
        )

        return LegalUnitEnrichment(
            unit_id="test_unit",
            status=SemanticEnrichmentStatus(status),
            base_unit_type=LegalUnitType.UNKNOWN,
            base_clause_function=ClauseFunction.UNKNOWN,
            base_topic_tags=[],
            effective_unit_type=LegalUnitType(unit_type),
            effective_clause_function=ClauseFunction(clause_function),
            effective_topic_tags=list(topic_tags or []),
            applied_fields=["unit_type", "clause_function", "topic_tags"],
        )

    def _make_gold_clause(
        self,
        gold_unit_type: str = "payment_term",
        gold_clause_function: str = "obligations",
        gold_topic_tags: list[str] | None = None,
        baseline_unit_type: str = "unknown",
    ) -> GoldClause:
        return GoldClause(
            id="test_01",
            language="en",
            category="payment",
            title="Payment",
            own_text="Payment shall be made within 30 days.",
            gold_unit_type=gold_unit_type,
            gold_clause_function=gold_clause_function,
            gold_topic_tags=gold_topic_tags or ["payment_terms"],
            baseline_unit_type=baseline_unit_type,
            notes="",
        )

    def test_perfect_match_metrics(self):
        evaluator = BenchmarkEvaluator()
        clause = self._make_gold_clause(
            gold_unit_type="payment_term",
            gold_clause_function="obligations",
            gold_topic_tags=["payment_terms", "purchase_price"],
        )
        enrichment = self._make_mock_enrichment(
            unit_type="payment_term",
            clause_function="obligations",
            topic_tags=["payment_terms", "purchase_price"],
        )
        result = evaluator.evaluate_clause(clause, enrichment)
        assert result.unit_type_correct is True
        assert result.clause_function_correct is True
        assert result.topic_recall == 1.0
        assert result.topic_precision == 1.0
        assert result.topic_f1 == 1.0

    def test_wrong_unit_type(self):
        evaluator = BenchmarkEvaluator()
        clause = self._make_gold_clause(gold_unit_type="payment_term")
        enrichment = self._make_mock_enrichment(unit_type="warranty")
        result = evaluator.evaluate_clause(clause, enrichment)
        assert result.unit_type_correct is False

    def test_partial_topic_recall(self):
        evaluator = BenchmarkEvaluator()
        clause = self._make_gold_clause(
            gold_topic_tags=["payment_terms", "purchase_price", "closing_date"]
        )
        enrichment = self._make_mock_enrichment(
            topic_tags=["payment_terms", "purchase_price"]
        )
        result = evaluator.evaluate_clause(clause, enrichment)
        assert abs(result.topic_recall - 2/3) < 0.01
        assert result.topic_precision == 1.0

    def test_extra_topics_lower_precision(self):
        evaluator = BenchmarkEvaluator()
        clause = self._make_gold_clause(gold_topic_tags=["payment_terms"])
        enrichment = self._make_mock_enrichment(
            topic_tags=["payment_terms", "governing_law", "warranties"]
        )
        result = evaluator.evaluate_clause(clause, enrichment)
        assert result.topic_recall == 1.0
        assert abs(result.topic_precision - 1/3) < 0.01

    def test_delta_vs_baseline_computed(self):
        """delta = enrichment accuracy - baseline accuracy."""
        evaluator = BenchmarkEvaluator()
        # baseline знал тип, enrichment тоже знает → delta = 0
        clause = self._make_gold_clause(
            gold_unit_type="definition",
            baseline_unit_type="definition",
        )
        enrichment = self._make_mock_enrichment(unit_type="definition")
        result = evaluator.evaluate_clause(clause, enrichment)
        assert result.unit_type_correct is True
        assert result.baseline_type_correct is True

    def test_empty_gold_topics_gives_perfect_recall(self):
        """Если gold topics пустой — recall = 1.0 по определению."""
        evaluator = BenchmarkEvaluator()
        recall, precision = evaluator._compute_topic_metrics(
            effective_topics=["payment_terms"],
            gold_topics=[],
        )
        assert recall == 1.0

    def test_aggregate_report_fields(self):
        """Агрегация корректно вычисляет accuracy."""
        evaluator = BenchmarkEvaluator()
        results = [
            ClauseEvalResult(
                clause_id=f"c{i}",
                language="en",
                category="payment",
                gold_unit_type="payment_term",
                gold_clause_function="obligations",
                gold_topic_tags=["payment_terms"],
                baseline_unit_type="unknown",
                enrichment_status="applied",
                effective_unit_type="payment_term",
                effective_clause_function="obligations",
                effective_topic_tags=["payment_terms"],
                unit_type_correct=(i % 2 == 0),  # 50% correct
                clause_function_correct=True,
                topic_recall=1.0,
                topic_precision=1.0,
                baseline_type_correct=False,
            )
            for i in range(4)
        ]
        report = evaluator._aggregate(results, total=4, skipped=0)
        assert report.unit_type_accuracy == 0.5
        assert report.clause_function_accuracy == 1.0
        assert report.avg_topic_recall == 1.0
        assert report.baseline_unit_type_accuracy == 0.0
        assert report.delta_unit_type == 0.5


class TestBenchmarkPipelineWithMockLLM:
    """
    Тест полного pipeline с mock LLM.

    LLM заменена на идеальный mock, возвращающий корректные ответы.
    Проверяем что pipeline не падает и метрики вычисляются.
    """

    def _make_perfect_llm_response(self, clause: GoldClause) -> str:
        response = {
            "suggested_unit_type": clause.gold_unit_type,
            "suggested_clause_function": clause.gold_clause_function,
            "suggested_topics": clause.gold_topic_tags[:4],
            "confidence": 0.92,
            "reasoning": f"This is a {clause.category} clause.",
            "evidence_quotes": [clause.own_text[:60]],
        }
        return json.dumps(response)

    def test_full_pipeline_with_mock_llm(self):
        """
        Запускает evaluator с mock LLM для 5 clauses.

        Проверяет:
        - pipeline не падает;
        - evaluated_clauses == total;
        - unit_type_accuracy > 0 (хотя бы что-то применилось).
        """
        loader = BenchmarkLoader()
        clauses = loader.load()[:5]  # первые 5 для скорости

        evaluator = BenchmarkEvaluator()

        def mock_call_llm(prompt: str) -> str:
            # Определяем clause по наличию текста в prompt
            for clause in clauses:
                if clause.own_text[:30] in prompt:
                    return self._make_perfect_llm_response(clause)
            # Fallback — ответ для первого clause
            return self._make_perfect_llm_response(clauses[0])

        # Патчим на уровне _llm_client (источник) чтобы перехватить
        # вызов независимо от того как он импортирован в _enricher
        with patch(
            "services.structure.semantic_enrichment._llm_client.call_semantic_enrichment_llm",
            side_effect=mock_call_llm,
        ), patch(
            "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
            side_effect=mock_call_llm,
        ), patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ), patch(
            "services.structure.semantic_enrichment._llm_client.is_semantic_enrichment_llm_available",
            return_value=True,
        ):
            report = evaluator.run(clauses)

        assert report.total_clauses == 5
        assert report.evaluated_clauses == 5
        assert report.skipped_clauses == 0
        # С идеальным mock — точность должна быть высокой
        assert report.unit_type_accuracy >= 0.6
        assert report.avg_topic_recall >= 0.5

    def test_llm_unavailable_skips_all(self):
        """
        Если LLM недоступна, enrich_legal_units() возвращает SKIPPED для всех units.

        Примечание: preflight gate живёт в enrich_legal_units(), не в enrich_single_unit().
        Benchmark evaluator использует enrich_single_unit() напрямую, поэтому
        этот тест проверяет enrich_legal_units() непосредственно.
        """
        from services.structure.legal_unit_models import LegalUnitsSnapshot
        from services.structure.semantic_enrichment._enricher import enrich_legal_units
        from services.structure.semantic_enrichment._types import SemanticEnrichmentPolicy

        loader = BenchmarkLoader()
        clauses = loader.load()[:3]
        evaluator = BenchmarkEvaluator()

        # Строим snapshot из первых 3 clauses
        units = [evaluator._make_legal_unit(c) for c in clauses]
        snapshot = LegalUnitsSnapshot(
            document_id="benchmark",
            document_version_id="v1",
            segment_id="seg1",
            segment_type="main_contract",
            segment_order=0,
            is_primary_segment=True,
            units=units,
        )

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=False,
        ):
            result = enrich_legal_units(snapshot, policy=SemanticEnrichmentPolicy())

        assert len(result.enrichments) == 3
        for enrichment in result.enrichments:
            assert enrichment.status.value == "skipped"
        assert "llm_unavailable_all_units_skipped" in result.build_warnings

    def test_report_summary_lines_not_empty(self):
        """BenchmarkReport.summary_lines() возвращает непустой список строк."""
        loader = BenchmarkLoader()
        clauses = loader.load()[:2]
        evaluator = BenchmarkEvaluator()

        perfect_response = json.dumps({
            "unit_type": "payment_term",
            "clause_function": "obligations",
            "topic_tags": ["payment_terms"],
            "confidence": 0.85,
            "reasoning": "Payment clause.",
            "evidence_quotes": [],
        })

        with patch(
            "services.structure.semantic_enrichment._llm_client.call_semantic_enrichment_llm",
            return_value=perfect_response,
        ), patch(
            "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
            return_value=perfect_response,
        ), patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ), patch(
            "services.structure.semantic_enrichment._llm_client.is_semantic_enrichment_llm_available",
            return_value=True,
        ):
            report = evaluator.run(clauses)

        lines = report.summary_lines()
        assert len(lines) > 5
        assert any("Benchmark" in line for line in lines)
        assert any("unit_type_accuracy" in line for line in lines)

# ---------------------------------------------------------------------------
# llm_integration тесты — только с живым LLM
# ---------------------------------------------------------------------------


@pytest.mark.llm_integration
class TestBenchmarkWithRealLLM:
    """
    Полный benchmark с реальным LLM.

    Запускается только с: pytest -m llm_integration

    Не проверяет конкретные пороги — только что pipeline
    завершается и метрики в разумных пределах.
    """

    def test_full_benchmark_run(self):
        """
        Запускает benchmark с реальным LLM.

        Количество clauses можно ограничить через:
            BENCHMARK_MAX_CLAUSES=5 pytest ... -m llm_integration
        """
        import os

        loader = BenchmarkLoader()
        clauses = loader.load()

        max_clauses = int(os.environ.get("BENCHMARK_MAX_CLAUSES", len(clauses)))
        clauses = clauses[:max_clauses]

        print(f"\nRunning benchmark on {len(clauses)} clauses (max={max_clauses})...")

        evaluator = BenchmarkEvaluator()
        report = evaluator.run(clauses)

        for line in report.summary_lines():
            print(line)

        # Детальные результаты
        print(f"\n{'ID':<12} {'Status':<12} {'Type OK':<9} {'Recall':<8} {'Effective type'}")
        print("-" * 65)
        for r in report.results:
            recall_str = f"{r.topic_recall:.0%}"
            print(
                f"{r.clause_id:<12} {r.enrichment_status:<12} "
                f"{'✓' if r.unit_type_correct else '✗':<9} "
                f"{recall_str:<8} "
                f"{r.effective_unit_type}"
            )

        assert report.total_clauses == len(clauses)
        assert report.evaluated_clauses + report.skipped_clauses == len(clauses)

        applied = sum(1 for r in report.results if r.enrichment_status == "applied")
        failed = sum(1 for r in report.results if r.enrichment_status == "failed")
        rejected = sum(1 for r in report.results if r.enrichment_status == "rejected")

        print(f"\napplied={applied} rejected={rejected} failed={failed}")

    def test_per_category_accuracy(self):
        """Детализированный отчёт по категориям."""
        loader = BenchmarkLoader()
        clauses = loader.load()
        evaluator = BenchmarkEvaluator()
        report = evaluator.run(clauses)

        print("\nPer-category breakdown:")
        for cat, metrics in sorted(report.by_category.items()):
            print(
                f"  {cat:<20} "
                f"type_acc={metrics['unit_type_accuracy']:.0%}  "
                f"recall={metrics['avg_topic_recall']:.0%}  "
                f"n={metrics['count']}"
            )

        assert len(report.by_category) > 0

    def test_per_language_accuracy(self):
        """Детализированный отчёт по языкам."""
        loader = BenchmarkLoader()
        clauses = loader.load()
        evaluator = BenchmarkEvaluator()
        report = evaluator.run(clauses)

        print("\nPer-language breakdown:")
        for lang, metrics in sorted(report.by_language.items()):
            print(
                f"  {lang:<10} "
                f"type_acc={metrics['unit_type_accuracy']:.0%}  "
                f"recall={metrics['avg_topic_recall']:.0%}  "
                f"n={metrics['count']}"
            )

        assert "en" in report.by_language
        assert "ru" in report.by_language


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


def run_standalone_benchmark() -> None:
    """
    Запускает полный benchmark с реальным LLM и печатает отчёт.

    Использование:
        python tests/benchmark/test_phase12_1_7_benchmark.py
    """
    print("Phase 12.1.7 — Offline Benchmark (Standalone)")
    print(f"Gold file: {GOLD_FILE}")

    loader = BenchmarkLoader()
    try:
        clauses = loader.load()
    except Exception as e:
        print(f"ERROR: Failed to load gold set: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(clauses)} gold clauses.")

    evaluator = BenchmarkEvaluator()
    report = evaluator.run(clauses)

    for line in report.summary_lines():
        print(line)

    # Детальные результаты
    print("\nDetailed results:")
    print(f"{'ID':<12} {'Lang':<6} {'Category':<20} {'Status':<12} {'Type OK':<8} {'Recall':<8}")
    print("-" * 72)
    for r in report.results:
        print(
            f"{r.clause_id:<12} {r.language:<6} {r.category:<20} "
            f"{r.enrichment_status:<12} "
            f"{'✓' if r.unit_type_correct else '✗':<8} "
            f"{r.topic_recall:.0%}"
        )


if __name__ == "__main__":
    run_standalone_benchmark()


    