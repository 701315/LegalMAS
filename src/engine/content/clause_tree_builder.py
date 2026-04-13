# src/engine/content/clause_tree_builder.py

"""
Clause tree → клауза- и section-чанки.


Здесь:
- вся логика обхода clause tree;
- сборка текста клаузы по element_ids из layout;
- сборка текста раздела по subtree_element_ids из layout;
- универсальные хелперы для:
  * root-узлов,
  * индекса элементов layout.
"""


from __future__ import annotations


import uuid
from typing import Any, Dict, List


from core.logging import get_logger


logger = get_logger(__name__)



class ClauseTreeBuilder:
    """
    Класс-хелпер для работы с clause tree.


    Для непрофессионального программиста:
    - Этот класс не знает про БД и MinIO.
    - Ему дают уже загруженный JSON clause tree и JSON layout,
      и он возвращает список "чистых" чанков по листовым клаузам
      и (при необходимости) по разделам верхнего уровня.
    """

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
        Построить индекс element_id → элемент layout'а.

        Это ускоряет сбор текста: вместо линейного поиска по всему
        списку elements мы обращаемся к нужному элементу напрямую по ключу.

        Формат элемента (см. build_text_layout_raw):
          {
            "element_id": str,
            "type": "heading" | "text" | "listitem",
            "text": str,
            "page": int,
            ...
          }
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
    # Leaf‑чанки (только тело клаузы по own_element_ids)
    # ------------------------------------------------------------------

    @classmethod
    def build_leaf_chunks(
        cls,
        doc_id: uuid.UUID,
        tree: Dict[str, Any],
        layout: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Построить клауза-чанки (листовые узлы) на основе clause tree + layout.

        Возвращает:
        [
          {
            "id": "<doc_id>:<clause_uid>",
            "text": "<тело клаузы без заголовка>",
            "metadata": {...}
          },
          ...
        ]
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
            return []

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

            cls._collect_leaf_chunks(
                doc_id=doc_id,
                node=child,
                element_index=element_index,
                out=chunks,
                path_titles=[],
            )

        leaf_count = len(chunks)

        uid_with_none = sum(
            1 for ch in chunks if (ch.get("metadata") or {}).get("clause_uid") is None
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
                "chunks_without_clause_uid": uid_with_none,
                "chunks_with_empty_text": empty_text_chunks,
            },
        )

        sample_clause_uids = [
            str((ch.get("metadata") or {}).get("clause_uid"))
            for ch in chunks[:10]
            if (ch.get("metadata") or {}).get("clause_uid") is not None
        ]
        if sample_clause_uids:
            logger.debug(
                "ClauseTreeBuilder: sample leaf clause_uids",
                extra={
                    "document_id": str(doc_id),
                    "sample_clause_uids": sample_clause_uids,
                },
            )

        return chunks

    @classmethod
    def _collect_leaf_chunks(
        cls,
        doc_id: uuid.UUID,
        node: Dict[str, Any],
        element_index: Dict[str, Dict[str, Any]],
        out: List[Dict[str, Any]],
        path_titles: List[str] | None = None,
    ) -> None:
        """
        Рекурсивно обойти дерево и добавить чанки для всех листовых клауз
        (то есть узлов без children).

        Для каждой листовой клаузы:
        - берём все её own_element_ids (или element_ids как fallback),
        - исключаем из тела заголовочные элементы layout (type == "heading"),
        - склеиваем оставшийся текст в одном чанке.
        """

        def _normalize_uid(value: Any) -> str | None:
            if value is None:
                return None
            uid = str(value).strip()
            return uid or None

        def _normalize_title(value: Any) -> str | None:
            if value is None:
                return None
            title = str(value).strip()
            return title or None

        def _extract_section_title(node_level: Any, path: List[str]) -> str | None:
            """
            Аккуратно достать заголовок раздела верхнего уровня для клаузы.

            Пока придерживаемся простого правила:
            - считаем, что path[0] — заголовок корневого раздела (level==1);
            - если путь пустой, section_title = None.
            """
            if not path:
                return None
            return path[0]

        current_path: List[str] = list(path_titles or [])
        node_title_raw = node.get("title")
        node_title = _normalize_title(node_title_raw)
        if node_title:
            current_path.append(node_title)

        children = node.get("children") or []

        if not children:
            clause_uid = _normalize_uid(node.get("clause_uid"))

            own_element_ids = node.get("own_element_ids") or []
            legacy_element_ids = node.get("element_ids") or []

            # Новый контракт: берём только own_element_ids; element_ids — мягкий fallback.
            element_ids: List[str] = own_element_ids or legacy_element_ids or []

            if not element_ids:
                logger.warning(
                    "ClauseTreeBuilder: leaf node has no element_ids",
                    extra={
                        "document_id": str(doc_id),
                        "clause_uid": clause_uid,
                        "title": node_title,
                        "level": node.get("level"),
                        "has_own_element_ids": bool(own_element_ids),
                        "has_legacy_element_ids": bool(legacy_element_ids),
                    },
                )
                return

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

                # Для leaf‑клаузы heading‑элементы считаем частью заголовка и выкидываем.
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
                        "clause_uid": clause_uid,
                        "title": node_title,
                        "level": node.get("level"),
                        "element_ids_count": len(element_ids),
                        "missing_elements": missing_elements,
                        "heading_elements": heading_elements,
                    },
                )

            if not full_text:
                logger.info(
                    "ClauseTreeBuilder: leaf node produced empty text after filtering",
                    extra={
                        "document_id": str(doc_id),
                        "clause_uid": clause_uid,
                        "title": node_title,
                        "level": node.get("level"),
                        "element_ids_count": len(element_ids),
                        "missing_elements": missing_elements,
                        "heading_elements": heading_elements,
                    },
                )
                return

            start_page = min(pages) if pages else node.get("start_page")
            end_page = max(pages) if pages else node.get("end_page")

            section_title = _extract_section_title(node.get("level"), current_path)

            metadata = {
                "doc_id": str(doc_id),
                "clause_uid": clause_uid,
                "title": node_title,
                "level": node.get("level"),
                "path_titles": current_path,
                "section_title": section_title,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
            }

            out.append(
                {
                    "id": f"{doc_id}:{clause_uid or 'full'}",
                    "text": full_text,
                    "metadata": metadata,
                }
            )

            if clause_uid in ("1", "1.1", "1.2"):
                logger.debug(
                    "ClauseTreeBuilder: sample built leaf chunk",
                    extra={
                        "document_id": str(doc_id),
                        "clause_uid": clause_uid,
                        "title": node_title,
                        "level": node.get("level"),
                        "path_depth": len(current_path),
                        "text_preview": full_text[:500],
                        "element_ids_count": len(element_ids),
                        "start_page": start_page,
                        "end_page": end_page,
                    },
                )

            return

        for child in children:
            if not isinstance(child, dict):
                logger.warning(
                    "ClauseTreeBuilder: child is not a dict, skipping",
                    extra={
                        "document_id": str(doc_id),
                        "parent_clause_uid": node.get("clause_uid"),
                        "parent_title": node_title,
                        "child_type": type(child).__name__,
                    },
                )
                continue

            cls._collect_leaf_chunks(
                doc_id=doc_id,
                node=child,
                element_index=element_index,
                out=out,
                path_titles=current_path,
            )

    # ------------------------------------------------------------------
    # Section‑чанки (разделы верхнего уровня по subtree_element_ids)
    # ------------------------------------------------------------------

    @classmethod
    def build_section_chunks(
        cls,
        doc_id: uuid.UUID,
        tree: Dict[str, Any],
        layout: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Построить section‑чанки по узлам верхнего уровня (root children)
        на основе clause tree + layout.

        Новый контракт:
        - один section‑чанк на каждый узел верхнего уровня (root‑child);
        - text = материализованный текст всего поддерева раздела
          (subtree_element_ids, включая заголовки);
        - element_ids = subtree_element_ids (fallback на own_element_ids / element_ids);
        - clause_uid = uid корневого раздела (например, "3");
        - title / section_title = заголовок раздела.
        """
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
        Построить один section‑чанк для узла верхнего уровня.

        В отличие от leaf‑клаузы:
        - используем subtree_element_ids (fallback на own_element_ids / element_ids);
        - НЕ выкидываем heading‑элементы (заголовок раздела должен быть в тексте);
        - text = весь текст поддерева.
        """

        def _normalize_uid(value: Any) -> str | None:
            if value is None:
                return None
            uid = str(value).strip()
            return uid or None

        def _normalize_title(value: Any) -> str | None:
            if value is None:
                return None
            title = str(value).strip()
            return title or None

        clause_uid = _normalize_uid(node.get("clause_uid"))
        node_title = _normalize_title(node.get("title"))

        subtree_element_ids = node.get("subtree_element_ids") or []
        own_element_ids = node.get("own_element_ids") or []
        legacy_element_ids = node.get("element_ids") or []

        # Новый контракт:
        # - приоритет subtree_element_ids (весь раздел),
        # - fallback own_element_ids,
        # - потом legacy element_ids.
        element_ids: List[str] = (
            list(subtree_element_ids)
            or list(own_element_ids)
            or list(legacy_element_ids)
        )

        if not element_ids:
            logger.warning(
                "ClauseTreeBuilder: root node has no subtree/own element_ids for section chunk",
                extra={
                    "document_id": str(doc_id),
                    "clause_uid": clause_uid,
                    "title": node_title,
                    "level": node.get("level"),
                    "has_subtree_element_ids": bool(subtree_element_ids),
                    "has_own_element_ids": bool(own_element_ids),
                    "has_legacy_element_ids": bool(legacy_element_ids),
                },
            )
            return

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

            el_type = (el.get("type") or "").strip().lower()
            page = el.get("page")

            if isinstance(page, int):
                pages.append(page)

            # Для section‑чанка заголовки включаем в текст.
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
                    "clause_uid": clause_uid,
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
                    "clause_uid": clause_uid,
                    "title": node_title,
                    "level": node.get("level"),
                    "element_ids_count": len(element_ids),
                    "missing_elements": missing_elements,
                },
            )
            return

        start_page = min(pages) if pages else node.get("start_page")
        end_page = max(pages) if pages else node.get("end_page")

        metadata = {
            "doc_id": str(doc_id),
            "clause_uid": clause_uid,
            "title": node_title,
            "level": node.get("level"),
            "path_titles": [node_title] if node_title else [],
            "section_title": node_title,
            "start_page": start_page,
            "end_page": end_page,
            "element_ids": element_ids,
        }

        out.append(
            {
                "id": f"{doc_id}:{clause_uid or 'section'}",
                "text": full_text,
                "metadata": metadata,
            }
        )

        if clause_uid in ("1", "2", "3"):
            logger.debug(
                "ClauseTreeBuilder: sample built section chunk",
                extra={
                    "document_id": str(doc_id),
                    "clause_uid": clause_uid,
                    "title": node_title,
                    "level": node.get("level"),
                    "text_preview": full_text[:500],
                    "element_ids_count": len(element_ids),
                    "start_page": start_page,
                    "end_page": end_page,
                },
            )


