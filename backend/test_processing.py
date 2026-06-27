"""
Тестовый скрипт для проверки полного pipeline обработки
плана эвакуации и генерации 3D модели
"""

import os
import sys

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.processing.binarization import BinarizationService
from app.processing.contours import ContourService
from app.processing.mesh_generator import MeshGeneratorService
import cv2
import numpy as np


def test_processing_pipeline(image_path: str, output_name: str = None):
    """
    Полный тест pipeline обработки изображения
    
    Args:
        image_path: Путь к изображению плана
        output_name: Имя для выходных файлов
    """
    print("=" * 60)
    print("ТЕСТ ОБРАБОТКИ ПЛАНА ЭВАКУАЦИИ")
    print("=" * 60)
    
    if not os.path.exists(image_path):
        print(f"Ошибка: файл не найден: {image_path}")
        return
    
    # Имя для выходных файлов
    if output_name is None:
        output_name = os.path.splitext(os.path.basename(image_path))[0]
    
    # === Шаг 1: Бинаризация ===
    print("\n--- Шаг 1: Бинаризация (метод Оцу) ---")
    bin_service = BinarizationService(output_dir="uploads/processed")
    
    mask, threshold, mask_path = bin_service.process(
        image_path,
        use_adaptive=False,
        morphology_kernel=3,
        morphology_iterations=2
    )
    
    print(f"  Порог бинаризации: {threshold}")
    print(f"  Размер маски: {mask.shape}")
    print(f"  Маска сохранена: {mask_path}")
    
    # === Шаг 2: Выделение контуров ===
    print("\n--- Шаг 2: Выделение контуров ---")
    contour_service = ContourService(output_dir="uploads/contours")
    
    elements = contour_service.extract_elements(
        mask,
        min_area=100,
        epsilon_factor=0.02
    )
    
    # Визуализация контуров
    # Загружаем с поддержкой Unicode путей
    with open(image_path, 'rb') as f:
        file_bytes = np.frombuffer(f.read(), dtype=np.uint8)
    original = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    contours_path = f"uploads/contours/{output_name}_contours.png"
    os.makedirs("uploads/contours", exist_ok=True)
    contour_service.save_visualization(original, elements, contours_path)
    print(f"  Визуализация контуров: {contours_path}")
    
    # === Шаг 3: Генерация 3D модели ===
    print("\n--- Шаг 3: Генерация 3D модели ---")
    mesh_service = MeshGeneratorService(
        output_dir="uploads/models",
        default_floor_height=3.0,
        pixels_per_meter=50.0
    )
    
    result = mesh_service.process_plan_image(
        mask,
        name=output_name,
        floor_number=1
    )
    
    if result:
        print(f"\n{'=' * 60}")
        print("РЕЗУЛЬТАТ")
        print(f"{'=' * 60}")
        print(f"  ID модели: {result.mesh_id}")
        print(f"  Вершин: {result.vertices_count}")
        print(f"  Граней: {result.faces_count}")
        print(f"  OBJ файл: {result.obj_path}")
        print(f"  GLB файл: {result.glb_path}")
    else:
        print("Ошибка: не удалось создать 3D модель")
    
    # Сводка по этапам
    print(f"\n{'=' * 60}")
    print("ВЫХОДНЫЕ ФАЙЛЫ")
    print(f"{'=' * 60}")
    print(f"  1. Маска: {mask_path}")
    print(f"  2. Контуры: {contours_path}")
    if result:
        print(f"  3. 3D модель OBJ: {result.obj_path}")
        print(f"  4. 3D модель GLB: {result.glb_path}")
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # По умолчанию используем тестовое изображение
        test_images = [
            r"C:\Users\Артёмка\Desktop\images\1.jpg",
            r"C:\Users\Артёмка\Desktop\images\2.jpg",
        ]
        
        for img_path in test_images:
            if os.path.exists(img_path):
                test_processing_pipeline(img_path)
                break
        else:
            print("Usage: python test_processing.py <image_path>")
            print("Или поместите изображение в C:\\Users\\Артёмка\\Desktop\\images\\")
    else:
        test_processing_pipeline(sys.argv[1])
