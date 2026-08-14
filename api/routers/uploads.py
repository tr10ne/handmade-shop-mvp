from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import shutil
import uuid

router = APIRouter(prefix="/upload", tags=["upload"])

MEDIA_DIR = Path("/app/media/images")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

@router.post("/images")
async def upload_images(files: list[UploadFile] = File(...)):
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

        uploaded.append({
            "filename": safe_name,
            "path": f"images/{safe_name}",
            "url": f"http://127.0.0.1:8001/media/images/{safe_name}"
        })

    return {
        "count": len(uploaded),
        "files": uploaded
    }