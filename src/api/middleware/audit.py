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

Трейсинг и logging correlation:
- middleware пишет один structured log ("HTTP request received") в начале
  обработки запроса, пока OpenTelemetry span ещё активен;
- в этот момент add_trace_context processor автоматически добавит
  trace_id и span_id в лог;
- это обеспечивает корреляцию: из лога можно перейти в trace в Grafana.
- технические пути (/metrics, /docs, /openapi.json) не логируются,
  чтобы не засорять логи.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging import clear_log_context, get_logger, set_request_context
from db.repositories.audit_repo import AuditRepository
from db.session import get_session

logger = get_logger(__name__)

# Точные пути (метод + путь), которые обязательно аудитим
# ключ: (HTTP-метод, путь), значение: action для AuditLog
_AUDITED_PATHS: dict[tuple[str, str], str] = {
    ("GET", "/admin/yaml-instructions"): "VIEW_YAML_INSTRUCTIONS",
}

# Суффиксы путей для динамических URL
# ключ: суффикс, значение: action
_AUDITED_PATH_SUFFIXES: dict[str, str] = {
    "/reclassify": "DOCUMENT_RECLASSIFIED_API",
    "/structured-data": "STRUCTURED_DATA_ACCESSED",
    "/tenant/dashboard": "ADMIN_VIEW_DASHBOARD",
    "/tenant/metrics": "ADMIN_VIEW_METRICS",
    "/tenant/logs": "ADMIN_VIEW_LOGS",
}

# Пути которые не нужно логировать в structured logs.
# Они очень частые и не несут бизнес-ценности для трейс-корреляции.
_SKIP_REQUEST_LOG_PREFIXES: tuple[str, ...] = (
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware, которое автоматически пишет аудит для выбранных запросов.

    Контракт:
    - не берёт db из Depends(get_db);
    - все операции с БД выполняет через отдельную сессию (get_session),
      чтобы не блокировать или не конфликтовать с транзакцией основного запроса;
    - любые ошибки внутри аудита проглатываются с логированием,
      ответ клиенту не меняется.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method
        path = request.url.path

        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        tenant_id_header = request.headers.get("X-Tenant-Id")
        user_id_header = request.headers.get("X-User-Id")
        actor_role_header = request.headers.get("X-Actor-Role")

        set_request_context(
            request_id=request_id,
            tenant_id=tenant_id_header,
            actor_role=actor_role_header,
        )
        request.state.request_id = request_id

        # -----------------------------------------------------------------
        # Structured request log — ключевая точка для trace correlation.
        #
        # Простым языком:
        # Этот лог пишется в самом начале обработки запроса, пока
        # OpenTelemetry span ещё активен. В этот момент наш processor
        # add_trace_context автоматически добавит trace_id и span_id.
        #
        # Результат: в каждой строке лога для HTTP-запроса будет trace_id,
        # по которому в Grafana можно нажать "View Trace" и сразу увидеть
        # визуальный путь этого запроса.
        #
        # Технические пути пропускаем — они не нужны для correlation
        # и только засоряют логи (Prometheus scrape каждые 15 секунд и т.д.)
        # -----------------------------------------------------------------
        _should_log = not any(
            path.startswith(prefix) for prefix in _SKIP_REQUEST_LOG_PREFIXES
        )
        if _should_log:
            logger.info(
                "HTTP request received",
                method=method,
                path=path,
                request_id=request_id,
                tenant_id=tenant_id_header,
            )

        try:
            action = _AUDITED_PATHS.get((method, path))

            if action is None:
                for suffix, suffix_action in _AUDITED_PATH_SUFFIXES.items():
                    if path.endswith(suffix):
                        action = suffix_action
                        break

            response = await call_next(request)
            response.headers.setdefault("X-Request-Id", request_id)

            # После call_next() request.state уже может быть заполнен
            # Depends(get_current_user), поэтому здесь читаем real identity.
            resolved_actor = (
                user_id_header
                or getattr(request.state, "user_id", None)
                or "unknown"
            )
            resolved_tenant_id_value = (
                tenant_id_header
                or getattr(request.state, "tenant_id", None)
            )
            resolved_actor_role = (
                actor_role_header
                or getattr(request.state, "actor_role", None)
            )

            # -----------------------------------------------------------------
            # Response log — фиксируем статус ответа и время.
            #
            # Простым языком:
            # После того как эндпоинт отработал, логируем статус ответа.
            # К этому моменту span ещё не закрыт, поэтому trace_id
            # тоже попадёт в этот лог.
            # -----------------------------------------------------------------
            if _should_log:
                logger.info(
                    "HTTP request completed",
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    request_id=request_id,
                )

            if action is None:
                return response

            if response.status_code >= 400:
                return response

            try:
                tenant_uuid = (
                    uuid.UUID(str(resolved_tenant_id_value))
                    if resolved_tenant_id_value
                    else uuid.UUID(int=0)
                )

                async with get_session() as session:
                    repo = AuditRepository(session)
                    await repo.log(
                        tenant_id=tenant_uuid,
                        action=action,
                        actor=str(resolved_actor),
                        deal_id=None,
                        actor_role=resolved_actor_role,
                        details={
                            "request_id": request_id,
                            "path": path,
                            "method": method,
                            "status_code": response.status_code,
                        },
                    )
                    await session.commit()

            except Exception:
                logger.exception(
                    "Audit middleware failed to write audit log",
                    path=path,
                    method=method,
                    action=action,
                    tenant_id=(
                        str(resolved_tenant_id_value)
                        if resolved_tenant_id_value is not None
                        else None
                    ),
                    actor=str(resolved_actor),
                    actor_role=resolved_actor_role,
                    request_id=request_id,
                )

            return response
        finally:
            clear_log_context()


            