"""
Pydantic модели для пользователей и аутентификации
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# === Auth ===

class LoginRequest(BaseModel):
    """Запрос на авторизацию"""
    username: str = Field(..., min_length=4, max_length=15)
    password: str = Field(..., min_length=8, max_length=20)


class TokenResponse(BaseModel):
    """Ответ с токеном"""
    auth_token: str


class RegisterRequest(BaseModel):
    """Запрос на регистрацию"""
    username: str = Field(..., min_length=4, max_length=50, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(..., min_length=8, max_length=20)
    re_password: str = Field(..., min_length=8, max_length=20)
    email: Optional[EmailStr] = None
    full_name: str = Field(..., min_length=2, max_length=255)


# === User ===

class UserBase(BaseModel):
    """Базовая модель пользователя"""
    username: str
    email: Optional[EmailStr] = None
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


class UserCreate(UserBase):
    """Создание пользователя"""
    password: str


class UserResponse(UserBase):
    """Ответ с данными пользователя"""
    id: int
    full_name: str
    is_staff: bool = False
    is_superuser: bool = False
    is_active: bool = True
    can_approve_users: bool = False
    display_name: str = ""
    date_joined: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Обновление данных пользователя"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None


class SetPasswordRequest(BaseModel):
    """Запрос на смену пароля"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=20)


class ChangePasswordRequest(BaseModel):
    """Административная смена пароля"""
    new_password: str = Field(..., min_length=8, max_length=20)
    re_new_password: str


class ForgotPasswordRequest(BaseModel):
    """Запрос на сброс пароля"""
    email: EmailStr


class UpdateFlagRequest(BaseModel):
    """Обновление флага пользователя"""
    value: bool
