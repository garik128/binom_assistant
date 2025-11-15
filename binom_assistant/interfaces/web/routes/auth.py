"""
Роуты для авторизации.
"""
import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path

from ..auth import authenticate_user, create_access_token

logger = logging.getLogger(__name__)

router = APIRouter()

# Настройка шаблонов
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class LoginRequest(BaseModel):
    """Запрос на логин"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Ответ с токеном"""
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest) -> TokenResponse:
    """
    Аутентификация пользователя и получение JWT токена.

    Args:
        login_data: Данные для входа (username, password)

    Returns:
        JWT токен для использования в дальнейших запросах

    Raises:
        HTTPException: Если учётные данные неверны
    """
    if not authenticate_user(login_data.username, login_data.password):
        logger.warning(f"Failed login attempt for user: {login_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Создаём токен
    access_token = create_access_token(data={"sub": login_data.username})

    logger.info(f"User '{login_data.username}' successfully authenticated")

    return TokenResponse(access_token=access_token)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Страница логина.
    """
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/logout")
async def logout() -> Dict[str, str]:
    """
    Выход из системы.
    JWT токены не сбрасываются на сервере (stateless),
    клиент должен удалить токен локально.
    """
    return {"message": "Successfully logged out. Please delete your token."}
