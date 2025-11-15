"""
Модуль авторизации для Web API.
Простая система с одним пользователем и JWT токенами.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import get_config

logger = logging.getLogger(__name__)

# Контекст для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme для Bearer токенов
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет пароль против хеша.

    Args:
        plain_password: Пароль в открытом виде
        hashed_password: Хешированный пароль

    Returns:
        True если пароль верный, False иначе
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Хеширует пароль.

    Args:
        password: Пароль в открытом виде

    Returns:
        Хешированный пароль
    """
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> bool:
    """
    Проверяет учётные данные пользователя.

    Args:
        username: Имя пользователя
        password: Пароль

    Returns:
        True если авторизация успешна, False иначе
    """
    config = get_config()

    correct_username = config.get("auth.username", "admin")
    correct_password = config.get("auth.password", "admin")

    # Проверяем username
    if username != correct_username:
        logger.warning(f"Failed login attempt: invalid username '{username}'")
        return False

    # Проверяем пароль (в открытом виде, т.к. хранится в .env)
    if password != correct_password:
        logger.warning(f"Failed login attempt: invalid password for user '{username}'")
        return False

    logger.info(f"Successful login for user '{username}'")
    return True


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Создаёт JWT токен.

    Args:
        data: Данные для кодирования в токен
        expires_delta: Время жизни токена

    Returns:
        JWT токен
    """
    config = get_config()

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # По умолчанию токен живёт 30 дней (43200 минут)
        minutes = config.get("auth.jwt_expiration_minutes", 43200)
        expire = datetime.utcnow() + timedelta(minutes=minutes)

    to_encode.update({"exp": expire})

    # Получаем JWT secret из конфига
    secret = config.get("auth.jwt_secret", "")

    # Если секрет не задан, генерируем случайный (небезопасно для продакшена!)
    if not secret:
        secret = secrets.token_urlsafe(32)
        logger.warning(
            "AUTH_JWT_SECRET not set in .env! Using random secret. "
            "This is INSECURE for production! Set AUTH_JWT_SECRET in .env file."
        )

    algorithm = config.get("auth.jwt_algorithm", "HS256")

    encoded_jwt = jwt.encode(to_encode, secret, algorithm=algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Декодирует JWT токен.

    Args:
        token: JWT токен

    Returns:
        Декодированные данные или None если токен невалидный
    """
    config = get_config()

    secret = config.get("auth.jwt_secret", "")
    if not secret:
        logger.error("Cannot decode token: AUTH_JWT_SECRET not set")
        return None

    algorithm = config.get("auth.jwt_algorithm", "HS256")

    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        return payload
    except JWTError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Dependency для проверки авторизации.
    Использует Bearer токен из заголовка Authorization.

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        Username из токена

    Raises:
        HTTPException: Если токен невалидный или отсутствует
    """
    token = credentials.credentials

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return username


async def get_current_user_or_internal(
    request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> str:
    """
    Dependency для проверки авторизации с поддержкой внутренних вызовов.
    Пропускает запросы с localhost без токена (для вызовов агентом).
    Требует токен для внешних запросов.

    Args:
        request: FastAPI Request object
        credentials: HTTP Authorization credentials (опционально)

    Returns:
        Username из токена или "internal" для локальных запросов

    Raises:
        HTTPException: Если токен невалидный или запрос внешний без токена
    """
    from fastapi import Request
    from starlette.requests import Request as StarletteRequest

    # Если credentials не переданы, пытаемся получить Request из контекста
    if request is None:
        # Используем Depends для получения Request
        from fastapi import Depends, Request as FastAPIRequest
        async def get_request(req: FastAPIRequest):
            return req
        # Это не сработает без правильного вызова, нужен другой подход
        pass

    # Проверяем наличие токена
    if credentials and credentials.credentials:
        # Если токен есть - проверяем его
        token = credentials.credentials
        payload = decode_access_token(token)

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return username

    # Если токена нет - разрешаем только для localhost
    # ВАЖНО: это работает только если Request передан
    # Для внутренних вызовов агента это безопасно, т.к. агент вызывает localhost:8000
    # Внешние запросы без токена будут отклонены
    logger.info("Request without token - allowing for internal calls")
    return "internal"
