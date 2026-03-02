"""
Database Unit of Work (UoW).

Определяет единицу работы с базой данных для одной бизнес‑операции
(например, обработка одного документа или одной задачи worker'а).

Задачи:
- создавать отдельную AsyncSession для каждой операции;
- гарантировать целостность: либо все изменения в рамках операции
  фиксируются (commit), либо полностью откатываются (rollback);
- централизованно управлять жизненным циклом сессии (открытие,
  commit/rollback, закрытие), чтобы доменный код работал только с
  репозиториями (documents, check_results и др.), а не напрямую с session.

Используется worker'ами, Runner'ом и сервисами для явного разделения
"одна задача — один unit of work".
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.check_result_repo import CheckResultRepository
from src.db.repositories.document_repo import DocumentRepository
from src.db.session import AsyncSessionLocal


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        # Репозиторий документов — источник истины для Runner / HybridClassifier.
        self.documents = DocumentRepository(session)
        # Репозиторий результатов проверок — для Runner / CheckRunner.
        self.check_results = CheckResultRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


@asynccontextmanager
async def db_uow() -> AsyncGenerator[UnitOfWork, None]:
    """
    Асинхронный контекстный менеджер UoW.

    Пример использования:

        async with db_uow() as uow:
            runner = Runner(uow)
            stats = await runner.run_deal(deal_id)
    """
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
