from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request
from pathlib import Path
import shutil
import uuid
import logging
import os

from config import settings

logger = logging.getLogger(__name__)

# Импортируем функцию проверки админа из main
async def verify_admin_access(request: Request) -> bool:
    """Проверяет, есть ли у пользователя доступ администратора"""
    tg_user_id = request.headers.get("X-Telegram-User-Id")

    if not tg_user_id:
        return False

    try:
        user_id = int(tg_user_id)
    except (ValueError, TypeError):
        return False
    
    # Получаем список админов из кэша или через Telegram API
    from main import get_group_admin_ids
    admin_ids = await get_group_admin_ids()
    
    # Если список администраторов пуст (нет токена/группы), проверяем по старому методу
    if not admin_ids:
        static_admin_ids = {
            int(id_str.strip())
            for id_str in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
            if id_str.strip()
        }
        return user_id in static_admin_ids
    
    return user_id in admin_ids


router = APIRouter(prefix="/upload", tags=["upload"])

# Используем путь из настроек
MEDIA_DIR = settings.MEDIA_ROOT / "images"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'}


@router.post("/images")
async def upload_images(request: Request, files: list[UploadFile] = File(...)):
    """Загрузка изображений для товаров - только для админов"""
    if not await verify_admin_access(request):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Только для администраторов.")
    if not files:
        raise HTTPException(400, "No files uploaded")

    uploaded = []

    for file in files:
        # Определяем тип файла более гибко - сначала по расширению, потом по content-type
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        
        logger.info(f"Processing file: filename={filename}, ext={ext}, content_type={file.content_type}")
        
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
        
        # Разрешаем загрузку, если расширение файла поддерживается
        # Мобильные браузеры могут отправлять файлы без правильного content-type
        is_allowed = ext.lower() in ALLOWED_EXTENSIONS
        
        if not is_allowed:
            logger.warning(f"Unsupported file type: {ext or 'unknown'} (filename: {filename})")
            raise HTTPException(400, f"Unsupported file type: {ext or 'unknown'} (filename: {filename})")

        if not ext:
            # Если расширения нет, добавляем по типу контента
            if content_type == 'image/jpeg' or content_type.startswith('image/jpg'):
                ext = '.jpg'
            elif content_type == 'image/png':
                ext = '.png'
            elif content_type == 'image/webp':
                ext = '.webp'
            elif content_type in ['image/heic', 'image/heif']:
                ext = '.heic'
            else:
                ext = '.jpg'  # По умолчанию JPG для совместимости
        
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = MEDIA_DIR / safe_name

        try:
            logger.info(f"Saving file to: {save_path}")
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Проверяем что файл действительно сохранился
            if not save_path.exists():
                logger.error(f"Failed to save file: {safe_name}")
                raise HTTPException(500, f"Failed to save file: {safe_name}")
            
            file_size = save_path.stat().st_size
            logger.info(f"File saved successfully: {safe_name}, size: {file_size} bytes")
                
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}", exc_info=True)
            raise HTTPException(500, f"Error saving file: {str(e)}")

        # Формируем URL с использованием MEDIA_URL из настроек
        uploaded.append({
            "filename": safe_name,
            "path": f"images/{safe_name}",
            "url": f"{settings.MEDIA_URL}/images/{safe_name}"
        })

    result = {
        "count": len(uploaded),
        "files": uploaded
    }
    logger.info(f"Upload complete: {result}")
    return result
