from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import shutil
import uuid

from config import settings

router = APIRouter(prefix="/upload", tags=["upload"])

# Используем путь из настроек
MEDIA_DIR = settings.MEDIA_ROOT / "images"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/images")
async def upload_images(files: list[UploadFile] = File(...)):
    """Загрузка изображений для товаров"""
    if not files:
        raise HTTPException(400, "No files uploaded")

    uploaded = []

    for file in files:
        if file.content_type not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported file type: {file.content_type}")

        ext = Path(file.filename).suffix.lower() or ".jpg"
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = MEDIA_DIR / safe_name

        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Формируем URL с использованием MEDIA_URL из настроек
        uploaded.append({
            "filename": safe_name,
            "path": f"images/{safe_name}",
            "url": f"{settings.MEDIA_URL}/images/{safe_name}"
        })

    return {
        "count": len(uploaded),
        "files": uploaded
    }
