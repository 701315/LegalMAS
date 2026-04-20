import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.check_result_persist_error import CheckResultPersistError


class CheckResultPersistErrorRepository:
    """
    Repository для записи и выборки ошибок persist слоя check_results.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_error(
        self,
        *,
        run_id: uuid.UUID | None,
        document_id: uuid.UUID | None,
        check_id: str | None,
        payload: dict[str, Any],
        error_type: str | None,
        sqlstate: str | None,
        error_message: str | None,
        retryable: bool = True,
    ) -> CheckResultPersistError:
        obj = CheckResultPersistError(
            run_id=run_id,
            document_id=document_id,
            check_id=check_id,
            payload=payload,
            error_type=error_type,
            sqlstate=sqlstate,
            error_message=error_message,
            retryable=retryable,
            attempts=0,
            last_attempt_at=None,
            resolved_at=None,
            resolution_status="open",
            resolution_comment=None,
        )
        self.session.add(obj)
        await self.session.flush()
        return obj

        