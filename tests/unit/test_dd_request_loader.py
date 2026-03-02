"""Unit tests for DD Request Template Loader."""

import pytest
import yaml

from src.services.export.dd_request_loader import DDRequestTemplateLoader

SAMPLE_YAML = {
    "type": "contract_1.1_spa",
    "dd_request_templates": {
        "coc_001": {
            "text": "Запрос по смене контроля в {doc_names}.",
            "addressee": "Юридический советник продавца",
        },
        "_default": {
            "text": "Запрос по «{check_name}» в {doc_names}.",
            "addressee": "Юридический советник",
        },
    },
}


@pytest.fixture
def templates_dir(tmp_path):
    f = tmp_path / "contract_1.1_spa.yaml"
    with open(f, "w", encoding="utf-8") as fh:
        yaml.dump(SAMPLE_YAML, fh, allow_unicode=True)
    return str(tmp_path)


class TestDDRequestTemplateLoader:
    def test_exact_match(self, templates_dir):
        loader = DDRequestTemplateLoader(templates_dir)
        text, addressee = loader.render("coc_001", "Change of Control", ["SPA_Doc.pdf"])
        assert "смене контроля" in text
        assert addressee == "Юридический советник продавца"

    def test_prefix_match_builtin(self, templates_dir):
        loader = DDRequestTemplateLoader(templates_dir)
        text, addressee = loader.render("termination_001", "Termination", ["Doc.pdf"])
        assert "расторжения" in text.lower() or "termination" in text.lower()

    def test_default_fallback(self, templates_dir):
        loader = DDRequestTemplateLoader(templates_dir)
        text, addressee = loader.render("unknown_999", "Unknown Check", ["Doc.pdf"])
        assert "Unknown Check" in text or "запрос" in text.lower()

    def test_multiple_docs(self, templates_dir):
        loader = DDRequestTemplateLoader(templates_dir)
        docs = ["Doc1.pdf", "Doc2.pdf", "Doc3.pdf"]
        text, _ = loader.render("coc_001", "CoC", docs)
        assert "Doc1.pdf" in text or "«Doc1.pdf»" in text

    def test_more_than_five_docs(self, templates_dir):
        loader = DDRequestTemplateLoader(templates_dir)
        docs = [f"Doc{i}.pdf" for i in range(8)]
        text, _ = loader.render("coc_001", "CoC", docs)
        assert "ещё" in text

    def test_missing_dir_uses_builtin(self, tmp_path):
        loader = DDRequestTemplateLoader(str(tmp_path / "nonexistent"))
        text, _ = loader.render("coc_001", "CoC", ["Doc.pdf"])
        assert len(text) > 10

    def test_cache(self, templates_dir):
        loader = DDRequestTemplateLoader(templates_dir)
        t1 = loader.get_all_templates()
        t2 = loader.get_all_templates()
        assert t1 is t2
