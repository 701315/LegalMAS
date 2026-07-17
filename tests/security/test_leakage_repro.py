import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, text

# Импорты
from api.main import app
from db.session import get_session
from db.models.deal import Deal
from db.models.result import CheckResult
from db.models.ops import AuditLog

@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with get_session() as session:
        # Очищаем логи перед тестом
        await session.execute(text("DELETE FROM audit_logs"))
        yield session
        await session.rollback()

@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

async def create_tenant(session, tenant_id, name):
    """Вспомогательная функция с учетом поля slug"""
    slug = f"test-{uuid.uuid4().hex[:8]}"
    await session.execute(
        text("INSERT INTO tenants (id, name, slug, is_active) VALUES (:id, :name, :slug, true) ON CONFLICT DO NOTHING"),
        {"id": tenant_id, "name": name, "slug": slug}
    )
    await session.flush()

@pytest.mark.asyncio
async def test_reproduce_unauthorized_deal_access(client: AsyncClient, db_session):
    """РЕПРОДУКЦИЯ НАХОДКИ №8: Анонимный доступ к сделке"""
    t_id = uuid.uuid4()
    await create_tenant(db_session, t_id, "Tenant A")
    
    d_id = uuid.uuid4()
    new_deal = Deal(id=d_id, tenant_id=t_id, name="Secret Deal", status="active")
    db_session.add(new_deal)
    await db_session.commit()

    response = await client.get(f"/api/v1/deals/{d_id}")
    # Теперь здесь будет 401, так как мы добавили Depends(get_current_user)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reproduce_cross_tenant_evidence_leakage(client: AsyncClient, db_session):
    """РЕПРОДУКЦИЯ НАХОДКИ №17: Кросс-тенантная утечка Evidence"""
    # 1. Тенант Б (Жертва)
    tb_id = uuid.uuid4()
    await create_tenant(db_session, tb_id, "Victim")
    db_id = uuid.uuid4()
    deal_b = Deal(id=db_id, tenant_id=tb_id, name="B Deal")
    db_session.add(deal_b)
    await db_session.flush()

    res_id = uuid.uuid4()
    result_b = CheckResult(
        id=res_id, deal_id=db_id, document_id=uuid.uuid4(),
        run_id=uuid.uuid4(), result="fail", severity="critical",
        display_text="SECRET"
    )
    db_session.add(result_b)
    await db_session.commit()

    # 2. Запрос от имени Тенанта А (валидный токен, но чужой тенант)
    # Используем твой реальный токен для теста, чтобы он прошел AuthMiddleware
    real_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." # Подставь сюда начало своего токена
    headers = {"Authorization": f"Bearer {real_token}"}
    
    response = await client.get(f"/api/v1/results/{res_id}/evidence", headers=headers)
    # Должно быть 404, так как эндпоинт теперь фильтрует по тенанту из токена
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_reproduce_audit_identity_spoofing(client: AsyncClient, db_session):
    """РЕПРОДУКЦИЯ НАХОДКИ №2: Подмена личности в аудит-лог"""
    fake_actor = str(uuid.uuid4())
    real_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." # Твой токен
    
    headers = {
        "Authorization": f"Bearer {real_token}",
        "X-User-Id": fake_actor # Попытка подмены
    }
    
    # Эндпоинт, который в аудите и который точно пустит (например, список сделок)
    await client.get("/api/v1/deals/", headers=headers)

    res = await db_session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1))
    log = res.scalar_one_or_none()

    # В базе должен быть ID из ТОКЕНА, а не fake_actor
    assert str(log.actor) != fake_actor


    