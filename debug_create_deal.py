import asyncio
import uuid

from src.queue.async_helpers import get_worker_session
from src.db.repositories import DealRepository

TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def main():
    async with get_worker_session() as session:
        repo = DealRepository(session)
        deal = await repo.create(
            tenant_id=uuid.UUID(TENANT_ID),
            name="DEBUG Vertical Slice Deal",
            deal_type="SPA",
        )
        print("DEBUG: created deal", deal.id)


if __name__ == "__main__":
    asyncio.run(main())
