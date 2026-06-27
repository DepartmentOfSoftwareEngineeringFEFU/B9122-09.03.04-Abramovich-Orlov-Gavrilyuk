"""
Diplom3D Backend - FastAPI Application
Построение виртуальных карт зданий
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import settings
from app.core.logging_config import setup_logging

# Setup logging at application startup
setup_logging(log_level="INFO")

app = FastAPI(
    title="Diplom3D API",
    description="API для построения виртуальных карт зданий на основе планов эвакуации",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

from fastapi.staticfiles import StaticFiles
import os
from app.core.config import settings

# Монтируем директорию загрузок для раздачи статики
# Создаем директорию если нет
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/api/v1/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Корневой эндпоинт для проверки работоспособности"""
    return {
        "message": "Diplom3D API",
        "version": "0.1.0",
        "docs": "/api/docs"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy"}
