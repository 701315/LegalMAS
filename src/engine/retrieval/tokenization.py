# src/engine/retrieval/tokenization.py

"""
Простейший счётчик "токенов" для чанка.

Для непрофессионального программиста:
- Считаем слова, умножаем на коэффициент компенсации под кириллицу.
- LLaMA-токенизатор разбивает русские слова на 2-3 субтокена (байты UTF-8).
- CYRILLIC_TOKEN_FACTOR = 2.5 — консервативная оценка для смешанного
  русско-английского юридического текста.
- В будущем заменить на tiktoken/sentencepiece без изменения остального кода.
"""

from __future__ import annotations

CYRILLIC_TOKEN_FACTOR = 3.8  # слово → ~3.8 токена модели для кириллицы


def count_tokens(text: str) -> int:
    """
    Подсчитать приблизительное количество токенов модели в строке.

    Сейчас: количество слов × CYRILLIC_TOKEN_FACTOR.
    Потом: заменить тело на вызов настоящего токенизатора.
    """
    if not text:
        return 0
    words = len([w for w in text.split() if w])
    return int(words * CYRILLIC_TOKEN_FACTOR)
