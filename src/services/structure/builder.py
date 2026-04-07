# src/services/structure/builder.py

"""
Structure Builder: из text_layout_raw строит дерево клауз (clause tree).

Берёт плоский список elements (text_layout_raw/layout_primary) и пытается
выделить заголовки пунктов/подпунктов, привязать к ним элементы и собрать
иерархию секций для документа.

Возможности:
- поддержка форматов заголовков:
  * числовые: 1., 1.1, 1.1.1, 1.1 (без точки после номера),
  * римские: I, II, III, IV (уровень 1),
  * буквенные: A., B., a), б) (уровень 2);
- подавление оглавления (TOC): обнаруживает и вырезает блок "Содержание"/
  "Table of contents" на первых страницах, чтобы его строки не попадали
  в дерево как реальные разделы;
- поиск перекрёстных ссылок: "см. п. 3.2", "Art. 5" и т.п. с привязкой
  source_clause_uid → target_clause_uid;
- degraded‑режим: если coverage заголовков по элементам < STRUCTURE_MIN_CLAUSE_COVERAGE,
  вместо дерева создаёт плоские Chunk‑узлы фиксированного размера
  (STRUCTURE_DEGRADED_CHUNK_TOKENS) с пометкой degraded=True.

Главная точка входа:
- StructureBuilder.build(document_id, elements) →
  ClauseTree (root: список ClauseNode, references_index: список CrossReference,
  structure_confidence: LOW/MEDIUM/HIGH, degraded: bool), который сохраняется
  как clause_tree_ref и используется API/viewer для показа структуры документа.
"""

import re

from core.config import settings
from core.logging import get_logger
from services.structure.models import ClauseNode, ClauseTree, CrossReference

logger = get_logger(__name__)

# Numeric: "1.", "1.1.", "1.1.1." — с точкой после номера (строгий)
_NUMERIC_FULL = re.compile(r"^(\d+(?:\.\d+)*)[\.\)]\s+(.{1,120})")

# Numeric без точки: "1.1 Title", "2.3.1 Title" — только для вложенных (есть хотя бы одна точка)
# Требуем заглавную букву или «» после пробела — защита от числовых данных
_NUMERIC_NO_DOT = re.compile(
    r"^(\d+(?:\.\d+)+)\s{1,3}([A-ZА-ЯЁ\«\"].{1,120})"
)

_ROMAN_L1 = re.compile(
    r"^(I{1,3}|IV|V?I{0,3}|IX|X{0,3}(?:IX|IV|V?I{0,3}))[\.\)]\s+(.{1,120})",
    re.IGNORECASE,
)
_ALPHA = re.compile(
    r"^([A-Fa-f\u0430-\u0436])[\.)\s]\s+(.{1,120})",
)
_CROSS_REF = re.compile(
    r"(?:см\.\s*п\.?|ст\.\s*|пункт\s+|п\.?\s*)(\d+(?:\.\d+)*)|"
    r"(?:Art(?:icle)?\.?\s*)(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)

# Маркеры начала блока оглавления (любой регистр)
_TOC_MARKERS = frozenset([
    "table of contents",
    "contents",
    "содержание",
    "оглавление",
])

# Максимальное число страниц, на которых может располагаться оглавление.
# Оглавление практически никогда не занимает больше 5 страниц.
_TOC_MAX_PAGES = 5


def _level_from_uid(uid: str) -> int:
    return uid.count(".") + 1


def _parse_element_as_heading(text: str) -> tuple | None:
    stripped = text.strip()
    # Порядок важен: строгий numeric (с точкой) проверяем первым,
    # затем numeric без точки (только вложенные), затем roman и alpha.
    for pattern in (_NUMERIC_FULL, _NUMERIC_NO_DOT, _ROMAN_L1, _ALPHA):
        m = pattern.match(stripped)
        if m:
            uid, title = m.group(1), m.group(2).strip()
            return uid, title[: settings.STRUCTURE_MAX_CLAUSE_TITLE_LEN]

    # Fallback для случаев, когда после language‑filter заголовок чуть "обрезался",
    # и не попал под строгие паттерны, но очевидно начинается с числового uid.
    # Примеры: "1 Definitions", "2.3 Other terms" без точки и с коротким title.
    m_simple = re.match(r"^(\d+(?:\.\d+)*)(?:\s+(.+))?$", stripped)
    if m_simple:
        uid = m_simple.group(1)
        title = (m_simple.group(2) or "").strip()
        if not title:
            # Если title совсем пустой, лучше не считать это заголовком.
            return None
        return uid, title[: settings.STRUCTURE_MAX_CLAUSE_TITLE_LEN]

    return None


class StructureBuilder:
    """Builds a clause tree from text_layout_raw elements."""

    def build(
        self,
        document_id: str,
        elements: list[dict],
    ) -> ClauseTree:

        # Попробуем понять, был ли layout помечен как degraded на стадии language filter.
        # Metadata обычно лежит на уровне layout, но до нас она доходит только
        # через элементы, поэтому смотрим на первый попадшийся language_filter.
        layout_degraded = False
        layout_degraded_reason: str | None = None
        for el in elements:
            lf = (el.get("language_filter") or {}) if isinstance(el, dict) else {}
            degraded_flag = lf.get("degraded")
            if degraded_flag is not None:
                layout_degraded = bool(degraded_flag)
                layout_degraded_reason = lf.get("degraded_reason")
                break


        # Определяем конец блока оглавления и работаем только с телом документа.
        # Это защищает от ситуации, когда строки оглавления ("1. Определения",
        # "2. Предмет договора") парсятся как реальные заголовки и создают
        # пустые чанки вместо содержательных.
        toc_end_idx = self._find_toc_end(elements)
        body_elements = elements[toc_end_idx:]

        if not body_elements:
            # На случай если весь документ был ошибочно принят за оглавление
            body_elements = elements
            toc_end_idx = 0

        headings: list[tuple] = []
        for i, el in enumerate(body_elements):
            text = el.get("text", "")
            parsed = _parse_element_as_heading(text)
            if parsed:
                uid, title = parsed
                headings.append((i, uid, title, el.get("page", 1)))

        if not headings:
            return self._degraded_tree(document_id, body_elements)

        coverage = self._calculate_coverage(headings, body_elements)
        confidence, degraded = self._confidence_and_mode(coverage)

        # Если уже на стадии language filter layout был помечен как degraded,
        # а coverage здесь не выглядит идеально, усиливаем решение в сторону degraded.
        if layout_degraded and not degraded and coverage < 0.8:
            logger.info(
                "Structure: forcing degraded mode due to degraded primary layout",
                document_id=document_id,
                coverage=round(coverage, 3),
                layout_degraded_reason=layout_degraded_reason,
            )
            degraded = True
            confidence = "LOW"

        if degraded:
            logger.info(
                "Structure degraded: low coverage",
                document_id=document_id,
                coverage=round(coverage, 3),
                toc_skipped_elements=toc_end_idx,
            )
            return self._degraded_tree(document_id, body_elements, coverage)

        root_nodes, references = self._build_tree(headings, body_elements)
        return ClauseTree(
            document_id=document_id,
            root=root_nodes,
            references_index=references,
            structure_confidence=confidence,
            degraded=False,
        )

    def _find_toc_end(self, elements: list[dict]) -> int:
        """
        Найти индекс первого элемента ПОСЛЕ блока оглавления.

        Стратегия:
        1) Ищем явный маркер оглавления ("TABLE OF CONTENTS", "СОДЕРЖАНИЕ" и т.п.).
           Если нашли — ищем конец блока оглавления после него.
        2) Если явного маркера нет — ищем кластер: несколько подряд идущих элементов,
           все проходящих как заголовки с последовательными uid верхнего уровня
           ("1", "2", "3"...) без вложенных подразделов между ними.
           Такой кластер — признак оглавления.
        3) Если ничего не нашли — возвращаем 0 (оглавления нет, обрабатываем всё).

        Ограничение: ищем только в первых _TOC_MAX_PAGES страницах.
        """
        if not elements:
            return 0

        # Определяем страницу-порог: не смотрим дальше _TOC_MAX_PAGES
        first_page = elements[0].get("page", 1)
        page_threshold = first_page + _TOC_MAX_PAGES

        # Шаг 1: поиск явного маркера
        toc_start_idx: int | None = None
        for i, el in enumerate(elements):
            if el.get("page", 1) > page_threshold:
                break
            text_lower = (el.get("text") or "").strip().lower()
            if text_lower in _TOC_MARKERS:
                toc_start_idx = i
                break

        if toc_start_idx is not None:
            # Нашли маркер — ищем конец блока оглавления.
            # Конец оглавления = первый элемент после маркера, который:
            # а) находится на новой странице относительно последней строки оглавления
            #    И при этом является заголовком (начало реального раздела),
            # б) ИЛИ не является заголовком и при этом достаточно длинный (>80 символов,
            #    явно не строка оглавления).
            # Дополнительное ограничение: не выходим за page_threshold.
            toc_last_page = elements[toc_start_idx].get("page", 1)

            for i in range(toc_start_idx + 1, len(elements)):
                el = elements[i]
                el_page = el.get("page", 1)

                if el_page > page_threshold:
                    # Вышли за лимит страниц — считаем что оглавление закончилось
                    return i

                text = (el.get("text") or "").strip()
                parsed = _parse_element_as_heading(text)

                # Если мы на новой странице относительно последней строки оглавления
                # и встретили заголовок — это начало реального тела документа
                if el_page > toc_last_page and parsed:
                    return i

                # Длинный не-заголовочный текст — явно тело документа
                if not parsed and len(text) > 80:
                    return i

                # Продолжаем сканировать оглавление
                toc_last_page = el_page

            # Прошли все элементы в пределах порога — оглавление не закончилось,
            # возвращаем индекс первого элемента за порогом страниц
            return toc_start_idx + 1  # минимальная защита

        # Шаг 2: поиск кластера без явного маркера.
        # Кластер оглавления: ≥3 подряд идущих элементов, все являются заголовками
        # верхнего уровня (uid без точек: "1", "2", "3"...), строго последовательные.
        cluster_start: int | None = None
        cluster_uids: list[str] = []
        cluster_last_idx: int = 0

        for i, el in enumerate(elements):
            if el.get("page", 1) > page_threshold:
                break
            text = (el.get("text") or "").strip()
            parsed = _parse_element_as_heading(text)

            if parsed:
                uid, _ = parsed
                # Только верхний уровень (без точки в uid) для детектирования кластера
                if "." not in uid:
                    if cluster_start is None:
                        cluster_start = i
                        cluster_uids = [uid]
                    else:
                        cluster_uids.append(uid)
                    cluster_last_idx = i
                    continue

            # Не-заголовочный элемент прерывает кластер
            if cluster_start is not None and len(cluster_uids) >= 3:
                # Нашли кластер из ≥3 верхнеуровневых заголовков подряд — это оглавление.
                # Возвращаем индекс следующего после кластера элемента.
                return cluster_last_idx + 1

            # Сбрасываем кластер
            cluster_start = None
            cluster_uids = []

        # Проверяем незакрытый кластер в конце диапазона
        if cluster_start is not None and len(cluster_uids) >= 3:
            return cluster_last_idx + 1

        return 0  # оглавление не обнаружено

    def _build_tree(
        self,
        headings: list,
        elements: list,
    ) -> tuple[list[ClauseNode], list[CrossReference]]:
        nodes: dict[str, ClauseNode] = {}
        root: list[ClauseNode] = []

        for h_idx, (elem_i, uid, title, page) in enumerate(headings):
            next_elem_i = (
                headings[h_idx + 1][0] if h_idx + 1 < len(headings) else len(elements)
            )
            element_ids = [
                elements[j].get("element_id", f"e{j:04d}")
                for j in range(elem_i, next_elem_i)
            ]
            end_page = (
                elements[next_elem_i - 1].get("page", page)
                if next_elem_i > elem_i
                else page
            )

            node = ClauseNode(
                clause_uid=uid,
                title=title,
                level=_level_from_uid(uid),
                element_ids=element_ids,
                start_page=page,
                end_page=end_page,
            )

            # Если uid уже существует в nodes — это дубль (например, два "1" в документе
            # после некорректного парсинга). Сохраняем только первый встреченный,
            # последующие дубли добавляем в root как отдельные узлы без регистрации
            # в nodes, чтобы они не ломали привязку дочерних узлов.
            if uid not in nodes:
                nodes[uid] = node

            parent_uid = self._find_parent_uid(uid, nodes)
            if parent_uid and parent_uid in nodes:
                nodes[parent_uid].children.append(node)
            else:
                root.append(node)

        references = self._extract_references(elements, nodes)
        return root, references

    # --- Остальные методы без изменений ---

    def _find_parent_uid(self, uid: str, nodes: dict) -> str | None:
        parts = uid.rsplit(".", 1)
        if len(parts) > 1:
            parent = parts[0]
            return parent if parent in nodes else None
        return None

    def _calculate_coverage(self, headings: list, elements: list) -> float:
        if not elements:
            return 0.0
        assigned = set()
        for h_idx, (elem_i, uid, title, page) in enumerate(headings):
            next_elem_i = (
                headings[h_idx + 1][0] if h_idx + 1 < len(headings) else len(elements)
            )
            for j in range(elem_i, next_elem_i):
                assigned.add(j)
        return len(assigned) / len(elements)

    def _confidence_and_mode(self, coverage: float) -> tuple[str, bool]:
        threshold = settings.STRUCTURE_MIN_CLAUSE_COVERAGE
        if coverage < threshold:
            return "LOW", True
        elif coverage < 0.80:
            return "MEDIUM", False
        return "HIGH", False

    def _extract_references(
        self, elements: list, nodes: dict
    ) -> list[CrossReference]:
        references: list[CrossReference] = []
        uid_set = set(nodes.keys())
        for el in elements:
            text = el.get("text", "")
            el_id = el.get("element_id", "")
            source_uid = self._element_to_clause(el_id, nodes)
            if not source_uid:
                continue
            for match in _CROSS_REF.finditer(text):
                target = match.group(1) or match.group(2)
                if target and target in uid_set and target != source_uid:
                    references.append(
                        CrossReference(
                            source_clause_uid=source_uid,
                            target_clause_uid=target,
                            reference_text=match.group(),
                        )
                    )
        return references

    def _element_to_clause(self, element_id: str, nodes: dict) -> str | None:
        for uid, node in nodes.items():
            if element_id in node.element_ids:
                return uid
        return None

    def _degraded_tree(
        self,
        document_id: str,
        elements: list,
        coverage: float = 0.0,
    ) -> ClauseTree:
        chunks: list[ClauseNode] = []
        current_ids: list[str] = []
        current_tokens = 0
        chunk_idx = 1
        max_tokens = settings.STRUCTURE_DEGRADED_CHUNK_TOKENS
        current_start_page: int | None = None
        last_page: int = elements[0].get("page", 1) if elements else 1

        for el in elements:
            text = el.get("text", "")
            tokens = len(text.split())
            page = el.get("page", 1)

            if current_tokens + tokens > max_tokens and current_ids:
                start_page = current_start_page or last_page
                end_page = last_page
                chunks.append(
                    ClauseNode(
                        clause_uid=str(chunk_idx),
                        title=f"Chunk {chunk_idx}",
                        level=1,
                        element_ids=current_ids,
                        start_page=start_page,
                        end_page=end_page,
                    )
                )
                chunk_idx += 1
                current_ids = []
                current_tokens = 0
                current_start_page = None

            current_ids.append(el.get("element_id", f"e{chunk_idx:04d}"))
            current_tokens += tokens
            if current_start_page is None:
                current_start_page = page
            last_page = page

        if current_ids:
            chunks.append(
                ClauseNode(
                    clause_uid=str(chunk_idx),
                    title=f"Chunk {chunk_idx}",
                    level=1,
                    element_ids=current_ids,
                    start_page=current_start_page or last_page,
                    end_page=last_page,
                )
            )

        return ClauseTree(
            document_id=document_id,
            root=chunks,
            references_index=[],
            structure_confidence="LOW",
            degraded=True,
        )
    
    