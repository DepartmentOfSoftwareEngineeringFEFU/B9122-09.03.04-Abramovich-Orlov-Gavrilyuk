"""
Create a superuser for the Diplom3D application.

Usage (run from the backend/ directory):
    cd backend
    python ../scripts/create_superuser.py
    python ../scripts/create_superuser.py --username admin --password secret

Options:
    --username   Login name (default: admin)
    --password   Password   (default: admin)
    --email      Email       (default: admin@localhost)
"""

import asyncio
import argparse
import sys
import os
from datetime import date

# Make sure backend/ is in path when running from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.database import async_session_maker, engine, Base
from app.core.security import get_password_hash
from app.db.models.user import User  # noqa: F401
from sqlalchemy import select


async def create_superuser(username: str, password: str, email: str) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"[!] User '{username}' already exists (id={existing.id}, "
                  f"is_active={existing.is_active}, is_superuser={existing.is_superuser})")
            if not existing.is_superuser:
                existing.is_superuser = True
                existing.is_active = True
                existing.can_approve_users = True
                await session.commit()
                print(f"[+] Promoted '{username}' to superuser.")
            else:
                print(f"    Nothing to do — already a superuser.")
            return

        hashed = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            full_name="Administrator",
            birth_date=date(1990, 1, 1),
            hashed_password=hashed,
            is_active=True,
            is_staff=True,
            is_superuser=True,
            can_approve_users=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"[+] Superuser created: username='{username}', id={user.id}")
        print(f"    You can now log in at /admin with these credentials.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create a superuser for Diplom3D")
    parser.add_argument("--username", default="admin", help="Login name (default: admin)")
    parser.add_argument("--password", default="admin",  help="Password   (default: admin)")
    parser.add_argument("--email",    default="admin@localhost", help="Email (default: admin@localhost)")
    args = parser.parse_args()

    await create_superuser(args.username, args.password, args.email)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
