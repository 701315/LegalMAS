# src/api/endpoints/auth.py

"""
Эндпоинты авторизации / аутентификации для FastAPI.

ТЕКУЩЕЕ СОСТОЯНИЕ (ВРЕМЕННО, ДЛЯ РАЗРАБОТКИ)
--------------------------------------------
Сейчас здесь реализован очень простой вариант логина:

- Есть один «админ» пользователь с логином "admin" и паролем "admin".
- При успешном логине возвращаем:
    - фиктивный access_token (строка "admin-token");
    - объект пользователя в формате CurrentUser (id, global_role, tenant_id, email).
- Никакого реального хранения пользователей в БД пока НЕТ.
- Никакой проверки токена в get_current_user пока НЕТ (заглушка в src/api/deps/auth.py).

Это сделано специально, чтобы:
- фронтенд уже мог «логиниться» и работать с API;
- в будущем любой разработчик мог постепенно заменить эту заглушку
  на настоящую авторизацию с минимальными изменениями в коде.


ЧТО НУЖНО БУДЕТ СДЕЛАТЬ ПОЗЖЕ (ПРИ ПЕРЕХОДЕ НА РЕАЛЬНЫЙ ЛОГИН)
--------------------------------------------------------------
1. Добавить настоящее хранение пользователей:
   - Таблица users в БД (id, email, хэш пароля, global_role, tenant_id, и т.д.).
   - Репозиторий для работы с users (UserRepository).

2. Сделать реальную проверку логина и пароля:
   - В login() вместо простого сравнения "admin"/"admin" нужно:
       - найти пользователя по email/username в БД;
       - сравнить введённый пароль с хэшем (через bcrypt/argon2 и т.п.);
       - при ошибке вернуть 401 Unauthorized.

3. Генерировать настоящий токен (чаще всего JWT):
   - Подключить библиотеку (например, PyJWT).
   - В payload токена положить:
       - user_id,
       - global_role,
       - tenant_id,
       - возможно, email.
   - Подписать токен секретным ключом (SECRET_KEY из настроек).

4. Переписать get_current_user() в src/api/deps/auth.py:
   - Считать токен из заголовка Authorization: Bearer <token> или из куки.
   - Проверить подпись и срок действия токена.
   - Распарсить payload, достать user_id, global_role, tenant_id, email.
   - Найти пользователя в БД при необходимости.
   - Вернуть CurrentUser с реальными данными.

ВАЖНО:
- Интерфейсы login() и CurrentUser лучше не менять радикально.
  Тогда фронтенд и остальные эндпоинты продолжат работать,
  а внутри можно будет постепенно заменить реализацию на «боевую».
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.deps.auth import CurrentUser

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    """
    ВХОДНЫЕ ДАННЫЕ ДЛЯ ЛОГИНА.

    Сейчас:
    - ожидаем username и password из формы логина на фронтенде.

    Потом:
    - поля можно оставить те же, чтобы фронт не переписывать,
      а внутри просто искать пользователя в БД по username/email.
    """
    username: str
    password: str


class LoginResponse(BaseModel):
    """
    ОТВЕТ НА УСПЕШНЫЙ ЛОГИН.

    Поля:
    - access_token: строка с токеном доступа.
        Сейчас: фиктивная строка "admin-token".
        Потом: настоящий JWT или другой токен.
    - token_type: тип токена, по умолчанию "bearer".
        Обычно это значение не меняется.
    - user: объект CurrentUser.
        Это важно: структура CurrentUser уже описана в src/api/deps/auth.py,
        и её удобно использовать и на фронте, и в других частях бэка.
    """
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    """
    ПРОСТОЙ ЛОГИН ПО ЛОГИНУ И ПАРОЛЮ.

    Сейчас:
    - Принимаем username и password.
    - Разрешаем вход только если username == "admin" и password == "admin".
    - Возвращаем фиктивный токен и «админского» пользователя.

    Зачем так:
    - Этого достаточно, чтобы фронтенд мог «играть» с системой,
      не настраивая сразу полноценную авторизацию.
    - Коду, который дальше будет дорабатывать auth, будет проще:
      структура ответа уже согласована.

    Что нужно будет сделать потом:
    - Заменить проверку логина/пароля на обращение к БД и проверку хэша пароля.
    - Заменить "admin-token" на настоящий JWT с данными о пользователе.
    """
    # ВРЕМЕННАЯ ПРОСТАЯ ПРОВЕРКА: только admin/admin
    if not (payload.username == "admin" and payload.password == "admin"):
        # Если логин или пароль не совпадают — отдаём 401 Unauthorized
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Создаём объект CurrentUser.
    # Сейчас он «фиктивный», но структура совпадает с тем,
    # что будет в настоящей авторизации.
    user = CurrentUser(
        id="admin",                # потом заменить на реальный user_id из БД
        global_role="superadmin",      # потом, например, "superadmin" или "tenant_admin"
        tenant_id=uuid.UUID(int=0),  # временный tenant_id = 00000000-0000-0000-0000-000000000000
        email="admin@example.com",   # можно заменить на реальный email
    )

    # ВОЗВРАЩАЕМ ОТВЕТ ДЛЯ ФРОНТЕНДА
    # access_token:
    #   - сейчас: простая строка "admin-token";
    #   - позже: здесь будет JWT.
    return LoginResponse(
        access_token="admin-token",
        user=user,
    )
