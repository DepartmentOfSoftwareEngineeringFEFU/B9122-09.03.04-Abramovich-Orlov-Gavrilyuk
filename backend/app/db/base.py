"""
Base class for database models
"""

from app.core.database import Base

# Import all models here for Alembic autogenerate
from app.db.models.user import User
from app.db.models.reconstruction import Reconstruction, UploadedFile, Room
from app.db.models.building import Building, Floor
from app.db.models.section import Section  # noqa: F401
