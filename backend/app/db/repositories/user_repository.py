"""
User repository for database operations
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository):
    """Repository for User model database operations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            User if found, None otherwise
        """
        logger.debug("get_by_username: username=%s", username)
        result = await self._session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: Email to search for

        Returns:
            User if found, None otherwise
        """
        logger.debug("get_by_email: email=%s", email)
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User if found, None otherwise
        """
        logger.debug("get_by_id: user_id=%d", user_id)
        return await self._session.get(User, user_id)

    async def create(
        self,
        username: str,
        email: str,
        full_name: str,
        hashed_password: str,
        is_active: bool = False,
        is_staff: bool = False,
        is_superuser: bool = False,
    ) -> User:
        """
        Create new user.

        Args:
            username: Username
            email: Email
            full_name: Full name
            hashed_password: Hashed password
            is_active: Active status (default False)
            is_staff: Staff status (default False)
            is_superuser: Superuser status (default False)

        Returns:
            Created User instance
        """
        logger.debug("create: username=%s, email=%s", username, email)
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=is_active,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_pending_users(self) -> list[User]:
        """
        Get all users with is_active=False, ordered by date_joined DESC.

        Returns:
            List of pending users
        """
        logger.debug("get_pending_users")
        result = await self._session.execute(
            select(User)
            .where(User.is_active.is_(False))
            .order_by(User.date_joined.desc())
        )
        return list(result.scalars().all())

    async def update_activation(
        self,
        user_id: int,
        is_active: bool,
        can_approve_users: bool = False,
    ) -> Optional[User]:
        """
        Update user activation status and approval permissions.

        Args:
            user_id: User ID
            is_active: New active status
            can_approve_users: Can approve other users (default False)

        Returns:
            Updated User if found, None otherwise
        """
        logger.debug(
            "update_activation: user_id=%d, is_active=%s, can_approve_users=%s",
            user_id,
            is_active,
            can_approve_users,
        )
        user = await self._session.get(User, user_id)
        if not user:
            return None
        user.is_active = is_active
        user.can_approve_users = can_approve_users
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def delete(self, user_id: int) -> bool:
        """
        Delete user by ID.

        Args:
            user_id: User ID

        Returns:
            True if deleted, False if not found
        """
        logger.debug("delete: user_id=%d", user_id)
        user = await self._session.get(User, user_id)
        if not user:
            return False
        await self._session.delete(user)
        await self._session.commit()
        return True
