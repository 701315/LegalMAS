# src/services/structure/hierarchy_state_machine.py

"""
HierarchyStateMachine — state machine для сборки ClauseNode дерева.

Роль модуля:
- инкапсулировать логику transitions между узлами дерева;
- правильно закрывать peer-level sections при встрече следующего peer heading;
- не поднимать definition_item в sibling sections;
- строить best-effort tree даже при средних confidence headings;
- запрещать total downgrade при наличии валидных headings.

Для непрофессионального программиста:
- hierarchy_builder.py — это оркестратор: он получает список heading candidates
  и вызывает state machine для каждого из них по очереди;
- hierarchy_state_machine.py — это сам механизм дерева: он знает
  "куда прикрепить следующий heading" и "как закрыть предыдущий раздел".

Ключевые правила:
1. Переход 1 -> 1.1 -> 1.1.1: каждый более глубокий uid становится child.
2. Переход 1.1 -> 1.2: закрываем 1.1, прикрепляем 1.2 к родителю (1).
3. Переход 1.1 -> 2: закрываем весь subtree 1.x, начинаем новый root.
4. definition_item не поднимается как sibling section.
5. Best-effort: если parent не найден — прикрепляем к root, не теряем узел.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.structure.models import (
    DEFAULT_SCOPE,
    NEGATIVE_HEADING_SEMANTIC_TYPES,
    ClauseNode,
)

logger = get_logger(__name__)

# ============================================================================
# Вспомогательные типы
# ============================================================================


@dataclass(slots=True)
class AttachResult:
    """
    Результат операции attach одного узла в дерево.

    attached: узел успешно прикреплён (к parent или к root).
    attach_mode: "child" / "root" / "best_effort_root" / "skipped".
    parent_effective_uid: к какому parent прикреплён (None если root).
    reject_reason: почему узел был пропущен (только если skipped).
    """

    attached: bool
    attach_mode: str
    parent_effective_uid: str | None = None
    reject_reason: str | None = None


@dataclass
class HierarchyBuildSummary:
    """
    Итоговая статистика сборки дерева через state machine.

    Используется для:
    - quality gates в structure_diagnostics;
    - diagnostics/logging;
    - решения о structure_degraded.
    """

    total_candidates: int = 0
    attached_as_child: int = 0
    attached_as_root: int = 0
    attached_best_effort: int = 0
    skipped_semantic_negative: int = 0
    skipped_invalid: int = 0
    duplicate_uid_skipped: int = 0
    parent_level_rejected: int = 0

    # Качество дерева
    root_count: int = 0
    max_depth_reached: int = 0
    has_valid_root_sections: bool = False
    structure_degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)

    # Quality gates для downstream
    quality_gates: dict[str, Any] = field(default_factory=dict)

    def mark_degraded(self, reason: str) -> None:
        if not self.structure_degraded:
            self.structure_degraded = True
        if reason not in self.degradation_reasons:
            self.degradation_reasons.append(reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "attached_as_child": self.attached_as_child,
            "attached_as_root": self.attached_as_root,
            "attached_best_effort": self.attached_best_effort,
            "skipped_semantic_negative": self.skipped_semantic_negative,
            "skipped_invalid": self.skipped_invalid,
            "duplicate_uid_skipped": self.duplicate_uid_skipped,
            "parent_level_rejected": self.parent_level_rejected,
            "root_count": self.root_count,
            "max_depth_reached": self.max_depth_reached,
            "has_valid_root_sections": self.has_valid_root_sections,
            "structure_degraded": self.structure_degraded,
            "degradation_reasons": list(self.degradation_reasons),
            "quality_gates": dict(self.quality_gates),
        }


# ============================================================================
# Вспомогательные функции
# ============================================================================


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _normalize_scope(value: Any) -> str:
    scope = _normalize_uid(value)
    return scope or DEFAULT_SCOPE


def _is_numeric_uid(uid: str) -> bool:
    """Проверяет что uid это чистый numeric uid типа 1 / 1.2 / 3.1.4."""
    import re

    return bool(re.fullmatch(r"\d+(?:\.\d+)*", uid.strip()))


def _uid_level(uid: str) -> int:
    """
    Возвращает уровень numeric uid.
    "1" -> 1, "1.2" -> 2, "3.1.4" -> 3.
    Для нечисловых uid возвращаем 1.
    """
    uid = _normalize_uid(uid)
    if not _is_numeric_uid(uid):
        return 1
    return uid.count(".") + 1


def _uid_parent_raw(uid: str) -> str | None:
    """
    Возвращает raw_uid родителя для numeric uid.
    "1.2.3" -> "1.2"
    "1.2" -> "1"
    "1" -> None
    """
    uid = _normalize_uid(uid)
    if not _is_numeric_uid(uid) or "." not in uid:
        return None
    return uid.rsplit(".", 1)[0]


def _is_semantic_negative_for_section(semantic_type: str | None) -> bool:
    """
    Возвращает True если semantic_type говорит что узел НЕ должен
    становиться section heading в иерархии.

    Важно: appendix_heading — это NOT negative здесь.
    Appendix heading может быть root-level section.
    Negative — только definition_item и signature_block и body_text.
    """
    if not semantic_type:
        return False
    return semantic_type.lower().strip() in NEGATIVE_HEADING_SEMANTIC_TYPES


# ============================================================================
# Основной класс
# ============================================================================


class HierarchyStateMachine:
    """
    State machine для построения ClauseNode дерева.

    Использование:
        sm = HierarchyStateMachine(scope="main_contract", document_id="...")
        for heading in headings:
            sm.attach(heading_node, raw_uid=heading.raw_uid, ...)
        root_nodes = sm.root_nodes
        summary = sm.build_summary()

    Принципы:
    - один экземпляр на один scope;
    - порядок вызовов attach() должен совпадать с порядком headings в документе;
    - machine не делает никакого parsing — только tree assembly.
    """

    def __init__(
        self,
        *,
        scope: str,
        document_id: str,
        allow_best_effort: bool = True,
        max_uid_depth: int = 8,
    ) -> None:
        self._scope = _normalize_scope(scope)
        self._document_id = str(document_id or "").strip()
        self._allow_best_effort = bool(allow_best_effort)
        self._max_uid_depth = int(max_uid_depth)

        # Основные структуры
        self._root_nodes: list[ClauseNode] = []
        self._nodes_by_raw_uid: dict[str, ClauseNode] = {}

        # Стек текущей "открытой" ветки для быстрого поиска parent
        # Каждый элемент: (raw_uid, node)
        self._open_stack: list[tuple[str, ClauseNode]] = []

        # Счётчики для summary
        self._total = 0
        self._attached_child = 0
        self._attached_root = 0
        self._attached_best_effort = 0
        self._skipped_semantic = 0
        self._skipped_invalid = 0
        self._duplicate_skipped = 0
        self._parent_level_rejected = 0
        self._max_depth = 0

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def root_nodes(self) -> list[ClauseNode]:
        return list(self._root_nodes)

    @property
    def nodes_by_raw_uid(self) -> dict[str, ClauseNode]:
        return dict(self._nodes_by_raw_uid)

    def attach(
        self,
        node: ClauseNode,
        *,
        raw_uid: str,
        semantic_type: str | None = None,
    ) -> AttachResult:
        """
        Прикрепляет узел в дерево согласно его raw_uid и текущему состоянию стека.

        Параметры:
        - node: уже созданный ClauseNode (без children — их добавим здесь);
        - raw_uid: числовой uid вида "1", "1.2", "3.1.4";
        - semantic_type: semantic_element_type из classifier/scorer.

        Возвращает AttachResult с объяснением что произошло.
        """
        self._total += 1
        raw_uid = _normalize_uid(raw_uid)

        # ── Guard: невалидный uid ─────────────────────────────────────────────
        if not raw_uid:
            self._skipped_invalid += 1
            logger.warning(
                "STRUCTURE hsm_attach_skipped_empty_uid",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "effective_uid": node.effective_uid,
                },
            )
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason="empty_raw_uid",
            )

        # ── Guard: дубликат uid в этом scope ─────────────────────────────────
        if raw_uid in self._nodes_by_raw_uid:
            self._duplicate_skipped += 1
            logger.warning(
                "STRUCTURE hsm_attach_skipped_duplicate_uid",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "raw_uid": raw_uid,
                    "existing_effective_uid": self._nodes_by_raw_uid[raw_uid].effective_uid,
                    "new_effective_uid": node.effective_uid,
                },
            )
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason="duplicate_uid",
            )

        # ── Guard: semantic negative (definition_item, signature_block) ───────
        # НЕ поднимаем их как section siblings.
        # Но всё равно регистрируем в nodes_by_raw_uid, чтобы не потерять.
        if _is_semantic_negative_for_section(semantic_type):
            self._skipped_semantic += 1
            node.diagnostics["semantic_attach_skipped"] = True
            node.diagnostics["semantic_type_at_attach"] = semantic_type
            logger.debug(
                "STRUCTURE hsm_attach_skipped_semantic_negative",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "raw_uid": raw_uid,
                    "semantic_type": semantic_type,
                    "effective_uid": node.effective_uid,
                },
            )
            # Регистрируем но не добавляем в дерево
            self._nodes_by_raw_uid[raw_uid] = node
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason=f"semantic_negative:{semantic_type}",
            )

        # ── Определяем уровень и ищем parent ─────────────────────────────────
        numeric = _is_numeric_uid(raw_uid)
        level = _uid_level(raw_uid) if numeric else 1

        # Ограничение глубины
        if level > self._max_uid_depth:
            level = self._max_uid_depth

        self._max_depth = max(self._max_depth, level)

        # ── Закрываем стек до нужного уровня ─────────────────────────────────
        # Смысл: если мы были на 1.1.1 и встречаем 1.2 —
        # нужно "закрыть" 1.1.1 и 1.1, оставить 1 открытым.
        self._pop_stack_to_level(level)

        # ── Ищем parent в стеке ───────────────────────────────────────────────
        parent_node = self._find_parent_in_stack(raw_uid=raw_uid, level=level)

        # ── Прикрепляем узел ─────────────────────────────────────────────────
        node.diagnostics["semantic_type_at_attach"] = semantic_type
        node.diagnostics["attach_level"] = level
        node.diagnostics["numeric_uid"] = numeric

        self._nodes_by_raw_uid[raw_uid] = node

        if parent_node is not None:
            # Проверяем что уровень parent < level нашего узла
            if parent_node.level >= level:
                # Это аномалия — parent должен быть выше нас
                self._parent_level_rejected += 1
                node.diagnostics["parent_attach_status"] = "rejected_invalid_parent_level"
                node.diagnostics["parent_level_mismatch"] = True

                logger.warning(
                    "STRUCTURE hsm_parent_level_mismatch",
                    extra={
                        "document_id": self._document_id,
                        "scope": self._scope,
                        "raw_uid": raw_uid,
                        "level": level,
                        "parent_raw_uid": parent_node.raw_uid,
                        "parent_level": parent_node.level,
                    },
                )

                # Best effort: прикрепляем к root
                if self._allow_best_effort:
                    self._attach_to_root(node, raw_uid=raw_uid)
                    self._attached_best_effort += 1
                    return AttachResult(
                        attached=True,
                        attach_mode="best_effort_root",
                        parent_effective_uid=None,
                    )

                self._skipped_invalid += 1
                return AttachResult(
                    attached=False,
                    attach_mode="skipped",
                    reject_reason="parent_level_mismatch",
                )

            # Нормальный attach: узел становится child parent-а
            parent_node.children.append(node)
            node.diagnostics["parent_attach_status"] = "attached_as_child"

            # Обновляем стек: добавляем текущий узел
            self._open_stack.append((raw_uid, node))

            self._attached_child += 1

            logger.debug(
                "STRUCTURE hsm_attached_as_child",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "raw_uid": raw_uid,
                    "level": level,
                    "parent_raw_uid": parent_node.raw_uid,
                    "parent_level": parent_node.level,
                },
            )

            return AttachResult(
                attached=True,
                attach_mode="child",
                parent_effective_uid=parent_node.effective_uid,
            )

        # Parent не найден — прикрепляем к root
        node.diagnostics["parent_attach_status"] = "root"

        if level == 1 or not self._allow_best_effort:
            # Это нормальный root-level узел
            self._attach_to_root(node, raw_uid=raw_uid)
            self._attached_root += 1
            return AttachResult(
                attached=True,
                attach_mode="root",
                parent_effective_uid=None,
            )

        # level > 1 но parent не найден — best effort
        node.diagnostics["parent_attach_status"] = "best_effort_root"
        node.diagnostics["best_effort_reason"] = "parent_not_found_in_stack"

        logger.debug(
            "STRUCTURE hsm_best_effort_root",
            extra={
                "document_id": self._document_id,
                "scope": self._scope,
                "raw_uid": raw_uid,
                "level": level,
                "reason": "parent_not_found",
            },
        )

        self._attach_to_root(node, raw_uid=raw_uid)
        self._attached_best_effort += 1

        return AttachResult(
            attached=True,
            attach_mode="best_effort_root",
            parent_effective_uid=None,
        )

    def build_summary(self) -> HierarchyBuildSummary:
        """
        Строит итоговый summary после того как все узлы прикреплены.

        Вызывать после того как все attach() завершены.
        """
        summary = HierarchyBuildSummary(
            total_candidates=self._total,
            attached_as_child=self._attached_child,
            attached_as_root=self._attached_root,
            attached_best_effort=self._attached_best_effort,
            skipped_semantic_negative=self._skipped_semantic,
            skipped_invalid=self._skipped_invalid,
            duplicate_uid_skipped=self._duplicate_skipped,
            parent_level_rejected=self._parent_level_rejected,
            root_count=len(self._root_nodes),
            max_depth_reached=self._max_depth,
        )

        # Есть ли реальные root sections
        summary.has_valid_root_sections = bool(
            self._root_nodes
            and any(
                not node.diagnostics.get("semantic_attach_skipped") for node in self._root_nodes
            )
        )

        # Оцениваем degradation
        total_attached = self._attached_child + self._attached_root + self._attached_best_effort

        if self._total > 0 and total_attached == 0:
            summary.mark_degraded("no_nodes_attached")

        if self._total > 0 and not self._root_nodes:
            summary.mark_degraded("no_root_nodes")

        if self._duplicate_skipped > 0:
            dup_ratio = self._duplicate_skipped / max(self._total, 1)
            if dup_ratio >= 0.3:
                summary.mark_degraded("high_duplicate_ratio")

        if self._parent_level_rejected > 0:
            reject_ratio = self._parent_level_rejected / max(self._total, 1)
            if reject_ratio >= 0.25:
                summary.mark_degraded("high_parent_level_rejection")

        if self._attached_best_effort > 0:
            be_ratio = self._attached_best_effort / max(total_attached, 1)
            if be_ratio >= 0.4:
                summary.mark_degraded("high_best_effort_ratio")

        # Quality gates для clause_tree_builder и downstream
        summary.quality_gates = self._compute_quality_gates(summary)

        return summary

    # ── Private helpers ───────────────────────────────────────────────────────

    def _pop_stack_to_level(self, incoming_level: int) -> None:
        """
        Закрывает открытые узлы в стеке у которых level >= incoming_level.

        Логика:
        - если мы были на 1.1.1 (level=3) и встречаем 1.2 (level=2):
          нужно закрыть 1.1.1 (уровень 3 >= 2) и 1.1 (уровень 2 >= 2);
          оставить 1 (уровень 1 < 2).
        - если встречаем 2 (level=1):
          закрываем всё что есть в стеке.
        """
        while self._open_stack:
            top_uid, top_node = self._open_stack[-1]
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level >= incoming_level:
                self._open_stack.pop()
            else:
                break

    def _find_parent_in_stack(
        self,
        *,
        raw_uid: str,
        level: int,
    ) -> ClauseNode | None:
        """
        Ищет подходящего parent для нового узла.

        Алгоритм:
        1. Для numeric uid пробуем найти явный parent по uid-цепочке:
           "1.2.3" -> parent должен быть "1.2".
        2. Если не нашли по uid — берём верхний элемент стека,
           если его level = level - 1 (прямой parent по уровню).
        3. Иначе — parent не найден.
        """
        if not self._open_stack:
            return None

        numeric = _is_numeric_uid(raw_uid)

        if numeric and level > 1:
            # Пробуем найти явный parent по uid
            parent_raw = _uid_parent_raw(raw_uid)
            if parent_raw and parent_raw in self._nodes_by_raw_uid:
                parent_node = self._nodes_by_raw_uid[parent_raw]
                if parent_node.level == level - 1:
                    return parent_node

            # Явный parent не найден — берём верхушку стека
            top_uid, top_node = self._open_stack[-1]
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level == level - 1:
                return top_node

            return None

        # Для нечисловых uid берём верхушку стека если уровень подходит
        if self._open_stack:
            top_uid, top_node = self._open_stack[-1]
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level < level:
                return top_node

        return None

    def _attach_to_root(self, node: ClauseNode, *, raw_uid: str) -> None:
        """
        Добавляет узел в root_nodes и обновляет открытый стек.
        """
        self._root_nodes.append(node)
        # Когда прикрепляем к root — открываем этот узел в стеке
        # (предварительно очистив стек от старых root-level элементов того же уровня)
        node_level = node.level
        while self._open_stack:
            top_uid, top_node = self._open_stack[-1]
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level >= node_level:
                self._open_stack.pop()
            else:
                break
        self._open_stack.append((raw_uid, node))

    def _compute_quality_gates(
        self,
        summary: HierarchyBuildSummary,
    ) -> dict[str, Any]:
        """
        Вычисляет quality gates для downstream consumers.

        section_chunking_allowed:
        - True только если дерево не degraded и есть реальные root sections;
        - clause_tree_builder.py читает именно это поле.

        technical_fallback_only:
        - True если структура деградировала до уровня fallback.
        """
        total_attached = self._attached_child + self._attached_root + self._attached_best_effort
        best_effort_ratio = (
            self._attached_best_effort / max(total_attached, 1) if total_attached > 0 else 0.0
        )

        section_chunking_allowed = (
            not summary.structure_degraded
            and summary.has_valid_root_sections
            and summary.root_count > 0
            and best_effort_ratio < 0.5
        )

        technical_fallback_only = summary.structure_degraded or not summary.has_valid_root_sections

        return {
            "section_chunking_allowed": section_chunking_allowed,
            "technical_fallback_only": technical_fallback_only,
            "structure_confidence": (
                "HIGH"
                if not summary.structure_degraded and summary.has_valid_root_sections
                else "LOW"
                if summary.structure_degraded
                else "MEDIUM"
            ),
            "recoverable_hierarchy_used": self._attached_best_effort > 0,
            "total_fallback_blocked": self._skipped_invalid + self._skipped_semantic,
            "hierarchy_quality": (
                "good"
                if not summary.structure_degraded and summary.has_valid_root_sections
                else "partial"
                if summary.has_valid_root_sections
                else "failed"
            ),
            "best_effort_ratio": round(best_effort_ratio, 4),
        }
