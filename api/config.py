"""
Централизованная конфигурация приложения.
Все переменные окружения загружаются здесь один раз при старте приложения.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла (если существует)
load_dotenv()


class Settings:
    """Настройки приложения из переменных окружения"""
    
    # FastAPI Settings
    FASTAPI_TITLE: str = os.getenv("FASTAPI_TITLE", "Handmade Shop API")
    FASTAPI_VERSION: str = os.getenv("FASTAPI_VERSION", "1.0.0")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Database Settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite+aiosqlite:////app/data/shop.db"
    )
    
    # CORS Settings
    CORS_ORIGINS: list[str] = [
        origin.strip() 
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
    ]
    
    # Media Settings
    MEDIA_ROOT: Path = Path(os.getenv("MEDIA_ROOT", "/app/media"))
    MEDIA_URL: str = os.getenv("MEDIA_URL", "/media")
    
    # Security Settings (for future use)
    SECRET_KEY: str | None = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Telegram Bot Settings (for future integration)
    TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_WEBHOOK_URL: str | None = os.getenv("TELEGRAM_WEBHOOK_URL")
    
    @property
    def allow_any_cors(self) -> bool:
        """Проверка, разрешены ли все CORS origins"""
        return "*" in self.CORS_ORIGINS


# Глобальный экземпляр настроек
settings = Settings()
