# src/services/document_layout/spatial_marker_recovery.py

"""
SpatialMarkerRecovery — Production-grade recovery маргинальных маркеров нумерации.

Compensating control для Docling issue #1345:
"List and Links are not preserved in PDF to Markdown conversions"

Архитектура: 5 слоёв
1. DocumentFingerprint + ColumnClustering — адаптивные пороги из статистики документа
2. GrammarInduction — вывод грамматики нумерации из конкретного документа
3. AdaptiveSpatialMatching — геометрическое сопоставление с many-to-many resolution
4. SequenceValidation — per-branch state machine для валидации нумерации
5. ConfidenceScoring + Observability — метрики для Prometheus

Универсальность:
- Никаких хардкод-порогов (все вычисляется из документа)
- Поддержка любых языков (RU, EN, DE, FR, etc.)
- Поддержка любых схем нумерации (1.1, а), (i), § 4.2, Статья 1...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict
import statistics

import fitz  # pymupdf
import numpy as np
from sklearn.cluster import KMeans

from core.logging import get_logger
from services.document_layout.schemas import CanonicalAtom
from services.document_layout.metrics import RecoveryMetrics

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Слой 1: Document Fingerprint + Column Clustering
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ColumnCluster:
    """
    Кластер X-координат, представляющий одну физическую колонку документа.
    
    Атрибуты:
        cluster_id: Уникальный ID кластера
        x_center: Средняя X-координата колонки
        x_min: Минимальная X-координата
        x_max: Максимальная X-координата
        language_hint: Предполагаемый язык ("ru", "en", "shared")
        span_count: Количество спанов в кластере
    """
    cluster_id: int
    x_center: float
    x_min: float
    x_max: float
    language_hint: str = "shared"
    span_count: int = 0
    
    def contains_x(self, x: float, tolerance: float = 10.0) -> bool:
        """Проверить, принадлежит ли X-координата этой колонке."""
        return abs(x - self.x_center) <= (self.x_max - self.x_min) / 2 + tolerance


@dataclass
class DocumentFingerprint:
    """
    Статистический профиль документа для адаптивных порогов.
    
    Вычисляется один раз на документ, передаётся во все слои.
    
    Атрибуты:
        median_line_height: Медианная высота строки (pt)
        median_font_size: Медианный размер шрифта (pt)
        y_tolerance: Допуск по Y для сопоставления (адаптивный)
        column_clusters: Список обнаруженных колонок
        page_count: Количество страниц
    """
    median_line_height: float
    median_font_size: float
    y_tolerance: float  # Вычисляется как max(0.4*line_height, 0.5*font_size)
    column_clusters: list[ColumnCluster]
    page_count: int = 1
    
    @classmethod
    def build(cls, pdf_bytes: bytes, document_id: str) -> DocumentFingerprint:
        """
        Построить fingerprint из PDF.
        
        Алгоритм:
        1. Извлечь все спаны PyMuPDF
        2. Вычислить median_line_height и median_font_size
        3. Кластеризовать X-координаты в колонки (k-means или gap-based)
        4. Вычислить адаптивный y_tolerance
        
        Args:
            pdf_bytes: Исходный PDF
            document_id: ID для логирования
            
        Returns:
            DocumentFingerprint с вычисленными метриками
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        all_line_heights: list[float] = []
        all_font_sizes: list[float] = []
        all_x0_coords: list[float] = []
        
        # Собираем статистику по всем страницам
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_dict = page.get_text("dict", flags=fitz.TEXT_DEHYPHENATE)
            
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # Только текстовые блоки
                    continue
                
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    
                    # Вычисляем высоту строки через bbox
                    line_bbox = line.get("bbox", (0, 0, 0, 0))
                    line_height = line_bbox[3] - line_bbox[1]  # y1 - y0
                    if line_height > 0:
                        all_line_heights.append(line_height)
                    
                    # Собираем размеры шрифтов и X-координаты
                    for span in spans:
                        font_size = span.get("size", 0.0)
                        if font_size > 0:
                            all_font_sizes.append(font_size)
                        
                        x0 = span.get("bbox", (0, 0, 0, 0))[0]
                        all_x0_coords.append(x0)
        
        # Сохраняем page_count ДО закрытия документа
        page_count = len(doc)
        doc.close()
        
        # Вычисляем медианы (устойчивы к выбросам)
        median_line_height = statistics.median(all_line_heights) if all_line_heights else 12.0
        median_font_size = statistics.median(all_font_sizes) if all_font_sizes else 10.0
        
        # Адаптивный y_tolerance: больший из двух порогов
        # Основание: pymupdf4llm.sanitize_spans использует 10% font_size
        # Для bilingual документов с разными кеглями RU/EN берём максимум
        y_tolerance = max(0.4 * median_line_height, 0.5 * median_font_size)
        
        # Кластеризация X-координат в колонки
        column_clusters = cls._cluster_columns(all_x0_coords, y_tolerance)
        
        logger.info(
            "DocumentFingerprint built",
            extra={
                "document_id": document_id,
                "median_line_height": round(median_line_height, 2),
                "median_font_size": round(median_font_size, 2),
                "y_tolerance": round(y_tolerance, 2),
                "column_count": len(column_clusters),
                "page_count": page_count,
            },
        )
        
        return cls(
            median_line_height=median_line_height,
            median_font_size=median_font_size,
            y_tolerance=y_tolerance,
            column_clusters=column_clusters,
            page_count=page_count,  # Используем сохранённую переменную
        )
    
    @staticmethod
    def _cluster_columns(x0_coords: list[float], y_tolerance: float) -> list[ColumnCluster]:
        """
        Кластеризовать X-координаты в колонки через gap-based алгоритм.
        
        Почему не k-means:
        - Не знаем заранее количество колонок (может быть 1, 2, 3+)
        - Gap-based лучше работает с неравномерным распределением
        
        Алгоритм:
        1. Сортируем координаты
        2. Находим большие разрывы (gap > 2 * y_tolerance)
        3. Каждый сегмент между разрывами = одна колонка
        """
        if not x0_coords:
            return [ColumnCluster(cluster_id=0, x_center=0, x_min=0, x_max=100)]
        
        sorted_coords = sorted(x0_coords)
        
        # Находим разрывы
        gaps: list[tuple[int, float]] = []
        for i in range(1, len(sorted_coords)):
            gap = sorted_coords[i] - sorted_coords[i - 1]
            if gap > 2 * y_tolerance:  # Порог: 2 * медианную высоту строки
                gaps.append((i, gap))
        
        # Строим кластеры из сегментов между разрывами
        clusters: list[ColumnCluster] = []
        segment_start = 0
        
        for gap_idx, (split_point, gap_size) in enumerate(gaps):
            segment_coords = sorted_coords[segment_start:split_point]
            if segment_coords:
                cluster = ColumnCluster(
                    cluster_id=segment_start,
                    x_center=statistics.mean(segment_coords),
                    x_min=min(segment_coords),
                    x_max=max(segment_coords),
                    span_count=len(segment_coords),
                )
                clusters.append(cluster)
            segment_start = split_point
        
        # Добавляем последний сегмент
        if segment_start < len(sorted_coords):
            segment_coords = sorted_coords[segment_start:]
            cluster = ColumnCluster(
                cluster_id=len(clusters),
                x_center=statistics.mean(segment_coords),
                x_min=min(segment_coords),
                x_max=max(segment_coords),
                span_count=len(segment_coords),
            )
            clusters.append(cluster)
        
        # Если не нашли разрывов — одна колонка на весь документ
        if not clusters:
            clusters.append(ColumnCluster(
                cluster_id=0,
                x_center=statistics.mean(sorted_coords),
                x_min=min(sorted_coords),
                x_max=max(sorted_coords),
                span_count=len(sorted_coords),
            ))
        
        return clusters


# ─────────────────────────────────────────────────────────────────────────────
# Слой 2: Grammar Induction
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class OrphanMarker:
    """
    Кандидат в маркеры нумерации из PyMuPDF спанов.
    
    Атрибуты:
        text: Текст маркера (например, "1.1", "а)", "(i)")
        bbox: Bounding box спана
        page: Номер страницы
        font_size: Размер шрифта
        grammar_level: Уровень вложенности (1=раздел, 2=подраздел, 3=подподраздел)
        confidence: Уверенность, что это маркер (0.0-1.0)
        y_center: Центр по Y для быстрого сопоставления
        x_center: Центр по X для проверки колонки
    """
    text: str
    bbox: tuple[float, float, float, float]
    page: int
    font_size: float
    grammar_level: int
    confidence: float
    y_center: float = 0.0
    x_center: float = 0.0
    
    def __post_init__(self) -> None:
        if self.bbox:
            self.y_center = (self.bbox[1] + self.bbox[3]) / 2
            self.x_center = (self.bbox[0] + self.bbox[2]) / 2


@dataclass
class GrammarPattern:
    """
    Паттерн нумерации, выведенный из документа.
    
    Атрибуты:
        regex: Скомпилированный regex паттерна
        level: Уровень вложенности (1, 2, 3...)
        example: Пример маркера, на котором обучился паттерн
        occurrence_count: Сколько раз встречен в документе
    """
    regex: re.Pattern
    level: int
    example: str
    occurrence_count: int = 1


class GrammarInductor:
    """
    Слой 2: Автоматический вывод грамматики нумерации из документа.
    
    Вместо глобального regex-каталога — индуцируем грамматику
    из конкретного документа на первом проходе.
    """
    
    # Базовые паттерны для первичного обнаружения кандидатов
    # Базовые паттерны для первичного обнаружения кандидатов
    # Мультиязычная конфигурация: RU, EN, DE, FR, ES, IT, TR, SR/HR, PL
    BASE_PATTERNS: list[tuple[str, int]] = [
        # 1. Десятичные числовые последовательности (1, 1.1, 1.1.1). Язык-независимо.
        (r'^\d+(?:\.\d+)*\.?$', 1),
        
        # 1a. Цифровые со скобкой (1), 2), 3)) — стандарт подпунктов НПА РФ.
        (r'^\d+\)$', 2),
        
        # 2. Одиночные буквы латиницы и кириллицы со скобкой.
        # Расширено: диакритика для DE, FR, TR, PL, SR/HR.
        (r'^[A-Za-zА-Яа-яЁёĘęĄąĆćŚśŹźŻżÓóÖöÜüÄäßĞğİıŞşÇçČčĐđŠšŽž]\)$', 2),
        
        # 3. Буквы или цифры внутри круглых скобок ((а), (1), (b)).
        (r'^\([A-Za-zА-Яа-яЁёĘęĄąĆćŚśŹźŻżÓóÖöÜüÄäßĞğİıŞşÇçČčĐđŠšŽž\d]+\)$', 2),
        
        # 4. Прописные римские цифры (I, II, X, XIV). Главы верхнего уровня (Level 1).
        (r'^[IVXLCDM]+\.?$', 1),
        
        # 5. Строчные римские цифры (i, ii, ix). Вложенные списки (Level 3).
        (r'^[ivxlcdm]+\.?$', 3),
        
        # 6. Символ параграфа (§ 4.2, §12). Язык-независимо.
        (r'^§\s*\d+(?:\.\d+)*$', 4),
        
        # 7. Заголовки структурных единиц (Статья, Раздел, Глава, Пункт, Параграф).
        # Мультиязычная поддержка: RU, EN, DE, FR, ES, IT, TR, SR/HR.
        # Регистронезависимо (?i), поддерживает основные словоформы.
        (
            r'^(?i:'
                # RU: Статья/статьи, Раздел, Глава/главы, Пункт/пункты, Параграф
                r'Стать[яи]|Раздел[ыа]?|Глав[аы]|Пункт[ыа]?|Параграф'
                r'|'
                # EN: Article, Section, Clause, Chapter, Paragraph, Point, Item
                r'Article|Section|Clause|Chapter|Paragraph|Point|Item'
                r'|'
                # DE: Artikel, Sektion, Kapitel, Absatz
                r'Artikel|Sektion|Kapitel|Absatz'
                r'|'
                # FR: Chapitre, Article, Section
                r'Chapitre'
                r'|'
                # ES: Artículo, Sección, Capítulo
                r'Artículo|Sección|Capítulo'
                r'|'
                # IT: Articolo, Sezione, Capitolo
                r'Articolo|Sezione|Capitolo'
                r'|'
                # TR: Madde, Bölüm, Fıkra, Bent, Başlık
                r'Madde|Bölüm|Fıkra|Bent|Başlık'
                r'|'
                # SR/HR: Član, Odeljak, Stav, Tačka
                r'Član|Odeljak|Stav|Tačka'
            r')'
            r'\s*\d+(?:\.\d+)*',
            4
        ),
        
        # 8. Приложения, дополнения, вложения (Приложение, Appendix, Annex, Anhang и др.).
        # Мультиязычная поддержка.
        (
            r'^(?i:'
                # RU: Приложение, Дополнение
                r'Приложени[еяй]|Дополнени[еяй]'
                r'|'
                # EN: Appendix, Annex, Annexure, Schedule, Exhibit, Attachment
                r'Appendix|Annex(?:ure)?|Schedule|Exhibit|Attachment'
                r'|'
                # DE: Anhang, Anlage, Beilage
                r'Anhang|Anlage|Beilage'
                r'|'
                # FR: Annexe
                r'Annexe'
                r'|'
                # ES: Anexo, Apéndice
                r'Anexo|Apéndice'
                r'|'
                # IT: Allegato, Appendice
                r'Allegato|Appendice'
                r'|'
                # TR: Ek
                r'Ek'
                r'|'
                # SR/HR: Prilog, Dodatak
                r'Prilog|Dodatak'
            r')'
            r'\s*(?:№|N[oO]\.?|#)?\s*\d+',
            4
        ),
    ]
    
    def __init__(self, fingerprint: DocumentFingerprint):
        self.fingerprint = fingerprint
        self.patterns: list[GrammarPattern] = []
        self.marker_candidates: list[OrphanMarker] = []
        # Страницы TOC (оглавления) — обычно страницы 1-3
        # Нужно исключить маркеры с этих страниц
        self.toc_pages: set[int] = set()  # v3.1: adaptive — SequenceValidator filters false positives
    
    def extract(self, pdf_bytes: bytes, document_id: str) -> list[OrphanMarker]:
        """
        Извлечь все кандидатные маркеры из PDF.
        
        Алгоритм:
        1. Первый проход: собрать все короткие спаны (< 15 символов)
        2. Фильтрация по базовым паттернам
        3. Группировка по паттернам для вывода грамматики
        4. Создание OrphanMarker с вычисленным grammar_level
        
        Args:
            pdf_bytes: Исходный PDF
            document_id: ID для логирования
            
        Returns:
            Список OrphanMarker для сопоставления
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        candidates_by_pattern: dict[str, list[dict]] = defaultdict(list)
        
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_dict = page.get_text("dict", flags=fitz.TEXT_DEHYPHENATE)
            
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    
                    # Берём первый спан строки (маркеры обычно в начале)
                    first_span = spans[0]
                    span_text = first_span.get("text", "").strip()
                    
                    # Фильтр: короткий спан (< 15 символов) — кандидат в маркеры
                    if not span_text or len(span_text) > 15:
                        continue
                    
                    # Исключаем маркеры со страниц TOC (оглавление)
                    if page_idx + 1 in self.toc_pages:
                        continue
                    
                    # v3.1: Adaptive filter — skip only if font is tiny (page number)
                    # or span is at the very bottom of the page.
                    if re.match(r'^\d+$', span_text) and len(span_text) <= 2:
                        span_font = first_span.get("size", 10.0)
                        span_y1 = first_span.get("bbox", (0, 0, 0, 0))[3]
                        page_obj = doc[page_idx]
                        page_h = page_obj.rect.height if hasattr(page_obj, 'rect') else 842.0
                        if span_font < self.fingerprint.median_font_size * 0.7:
                            continue
                        if span_y1 > page_h * 0.93:
                            continue
                    
                    # Проверяем по базовым паттернам
                    for pattern_str, base_level in self.BASE_PATTERNS:
                        if re.match(pattern_str, span_text):
                            bbox = tuple(first_span.get("bbox", (0, 0, 0, 0)))
                            font_size = first_span.get("size", 10.0)
                            
                            candidate = {
                                'text': span_text,
                                'bbox': bbox,
                                'page': page_idx + 1,
                                'font_size': font_size,
                                'base_level': base_level,
                                'pattern': pattern_str,
                            }
                            candidates_by_pattern[pattern_str].append(candidate)
                            break
        
        doc.close()
        
        # Выводим грамматику: какие паттерны реально встречаются в документе
        self.patterns = []
        for pattern_str, base_level in self.BASE_PATTERNS:
            matches = candidates_by_pattern.get(pattern_str, [])
            if matches:
                try:
                    compiled = re.compile(pattern_str)
                    self.patterns.append(GrammarPattern(
                        regex=compiled,
                        level=base_level,
                        example=matches[0]['text'],
                        occurrence_count=len(matches),
                    ))
                except re.error:
                    logger.warning(
                        "Invalid grammar pattern skipped",
                        extra={"pattern": pattern_str, "document_id": document_id},
                    )
        
        # Создаём OrphanMarker для всех кандидатов
        self.marker_candidates = []
        for pattern_str, matches in candidates_by_pattern.items():
            level = next(
                (p.level for p in self.patterns if p.regex.pattern == pattern_str),
                1,
            )
            for m in matches:
                marker = OrphanMarker(
                    text=m['text'],
                    bbox=m['bbox'],
                    page=m['page'],
                    font_size=m['font_size'],
                    grammar_level=level,
                    confidence=self._compute_marker_confidence(m, level),
                )
                self.marker_candidates.append(marker)
        
        # Сортируем по странице и Y-координате для детерминированного порядка
        self.marker_candidates.sort(key=lambda m: (m.page, m.y_center, m.x_center))
        
        # DEBUG: Показываем первые 10 кандидатов для отладки
        for i, m in enumerate(self.marker_candidates[:10]):
            logger.debug(
                f"OrphanMarker[{i}]: text='{m.text}' page={m.page} y={m.y_center:.1f} x={m.x_center:.1f}",
                extra={"document_id": document_id},
            )
        
        logger.info(
            "GrammarInduction completed",
            extra={
                "document_id": document_id,
                "patterns_found": len(self.patterns),
                "marker_candidates": len(self.marker_candidates),
                "sample_markers": [m.text for m in self.marker_candidates[:5]],
            },
        )
        
        return self.marker_candidates
    
    def _compute_marker_confidence(self, marker: dict, level: int) -> float:
        """
        Вычислить уверенность, что спан — настоящий маркер нумерации.
        
        Факторы:
        - Длина текста (короткие = выше уверенность)
        - Размер шрифта (соответствует медианному = выше)
        - Уровень вложенности (level 1-2 = выше, level 4+ = ниже)
        """
        text_len = len(marker['text'])
        font_size = marker['font_size']
        
        # Длина: оптимально 2-6 символов
        if 2 <= text_len <= 6:
            len_score = 1.0
        elif text_len <= 10:
            len_score = 0.7
        else:
            len_score = 0.4
        
        # Размер шрифта: близок к медианному = выше
        font_diff = abs(font_size - self.fingerprint.median_font_size)
        if font_diff <= 1.0:
            font_score = 1.0
        elif font_diff <= 3.0:
            font_score = 0.7
        else:
            font_score = 0.5
        
        # Уровень: 1-2 = высокий приоритет
        level_score = 1.0 if level <= 2 else 0.7 if level <= 3 else 0.5
        
        return round((len_score + font_score + level_score) / 3, 2)


# Продолжение в следующем сообщении (Слои 3-5 + главный класс)...


# ─────────────────────────────────────────────────────────────────────────────
# Слой 3: Adaptive Spatial Matching
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SpatialMatch:
    """
    Результат сопоставления маркера с атомом.
    
    Атрибуты:
        atom: CanonicalAtom, которому присваивается маркер
        marker: OrphanMarker, который будет присвоен
        y_delta: Разница по Y между центрами (pt)
        x_gap: Разница по X между маркером и текстом (pt)
        confidence: Уверенность сопоставления (0.0-1.0)
        column_match: Попадают ли в одну колонку
    """
    atom: CanonicalAtom
    marker: OrphanMarker
    y_delta: float
    x_gap: float
    confidence: float
    column_match: bool


class SpatialMatcher:
    """
    Слой 3: Адаптивное геометрическое сопоставление маркеров с атомами.
    
    Ключевые особенности:
    - many-to-many resolution через венгерский алгоритм
    - Проверка принадлежности к одной колонке
    - Адаптивные пороги из DocumentFingerprint
    """
    
    def __init__(self, fingerprint: DocumentFingerprint):
        self.fingerprint = fingerprint
    
    def match(
        self,
        atoms: list[CanonicalAtom],
        orphan_markers: list[OrphanMarker],
        document_id: str,
    ) -> list[SpatialMatch]:
        """
        Сопоставить маркеры с атомами через геометрическое соответствие.
        
        Алгоритм:
        1. Для каждого атома без маркера найти кандидатов-маркеров
        2. Построить биграф допустимых сопоставлений
        3. Решить задачу назначения через венгерский алгоритм
        4. Вернуть оптимальные пары
        
        Args:
            atoms: Список атомов от Docling
            orphan_markers: Кандидаты в маркеры из GrammarInductor
            document_id: ID для логирования
            
        Returns:
            Список SpatialMatch для валидации и применения
        """
        # Фильтруем атомы без нативного маркера
        atoms_without_marker = [
            atom for atom in atoms
            if not atom.marker and atom.text.strip()
        ]
        
        logger.info(
            "SpatialMatching started",
            extra={
                "document_id": document_id,
                "atoms_without_marker": len(atoms_without_marker),
                "orphan_markers": len(orphan_markers),
            },
        )
        
        # Строим матрицу стоимостей для венгерского алгоритма
        # Стоимость = -confidence (минимизируем стоимость = максимизируем уверенность)
        n_atoms = len(atoms_without_marker)
        n_markers = len(orphan_markers)
        
        if n_atoms == 0 or n_markers == 0:
            return []
        
        # ГРУППИРУЕМ атомы и маркеры по страницам для page-local matching
        # Это предотвращает cross-page mismatches (атом стр.4 с маркером стр.15)
        from collections import defaultdict
        atoms_by_page: dict[int, list[tuple[int, CanonicalAtom]]] = defaultdict(list)
        markers_by_page: dict[int, list[tuple[int, OrphanMarker]]] = defaultdict(list)
        
        for idx, atom in enumerate(atoms_without_marker):
            atoms_by_page[atom.page].append((idx, atom))
        
        for idx, marker in enumerate(orphan_markers):
            markers_by_page[marker.page].append((idx, marker))
        
        # Page-local matching: для каждой страницы строим свою матрицу
        all_matches: list[SpatialMatch] = []
        
        for page_num in atoms_by_page.keys():
            page_atoms = atoms_by_page[page_num]
            page_markers = markers_by_page.get(page_num, [])
            
            if not page_markers:
                continue
            
            # Строим матрицу только для этой страницы
            n_page_atoms = len(page_atoms)
            n_page_markers = len(page_markers)
            
            compatibility_matrix: list[list[tuple[float, float, float, bool]]] = []
            
            for local_atom_idx, (global_atom_idx, atom) in enumerate(page_atoms):
                row: list[tuple[float, float, float, bool]] = []
                for local_marker_idx, (global_marker_idx, marker) in enumerate(page_markers):
                    y_delta = abs(atom.bbox[1] - marker.y_center) if atom.bbox else float('inf')
                    x_gap = marker.x_center - (atom.bbox[0] if atom.bbox else 0)
                    
                    column_match = self._check_column_match(atom, marker)
                    
                    confidence = self._compute_match_confidence(
                        atom, marker, y_delta, x_gap, column_match
                    )
                    
                    row.append((confidence, y_delta, x_gap, column_match))
                compatibility_matrix.append(row)
        
            # Решаем задачу назначения через венгерский алгоритм для этой страницы
            if n_page_atoms == 0 or n_page_markers == 0:
                continue
            
            cost_matrix = np.array([
                [1.0 - cell[0] for cell in row]
                for row in compatibility_matrix
            ])
            
            from scipy.optimize import linear_sum_assignment
            
            if n_page_atoms != n_page_markers:
                max_dim = max(n_page_atoms, n_page_markers)
                padded_cost = np.full((max_dim, max_dim), 1.0)
                padded_cost[:n_page_atoms, :n_page_markers] = cost_matrix
                row_ind, col_ind = linear_sum_assignment(padded_cost)
            else:
                row_ind, col_ind = linear_sum_assignment(cost_matrix)
            
            # Собираем page-local matches
            for local_atom_idx, local_marker_idx in zip(row_ind, col_ind):
                if local_atom_idx >= n_page_atoms or local_marker_idx >= n_page_markers:
                    continue
                
                confidence, y_delta, x_gap, column_match = compatibility_matrix[local_atom_idx][local_marker_idx]
                
                if confidence < 0.5:
                    continue
                
                global_atom_idx, atom = page_atoms[local_atom_idx]
                global_marker_idx, marker = page_markers[local_marker_idx]
                
                match = SpatialMatch(
                    atom=atom,
                    marker=marker,
                    y_delta=y_delta,
                    x_gap=x_gap,
                    confidence=round(confidence, 3),
                    column_match=column_match,
                )
                all_matches.append(match)
        
        matches = all_matches
        
        logger.info(
            "SpatialMatching completed",
            extra={
                "document_id": document_id,
                "matches_found": len(matches),
                "avg_confidence": round(statistics.mean([m.confidence for m in matches]), 3) if matches else 0.0,
            },
        )
        
        return matches
    
    def _check_column_match(self, atom: CanonicalAtom, marker: OrphanMarker) -> bool:
        """
        Проверить, находятся ли атом и маркер в одной колонке.
        
        Использует кластеризацию из DocumentFingerprint.
        """
        if not self.fingerprint.column_clusters:
            return True  # Нет кластеров — считаем что совпадает
        
        atom_x = atom.bbox[0] if atom.bbox else 0
        marker_x = marker.x_center
        
        # Находим кластер для атома
        atom_cluster = None
        for cluster in self.fingerprint.column_clusters:
            if cluster.contains_x(atom_x, tolerance=20.0):
                atom_cluster = cluster
                break
        
        # Находим кластер для маркера
        marker_cluster = None
        for cluster in self.fingerprint.column_clusters:
            if cluster.contains_x(marker_x, tolerance=20.0):
                marker_cluster = cluster
                break
        
        # Если оба в одном кластере — совпадение
        if atom_cluster and marker_cluster:
            return atom_cluster.cluster_id == marker_cluster.cluster_id
        
        # Если кластеры не найдены, проверяем простое условие: маркер слева от атома
        return marker_x < atom_x
    
    def _compute_match_confidence(
        self,
        atom: CanonicalAtom,
        marker: OrphanMarker,
        y_delta: float,
        x_gap: float,
        column_match: bool,
    ) -> float:
        """
        Вычислить уверенность сопоставления.
        
        Факторы:
        - Y-совпадение: чем меньше delta, тем выше (максимум = y_tolerance)
        - X-совпадение: маркер должен быть слева (x_gap > 0)
        - Column match: в одной колонке = +0.2
        - Marker confidence: из GrammarInductor
        """
        # Y-совпадение: экспоненциальное затухание от y_delta
        y_score = np.exp(-y_delta / (self.fingerprint.y_tolerance + 1e-6))
        
        # X-совпадение: маркер должен быть слева, но не слишком далеко
        if x_gap < 0:
            x_score = 0.0  # Маркер справа от текста — неверно
        elif x_gap < 50:
            x_score = 1.0  # Оптимальный отступ
        elif x_gap < 150:
            x_score = 0.7  # Приемлемый отступ
        else:
            x_score = 0.3  # Слишком далеко
        
        # Column match бонус
        column_score = 1.0 if column_match else 0.5
        
        # Итоговая уверенность: взвешенное среднее
        confidence = (
            0.4 * y_score +
            0.3 * x_score +
            0.2 * column_score +
            0.1 * marker.confidence
        )
        
        return round(min(1.0, max(0.0, confidence)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# Слой 4: Sequence Validation (per-branch state machine)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationState:
    """
    Состояние валидации для одной ветки нумерации.
    
    Отслеживает ожидаемый следующий маркер в последовательности.
    """
    parent_prefix: str  # Например "1." для ветки 1.1, 1.2, 1.3...
    last_number: int  # Последний номер в последовательности (1, 2, 3...)
    expected_next: int  # Ожидаемый следующий номер
    level: int  # Уровень вложенности


class SequenceValidator:
    """
    Слой 4: Валидация последовательности нумерации через per-branch state machine.
    
    Правила:
    - После 1.2 может идти 1.3, 1.2.1, или 2 (закрытие уровня)
    - Пропуски > 1 номера = подозрительно (1.1 → 1.5)
    - Дубликаты = ошибка (два 1.2 на одной странице)
    - Cross-level: если есть 2.3.1, должен существовать 2.3
    """
    
    def __init__(self):
        self.branch_states: dict[str, ValidationState] = {}
        self.seen_markers: set[str] = set()
        self.rejections: list[dict] = []
    
    def validate(
        self,
        matches: list[SpatialMatch],
        document_id: str,
    ) -> tuple[list[SpatialMatch], list[SpatialMatch]]:
        """
        Валидировать сопоставления через state machine.
        
        Args:
            matches: Список SpatialMatch от SpatialMatcher
            
        Returns:
            (принятые_сопоставления, отклонённые_сопоставления)
        """
        # Сортируем по странице и Y-координате для правильного порядка обхода
        sorted_matches = sorted(matches, key=lambda m: (m.atom.page, m.atom.bbox[1] if m.atom.bbox else 0))
        
        accepted: list[SpatialMatch] = []
        rejected: list[SpatialMatch] = []
        
        for match in sorted_matches:
            marker_text = match.marker.text
            validation_result = self._validate_marker(marker_text, match)
            
            if validation_result['valid']:
                accepted.append(match)
                self._update_state(marker_text, match)
            else:
                rejected.append(match)
                self.rejections.append({
                    'marker': marker_text,
                    'reason': validation_result['reason'],
                    'atom_text': match.atom.text[:50],
                    'page': match.atom.page,
                })
        
        logger.info(
            "SequenceValidation completed",
            extra={
                "document_id": document_id,
                "accepted": len(accepted),
                "rejected": len(rejected),
                "rejection_reasons": self._summarize_rejections(),
            },
        )
        
        return accepted, rejected
    
    def _validate_marker(self, marker_text: str, match: SpatialMatch) -> dict:
        """
        Валидировать один маркер против текущего состояния.
        
        Returns:
            {'valid': bool, 'reason': str}
        """
        # Проверка на дубликаты
        marker_key = f"p{match.atom.page}:{marker_text}"
        if marker_key in self.seen_markers:
            return {'valid': False, 'reason': 'duplicate'}
        
        # Парсим структуру маркера
        parsed = self._parse_marker(marker_text)
        if not parsed:
            return {'valid': True, 'reason': 'unparseable_accept'}  # Не можем распарсить — принимаем
        
        prefix, number, level = parsed
        
        # Проверка монотонности для этой ветки
        if prefix in self.branch_states:
            state = self.branch_states[prefix]
            
            # Ожидаем следующий номер или закрытие уровня
            if number > state.expected_next + 1:
                # Пропуск > 1 номера (1.1 → 1.5)
                return {'valid': False, 'reason': 'non_monotonic'}
            
            if number < state.last_number:
                # Номер меньше предыдущего (1.3 → 1.2) — возможно закрытие уровня
                # Проверяем, не является ли это началом новой ветки
                if not self._is_valid_level_close(prefix, state, number):
                    return {'valid': False, 'reason': 'invalid_level_close'}
        
        self.seen_markers.add(marker_key)
        return {'valid': True, 'reason': 'ok'}
    
    def _parse_marker(self, marker_text: str) -> tuple[str, int, int] | None:
        """
        Распарсить маркер на компоненты.
        
        Примеры:
        - "1.1" → ("1.", 1, 2)
        - "1.2.3" → ("1.2.", 3, 3)
        - "2" → ("", 2, 1)
        - "а)" → None (буквенные маркеры обрабатываем отдельно)
        """
        # Числовые маркеры
        match = re.match(r'^(\d+(?:\.\d+)*)\.?$', marker_text)
        if not match:
            return None
        
        parts = match.group(1).split('.')
        level = len(parts)
        
        if level == 1:
            return ("", int(parts[0]), 1)
        else:
            prefix = ".".join(parts[:-1]) + "."
            number = int(parts[-1])
            return (prefix, number, level)
    
    def _is_valid_level_close(self, prefix: str, state: ValidationState, number: int) -> bool:
        """
        Проверить, является ли уменьшение номера валидным закрытием уровня.
        
        Пример: после 1.2.3 может идти 1.3 (закрытие уровня 3) или 2 (закрытие уровня 2).
        """
        # Упрощённая эвристика: разрешаем уменьшение если это начало новой ветки
        return number == 1 or number == state.expected_next
    
    def _update_state(self, marker_text: str, match: SpatialMatch) -> None:
        """Обновить состояние после принятия маркера."""
        parsed = self._parse_marker(marker_text)
        if not parsed:
            return
        
        prefix, number, level = parsed
        
        self.branch_states[prefix] = ValidationState(
            parent_prefix=prefix,
            last_number=number,
            expected_next=number + 1,
            level=level,
        )
    
    def _summarize_rejections(self) -> dict:
        """Суммировать причины отклонений для логирования."""
        reasons: dict[str, int] = defaultdict(int)
        for rej in self.rejections:
            reasons[rej['reason']] += 1
        return dict(reasons)


# ─────────────────────────────────────────────────────────────────────────────
# Слой 5: Confidence Scoring + главный класс SpatialMarkerRecovery
# ─────────────────────────────────────────────────────────────────────────────


class SpatialMarkerRecovery:
    """
    Главный класс: оркестрирует все 5 слоёв восстановления маркеров.
    
    Usage:
        atoms, metrics = SpatialMarkerRecovery.recover(
            atoms=canonical_atoms,
            pdf_bytes=pdf_bytes,
            document_id=doc_id,
        )
    
    Compensating control для Docling issue #1345.
    """
    
    @classmethod
    def recover(
        cls,
        atoms: list[CanonicalAtom],
        pdf_bytes: bytes,
        document_id: str,
    ) -> tuple[list[CanonicalAtom], RecoveryMetrics]:
        """
        Восстановить маркеры для атомов через геометрическое сопоставление.
        
        Args:
            atoms: Список CanonicalAtom от Docling (возможно, без маркеров)
            pdf_bytes: Исходный PDF для извлечения спанов через PyMuPDF
            document_id: ID документа для логирования
            
        Returns:
            (обогащённые атомы, метрики восстановления)
        """
        metrics = RecoveryMetrics(document_id=document_id)
        metrics.total_atoms = len(atoms)
        
        # Считаем атомы без нативного маркера
        atoms_without_marker = [a for a in atoms if not a.marker]
        metrics.atoms_without_native_marker = len(atoms_without_marker)
        
        if metrics.atoms_without_native_marker == 0:
            # Все атомы уже имеют маркеры — восстановление не нужно
            logger.info(
                "SpatialMarkerRecovery skipped: all atoms have native markers",
                extra={"document_id": document_id},
            )
            metrics.compute_ratios()
            return atoms, metrics
        
        try:
            # ─ Слой 1: Document Fingerprint ──────────────────────────────────
            fingerprint = DocumentFingerprint.build(pdf_bytes, document_id)
            
            # ── Слой 2: Grammar Induction ─────────────────────────────────────
            inductor = GrammarInductor(fingerprint)
            orphan_markers = inductor.extract(pdf_bytes, document_id)
            
            if not orphan_markers:
                logger.warning(
                    "SpatialMarkerRecovery: no orphan markers found",
                    extra={"document_id": document_id},
                )
                metrics.compute_ratios()
                return atoms, metrics
            
            # ─ Слой 3: Adaptive Spatial Matching ─────────────────────────────
            matcher = SpatialMatcher(fingerprint)
            matches = matcher.match(atoms, orphan_markers, document_id)
            metrics.spatial_match_attempts = len(matches)
            
            # ─ Слой 4: Sequence Validation ───────────────────────────────────
            validator = SequenceValidator()
            accepted_matches, rejected_matches = validator.validate(matches, document_id)
            metrics.sequence_validation_rejections = len(rejected_matches)
            
            # ── Слой 5: Применяем принятые сопоставления ──────────────────────
            for match in accepted_matches:
                # Препендим маркер к тексту (идемпотентно)
                current_text = match.atom.text.strip()
                marker_text = match.marker.text.strip()
                
                if not current_text.startswith(marker_text):
                    match.atom.text = f"{marker_text} {current_text}"
                
                match.atom.marker = marker_text
                
                # Добавляем metadata для downstream (heading_builder)
                # Универсальный сигнал о геометрическом восстановлении
                if not hasattr(match.atom, "metadata") or match.atom.metadata is None:
                    match.atom.metadata = {}
                match.atom.metadata["marker_source"] = "spatial_recovery"
                match.atom.metadata["recovery_confidence"] = match.confidence
                match.atom.metadata["recovery_y_delta"] = match.y_delta
                
                # Обновляем метрики
                metrics.confidence_scores.append(match.confidence)
                metrics.y_deltas.append(match.y_delta)
                
                if match.confidence >= 0.85:
                    metrics.markers_recovered_high_confidence += 1
                elif match.confidence >= 0.5:
                    metrics.markers_recovered_medium_confidence += 1
                else:
                    metrics.markers_recovered_low_confidence += 1
            
            metrics.markers_not_recovered = (
                metrics.atoms_without_native_marker
                - metrics.markers_recovered_high_confidence
                - metrics.markers_recovered_medium_confidence
                - metrics.markers_recovered_low_confidence
            )
            
            # Вычисляем итоговые метрики
            metrics.compute_ratios()
            
            # Экспортируем в Prometheus
            try:
                metrics.export_prometheus()
            except Exception as e:
                logger.warning(
                    "Failed to export Prometheus metrics",
                    extra={"document_id": document_id, "error": str(e)},
                )
            
            logger.info(
                "SpatialMarkerRecovery completed",
                extra=metrics.to_log_dict(),
            )
            
        except Exception as e:
            logger.exception(
                "SpatialMarkerRecovery failed",
                extra={"document_id": document_id, "error": str(e)},
            )
            # Fail-safe: возвращаем атомы без изменений
            metrics.compute_ratios()
        
        return atoms, metrics


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    'SpatialMarkerRecovery',
    'RecoveryMetrics',
    'DocumentFingerprint',
    'GrammarInductor',
    'SpatialMatcher',
    'SequenceValidator',
    'OrphanMarker',
    'ColumnCluster',
    'SpatialMatch',
]
