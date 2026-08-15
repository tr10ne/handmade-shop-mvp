from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pathlib import Path
import shutil
import uuid
import io

from api.config import settings

router = APIRouter(prefix="/upload", tags=["upload"])

# Используем путь из настроек
MEDIA_DIR = settings.MEDIA_ROOT / "images"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@router.post("/images")
async def upload_images(files: list[UploadFile] = File(...)):
    """Загрузка изображений для товаров"""
    if not files:
        raise HTTPException(400, "No files uploaded")

    uploaded = []

    for file in files:
        # Определяем тип файла более гибко - сначала по расширению, потом по content-type
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        
        # Сначала пробуем определить тип по расширению файла (важно для мобильных)
        content_type = ""
        if ext in ['.jpg', '.jpeg']:
            content_type = 'image/jpeg'
        elif ext == '.png':
            content_type = 'image/png'
        elif ext == '.webp':
            content_type = 'image/webp'
        elif ext in ['.heic', '.heif']:
            content_type = 'image/heic'  # Сохраняем HEIC как есть, конвертация на клиенте или позже
        else:
            # Если расширение не узнаваемо, используем content-type из запроса
            content_type = file.content_type or ""
        
        # Разрешаем загрузку, если тип поддерживается ИЛИ это мобильный формат (HEIC)
        # Мобильные браузеры могут отправлять HEIC без правильного content-type
        is_allowed = content_type in ALLOWED_TYPES or ext in ['.heic', '.heif']
        
        if not is_allowed:
            raise HTTPException(400, f"Unsupported file type: {content_type or 'unknown'} (filename: {filename})")

        if not ext:
            # Если расширения нет, добавляем по типу контента
            if content_type == 'image/jpeg':
                ext = '.jpg'
            elif content_type == 'image/png':
                ext = '.png'
            elif content_type == 'image/webp':
                ext = '.webp'
            elif content_type == 'image/heic':
                ext = '.heic'
            else:
                ext = '.jpg'
        
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = MEDIA_DIR / safe_name

        try:
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Проверяем что файл действительно сохранился
            if not save_path.exists():
                raise HTTPException(500, f"Failed to save file: {safe_name}")
                
        except Exception as e:
            raise HTTPException(500, f"Error saving file: {str(e)}")

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
