"""
Конфигурация приложения
"""

from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Приложение
    APP_NAME: str = "Diplom3D"
    DEBUG: bool = True
    
    # База данных
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/diplom3d"
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 часа
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # Файлы
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS: List[str] = ["png", "jpg", "jpeg"]
    
    # Обработка изображений
    MIN_IMAGE_RESOLUTION: int = 1000  # минимальное разрешение
    DEFAULT_FLOOR_HEIGHT: float = 3.0  # высота этажа в метрах
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
