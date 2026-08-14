from fastapi import FastAPI
from database import engine, Base
import models
from routers import products
from fastapi.middleware.cors import CORSMiddleware
from routers import products, uploads
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Shop API")

app.mount("/media", StaticFiles(directory="/app/media"), name="media")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(products.router)
app.include_router(uploads.router)