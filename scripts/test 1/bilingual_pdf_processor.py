# scripts/test 1/bilingual_pdf_processor.py

#!/usr/bin/env python3
"""
Bilingual PDF Processor v18.0
Исправлена агрессивная детекция колонок.
Более консервативный подход — лучше оставить лишнее, чем удалить нужное.
"""

import fitz
import re
from pathlib import Path

# ==================== КОНФИГУРАЦИЯ ====================

INPUT_FOLDER = "/home/vladi/projects/LegalMAS/scripts/test 1"
OUTPUT_SUFFIX = "_rus only"
TARGET_LANG = 'ru'  # 'ru' или 'en'

# ==================== ДЕТЕКЦИЯ ЯЗЫКА ====================

def is_cyrillic(char: str) -> bool:
    code = ord(char)
    return (0x0400 <= code <= 0x04FF) or char in 'ЁёЄєІіЇїҐґ'

def is_latin(char: str) -> bool:
    code = ord(char)
    return (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A)

def is_letter(char: str) -> bool:
    return is_cyrillic(char) or is_latin(char)

def detect_text_language(text: str) -> str:
    """Определяет язык текста."""
    if not text or not text.strip():
        return 'empty'
    
    cyrillic = sum(1 for c in text if is_cyrillic(c))
    latin = sum(1 for c in text if is_latin(c))
    total = cyrillic + latin
    
    if total == 0:
        return 'other'
    
    ratio = cyrillic / total
    
    # Консервативные пороги
    if ratio > 0.8:
        return 'ru'
    elif ratio < 0.2:
        return 'en'
    else:
        return 'mixed'

# ==================== АНАЛИЗ СТРАНИЦЫ ====================

def analyze_page_structure(page) -> dict:
    """
    Анализирует структуру страницы.
    КОНСЕРВАТИВНО определяет, есть ли две языковые колонки.
    """
    page_width = page.rect.width
    mid_x = page_width / 2
    
    blocks = page.get_text("dict")["blocks"]
    
    # Собираем блоки с их языком и позицией
    left_blocks = []
    right_blocks = []
    
    for block in blocks:
        if "lines" not in block:
            continue
        
        block_text = ""
        for line in block["lines"]:
            for span in line["spans"]:
                block_text += span["text"] + " "
        
        block_lang = detect_text_language(block_text)
        block_center = (block["bbox"][0] + block["bbox"][2]) / 2
        block_width = block["bbox"][2] - block["bbox"][0]
        
        # Блок считается "в колонке" только если он узкий (< 60% ширины страницы)
        is_narrow = block_width < page_width * 0.6
        
        block_info = {
            'lang': block_lang,
            'center': block_center,
            'width': block_width,
            'text': block_text[:100]
        }
        
        if is_narrow:
            if block_center < mid_x * 0.9:  # Явно слева
                left_blocks.append(block_info)
            elif block_center > mid_x * 1.1:  # Явно справа
                right_blocks.append(block_info)
    
    # Определяем двухколоночность СТРОГО:
    # - Минимум 5 блоков с каждой стороны
    # - Языки колонок должны ЯВНО отличаться
    is_two_column = False
    left_lang = 'unknown'
    right_lang = 'unknown'
    
    if len(left_blocks) >= 5 and len(right_blocks) >= 5:
        # Считаем преобладающий язык в каждой колонке
        left_ru = sum(1 for b in left_blocks if b['lang'] == 'ru')
        left_en = sum(1 for b in left_blocks if b['lang'] == 'en')
        right_ru = sum(1 for b in right_blocks if b['lang'] == 'ru')
        right_en = sum(1 for b in right_blocks if b['lang'] == 'en')
        
        # Колонка считается "языковой" если >70% блоков одного языка
        left_total = left_ru + left_en
        right_total = right_ru + right_en
        
        if left_total > 0 and right_total > 0:
            if left_en / left_total > 0.7:
                left_lang = 'en'
            elif left_ru / left_total > 0.7:
                left_lang = 'ru'
            
            if right_en / right_total > 0.7:
                right_lang = 'en'
            elif right_ru / right_total > 0.7:
                right_lang = 'ru'
            
            # Двухколоночность только если языки РАЗНЫЕ и ОПРЕДЕЛЁННЫЕ
            if left_lang in ['ru', 'en'] and right_lang in ['ru', 'en']:
                if left_lang != right_lang:
                    is_two_column = True
    
    return {
        'is_two_column': is_two_column,
        'split_x': mid_x,
        'left_lang': left_lang,
        'right_lang': right_lang,
        'left_blocks': len(left_blocks),
        'right_blocks': len(right_blocks)
    }

def get_column_to_remove(page_info: dict, target_lang: str) -> str:
    """Определяет какую колонку удалять."""
    if not page_info['is_two_column']:
        return 'none'
    
    left = page_info['left_lang']
    right = page_info['right_lang']
    remove_lang = 'en' if target_lang == 'ru' else 'ru'
    
    if left == remove_lang:
        return 'left'
    if right == remove_lang:
        return 'right'
    
    return 'none'

# ==================== ОБРАБОТКА СТРОК ====================

def collect_page_lines(page) -> list:
    """Собирает все строки страницы."""
    lines_info = []
    raw_blocks = page.get_text("rawdict")["blocks"]
    
    for block in raw_blocks:
        if "lines" not in block:
            continue
        
        for line in block["lines"]:
            all_chars = []
            line_bbox = fitz.Rect()
            
            for span in line["spans"]:
                span_bbox = fitz.Rect(span["bbox"])
                line_bbox = line_bbox | span_bbox if not line_bbox.is_empty else span_bbox
                
                if "chars" in span:
                    for char_info in span["chars"]:
                        all_chars.append({
                            'char': char_info.get('c', ''),
                            'bbox': fitz.Rect(char_info['bbox'])
                        })
            
            full_text = ''.join(c['char'] for c in all_chars) if all_chars else \
                        ''.join(span['text'] for span in line['spans'])
            
            lines_info.append({
                'text': full_text,
                'stripped': full_text.strip(),
                'bbox': line_bbox,
                'chars': all_chars,
                'lang': detect_text_language(full_text),
                'has_letters': any(is_letter(c) for c in full_text),
                'center_x': (line_bbox.x0 + line_bbox.x1) / 2 if not line_bbox.is_empty else 0,
                'width': line_bbox.width if not line_bbox.is_empty else 0
            })
    
    return lines_info

def determine_orphan_language(orphan_line: dict, all_lines: list, page_info: dict) -> str:
    """
    Определяет язык строки без букв по контексту.
    КОНСЕРВАТИВНО — если не уверены, возвращаем 'keep'.
    """
    if not page_info['is_two_column']:
        return 'keep'  # На одноколоночных страницах не удаляем номера
    
    orphan_x = orphan_line['center_x']
    split_x = page_info['split_x']
    
    # Определяем по колонке
    is_left = orphan_x < split_x * 0.9
    is_right = orphan_x > split_x * 1.1
    
    if is_left:
        return page_info['left_lang']
    elif is_right:
        return page_info['right_lang']
    
    return 'keep'  # В середине — не трогаем

# ==================== ГЛАВНАЯ ОБРАБОТКА ====================

def process_pdf(input_path: Path, output_path: Path) -> dict:
    doc = fitz.open(str(input_path))
    
    remove_lang = 'en' if TARGET_LANG == 'ru' else 'ru'
    
    stats = {
        'pages': len(doc),
        'lines_total': 0,
        'removed_full': 0,
        'removed_partial': 0,
        'removed_orphans': 0,
        'kept': 0,
        'two_col_pages': 0
    }
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_width = page.rect.width
        
        # Анализируем страницу
        page_info = analyze_page_structure(page)
        column_to_remove = get_column_to_remove(page_info, TARGET_LANG)
        split_x = page_info['split_x']
        
        if page_info['is_two_column']:
            stats['two_col_pages'] += 1
        
        # Собираем строки
        all_lines = collect_page_lines(page)
        
        for line_info in all_lines:
            stats['lines_total'] += 1
            
            text = line_info['stripped']
            line_bbox = line_info['bbox']
            lang = line_info['lang']
            all_chars = line_info['chars']
            line_center = line_info['center_x']
            line_width = line_info['width']
            
            if not text:
                stats['kept'] += 1
                continue
            
            # Определяем позицию строки
            is_narrow = line_width < page_width * 0.55
            is_in_left = line_center < split_x * 0.9
            is_in_right = line_center > split_x * 1.1
            
            # 1. Двухколоночная страница: удаляем колонку
            if page_info['is_two_column'] and is_narrow:
                if column_to_remove == 'left' and is_in_left:
                    stats['removed_full'] += 1
                    page.add_redact_annot(line_bbox + (-2, -2, 2, 2), fill=(1, 1, 1))
                    continue
                
                if column_to_remove == 'right' and is_in_right:
                    stats['removed_full'] += 1
                    page.add_redact_annot(line_bbox + (-2, -2, 2, 2), fill=(1, 1, 1))
                    continue
            
            # 2. Чистый нецелевой язык — удаляем
            if lang == remove_lang:
                stats['removed_full'] += 1
                page.add_redact_annot(line_bbox + (-2, -2, 2, 2), fill=(1, 1, 1))
                continue
            
            # 3. Чистый целевой язык — оставляем
            if lang == TARGET_LANG:
                stats['kept'] += 1
                continue
            
            # 4. Строка без букв
            if not line_info['has_letters']:
                orphan_lang = determine_orphan_language(line_info, all_lines, page_info)
                
                if orphan_lang == remove_lang:
                    stats['removed_orphans'] += 1
                    page.add_redact_annot(line_bbox + (-2, -2, 2, 2), fill=(1, 1, 1))
                    continue
                else:
                    stats['kept'] += 1
                    continue
            
            # 5. Смешанный текст — удаляем слова нецелевого языка
            if lang == 'mixed' and all_chars:
                check_func = is_latin if TARGET_LANG == 'ru' else is_cyrillic
                keep_func = is_cyrillic if TARGET_LANG == 'ru' else is_latin
                
                # Находим слова нецелевого языка (минимум 3 буквы подряд)
                word_regions = []
                word_start = None
                consecutive = 0
                
                for i, char_info in enumerate(all_chars):
                    char = char_info['char']
                    
                    if check_func(char):
                        if word_start is None:
                            word_start = i
                        consecutive += 1
                    else:
                        if word_start is not None and consecutive >= 3:
                            word_regions.append((word_start, i))
                        word_start = None
                        consecutive = 0
                
                if word_start is not None and consecutive >= 3:
                    word_regions.append((word_start, len(all_chars)))
                
                # Расширяем ОСТОРОЖНО — только на пробелы и разделители
                expanded_regions = []
                for start_idx, end_idx in word_regions:
                    actual_start = start_idx
                    actual_end = end_idx
                    
                    # Влево: только пробелы и разделители
                    while actual_start > 0:
                        prev_char = all_chars[actual_start - 1]['char']
                        if keep_func(prev_char):
                            break
                        if prev_char in ' \t/':
                            actual_start -= 1
                        else:
                            break
                    
                    # Вправо: только пробелы и разделители
                    while actual_end < len(all_chars):
                        next_char = all_chars[actual_end]['char']
                        if keep_func(next_char):
                            break
                        if next_char in ' \t/':
                            actual_end += 1
                        else:
                            break
                    
                    expanded_regions.append((actual_start, actual_end))
                
                # Объединяем
                merged_regions = []
                for region in sorted(expanded_regions):
                    if merged_regions and region[0] <= merged_regions[-1][1] + 1:
                        merged_regions[-1] = (merged_regions[-1][0], max(merged_regions[-1][1], region[1]))
                    else:
                        merged_regions.append(region)
                
                # Удаляем
                for start_idx, end_idx in merged_regions:
                    if start_idx < len(all_chars) and end_idx > 0 and end_idx > start_idx:
                        start_bbox = all_chars[start_idx]['bbox']
                        end_bbox = all_chars[min(end_idx - 1, len(all_chars) - 1)]['bbox']
                        
                        region_rect = fitz.Rect(
                            start_bbox.x0,
                            min(start_bbox.y0, end_bbox.y0) - 1,
                            end_bbox.x1,
                            max(start_bbox.y1, end_bbox.y1) + 1
                        )
                        page.add_redact_annot(region_rect, fill=(1, 1, 1))
                
                if merged_regions:
                    stats['removed_partial'] += 1
                else:
                    stats['kept'] += 1
                continue
            
            stats['kept'] += 1
        
        page.apply_redactions()
    
    doc.save(str(output_path), garbage=4, deflate=True, clean=True)
    doc.close()
    
    return stats

# ==================== MAIN ====================

def main():
    folder = Path(INPUT_FOLDER)
    
    if not folder.exists():
        print(f"❌ Папка не найдена: {folder}")
        return
    
    print(f"📁 Папка: {folder}")
    print(f"🔧 Версия: 18.0 (консервативная)")
    print(f"🎯 Оставляем: {'РУССКИЙ' if TARGET_LANG == 'ru' else 'АНГЛИЙСКИЙ'}")
    print("=" * 60)
    
    for f in folder.glob(f"*{OUTPUT_SUFFIX}.pdf"):
        f.unlink()
    for f in folder.glob("TEST*.pdf"):
        f.unlink()
    
    pdf_files = sorted([
        f for f in folder.glob("*.pdf") 
        if OUTPUT_SUFFIX not in f.stem and not f.name.startswith("TEST")
    ])
    
    if not pdf_files:
        print("⚠️  PDF не найдены")
        return
    
    print(f"📄 Файлов: {len(pdf_files)}\n")
    
    for idx, pdf_path in enumerate(pdf_files, 1):
        print(f"[{idx}/{len(pdf_files)}] {pdf_path.name}")
        
        output_path = folder / f"{pdf_path.stem}{OUTPUT_SUFFIX}.pdf"
        
        try:
            stats = process_pdf(pdf_path, output_path)
            
            print(f"   📊 Страниц: {stats['pages']} (двухкол.: {stats['two_col_pages']})")
            print(f"   ❌ Удалено строк: {stats['removed_full']}")
            print(f"   👻 Удалено номеров: {stats['removed_orphans']}")
            print(f"   ✂️  Частично: {stats['removed_partial']}")
            print(f"   ✅ Оставлено: {stats['kept']}")
            
            if output_path.exists():
                print(f"   💾 Создан: {output_path.name}")
                
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    print("=" * 60)
    print("✅ Готово!")

if __name__ == "__main__":
    main()


    