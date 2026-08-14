from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

from database import engine, Base, get_db
from routers import products, categories, auctions, uploads
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path


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
    title=os.getenv("FASTAPI_TITLE", "Handmade Shop API"),
    version=os.getenv("FASTAPI_VERSION", "1.0.0"),
    lifespan=lifespan
)

# Монтирование статических файлов для медиа
media_path = Path(os.getenv("MEDIA_ROOT", "/app/media/images")).parent
app.mount(os.getenv("MEDIA_URL", "/media"), StaticFiles(directory=str(media_path)), name="media")

# CORS настройки из env
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
allow_any = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if not allow_any else ["*"],
    allow_credentials=not allow_any,
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