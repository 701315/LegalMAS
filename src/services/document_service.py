# src/services/document_service.py

"""
Сервис для работы с отдельными документами на уровне бизнес-логики.

Задачи этого модуля:
- инкапсулировать операции над документом (поиск по id, обновление флагов)
  поверх сырого SQLAlchemy-сессии;
- предоставить прикладной метод set_reviewed_flag, который отвечает за
  изменение статуса reviewed_by_person и возврат обновлённого документа в
  виде стабильной API-схемы DocumentResponse;
- централизовать обработку ситуации, когда документ не найден
  (через исключение DocumentNotFoundError), чтобы контроллеры не работали
  напрямую с результатами SQL-запросов.

Где используется:
- в REST-эндпоинтах, где нужно пометить документ как просмотренный
  пользователем и сразу вернуть его актуальное состояние клиенту;
- в сервисном слое, чтобы не дублировать SQL и маппинг Document → DocumentResponse
  в нескольких местах приложения.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from api.mappers.documents import map_document_to_response

from db.models.document import Document
from api.schemas.documents import DocumentResponse


class DocumentNotFoundError(Exception):
    pass


class DocumentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_reviewed_flag(
        self,
        doc_id: uuid.UUID,
        reviewed_by_person: bool,
    ) -> DocumentResponse:
        """
        Установить флаг reviewed_by_person у документа и вернуть обновлённый документ.
        """
        stmt = select(Document).where(Document.id == doc_id)
        result = await self.session.execute(stmt)
        document: Optional[Document] = result.scalar_one_or_none()

        if document is None:
            raise DocumentNotFoundError

        document.reviewed_by_person = reviewed_by_person
        await self.session.commit()
        await self.session.refresh(document)

        return map_document_to_response(document)