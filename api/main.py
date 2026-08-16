from fastapi import FastAPI, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from config import settings
from pathlib import Path
import logging
import aiohttp
import os

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


# Кэш администраторов группы: {tg_user_id: True}
_admin_cache = {}
_admin_cache_timestamp = 0
ADMIN_CACHE_TTL = 300  # 5 минут


async def get_group_admin_ids() -> set[int]:
    """Получает ID администраторов из Telegram группы через Bot API"""
    global _admin_cache, _admin_cache_timestamp
    import time
    
    # Проверяем кэш
    now = time.time()
    if _admin_cache and (now - _admin_cache_timestamp) < ADMIN_CACHE_TTL:
        return set(_admin_cache.keys())
    
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_GROUP_ID:
        # Если нет токена или ID группы, возвращаем пустое множество
        return set()
    
    try:
        bot_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
        
        # Получаем список администраторов чата
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bot_url}/getChatAdministrators",
                json={"chat_id": settings.TELEGRAM_ADMIN_GROUP_ID}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        admins = data.get("result", [])
                        # Извлекаем user.id для каждого администратора
                        admin_ids = set()
                        for admin in admins:
                            user = admin.get("user", {})
                            user_id = user.get("id")
                            if user_id:
                                admin_ids.add(user_id)
                        
                        # Обновляем кэш
                        _admin_cache = {uid: True for uid in admin_ids}
                        _admin_cache_timestamp = now
                        return admin_ids
    except Exception as e:
        logging.error(f"Ошибка получения администраторов группы: {e}")
    
    return set(_admin_cache.keys())


async def verify_admin_access(request: Request) -> bool:
    """Проверяет, есть ли у пользователя доступ администратора"""
    # Получаем Telegram user ID из заголовка
    tg_user_id = request.headers.get("X-Telegram-User-Id")

    if not tg_user_id:
        return False

    try:
        user_id = int(tg_user_id)
    except (ValueError, TypeError):
        return False
    
    # Получаем актуальный список администраторов
    admin_ids = await get_group_admin_ids()
    
    # Если список администраторов пуст (нет токена/группы), проверяем по старому методу
    if not admin_ids:
        # Fallback на статический список из переменных окружения
        static_admin_ids = {
            int(id_str.strip())
            for id_str in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
            if id_str.strip()
        }
        return user_id in static_admin_ids
    
    return user_id in admin_ids

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
    openapi_url="/openapi.json"
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