"""
Database Unit of Work (UoW).

Определяет единицу работы с базой данных для одной бизнес‑операции
(например, обработка одного документа или одной задачи worker'а).

Задачи:
- создавать отдельную AsyncSession для каждой операции;
- гарантировать целостность: либо все изменения в рамках операции
  фиксируются (commit), либо полностью откатываются (rollback);
- централизованно управлять жизненным циклом сессии (открытие,
  commit/rollback, закрытие), чтобы доменный код не трогал глобальный
  engine/get_session и не создавал скрытых транзакций.

Используется worker'ами и сервисами для явного разделения
"одна задача — один unit of work".
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import AsyncSessionLocal


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


@asynccontextmanager
async def db_uow() -> AsyncGenerator[UnitOfWork, None]:
    session = AsyncSessionLocal()
    uow = UnitOfWork(session)
    try:
        yield uow
        await uow.commit()
    except Exception:
        await uow.rollback()
        raise
    finally:
        await session.close()
