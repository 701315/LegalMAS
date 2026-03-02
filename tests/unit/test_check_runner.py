import uuid
from types import SimpleNamespace

import pytest

from src.engine.checks_runner import CheckRunner
from src.engine.playbook.models import (
    CheckDefinition,
    ConditionalConfig,
    LLMConfig,
    RetrievalConfig,
    RulesConfig,
)


class DummyLLMClient:
    def complete(self, prompt: str) -> str:
        return '{"found": false, "evidence": "", "confidence": 0.0}'


class DummyUoW:
    """Фейковый UoW, имитирующий контекстный менеджер db_uow()."""

    def __init__(self):
        self.session = SimpleNamespace()
        self.check_results = SimpleNamespace(create=self._fake_create)
        self.created_dtos = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def _fake_create(self, dto):
        self.created_dtos.append(dto)
        return dto


@pytest.fixture
def sample_doc():
    return SimpleNamespace(
        id=uuid.uuid4(),
        doc_type="SPA",
        applicable_triggers=["coc"],
        text="Some contract text about change of control.",
    )


@pytest.fixture
def sample_check():
    return CheckDefinition(
        id="chk_1",
        name="Change of Control",
        description="Detect change of control clause",
        doc_types=["SPA"],
        severity="critical",
        rules=RulesConfig(
            keywords=["change of control"],
        ),
        llm=LLMConfig(),
        retrieval=RetrievalConfig(context_k=1),
        conditional=ConditionalConfig(trigger="coc"),
    )


@pytest.mark.asyncio
async def test_run_checks_for_document_builds_correct_dto(monkeypatch, sample_doc, sample_check):
    """Проверяем, что _run_checks_for_document мапит exec_result в dto для CheckResult."""
    llm_client = DummyLLMClient()
    runner = CheckRunner(llm_client=llm_client)

    # 1. Подменяем db_uow, чтобы внутри CheckRunner использовался наш DummyUoW
    dummy_uow = DummyUoW()

    def fake_db_uow():
        # db_uow() возвращает асинхронный контекстный менеджер,
        # поэтому здесь просто возвращаем наш DummyUoW
        return dummy_uow

    monkeypatch.setattr("src.engine.checks_runner.db_uow", fake_db_uow)

    # 2. Мокаем executor.execute, чтобы он вернул контролируемый exec_result
    def fake_execute(doc, check, chunks):
        return {
            "doc_id": str(doc.id),
            "check_id": check.id,
            "check_name": check.name,
            "result": "fail",
            "found": True,
            "evidence": "change of control",
            "confidence": 0.9,
            "severity": "critical",
            "detector_method": "rules",
            "reason": "Found change of control clause",
            "sources": [{"page": 1}],
            "location": {"page": 1},
            "raw": {
                "source": "rules_confident",
                "rules_confidence": 0.9,
                "llm_confidence": 0.0,
            },
        }

    runner.executor.execute = fake_execute

    run_id = uuid.uuid4()
    playbook = SimpleNamespace(get_conditional_checks=lambda doc_type, triggers: [sample_check])

    total, failed = await runner._run_checks_for_document(
        doc=sample_doc,
        run_id=run_id,
        playbook=playbook,
    )

    assert total == 1
    assert failed == 1

    assert len(dummy_uow.created_dtos) == 1
    dto = dummy_uow.created_dtos[0]

    assert dto["run_id"] == run_id
    assert dto["document_id"] == sample_doc.id
    assert dto["check_id"] == sample_check.id
    assert dto["check_name"] == sample_check.name
    assert dto["result"] == "fail"
    assert dto["severity"] == "critical"
    assert dto["confidence"] == 0.9

    assert dto["value_text"] == "Found change of control clause"
    assert dto["evidence_ref"] == "change of control"

    assert dto["detector_used"] == "rules"

    qf = dto["quality_flags"]
    assert qf["source"] == "rules_confident"
    assert qf["rules_confidence"] == 0.9
    assert qf["llm_confidence"] == 0.0
    assert "raw" in qf

    assert dto["conditional_check_triggered"] is True
    assert dto["trigger_name"] == "coc"
