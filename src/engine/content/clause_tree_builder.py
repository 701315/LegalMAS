# src/engine/content/clause_tree_builder.py

"""
Legacy clause tree materialization helper (Sprint 3).

ВАЖНО:
- Это legacy helper для materialization из clause tree + layout.
- Основной retrieval corpus живёт в chunk snapshots v2 (CHUNKS v2).
- Этот builder используется только для старых документов и вспомогательных
  сценариев вроде header/snippet.

Canonical chunk contract (Sprint 3):
- canonical identity узла = effective_uid (обязательное поле);
- raw_uid используется как display/reference field;
- scope фиксирует область интерпретации raw_uid;
- metadata чанков сохраняет effective_uid/raw_uid/scope;
- chunk_kind различает "clause" и "section";
- node_kind различает "leaf" и "section" узлы дерева;
- section chunks разрешены только при открытом quality gate;
- leaf chunks строятся только по own_element_ids;
- section chunks строятся только по subtree_element_ids;
- если effective_uid отсутствует, это structural anomaly.

Этап 4 — новые поля в metadata чанков:
- semantic_node_type: тип узла из classifier/scorer
- parse_confidence: уверенность в parse этого узла
- citability_hint: "high" / "medium" / "low" — пригодность для цитирования
- recovered_via_best_effort: узел был прикреплён через best-effort recovery
- fallback_reason: причина fallback если recovered_via_best_effort == True
- is_heading_only_leaf: True если leaf содержит только heading без body
- is_structural_fallback: True если chunk создан через технический fallback

Модуль не знает про БД и MinIO — работает только с загруженными JSON.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from core.logging import get_logger
from engine.content.chunk_ids import build_leaf_chunk_id, build_section_chunk_id

logger = get_logger(__name__)


@dataclass
class LeafChunkBuildResult:
    """
    Результат сборки leaf-чанков по clause tree.

    chunks:
      - список нормализованных чанков по листовым клаузам;
    total_leaf_nodes:
      - сколько листовых узлов вообще встретилось в дереве;
    leaf_nodes_without_element_ids:
      - сколько листов были без element_ids и были пропущены;
    leaf_nodes_empty_after_filtering:
      - сколько листов не дали текста даже после fallback по heading;

    Этап 4 — новые поля диагностики:
    heading_only_leaf_nodes:
      - сколько листов содержали только heading-элемент без body;
      - такие узлы маркируются is_heading_only_leaf=True и citability_hint="low";
      - они НЕ используют heading text как body — это тихий fallback который создавал
        шумные чанки типа "1.1 Definitions" без содержимого.
    best_effort_leaf_nodes:
      - сколько листов были прикреплены через best-effort recovery.
    """

    chunks: List[Dict[str, Any]]
    total_leaf_nodes: int
    leaf_nodes_without_element_ids: int
    leaf_nodes_empty_after_filtering: int
    # ── Этап 4: новые счётчики ────────────────────────────────────────────────
    heading_only_leaf_nodes: int = 0
    best_effort_leaf_nodes: int = 0


class ClauseTreeBuilder:
    """
    Legacy clause tree materialization helper (Sprint 3).

    ВАЖНО:
    - Это legacy helper для материализации clause tree + layout в chunks.
    - Source of truth для retrieval — CHUNKS v2 snapshots, а не этот builder.
    - Используется только для старых документов и header/snippet scenarios.

    Для непрофессионального программиста:
    - Класс не знает про БД и MinIO.
    - Ему дают уже загруженный JSON clause tree и JSON layout,
      и он возвращает список canonical chunks по листовым клаузам
      и (опционально) по разделам верхнего уровня.
    - Chunk metadata строго следует Sprint 3 canonical contract:
      effective_uid/raw_uid/scope/chunk_kind/node_kind.
    - После Этапа 4: metadata дополнена semantic/citability полями.
    """

    @staticmethod
    def _normalize_uid(value: Any) -> str | None:
        if value is None:
            return None
        uid = str(value).strip()
        return uid or None

    @staticmethod
    def _normalize_title(value: Any) -> str | None:
        if value is None:
            return None
        title = str(value).strip()
        return title or None

    @classmethod
    def _node_effective_uid(cls, node: Dict[str, Any]) -> str | None:
        return cls._normalize_uid(node.get("effective_uid"))

    @classmethod
    def _node_raw_uid(cls, node: Dict[str, Any]) -> str | None:
        return cls._normalize_uid(node.get("raw_uid"))

    @classmethod
    def _node_scope(cls, node: Dict[str, Any]) -> str | None:
        return cls._normalize_uid(node.get("scope"))

    @classmethod
    def _node_chunk_identity(cls, node: Dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        effective_uid = cls._node_effective_uid(node)
        raw_uid = cls._node_raw_uid(node)
        scope = cls._node_scope(node)
        return effective_uid, raw_uid, scope

    @staticmethod
    def _extract_node_etap4_fields(node: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлекает из node dict новые поля Этапа 4.

        Эти поля появляются в node dict после того как ClauseNode.to_dict()
        был обновлён в Этапе 4. Для старых документов где этих полей нет —
        возвращаем безопасные defaults.

        Для непрофессионального программиста:
        - node — это python dict полученный из ClauseNode.to_dict();
        - если документ старый и поля отсутствуют — dict.get() вернёт None;
        - мы явно возвращаем None/False/defaults чтобы downstream знал
          что данные недоступны, а не что значение False/low.
        """
        return {
            "semantic_node_type": node.get("semantic_node_type"),
            "parse_confidence": node.get("parse_confidence"),
            "citability_hint": node.get("citability_hint"),
            "recovered_via_best_effort": bool(node.get("recovered_via_best_effort", False)),
            "fallback_reason": node.get("fallback_reason"),
        }

    # ------------------------------------------------------------------
    # Базовые хелперы
    # ------------------------------------------------------------------

    @staticmethod
    def extract_root_children(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Извлечь список узлов верхнего уровня из clause tree JSON.

        Формат ClauseTree.to_dict():
          {
            "document_id": "...",
            "root": [ {...}, {...} ],
            ...
          }

        На всякий случай поддерживаем и формат:
          { "root": { "children": [ {...}, ... ] } }
        """
        raw_root = tree.get("root")

        if isinstance(raw_root, list):
            return raw_root

        if isinstance(raw_root, dict):
            children = raw_root.get("children")
            if isinstance(children, list):
                return children

        return []

    @staticmethod
    def build_element_index(layout: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Построить индекс element_id -> элемент layout'а.
        """
        elements = layout.get("elements") or []
        index: Dict[str, Dict[str, Any]] = {}

        missing_id_count = 0
        for el in elements:
            el_id = el.get("element_id")
            if el_id:
                if el_id in index:
                    logger.warning(
                        "ClauseTreeBuilder: duplicate element_id in layout, overriding",
                        extra={
                            "element_id": el_id,
                            "existing_type": (index[el_id].get("type") or "").strip().lower(),
                            "new_type": (el.get("type") or "").strip().lower(),
                        },
                    )
                index[el_id] = el
            else:
                missing_id_count += 1

        logger.info(
            "ClauseTreeBuilder: element index built",
            extra={
                "layout_elements": len(elements),
                "indexed_elements": len(index),
                "missing_element_id_count": missing_id_count,
            },
        )

        if not index:
            logger.warning(
                "ClauseTreeBuilder: empty element index, layout has no usable elements",
                extra={
                    "layout_elements": len(elements),
                },
            )

        return index

    # ------------------------------------------------------------------
    # Leaf-чанки
    # ------------------------------------------------------------------

    @classmethod
    def build_leaf_chunks(
        cls,
        doc_id: uuid.UUID,
        tree: Dict[str, Any],
        layout: Dict[str, Any],
    ) -> LeafChunkBuildResult:
        """
        Построить клауза-чанки (листовые узлы) на основе clause tree + layout.

        Возвращает:
        [
          {
            "id": "<doc_id>:<effective_uid>",
            "text": "<тело клаузы без заголовка>",
            "metadata": {...}
          },
          ...
        ]

        Этап 4:
        - heading-only leaf узлы больше НЕ используют heading text как body fallback;
        - они маркируются is_heading_only_leaf=True и citability_hint="low";
        - это предотвращает создание шумных чанков типа "1.1 Definitions" без body.
        """
        root_children = cls.extract_root_children(tree)

        if not root_children:
            logger.warning(
                "ClauseTreeBuilder: empty root in clause_tree, no leaf chunks will be built",
                extra={
                    "document_id": str(doc_id),
                    "tree_keys": sorted(tree.keys()),
                    "layout_elements": len(layout.get("elements") or []),
                },
            )
            return LeafChunkBuildResult(
                chunks=[],
                total_leaf_nodes=0,
                leaf_nodes_without_element_ids=0,
                leaf_nodes_empty_after_filtering=0,
                heading_only_leaf_nodes=0,
                best_effort_leaf_nodes=0,
            )

        logger.info(
            "ClauseTreeBuilder: building leaf chunks from clause_tree",
            extra={
                "document_id": str(doc_id),
                "tree_root_nodes": len(root_children),
                "layout_elements": len(layout.get("elements") or []),
                "clause_tree_structure_confidence": tree.get("structure_confidence"),
                "clause_tree_degraded": tree.get("degraded"),
            },
        )

        element_index = cls.build_element_index(layout)

        chunks: List[Dict[str, Any]] = []
        total_leaf_nodes = 0
        leaf_nodes_without_element_ids = 0
        leaf_nodes_empty_after_filtering = 0
        heading_only_leaf_nodes = 0
        best_effort_leaf_nodes = 0

        for child in root_children:
            if not isinstance(child, dict):
                logger.warning(
                    "ClauseTreeBuilder: root child is not a dict, skipping",
                    extra={
                        "document_id": str(doc_id),
                        "child_type": type(child).__name__,
                    },
                )
                continue

            (
                inc_total,
                inc_no_ids,
                inc_empty,
                inc_heading_only,
                inc_best_effort,
            ) = cls._collect_leaf_chunks(
                doc_id=doc_id,
                node=child,
                element_index=element_index,
                out=chunks,
                path_titles=[],
            )

            total_leaf_nodes += inc_total
            leaf_nodes_without_element_ids += inc_no_ids
            leaf_nodes_empty_after_filtering += inc_empty
            heading_only_leaf_nodes += inc_heading_only
            best_effort_leaf_nodes += inc_best_effort

        leaf_count = len(chunks)

        uid_with_none = sum(
            1 for ch in chunks if (ch.get("metadata") or {}).get("effective_uid") is None
        )
        empty_text_chunks = sum(
            1 for ch in chunks if not (ch.get("text") or "").strip()
        )

        logger.info(
            "ClauseTreeBuilder: leaf chunks built",
            extra={
                "document_id": str(doc_id),
                "total_chunks": leaf_count,
                "tree_root_nodes": len(root_children),
                "layout_elements": len(layout.get("elements") or []),
                "chunks_without_effective_uid": uid_with_none,
                "chunks_with_empty_text": empty_text_chunks,
                "total_leaf_nodes": total_leaf_nodes,
                "leaf_nodes_without_element_ids": leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_nodes_empty_after_filtering,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": heading_only_leaf_nodes,
                "best_effort_leaf_nodes": best_effort_leaf_nodes,
            },
        )

        sample_effective_uids = [
            str((ch.get("metadata") or {}).get("effective_uid"))
            for ch in chunks[:10]
            if (ch.get("metadata") or {}).get("effective_uid") is not None
        ]
        if sample_effective_uids:
            logger.debug(
                "ClauseTreeBuilder: sample leaf effective_uids",
                extra={
                    "document_id": str(doc_id),
                    "sample_effective_uids": sample_effective_uids,
                },
            )

        return LeafChunkBuildResult(
            chunks=chunks,
            total_leaf_nodes=total_leaf_nodes,
            leaf_nodes_without_element_ids=leaf_nodes_without_element_ids,
            leaf_nodes_empty_after_filtering=leaf_nodes_empty_after_filtering,
            heading_only_leaf_nodes=heading_only_leaf_nodes,
            best_effort_leaf_nodes=best_effort_leaf_nodes,
        )

    @classmethod
    def _collect_leaf_chunks(
        cls,
        doc_id: uuid.UUID,
        node: Dict[str, Any],
        element_index: Dict[str, Dict[str, Any]],
        out: List[Dict[str, Any]],
        path_titles: List[str] | None = None,
    ) -> tuple[int, int, int, int, int]:
        """
        Рекурсивно обходит дерево и строит leaf-чанки.

        Возвращает кортеж из 5 счётчиков:
        (
            leaf_seen_inc,           # сколько leaf узлов встретили
            no_element_ids_inc,      # сколько leaf узлов без element_ids
            empty_after_filtering_inc, # сколько дали пустой текст
            heading_only_inc,        # сколько были heading-only (Этап 4)
            best_effort_inc,         # сколько были best-effort recovery (Этап 4)
        )

        Изменения Этапа 4:
        - убран silent fallback "heading text as body" для single-heading leaf;
        - такие узлы теперь маркируются is_heading_only_leaf=True, citability_hint="low"
          и пропускаются как пустые (empty_after_filtering_inc++);
        - это предотвращает downstream от получения бессодержательных чанков.
        """

        def _extract_section_title(path: List[str]) -> str | None:
            if not path:
                return None
            return path[0]

        leaf_seen_inc = 0
        no_element_ids_inc = 0
        empty_after_filtering_inc = 0
        heading_only_inc = 0
        best_effort_inc = 0

        current_path: List[str] = list(path_titles or [])
        node_title = cls._normalize_title(node.get("title"))
        if node_title:
            current_path.append(node_title)

        children = node.get("children") or []

        if not children:
            # ── Это leaf узел ─────────────────────────────────────────────────
            leaf_seen_inc += 1

            effective_uid, raw_uid, scope = cls._node_chunk_identity(node)

            # Читаем новые поля Этапа 4
            etap4 = cls._extract_node_etap4_fields(node)
            is_best_effort = etap4["recovered_via_best_effort"]
            citability_hint = etap4["citability_hint"]

            if is_best_effort:
                best_effort_inc += 1

            own_element_ids: List[str] = node.get("own_element_ids") or []

            if not own_element_ids:
                logger.warning(
                    "ClauseTreeBuilder: leaf node has no own_element_ids",
                    extra={
                        "document_id": str(doc_id),
                        "effective_uid": effective_uid,
                        "raw_uid": raw_uid,
                        "scope": scope,
                        "title": node_title,
                        "citability_hint": citability_hint,
                        "recovered_via_best_effort": is_best_effort,
                    },
                )
                no_element_ids_inc += 1
                return (
                    leaf_seen_inc,
                    no_element_ids_inc,
                    empty_after_filtering_inc,
                    heading_only_inc,
                    best_effort_inc,
                )

            element_ids = own_element_ids

            # Проверяем heading-only ситуацию ДО сборки текста
            # чтобы сразу решить — пропускать или нет.
            is_single_heading_only = False
            if len(element_ids) == 1:
                el0 = element_index.get(element_ids[0])
                if el0 is not None:
                    el0_type = (el0.get("type") or "").strip().lower()
                    if el0_type == "heading":
                        is_single_heading_only = True

            missing_elements = 0
            heading_elements = 0
            texts: List[str] = []
            pages: List[int] = []
            last_page: int | None = None

            for el_id in element_ids:
                el = element_index.get(el_id)
                if not el:
                    missing_elements += 1
                    continue

                raw_text = el.get("text") or ""
                text = raw_text.strip()

                el_type = (el.get("type") or "").strip().lower()
                page = el.get("page")

                if isinstance(page, int):
                    pages.append(page)

                if el_type == "heading":
                    heading_elements += 1
                    last_page = page if isinstance(page, int) else last_page
                    continue

                if not text:
                    continue

                if last_page is not None and page is not None and page != last_page:
                    texts.append("")

                texts.append(text)
                last_page = page

            full_text = "\n\n".join(texts).strip()

            if missing_elements:
                logger.warning(
                    "ClauseTreeBuilder: some element_ids from leaf node not found in layout index",
                    extra={
                        "document_id": str(doc_id),
                        "effective_uid": effective_uid,
                        "raw_uid": raw_uid,
                        "scope": scope,
                        "title": node_title,
                        "level": node.get("level"),
                        "element_ids_count": len(element_ids),
                        "missing_elements": missing_elements,
                        "heading_elements": heading_elements,
                    },
                )

            # ── Этап 4: heading-only fallback убран ───────────────────────────
            # Раньше здесь был код:
            #   if not full_text and single_heading_element and heading_raw_text:
            #       full_text = heading_raw_text
            # Это создавало чанки где text == "1.1 Definitions" — бесполезно для retrieval.
            #
            # Теперь: если текста нет и это heading-only узел —
            # маркируем как heading_only_leaf, логируем с правильным уровнем,
            # и пропускаем без создания чанка.
            if not full_text and is_single_heading_only:
                heading_only_inc += 1
                # citability_hint от hierarchy_builder должен уже быть "low"
                # но на случай старых документов — переопределяем здесь
                effective_citability = citability_hint or "low"
                logger.info(
                    "ClauseTreeBuilder: heading_only_leaf_skipped",
                    extra={
                        "document_id": str(doc_id),
                        "effective_uid": effective_uid,
                        "raw_uid": raw_uid,
                        "scope": scope,
                        "title": node_title,
                        "level": node.get("level"),
                        "citability_hint": effective_citability,
                        "recovered_via_best_effort": is_best_effort,
                        "reason": "single_heading_element_no_body_text",
                    },
                )
                # Считаем как empty — чанк не создаём
                empty_after_filtering_inc += 1
                return (
                    leaf_seen_inc,
                    no_element_ids_inc,
                    empty_after_filtering_inc,
                    heading_only_inc,
                    best_effort_inc,
                )

            if not full_text:
                logger.info(
                    "ClauseTreeBuilder: leaf node produced empty text after filtering",
                    extra={
                        "document_id": str(doc_id),
                        "effective_uid": effective_uid,
                        "raw_uid": raw_uid,
                        "scope": scope,
                        "title": node_title,
                        "level": node.get("level"),
                        "element_ids_count": len(element_ids),
                        "missing_elements": missing_elements,
                        "heading_elements": heading_elements,
                    },
                )
                empty_after_filtering_inc += 1
                return (
                    leaf_seen_inc,
                    no_element_ids_inc,
                    empty_after_filtering_inc,
                    heading_only_inc,
                    best_effort_inc,
                )

            start_page = min(pages) if pages else node.get("start_page")
            end_page = max(pages) if pages else node.get("end_page")
            section_title = _extract_section_title(current_path)

            if not effective_uid:
                logger.warning(
                    "ClauseTreeBuilder: leaf node missing effective_uid, skipping chunk",
                    extra={
                        "document_id": str(doc_id),
                        "raw_uid": raw_uid,
                        "scope": scope,
                        "title": node_title,
                        "level": node.get("level"),
                    },
                )
                empty_after_filtering_inc += 1
                return (
                    leaf_seen_inc,
                    no_element_ids_inc,
                    empty_after_filtering_inc,
                    heading_only_inc,
                    best_effort_inc,
                )

            # Финальный citability_hint для этого чанка.
            # Приоритет: значение от hierarchy_builder > вычисленное здесь.
            # Если оба None — "high" как safe default для чанка с реальным текстом.
            effective_citability = citability_hint or "high"

            metadata = {
                "doc_id": str(doc_id),
                "chunk_kind": "clause",
                "effective_uid": effective_uid,
                "raw_uid": raw_uid,
                "scope": scope,
                "node_kind": "leaf",
                "title": node_title,
                "level": node.get("level"),
                "path_titles": current_path,
                "section_title": section_title,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
                # ── Этап 4: новые поля ────────────────────────────────────────
                # Эти поля позволяют downstream (detectors, retrieval) знать
                # качество и семантику каждого чанка без обращения к clause tree.
                "semantic_node_type": etap4["semantic_node_type"],
                "parse_confidence": etap4["parse_confidence"],
                "citability_hint": effective_citability,
                "recovered_via_best_effort": is_best_effort,
                "fallback_reason": etap4["fallback_reason"],
                "is_heading_only_leaf": False,      # True только если бы мы дошли сюда
                "is_structural_fallback": is_best_effort,
            }

            range_end_reason = node.get("range_end_reason")
            if range_end_reason:
                metadata["range_end_reason"] = range_end_reason

            chunk_id = build_leaf_chunk_id(doc_id, effective_uid)

            out.append(
                {
                    "id": chunk_id,
                    "text": full_text,
                    "metadata": metadata,
                }
            )

            if raw_uid in ("1", "1.1", "1.2") or effective_uid in (
                "main_contract::1",
                "main_contract::1.1",
                "main_contract::1.2",
            ):
                logger.debug(
                    "ClauseTreeBuilder: sample built leaf chunk",
                    extra={
                        "document_id": str(doc_id),
                        "effective_uid": effective_uid,
                        "raw_uid": raw_uid,
                        "scope": scope,
                        "title": node_title,
                        "level": node.get("level"),
                        "path_depth": len(current_path),
                        "text_preview": full_text[:500],
                        "element_ids_count": len(element_ids),
                        "start_page": start_page,
                        "end_page": end_page,
                        "citability_hint": effective_citability,
                        "recovered_via_best_effort": is_best_effort,
                    },
                )

            return (
                leaf_seen_inc,
                no_element_ids_inc,
                empty_after_filtering_inc,
                heading_only_inc,
                best_effort_inc,
            )

        # ── Это section узел — рекурсируем в children ─────────────────────────
        for child in children:
            if not isinstance(child, dict):
                logger.warning(
                    "ClauseTreeBuilder: child is not a dict, skipping",
                    extra={
                        "document_id": str(doc_id),
                        "parent_effective_uid": cls._node_effective_uid(node),
                        "parent_raw_uid": cls._node_raw_uid(node),
                        "parent_title": node_title,
                        "child_type": type(child).__name__,
                    },
                )
                continue

            (
                c_leaf,
                c_no_ids,
                c_empty,
                c_heading_only,
                c_best_effort,
            ) = cls._collect_leaf_chunks(
                doc_id=doc_id,
                node=child,
                element_index=element_index,
                out=out,
                path_titles=current_path,
            )
            leaf_seen_inc += c_leaf
            no_element_ids_inc += c_no_ids
            empty_after_filtering_inc += c_empty
            heading_only_inc += c_heading_only
            best_effort_inc += c_best_effort

        return (
            leaf_seen_inc,
            no_element_ids_inc,
            empty_after_filtering_inc,
            heading_only_inc,
            best_effort_inc,
        )

    # ------------------------------------------------------------------
    # Section-чанки
    # ------------------------------------------------------------------

    @classmethod
    def build_section_chunks(
        cls,
        doc_id: uuid.UUID,
        tree: Dict[str, Any],
        layout: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Построить section-чанки по узлам верхнего уровня (root children)
        на основе clause tree + layout.

        ВАЖНО (Sprint 3):
        - Это legacy-only метод для старых документов.
        - Для современных документов section chunks идут из CHUNKS v2 snapshot.
        - Section chunking разрешён только при открытом quality gate.
        - Если quality_gates.section_chunking_allowed == False, возвращается пустой список.

        Этап 4:
        - Section chunks от best-effort узлов логируются с предупреждением.
        - metadata дополняется новыми полями semantic/citability.
        """

        quality_gates = (tree.get("structure_diagnostics") or {}).get("quality_gates") or {}
        if not quality_gates.get("section_chunking_allowed", True):
            logger.warning(
                "ClauseTreeBuilder: section_chunking_blocked_by_quality_gate",
                extra={
                    "document_id": str(doc_id),
                    "structure_confidence": quality_gates.get("structure_confidence"),
                    "technical_fallback_only": quality_gates.get("technical_fallback_only"),
                },
            )
            return []

        root_children = cls.extract_root_children(tree)

        if not root_children:
            logger.warning(
                "ClauseTreeBuilder: empty root in clause_tree, no section chunks will be built",
                extra={
                    "document_id": str(doc_id),
                    "tree_keys": sorted(tree.keys()),
                    "layout_elements": len(layout.get("elements") or []),
                },
            )
            return []

        logger.info(
            "ClauseTreeBuilder: building section chunks from clause_tree",
            extra={
                "document_id": str(doc_id),
                "tree_root_nodes": len(root_children),
                "layout_elements": len(layout.get("elements") or []),
                "clause_tree_structure_confidence": tree.get("structure_confidence"),
                "clause_tree_degraded": tree.get("degraded"),
            },
        )

        element_index = cls.build_element_index(layout)
        chunks: List[Dict[str, Any]] = []

        for node in root_children:
            if not isinstance(node, dict):
                logger.warning(
                    "ClauseTreeBuilder: root child is not a dict, skipping for section chunks",
                    extra={
                        "document_id": str(doc_id),
                        "child_type": type(node).__name__,
                    },
                )
                continue

            cls._build_single_section_chunk(
                doc_id=doc_id,
                node=node,
                element_index=element_index,
                out=chunks,
            )

        logger.info(
            "ClauseTreeBuilder: section chunks built",
            extra={
                "document_id": str(doc_id),
                "section_count": len(chunks),
                "tree_root_nodes": len(root_children),
                "layout_elements": len(layout.get("elements") or []),
            },
        )

        return chunks

    @classmethod
    def _build_single_section_chunk(
        cls,
        doc_id: uuid.UUID,
        node: Dict[str, Any],
        element_index: Dict[str, Dict[str, Any]],
        out: List[Dict[str, Any]],
    ) -> None:
        """
        Построить один section-чанк для узла верхнего уровня.

        Этап 4: добавляем semantic/citability поля в metadata.
        Best-effort узлы логируются с предупреждением но чанк всё равно строится
        (section level — это нормально для best-effort rootов).
        """

        effective_uid, raw_uid, scope = cls._node_chunk_identity(node)
        node_title = cls._normalize_title(node.get("title"))

        # Читаем новые поля Этапа 4
        etap4 = cls._extract_node_etap4_fields(node)
        is_best_effort = etap4["recovered_via_best_effort"]
        citability_hint = etap4["citability_hint"]

        if is_best_effort:
            logger.warning(
                "ClauseTreeBuilder: building section chunk for best_effort_root node",
                extra={
                    "document_id": str(doc_id),
                    "effective_uid": effective_uid,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": node_title,
                    "fallback_reason": etap4["fallback_reason"],
                    "citability_hint": citability_hint,
                },
            )

        subtree_element_ids: List[str] = node.get("subtree_element_ids") or []

        if not subtree_element_ids:
            logger.warning(
                "ClauseTreeBuilder: section node has no subtree_element_ids",
                extra={
                    "document_id": str(doc_id),
                    "effective_uid": effective_uid,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": node_title,
                },
            )
            return

        element_ids = subtree_element_ids

        missing_elements = 0
        texts: List[str] = []
        pages: List[int] = []
        last_page: int | None = None

        for el_id in element_ids:
            el = element_index.get(el_id)
            if not el:
                missing_elements += 1
                continue

            raw_text = el.get("text") or ""
            text = raw_text.strip()
            page = el.get("page")

            if isinstance(page, int):
                pages.append(page)

            if not text:
                continue

            if last_page is not None and page is not None and page != last_page:
                texts.append("")

            texts.append(text)
            last_page = page

        full_text = "\n\n".join(texts).strip()

        if missing_elements:
            logger.warning(
                "ClauseTreeBuilder: some element_ids from section node not found in layout index",
                extra={
                    "document_id": str(doc_id),
                    "effective_uid": effective_uid,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": node_title,
                    "level": node.get("level"),
                    "element_ids_count": len(element_ids),
                    "missing_elements": missing_elements,
                },
            )

        if not full_text:
            logger.info(
                "ClauseTreeBuilder: root node produced empty section text",
                extra={
                    "document_id": str(doc_id),
                    "effective_uid": effective_uid,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": node_title,
                    "level": node.get("level"),
                    "element_ids_count": len(element_ids),
                    "missing_elements": missing_elements,
                },
            )
            return

        start_page = min(pages) if pages else node.get("start_page")
        end_page = max(pages) if pages else node.get("end_page")

        if not effective_uid:
            logger.warning(
                "ClauseTreeBuilder: section node missing effective_uid, skipping chunk",
                extra={
                    "document_id": str(doc_id),
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": node_title,
                    "level": node.get("level"),
                },
            )
            return

        # Финальный citability_hint для section chunk.
        # Section chunks от нормальных root узлов — "high".
        # От best-effort — "medium" (уже должно быть выставлено hierarchy_builder-ом).
        effective_citability = citability_hint or ("medium" if is_best_effort else "high")

        metadata = {
            "doc_id": str(doc_id),
            "chunk_kind": "section",
            "effective_uid": effective_uid,
            "raw_uid": raw_uid,
            "scope": scope,
            "node_kind": "section",
            "title": node_title,
            "level": node.get("level"),
            "path_titles": [node_title] if node_title else [],
            "section_title": node_title,
            "start_page": start_page,
            "end_page": end_page,
            "element_ids": element_ids,
            # ── Этап 4: новые поля ────────────────────────────────────────────
            "semantic_node_type": etap4["semantic_node_type"],
            "parse_confidence": etap4["parse_confidence"],
            "citability_hint": effective_citability,
            "recovered_via_best_effort": is_best_effort,
            "fallback_reason": etap4["fallback_reason"],
            "is_heading_only_leaf": False,
            "is_structural_fallback": is_best_effort,
        }

        range_end_reason = node.get("range_end_reason")
        if range_end_reason:
            metadata["range_end_reason"] = range_end_reason

        chunk_id = build_section_chunk_id(doc_id, effective_uid)

        out.append(
            {
                "id": chunk_id,
                "text": full_text,
                "metadata": metadata,
            }
        )

        if raw_uid in ("1", "2", "3") or effective_uid in (
            "main_contract::1",
            "main_contract::2",
            "main_contract::3",
        ):
            logger.debug(
                "ClauseTreeBuilder: sample built section chunk",
                extra={
                    "document_id": str(doc_id),
                    "effective_uid": effective_uid,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": node_title,
                    "level": node.get("level"),
                    "text_preview": full_text[:500],
                    "element_ids_count": len(element_ids),
                    "start_page": start_page,
                    "end_page": end_page,
                    "citability_hint": effective_citability,
                    "recovered_via_best_effort": is_best_effort,
                },
            )
            

