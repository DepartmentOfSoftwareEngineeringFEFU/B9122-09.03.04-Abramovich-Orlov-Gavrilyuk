"""
Base repository class for all repositories
"""

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base class for all repositories providing session access."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self._session = session
