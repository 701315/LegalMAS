import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

import api.middleware.audit as audit_middleware
from api.deps.auth import get_current_user
from api.main import app

from db.models.bundle import Bundle
from db.models.deal import Deal
from db.models.document import Document
from db.models.ops import AuditLog
from db.models.playbook import PlaybookVersion
from db.models.result import CheckResult
from db.models.run import Run
from db.session import engine, get_session


@pytest_asyncio.fixture(scope="function")
async def db_session():
    # В тестах используется глобальный async engine из приложения.
    # pytest-asyncio создаёт function-scoped event loops, поэтому pooled
    # asyncpg connections могут оказаться привязаны к старому loop.
    # Полный dispose перед/после теста делает fixture loop-safe.
    await engine.dispose()
    async with get_session() as session:
        await session.execute(text("DELETE FROM audit_logs"))
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client():
    app.dependency_overrides.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


async def create_tenant(session, tenant_id, name):
    slug = f"test-{uuid.uuid4().hex[:8]}"
    await session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, is_active) "
            "VALUES (:id, :name, :slug, true) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": tenant_id, "name": name, "slug": slug},
    )
    await session.flush()


def _override_current_user(*, user_id: uuid.UUID, tenant_id: uuid.UUID, global_role: str = "tenant_admin"):
    async def _dependency(request: Request):
        # Для audit middleware canonical identity должна идти через request.state,
        # а не через клиентские X-* headers.
        request.state.user_id = user_id
        request.state.tenant_id = tenant_id
        request.state.actor_role = global_role
        return SimpleNamespace(
            id=user_id,
            tenant_id=tenant_id,
            global_role=global_role,
        )

    return _dependency


@pytest.mark.asyncio
async def test_reproduce_unauthorized_deal_access(client: AsyncClient, db_session):
    """РЕПРОДУКЦИЯ НАХОДКИ №8: анонимный доступ к сделке должен быть запрещён."""
    t_id = uuid.uuid4()
    await create_tenant(db_session, t_id, "Tenant A")

    d_id = uuid.uuid4()
    new_deal = Deal(id=d_id, tenant_id=t_id, name="Secret Deal", status="active")
    db_session.add(new_deal)
    await db_session.commit()

    response = await client.get(f"/api/v1/deals/{d_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reproduce_cross_tenant_evidence_leakage(client: AsyncClient, db_session):
    """РЕПРОДУКЦИЯ НАХОДКИ №17: tenant A не должен получать evidence tenant B."""
    # Tenant A (attacker)
    ta_id = uuid.uuid4()
    await create_tenant(db_session, ta_id, "Attacker")

    # Tenant B (victim)
    tb_id = uuid.uuid4()
    await create_tenant(db_session, tb_id, "Victim")

    db_id = uuid.uuid4()
    deal_b = Deal(id=db_id, tenant_id=tb_id, name="B Deal")
    db_session.add(deal_b)
    await db_session.flush()

    bundle_id = uuid.uuid4()
    bundle_b = Bundle(
        id=bundle_id,
        deal_id=db_id,
    )
    db_session.add(bundle_b)
    await db_session.flush()

    document_id = uuid.uuid4()
    document_b = Document(
        id=document_id,
        deal_id=db_id,
        bundle_id=bundle_id,
        filename="victim.pdf",
    )
    db_session.add(document_b)
    await db_session.flush()

    playbook_version_id = uuid.uuid4()
    playbook_version = PlaybookVersion(
        id=playbook_version_id,
        name="test-playbook",
        semver="0.0.1",
        compiled_checks={},
        status="published",
    )
    db_session.add(playbook_version)
    await db_session.flush()

    run_id = uuid.uuid4()
    run_b = Run(
        id=run_id,
        deal_id=db_id,
        tenant_id=tb_id,
        playbook_version_id=playbook_version_id,
        status="completed",
    )
    db_session.add(run_b)
    await db_session.flush()

    res_id = uuid.uuid4()
    result_b = CheckResult(
        id=res_id,
        run_id=run_id,
        document_id=document_id,
        check_id="check_001",
        check_name="Test check",
        result="fail",
        severity="critical",
        display_text="SECRET",
    )
    db_session.add(result_b)
    await db_session.commit()

    attacker_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _override_current_user(
        user_id=attacker_user_id,
        tenant_id=ta_id,
        global_role="tenant_admin",
    )

    response = await client.get(f"/api/v1/results/{res_id}/evidence")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reproduce_audit_identity_spoofing(client: AsyncClient, db_session, monkeypatch):
    """РЕПРОДУКЦИЯ НАХОДКИ №2: X-User-Id не должен подменять actor в audit log."""
    tenant_id = uuid.uuid4()
    await create_tenant(db_session, tenant_id, "Tenant A")

    real_user_id = uuid.uuid4()
    fake_actor = str(uuid.uuid4())

    app.dependency_overrides[get_current_user] = _override_current_user(
        user_id=real_user_id,
        tenant_id=tenant_id,
        global_role="tenant_admin",
    )

    # Маршрут /api/v1/deals/ по умолчанию не входит в audited paths middleware,
    # поэтому локально помечаем его как аудируемый для изолированного security test.
    monkeypatch.setitem(
        audit_middleware._AUDITED_PATHS,
        ("GET", "/api/v1/deals/"),
        "TEST_VIEW_DEALS",
    )

    response = await client.get(
        "/api/v1/deals/",
        headers={"X-User-Id": fake_actor},  # попытка spoofing
    )
    assert response.status_code == 200

    res = await db_session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1)
    )
    log = res.scalar_one_or_none()

    assert log is not None
    assert str(log.actor) == str(real_user_id)
    assert str(log.actor) != fake_actor


    