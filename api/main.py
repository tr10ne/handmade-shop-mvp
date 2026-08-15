from fastapi import FastAPI, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from config import settings
from pathlib import Path
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from database import engine, Base, get_db
from routers import products, categories, auctions, uploads
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse


# Список Telegram ID администраторов (заполняется из переменных окружения)
import os
ADMIN_TELEGRAM_IDS = [
    int(id_str.strip())
    for id_str in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if id_str.strip()
]

async def verify_admin_access(request: Request) -> bool:
    """Проверяет, есть ли у пользователя доступ администратора"""
    # Получаем Telegram user ID из заголовка или параметра запроса
    tg_user_id = request.headers.get("X-Telegram-User-Id")

    if not tg_user_id:
        return False

    try:
        user_id = int(tg_user_id)
        return user_id in ADMIN_TELEGRAM_IDS
    except (ValueError, TypeError):
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown (если нужно)
    await engine.dispose()


app = FastAPI(
    title=settings.FASTAPI_TITLE,
    version=settings.FASTAPI_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Монтирование статических файлов для медиа
# MEDIA_ROOT указывает на директорию с файлами, монтируем её напрямую
app.mount(settings.MEDIA_URL, StaticFiles(directory=str(settings.MEDIA_ROOT)), name="media")

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if not settings.allow_any_cors else ["*"],
    allow_credentials=not settings.allow_any_cors,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health(request: Request):
    """Проверка доступности API - доступно всем"""
    return {"status": "ok"}

@app.get("/openapi.json")
async def get_openapi(request: Request):
    """OpenAPI схема - только для админов"""
    if not await verify_admin_access(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "Доступ запрещён. Только для администраторов."}
        )
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

from fastapi.openapi.docs import get_swagger_ui_html

@app.get("/docs")
async def swagger_docs(request: Request):
    """Swagger UI - только для админов"""
    if not await verify_admin_access(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "Доступ запрещён. Только для администраторов."}
        )
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title)

app.include_router(categories.router)
app.include_router(products.router)
app.include_router(auctions.router)
app.include_router(uploads.router)