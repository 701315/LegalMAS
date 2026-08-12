from services.embeddings._preprocess import (
    apply_embedding_role_prefix,
    truncate_text_to_token_limit,
)


class _FakeTokenizer:
    def __call__(self, text, add_special_tokens=False, truncation=False, return_attention_mask=False):
        # Простая токенизация по пробелам для unit test
        return {"input_ids": text.split()}

    def decode(self, input_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True):
        return " ".join(input_ids)


def test_apply_embedding_role_prefix_query():
    assert apply_embedding_role_prefix("hello world", role="query") == "query: hello world"


def test_apply_embedding_role_prefix_passage():
    assert apply_embedding_role_prefix("hello world", role="passage") == "passage: hello world"


def test_apply_embedding_role_prefix_unknown_role_falls_back_to_passage():
    assert apply_embedding_role_prefix("hello world", role="unknown") == "passage: hello world"


def test_truncate_text_to_token_limit_short_text_no_truncation():
    tokenizer = _FakeTokenizer()
    text = "one two three"
    truncated, was_truncated, original_tokens = truncate_text_to_token_limit(
        tokenizer=tokenizer,
        text=text,
        max_tokens=10,
    )

    assert truncated == text
    assert was_truncated is False
    assert original_tokens == 3


def test_truncate_text_to_token_limit_long_text_truncates():
    tokenizer = _FakeTokenizer()
    text = "one two three four five six"
    truncated, was_truncated, original_tokens = truncate_text_to_token_limit(
        tokenizer=tokenizer,
        text=text,
        max_tokens=3,
    )

    assert truncated == "one two three"
    assert was_truncated is True
    assert original_tokens == 6


    