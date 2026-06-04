from services.structure._models._constants import DEFAULT_SCOPE
from services.structure._models._normalization import (
    _normalize_scope_name_ascii,
    _validate_scope_name,
)


def test_ascii_scope_name_unchanged():
    assert _normalize_scope_name_ascii("main_contract") == "main_contract"
    assert _validate_scope_name("main_contract") == "main_contract"


def test_cyrillic_appendix_letter_becomes_codepoint_token():
    assert _normalize_scope_name_ascii("appendix_м") == "appendix_u043c"
    assert _validate_scope_name("appendix_м") == "appendix_u043c"


def test_unicode_mixed_scope_name_is_deterministically_ascii():
    assert _normalize_scope_name_ascii("schedule_附录") == "schedule_u9644_u5f55"
    assert _validate_scope_name("schedule_附录") == "schedule_u9644_u5f55"


def test_scope_name_collapses_separators():
    assert _normalize_scope_name_ascii(" Appendix   М ") == "appendix_u043c"
    assert _validate_scope_name(" Appendix   М ") == "appendix_u043c"


def test_empty_scope_falls_back_to_default():
    assert _normalize_scope_name_ascii("") == DEFAULT_SCOPE
    assert _validate_scope_name("") == DEFAULT_SCOPE

    