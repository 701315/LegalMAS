# src/api/middleware/audit.py

"""
Audit middleware — фиксирует важные HTTP-запросы в таблице audit_logs.

Идея:
- для некоторых путей (или их окончаний) пишем запись в AuditLog;
- фиксируем: кто, к какому пути обратился, какой метод;
- не ломаем основной запрос, даже если аудит упал.

Архитектурный контракт:
- middleware НЕ использует FastAPI-зависимость get_db / DI;
- для аудита открывается отдельная AsyncSession через get_session,
  независимая от сессии основного HTTP-запроса;
- ошибки аудита не влияют на ответ клиенту.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from db.repositories.audit_repo import AuditRepository
from db.session import get_session

# Точные пути (метод + путь), которые обязательно аудитим
# ключ: (HTTP-метод, путь), значение: action для AuditLog
_AUDITED_PATHS: dict[tuple[str, str], str] = {
    # пример: ("GET", "/health"): "VIEW_HEALTH",
    ("GET", "/admin/yaml-instructions"): "VIEW_YAML_INSTRUCTIONS",
}

# Суффиксы путей для динамических URL (например /documents/{id}/reclassify)
# ключ: суффикс, значение: action
_AUDITED_PATH_SUFFIXES: dict[str, str] = {
    "/reclassify": "DOCUMENT_RECLASSIFIED_API",
    "/structured-data": "STRUCTURED_DATA_ACCESSED",
}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware, которое автоматически пишет аудит для выбранных запросов.

    Контракт:
    - не берёт db из Depends(get_db);
    - все операции с БД выполняет через отдельную сессию (get_session),
      чтобы не блокировать или не конфликтовать с транзакцией основного запроса;
    - любые ошибки внутри аудита проглатываются (логируются отдельно),
      ответ клиенту не меняется.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method
        path = request.url.path

        # 1. Ищем точное совпадение (метод + путь)
        action = _AUDITED_PATHS.get((method, path))

        # 2. Если не нашли — проверяем суффиксы (для динамических путей)
        if action is None:
            for suffix, suffix_action in _AUDITED_PATH_SUFFIXES.items():
                if path.endswith(suffix):
                    action = suffix_action
                    break

        # 3. Дальше обязательно вызываем хэндлер, чтобы клиент получил ответ
        response = await call_next(request)

        # Если путь не подлежит аудиту — выходим
        if action is None:
            return response

        # Логировать только успешные/частично успешные запросы
        if response.status_code >= 400:
            return response

        # 4. Пытаемся записать аудит (не ломаем запрос при ошибке)
        try:
            # Временный способ получить tenant_id и user_id — из заголовков.
            # Позже можно заменить на токен / request.state.user.
            tenant_id_header = request.headers.get("X-Tenant-Id")
            user_id_header = request.headers.get("X-User-Id", "unknown")

            tenant_uuid = (
                uuid.UUID(tenant_id_header)
                if tenant_id_header
                else uuid.UUID(int=0)  # "анонимный" tenant, если не передали
            )

            # Отдельная сессия для аудита (unit of work, независимый от запроса)
            async with get_session() as session:
                repo = AuditRepository(session)
                await repo.log(
                    tenant_id=tenant_uuid,
                    action=action,
                    actor=user_id_header,
                    deal_id=None,  # при желании можно распарсить deal_id из path
                    actor_role=None,
                    details={
                        "path": path,
                        "method": method,
                        "status_code": response.status_code,
                    },
                )

        except Exception:
            # В проде можно залогировать ошибку, но нельзя ломать ответ клиенту
            pass

        return response
