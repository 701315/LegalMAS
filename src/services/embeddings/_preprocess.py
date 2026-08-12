# src/services/embeddings/_preprocess.py

"""
Pure helpers for embedding text preprocessing.

Вынесены в отдельный модуль чтобы:
- не тянуть загрузку real SentenceTransformer в unit tests,
- тестировать truncation и role-prefix как чистую логику.
"""

from __future__ import annotations

from typing import Any


def apply_embedding_role_prefix(text: str, role: str = "passage") -> str:
    """
    Add E5-compatible role prefix.

    Supported roles:
    - query   -> "query: "
    - passage -> "passage: "
    Any unknown role falls back to "passage".
    """
    prefix = "query: " if role == "query" else "passage: "
    return prefix + (text or "")


def truncate_text_to_token_limit(
    tokenizer: Any,
    text: str,
    max_tokens: int,
) -> tuple[str, bool, int]:
    """
    Truncate text explicitly to max_tokens using the model tokenizer.

    Returns:
    - truncated_text
    - was_truncated: bool
    - original_token_count: int

    Contract:
    - if original token count <= max_tokens -> text unchanged, was_truncated=False
    - if original token count > max_tokens  -> decode first max_tokens back to text
    """
    if not text:
        return text, False, 0

    if max_tokens <= 0:
        return text, False, 0

    encoded = tokenizer(
        text,
        add_special_tokens=False,
        truncation=False,
        return_attention_mask=False,
    )
    input_ids = encoded.get("input_ids") or []
    original_token_count = len(input_ids)

    if original_token_count <= max_tokens:
        return text, False, original_token_count

    truncated_ids = input_ids[:max_tokens]
    truncated_text = tokenizer.decode(
        truncated_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    ).strip()

    # Defensive fallback: если decode почему-то дал пустую строку,
    # возвращаем исходный text чтобы не ломать encode path.
    if not truncated_text:
        return text, False, original_token_count

    return truncated_text, True, original_token_count


