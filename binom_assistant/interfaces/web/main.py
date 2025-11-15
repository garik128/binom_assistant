"""
Основное приложение FastAPI.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from datetime import datetime
from config import get_config
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Импортируем роуты
from .routes import health, campaigns, stats, alerts, system, modules, settings, chat, auth

logger = logging.getLogger(__name__)

# Глобальная переменная для отслеживания времени старта приложения
APP_START_TIME = None

# Пути к статическим файлам и шаблонам
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Настройка шаблонов
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения.
    """
    # Startup
    global APP_START_TIME
    APP_START_TIME = datetime.now()

    logger.info("Starting Binom Assistant API...")

    config = get_config()
    environment = config.get("environment", "development")
    debug = config.get("debug", False)

    logger.info(f"Environment: {environment}")
    logger.info(f"Debug mode: {debug}")

    # Проверяем first_run перед запуском scheduler'ов
    scheduler_instance = None
    first_run_flag = False
    try:
        from services.settings_manager import get_settings_manager
        settings = get_settings_manager()
        first_run_value = settings.get('system.first_run', default='true')
        first_run_flag = first_run_value.lower() == 'true'

        if first_run_flag:
            logger.warning("=" * 60)
            logger.warning("FIRST RUN DETECTED")
            logger.warning("Schedulers will NOT start automatically")
            logger.warning("Waiting for initial data collection to complete...")
            logger.warning("=" * 60)
        else:
            # Запускаем планировщик только если НЕ first run
            from services.scheduler.scheduler import TaskScheduler
            scheduler_instance = TaskScheduler()
            scheduler_instance.setup_jobs()
            scheduler_instance.start()
            logger.info("TaskScheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to check/start scheduler: {e}")

    # Инициализируем систему модулей
    try:
        from modules.startup import init_modules
        init_modules()
    except Exception as e:
        logger.error(f"Failed to initialize modules: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Binom Assistant API...")

    # Останавливаем планировщик
    if scheduler_instance:
        try:
            scheduler_instance.stop()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Failed to stop scheduler: {e}")

    # Останавливаем систему модулей
    try:
        from modules.startup import shutdown_modules
        shutdown_modules()
    except Exception as e:
        logger.error(f"Failed to shutdown modules: {e}")


# Создаем приложение FastAPI
app = FastAPI(
    title="Binom Assistant API",
    description="API для системы анализа рекламных кампаний Binom",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Настройка Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Настройка Response Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Сжимаем ответы > 1KB

# Настройка CORS
config = get_config()
cors_origins_str = config.get("cors.origins", "*")

# Парсим CORS origins из строки
if cors_origins_str == "*":
    cors_origins = ["*"]
    allow_credentials = False  # С allow_origins=["*"] нельзя использовать allow_credentials=True
else:
    cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем статические файлы
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Подключаем роуты API
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(campaigns.router, prefix="/api/v1", tags=["campaigns"])
app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
app.include_router(alerts.router, prefix="/api/v1", tags=["alerts"])
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(modules.router, prefix="/api/v1", tags=["modules"])
app.include_router(modules.run_router, prefix="/api/v1", tags=["modules"])  # Роутер для /run без обязательной авторизации
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Главная страница - веб-интерфейс.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """
    Страница аналитики.
    """
    return templates.TemplateResponse("analytics.html", {"request": request})


@app.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request):
    """
    Страница алертов.
    """
    return templates.TemplateResponse("alerts.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """
    Страница AI чата.
    """
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Страница настроек.
    """
    config = get_config()

    # Получаем актуальные значения из БД (через settings_manager)
    try:
        from services.settings_manager import get_settings_manager
        settings_mgr = get_settings_manager()

        # Читаем актуальные значения из БД
        collector_config = {
            "enabled": settings_mgr.get('collector.enabled', default=True),
            "interval_hours": settings_mgr.get('collector.interval_hours', default=1),
            "update_days": settings_mgr.get('collector.update_days', default=7),
        }
    except Exception:
        # Fallback на значения из .env
        collector_config = config.get_section("collector")

    # Собираем все настройки для отображения
    context = {
        "request": request,
        "config": config,
        "db_config": config.get_section("database"),
        "telegram_config": config.get_section("telegram"),
        "collector": collector_config,  # используем актуальные значения из БД
        "app": config.get_section("app"),
        "openrouter_config": config.get_section("openrouter"),
    }

    return templates.TemplateResponse("settings.html", context)


@app.get("/modules/{module_id}", response_class=HTMLResponse)
async def module_detail_page(request: Request, module_id: str):
    """
    Страница детального просмотра модуля.
    """
    return templates.TemplateResponse("module_detail.html", {
        "request": request,
        "module_id": module_id,
        "module_name": "Module"  # Будет обновлено через JS
    })


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    debug = config.get("debug", True)

    uvicorn.run(
        "interfaces.web.main:app",
        host="0.0.0.0",
        port=8000,
        reload=debug,
        log_level="info"
    )
