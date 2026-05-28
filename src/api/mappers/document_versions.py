# src/api/mappers/document_versions.py

"""
Мапперы для преобразования ORM-моделей версий документов в API-схемы.

Задачи этого модуля:
- разорвать жёсткую связь между слоем хранения (SQLAlchemy-модель DocumentVersion)
  и REST API, которое оперирует Pydantic-схемой DocumentVersionResponse;
- инкапсулировать в одном месте логику преобразования ORM-объекта версии документа
  в стабильный контракт API;
- использовать возможности Pydantic (model_validate, from_attributes), чтобы
  безопасно валидировать и сериализовать версии документов в JSON.

Где используется:
- при формировании детальной карточки документа (DocumentDetailResponse),
  когда нужно отдать клиенту информацию о последней версии документа;
- в сервисах/эндпоинтах, где требуется отдавать версии документов через внешнее API
  и не светить внутренние детали ORM-модели.
"""

from collections.abc import Iterable

from api.schemas.documents import DocumentVersionResponse
from db.models.document import DocumentVersion


def map_document_version_to_response(
    dv: DocumentVersion,
) -> DocumentVersionResponse:
    return DocumentVersionResponse.model_validate(dv)


def map_document_versions_to_response(
    versions: Iterable[DocumentVersion],
) -> list[DocumentVersionResponse]:
    return [map_document_version_to_response(v) for v in versions]
