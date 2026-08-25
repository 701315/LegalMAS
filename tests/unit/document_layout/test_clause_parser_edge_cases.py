"""
Тесты для parse_llm_response() — edge cases.

Проверяет устойчивость парсера к:
- markdown-обёрткам
- невалидному JSON
- missing required fields
- дубликатам uid
"""

from services.structure._clause_detector.parser import parse_llm_response


def test_markdown_wrapper():
    """LLM вернул JSON в markdown-обёртке."""
    raw_response = '''
    Вот результат анализа:
    ```json
    {"clauses": [{"uid": "1.1", "title": "Тест", "quote_start": "текст", "quote_end": "конец"}]}
    ```
    '''
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 1
    assert clauses[0].uid == "1.1"


def test_json_embedded_in_text():
    """LLM вернул JSON внутри текста (без markdown)."""
    raw_response = '''
    Я проанализировал главу 1 и нашёл следующие пункты:
    {"clauses": [{"uid": "1.1", "title": "Тест", "quote_start": "текст", "quote_end": "конец"}]}
    Надеюсь, это поможет!
    '''
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 1
    assert clauses[0].uid == "1.1"


def test_missing_clauses_key():
    """LLM вернул JSON, но без ключа "clauses"."""
    raw_response = '{"items": [], "reasoning": "no clauses found"}'
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 0


def test_missing_required_field():
    """В пункте отсутствует обязательное поле."""
    raw_response = '{"clauses": [{"uid": "1.1", "title": "Тест"}]}'  # нет quote_start/quote_end
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 0


def test_duplicate_uid():
    """Дубликаты uid игнорируются."""
    raw_response = '''
    {"clauses": [
        {"uid": "1.1", "title": "Первый", "quote_start": "текст", "quote_end": "конец"},
        {"uid": "1.1", "title": "Дубликат", "quote_start": "текст", "quote_end": "конец"}
    ]}
    '''
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 1
    assert clauses[0].title == "Первый"


def test_empty_response():
    """Пустой ответ."""
    clauses = parse_llm_response("", "1")
    assert len(clauses) == 0


def test_invalid_json():
    """Невалидный JSON."""
    raw_response = '{"clauses": [invalid json]}'
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 0


def test_extra_keys_ignored():
    """Лишние ключи в JSON игнорируются."""
    raw_response = '''
    {"clauses": [{"uid": "1.1", "title": "Тест", "quote_start": "текст", "quote_end": "конец"}],
     "extra_key": "should be ignored",
     "reasoning": "also ignored"}
    '''
    clauses = parse_llm_response(raw_response, "1")
    assert len(clauses) == 1



    