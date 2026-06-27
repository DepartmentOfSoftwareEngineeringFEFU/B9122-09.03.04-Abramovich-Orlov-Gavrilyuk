
import asyncio
import sys
import os
from datetime import date

# Добавляем путь к приложению
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from app.core.database import async_session_maker
from app.db.models.user import User
from app.core.security import get_password_hash

async def create_admin(username="admin", password="admin", email="admin@example.com"):
    async with async_session_maker() as session:
        # Проверяем, существует ли пользователь
        result = await session.execute(select(User).where(User.username == username))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"Пользователь '{username}' уже существует.")
            return

        # Создаем нового админа
        new_user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_staff=True,
            is_superuser=True,
            display_name="Administrator",
            birth_date=date(1990, 1, 1),
            full_name="Administrator",
        )
        
        session.add(new_user)
        await session.commit()
        print(f"✅ Успешно создан суперпользователь:")
        print(f"   Логин: {username}")
        print(f"   Пароль: {password}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create superuser")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument("--password", default="admin", help="Admin password")
    parser.add_argument("--full_name", default="Administrator")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(create_admin(args.username, args.password))
    except Exception as e:
        print(f"Ошибка при создании: {e}")
