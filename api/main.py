from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from config import settings
from pathlib import Path

from database import engine, Base, get_db
from routers import products, categories, auctions, uploads
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


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
    lifespan=lifespan
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
async def health():
    return {"status": "ok"}

app.include_router(categories.router)
app.include_router(products.router)
app.include_router(auctions.router)
app.include_router(uploads.router)