# src/engine/content/clause_tree_builder.py

"""
Clause tree → клауза-чанки.

Здесь:
- вся логика обхода clause tree;
- сборка текста клаузы по element_ids из layout;
- универсальные хелперы для:
  * root-узлов,
  * индекса элементов layout.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List


class ClauseTreeBuilder:
    """
    Класс-хелпер для работы с clause tree.

    Для непрофессионального программиста:
    - Этот класс не знает про БД и MinIO.
    - Ему дают уже загруженный JSON clause tree и JSON layout,
      и он возвращает список "чистых" чанков по листовым клаузам.
    """

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

        Это ускоряет сбор текста клаузы: вместо линейного поиска по всему
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
        for el in elements:
            el_id = el.get("element_id")
            if el_id:
                index[el_id] = el
        return index

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
            "text": "<полный текст клаузы>",
            "metadata": {...}
          },
          ...
        ]
        """
        root_children = cls.extract_root_children(tree)
        if not root_children:
            return []

        element_index = cls.build_element_index(layout)

        chunks: List[Dict[str, Any]] = []
        for child in root_children:
            cls._collect_leaf_chunks(
                doc_id=doc_id,
                node=child,
                element_index=element_index,
                out=chunks,
                path_titles=[],
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
        - берём все её element_ids,
        - находим соответствующие элементы в layout,
        - склеиваем их текст в одном чанке.
        """
        # path_titles — это "хлебные крошки" из заголовков от корня до текущего узла.
        current_path: List[str] = list(path_titles or [])
        node_title = node.get("title")
        if node_title:
            current_path.append(node_title)

        children = node.get("children") or []

        if not children:
            clause_uid = node.get("clause_uid")
            element_ids: List[str] = node.get("element_ids") or []

            # Собираем текст клаузы из элементов layout.
            texts: List[str] = []
            pages: List[int] = []
            last_page: int | None = None

            for el_id in element_ids:
                el = element_index.get(el_id)
                if not el:
                    continue

                raw_text = el.get("text") or ""
                text = raw_text.strip()
                if not text:
                    continue

                page = el.get("page")
                if isinstance(page, int):
                    pages.append(page)

                # Если элемент на новой странице — добавляем пустую строку
                # как явный разделитель, чтобы модели видели разрыв страниц.
                if last_page is not None and page is not None and page != last_page:
                    texts.append("")

                texts.append(text)
                last_page = page

            # Склеиваем блоки через двойной перевод строки, чтобы сохранить структуру.
            # Пустые строки, добавленные при смене страницы, превратятся в лишние
            # пустые абзацы, что удобно для LLM.
            full_text = "\n\n".join(texts).strip()

            if not full_text:
                # Для непрофессионального программиста:
                # - если после фильтрации / санитизации в этой листовой клаузе
                #   не осталось ни одного непустого текстового элемента,
                #   пустой чанк создавать не нужно.
                return

            start_page = min(pages) if pages else node.get("start_page")
            end_page = max(pages) if pages else node.get("end_page")

            metadata = {
                "doc_id": str(doc_id),
                "clause_uid": clause_uid,
                "title": node.get("title"),
                "level": node.get("level"),
                "path_titles": current_path,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
            }

            out.append(
                {
                    "id": f"{doc_id}:{clause_uid}",
                    "text": full_text,
                    "metadata": metadata,
                }
            )
            return

        # Если у узла есть дети — спускаемся ниже по дереву.
        for child in children:
            cls._collect_leaf_chunks(
                doc_id=doc_id,
                node=child,
                element_index=element_index,
                out=out,
                path_titles=current_path,
            )

            