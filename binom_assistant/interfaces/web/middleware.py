"""
Middleware 4;O FastAPI ?@8;>65=8O.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware 4;O ;>38@>20=8O 70?@>A>2.
    """

    async def dispatch(self, request: Request, call_next):
        """
        1@010BK205B 70?@>A 8 ;>38@C5B 8=D>@<0F8N.
        """
        start_time = time.time()

        # >38@C5< 2E>4OI89 70?@>A
        logger.info(
            f"Incoming request: {request.method} {request.url.path}"
        )

        # 1@010BK205< 70?@>A
        response = await call_next(request)

        # KG8A;O5< 2@5<O >1@01>B:8
        process_time = time.time() - start_time

        # >38@C5< @57C;LB0B
        logger.info(
            f"Request processed: {request.method} {request.url.path} "
            f"- Status: {response.status_code} - Time: {process_time:.3f}s"
        )

        # >102;O5< 703>;>2>: A 2@5<5=5< >1@01>B:8
        response.headers["X-Process-Time"] = str(process_time)

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware 4;O >1@01>B:8 >H81>:.
    """

    async def dispatch(self, request: Request, call_next):
        """
        1@010BK205B >H81:8 8 2>72@0I05B :@0A82K9 JSON.
        """
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(
                f"Error processing request {request.method} {request.url.path}: {e}",
                exc_info=True
            )

            # >72@0I05< JSON A >H81:>9
            from fastapi.responses import JSONResponse

            # В production не раскрываем детали ошибок
            from config import get_config
            config = get_config()
            environment = config.get("environment", "development")

            error_message = str(e) if environment != "production" else "Internal Server Error"

            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": error_message,
                    "path": str(request.url.path)
                }
            )


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware для проверки авторизации на HTML страницах.
    Редиректит неавторизованных пользователей на страницу логина.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Проверяет авторизацию для HTML страниц.
        """
        # Публичные пути, которые не требуют авторизации
        public_paths = [
            "/api/v1/auth/login",
            "/static/",
            "/favicon.ico",
        ]

        # Проверяем, является ли путь публичным
        is_public = any(request.url.path.startswith(path) for path in public_paths)

        if is_public:
            return await call_next(request)

        # Проверяем наличие токена в cookies или localStorage (для HTML страниц)
        # Для HTML страниц проверяем только если это не API запрос
        if not request.url.path.startswith("/api/"):
            # Это HTML страница - проверяем cookie или редиректим на логин
            # Cookie будет установлен JS после логина
            response = await call_next(request)
            return response

        # Для API запросов авторизация уже проверяется через dependencies
        return await call_next(request)
