# src/services/document_layout/marker_recovery.py

"""
Universal Marker Recovery Module.

Восстанавливает нумерацию для ЛЮБОГО формата bilingual документов:
1. TAB-колонки (номер отдельно от текста)
2. Таблица разделённая (marker | text)
3. Таблица встроенная (marker+text | marker+text)
4. Построчно (EN затем RU)
5. Таблица данных (№ | description | name | price...)

Работает для любых языков (ru, en, de, fr, etc.)
"""

from __future__ import annotations

import re
from typing import Any

from core.logging import get_logger
from services.document_layout.schemas import CanonicalAtom, CanonicalTable

logger = get_logger(__name__)

# Универсальный паттерн для ВСЕХ систем нумерации:
# 1. Арабские цифры: 1, 1.1, 2.8.3 (ГОСТ, ISO)
# 2. Римские цифры: I, II, III, IV, V, i, ii, iii (договоры, НПА)
# 3. Кириллические буквы: А, Б, В, а, б, в (приложения, подпункты)
# 4. Латинские буквы: A, B, C, a, b, c (международные контракты)
_MARKER_PATTERN = re.compile(
    r'^('
    r'\d+(?:\.\d+)*'           # 1. Арабские: 1, 1.1, 2.8.3
    r'|'
    r'[IVXLCDMivxlcdm]+'       # 2. Римские: I, II, III, iv, v
    r'|'
    r'[А-ЯЁа-яё]'              # 3. Кириллица: А, Б, В, а, б, в
    r'|'
    r'[A-Za-z]'                # 4. Латиница: A, B, C, a, b, c
    r')\.?\s+'
)

_SECTION_MARKER_PATTERN = re.compile(
    r'^('
    r'\d+'
    r'|'
    r'[IVXLCDMivxlcdm]+'
    r'|'
    r'[А-ЯЁа-яё]'
    r'|'
    r'[A-Za-z]'
    r')\.?\s*$'
)

# Отдельный паттерн для чистых римских цифр (для детекции в тексте)
_ROMAN_MARKER_PATTERN = re.compile(r'^([IVXLCDMivxlcdm]+)\.?\s+')


def _extract_marker_from_text(text: str) -> str | None:
    """
    Извлечь маркер из начала текста.
    
    Поддерживает ВСЕ системы нумерации:
    - 1, 2, 3... (арабские цифры)
    - 1.1, 1.2, 2.8... (иерархические)
    - I., II., III., IV... (римские цифры)
    - А., Б., В... (кириллические заглавные)
    - а), б), в)... (кириллические строчные)
    - A., B., C... (латинские заглавные)
    - a), b), c)... (латинские строчные)
    """
    if not text:
        return None
    
    text_stripped = text.strip()
    
    # Пробуем основной универсальный паттерн
    match = _MARKER_PATTERN.match(text_stripped)
    if match:
        return match.group(1)
    
    # Fallback: проверяем чистые римские цифры (без точки в начале)
    roman_match = _ROMAN_MARKER_PATTERN.match(text_stripped)
    if roman_match:
        return roman_match.group(1)
    
    return None


def _is_data_table(table: CanonicalTable) -> bool:
    """
    Определить является ли таблица таблицей данных (не clause table).
    
    Признаки data table:
    - 3+ колонок
    - Первая колонка содержит только номера (1, 2, 3...)
    """
    if not hasattr(table, 'data') or not getattr(table.data, 'grid', None):
        return False
    
    grid = table.data.grid
    num_cols = len(grid[0]) if grid else 0
    num_rows = len(grid)
    
    # Data table обычно имеет 3+ колонок
    if num_cols < 3:
        return False
    
    # Проверить первую колонку на номера (первые 10 строк)
    for row in grid[:min(10, num_rows)]:
        if row:
            first_cell = row[0]
            first_text = getattr(first_cell, 'text', str(first_cell)).strip()
            if first_text and not re.match(r'^\d+\.?$', first_text):
                return False
    
    return True


def _is_clause_marker_cell(text: str) -> bool:
    """
    Проверить является ли текст clause-маркером.
    
    Поддерживает:
    - 1.1, 1.1.1, 2.8... (числовые)
    - (a), (b), a), b)... (буквенные)
    - I., II., III.... (римские)
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 12:
        return False
    
    # Числовые маркеры
    if re.match(r'^\d+(?:\.\d+)*\.?$', stripped):
        return True
    
    # Буквенные в скобках
    if re.match(r'^\([a-zA-Zа-яА-Я\d]+\)$', stripped):
        return True
    
    # Буквенные с закрывающей скобкой
    if re.match(r'^[a-zA-Zа-яА-Я]\)$', stripped):
        return True
    
    # Римские цифры
    if re.match(r'^[IVXLCDMivxlcdm]+\.?$', stripped):
        return True
    
    return False


def recover_markers_from_atoms(atoms: list[CanonicalAtom]) -> list[CanonicalAtom]:
    """
    Уровень 1: Восстановить маркеры для атомов (non-table).
    
    Работает для форматов 1 и 4.
    
    Алгоритм:
    1. Извлечь маркер из текста если нет в поле marker
    2. Восстановить пропущенные подразделы по контексту
    """
    if not atoms:
        return atoms
    
    current_section = None
    subsection_counter = 0
    
    for atom in atoms:
        # Если маркера нет, попробовать извлечь из текста
        if not atom.marker and atom.text:
            extracted = _extract_marker_from_text(atom.text)
            if extracted:
                atom.marker = extracted
        
        # Восстановить пропущенные подразделы по контексту
        if atom.marker:
            # Это раздел? (1, 2, 3... без точек)
            if re.match(r'^\d+$', atom.marker):
                current_section = atom.marker
                subsection_counter = 0
            # Это подраздел? (1.1, 1.1.1, 2.8...)
            elif '.' in atom.marker and current_section:
                section_part = atom.marker.split('.')[0]
                if section_part == current_section:
                    subsection_counter += 1
    
    return atoms


def recover_markers_from_tables(
    tables: list[CanonicalTable],
    target_language: str,
) -> list[dict[str, Any]]:
    """
    Уровень 2: Восстановить маркеры из таблиц.
    
    Работает для форматов 2, 3 и 5.
    
    Returns:
        Список элементов с маркерами (для добавления в layout)
    """
    elements = []
    
    for table in tables:
        if not hasattr(table, 'data') or not getattr(table.data, 'grid', None):
            continue
        
        grid = table.data.grid
        num_rows = len(grid)
        num_cols = len(grid[0]) if grid else 0
        
        if num_rows < 2 or num_cols < 1:
            continue
        
        # Определить тип таблицы
        is_data_table = _is_data_table(table)
        
        # Пропустить заголовок (строка 0)
        for row_idx in range(1, num_rows):
            row = grid[row_idx]
            if not row:
                continue
            
            marker = None
            text = None
            
            # ── Формат 5: Таблица данных (№ в первой колонке) ──────
            if is_data_table and num_cols >= 2:
                first_cell = row[0]
                marker_text = getattr(first_cell, 'text', str(first_cell)).strip()
                
                if re.match(r'^\d+\.?$', marker_text):
                    marker = marker_text.rstrip('.')
                    
                    # Собрать текст из второй колонки (описание объекта)
                    second_cell = row[1]
                    text = getattr(second_cell, 'text', str(second_cell)).strip()
                    
                    # Удалить маркер из текста если есть
                    if text and text.startswith(marker):
                        text = re.sub(r'^\d+\.?\s*', '', text)
            
            # ── Формат 2/3: Clause table ───────────────────────────
            elif num_cols >= 2:
                first_cell = row[0]
                first_text = getattr(first_cell, 'text', str(first_cell)).strip()
                second_cell = row[1]
                second_text = getattr(second_cell, 'text', str(second_cell)).strip()
                
                # Формат 2: Разделённый (marker | text)
                if _is_clause_marker_cell(first_text) and len(second_text) > 10:
                    marker = first_text
                    text = second_text
                
                # Формат 3: Встроенный (marker+text | marker+text)
                elif len(first_text) > 10 and len(second_text) > 10:
                    extracted = _extract_marker_from_text(first_text)
                    if extracted:
                        marker = extracted
                        # Предпочитать русский текст (target_language)
                        text = second_text
            
            # Создать элемент если маркер найден
            if marker and text:
                element = {
                    'element_id': f"{target_language}:table:{table.table_id}:r{row_idx}",
                    'source_element_ids': [table.table_id],
                    'text': f"{marker} {text}",
                    'page': table.page,
                    'reading_order': table.page * 1000 + row_idx,
                    'type': 'list_item',
                    'label': 'list_item',
                    'marker': marker,
                    'is_marker_only': False,
                    'bbox': table.bbox,
                    'language': target_language,
                    'projection_method': 'table_marker_recovery',
                    'projection_confidence': 0.90,
                    'is_table': False,
                }
                elements.append(element)
    
    return elements



    