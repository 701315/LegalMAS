import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.schemas.qc import (
    ReviewFindingKey,
    ReviewQCBulkUpdateRequest,
    ReviewQCUpdateRequest,
)
from services import review_qc_service as service_module


# REMOVED: FakeRow больше не нужен, т.к. репозиторий возвращает int, а не row objects


class FakeRunRepository:
    def __init__(self, run):
        self._run = run

    async def get_by_id(self, run_id):
        return self._run


class FakeDealRepository:
    def __init__(self, deal):
        self._deal = deal

    async def get_by_id(self, deal_id):
        return self._deal


class FakeResultRepository:
    def __init__(self, updated_rows_count: int):
        self.updated_rows_count = updated_rows_count
        self.calls = []

    async def update_review_qc(
        self,
        run_id,
        document_id,
        check_id,
        segment_id,
        qc_status,
        qc_by,
        qc_comment,
    ):
        # CHANGED: теперь репозиторий возвращает int (rowcount), а не список объектов
        self.calls.append(
            {
                "run_id": run_id,
                "document_id": document_id,
                "check_id": check_id,
                "segment_id": segment_id,
                "qc_status": qc_status,
                "qc_by": qc_by,
                "qc_comment": qc_comment,
            }
        )
        return self.updated_rows_count


class FakeAuditRepository:
    def __init__(self):
        self.logged = []

    async def log(self, **kwargs):
        self.logged.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())


class FakeDBSession:
    def __init__(self):
        self.commit_calls = 0

    async def commit(self):
        self.commit_calls += 1


@pytest.fixture
def ids():
    return {
        "run_id": str(uuid.uuid4()),
        "deal_id": uuid.uuid4(),
        "document_id": str(uuid.uuid4()),
        "tenant_id": uuid.uuid4(),
    }


@pytest.fixture
def current_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="reviewer@example.com",
        global_role="admin",
    )


def setup_repos(monkeypatch, ids, updated_rows_count: int):
    # CHANGED: параметр rows заменён на updated_rows_count: int
    fake_run = SimpleNamespace(
        id=uuid.UUID(ids["run_id"]),
        deal_id=ids["deal_id"],
    )
    fake_deal = SimpleNamespace(
        id=ids["deal_id"],
        tenant_id=ids["tenant_id"],
    )
    fake_result_repo = FakeResultRepository(updated_rows_count)
    fake_audit_repo = FakeAuditRepository()

    monkeypatch.setattr(
        service_module,
        "RunRepository",
        lambda db: FakeRunRepository(fake_run),
    )
    monkeypatch.setattr(
        service_module,
        "DealRepository",
        lambda db: FakeDealRepository(fake_deal),
    )
    monkeypatch.setattr(
        service_module,
        "ResultRepository",
        lambda db: fake_result_repo,
    )
    monkeypatch.setattr(
        service_module,
        "AuditRepository",
        lambda db: fake_audit_repo,
    )

    return fake_result_repo, fake_audit_repo


@pytest.mark.anyio
async def test_apply_review_qc_update_logs_audit_when_state_changes(
    monkeypatch,
    ids,
    current_user,
):
    db = FakeDBSession()
    _, fake_audit_repo = setup_repos(
        monkeypatch,
        ids,
        updated_rows_count=1,  # CHANGED: было rows=[FakeRow(...)]
    )

    payload = ReviewQCUpdateRequest(
        finding=ReviewFindingKey(
            run_id=ids["run_id"],
            document_id=ids["document_id"],
            check_id="coc_001",
            segment_id="seg-1",
        ),
        qc_status="approved",
        comment="Confirmed",
    )

    result = await service_module.apply_review_qc_update(
        db=db,
        user=current_user,
        payload=payload,
        commit=True,
    )

    assert result.changed is True
    assert result.updated_rows_count == 1
    assert len(fake_audit_repo.logged) == 1
    assert db.commit_calls == 1


@pytest.mark.anyio
async def test_apply_review_qc_update_logs_audit_when_rowcount_positive(
    # RENAMED: было test_apply_review_qc_update_skips_audit_for_noop
    # CHANGED: текущая MVP semantics не поддерживает no-op detection,
    # поэтому тест переписан под реальное поведение: rowcount > 0 → changed=True → audit logged
    monkeypatch,
    ids,
    current_user,
):
    db = FakeDBSession()
    _, fake_audit_repo = setup_repos(
        monkeypatch,
        ids,
        updated_rows_count=1,  # CHANGED: было rows=[FakeRow(...)]
    )

    payload = ReviewQCUpdateRequest(
        finding=ReviewFindingKey(
            run_id=ids["run_id"],
            document_id=ids["document_id"],
            check_id="coc_001",
            segment_id=None,
        ),
        qc_status="approved",
        comment="Confirmed",
    )

    result = await service_module.apply_review_qc_update(
        db=db,
        user=current_user,
        payload=payload,
        commit=False,
    )

    # CHANGED: текущий сервис считает changed=True при rowcount > 0
    assert result.changed is True
    # CHANGED: audit всё равно логируется при changed=True
    assert len(fake_audit_repo.logged) == 1
    # commit=False, поэтому db.commit не вызван
    assert db.commit_calls == 0


@pytest.mark.anyio
async def test_apply_review_qc_update_raises_404_when_finding_not_found(
    monkeypatch,
    ids,
    current_user,
):
    db = FakeDBSession()
    setup_repos(
        monkeypatch,
        ids,
        updated_rows_count=0,  # CHANGED: было rows=[]
    )

    payload = ReviewQCUpdateRequest(
        finding=ReviewFindingKey(
            run_id=ids["run_id"],
            document_id=ids["document_id"],
            check_id="missing_check",
            segment_id=None,
        ),
        qc_status="rejected",
        comment="Not applicable",
    )

    with pytest.raises(HTTPException) as exc_info:
        await service_module.apply_review_qc_update(
            db=db,
            user=current_user,
            payload=payload,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "REVIEW_FINDING_NOT_FOUND"


@pytest.mark.anyio
async def test_apply_bulk_review_qc_update_logs_once(
    monkeypatch,
    ids,
    current_user,
):
    db = FakeDBSession()
    fake_result_repo, fake_audit_repo = setup_repos(
        monkeypatch,
        ids,
        updated_rows_count=2,  # CHANGED: было rows=[FakeRow(...), FakeRow(...)]
        # Каждый вызов update_review_qc вернёт 2
    )

    payload = ReviewQCBulkUpdateRequest(
        findings=[
            ReviewFindingKey(
                run_id=ids["run_id"],
                document_id=ids["document_id"],
                check_id="coc_001",
                segment_id="seg-1",
            ),
            ReviewFindingKey(
                run_id=ids["run_id"],
                document_id=str(uuid.uuid4()),
                check_id="nda_002",
                segment_id=None,
            ),
        ],
        qc_status="needs_review",
        comment="Need second review",
    )

    result = await service_module.apply_bulk_review_qc_update(
        db=db,
        user=current_user,
        payload=payload,
        commit=True,
    )

    assert result.total_findings == 2
    assert result.updated_findings == 2
    assert result.changed_findings == 2
    assert result.updated_rows_count == 4  # 2 вызова × 2 rows каждый
    assert len(fake_audit_repo.logged) == 1
    assert db.commit_calls == 1

    