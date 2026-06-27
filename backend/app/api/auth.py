"""
API routes for authentication
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm

from app.models import (
    TokenResponse,
    RegisterRequest,
    UserResponse,
    UserUpdate,
    SetPasswordRequest,
    ForgotPasswordRequest,
)
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_token,
)
from app.db.repositories.user_repository import UserRepository
from app.api.deps import get_user_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/token", tags=["Authentication"])
security = HTTPBearer()


@router.post("/login/", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Авторизация пользователя (OAuth2 standard)
    """
    user = await repo.get_by_username(form_data.username)

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Пользователь неактивен")

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(auth_token=token)


@router.post("/logout/", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Выход из системы

    Инвалидирует токен (реализовать через blacklist)
    """
    # TODO: Добавить токен в blacklist
    return None


@router.post("/forgot-password/")
async def forgot_password(
    request: ForgotPasswordRequest,
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Запрос на сброс пароля.

    Принимает email, проверяет существование пользователя.
    Всегда возвращает успех (чтобы не раскрывать существование аккаунтов).
    В production: здесь отправка email со ссылкой для сброса.
    """
    user = await repo.get_by_email(request.email)

    # Логируем для отладки, но клиенту всегда возвращаем одинаковый ответ
    if user:
        # TODO: Отправка email с токеном сброса пароля
        pass

    msg = "Если аккаунт с указанным email существует, инструкции отправлены на почту"
    return {"detail": msg}


# === Users API ===

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Регистрация нового пользователя
    """
    if request.password != request.re_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароли не совпадают"
        )

    # 1. Проверяем существование пользователя
    existing_user = await repo.get_by_username(request.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким именем уже существует"
        )

    # 2. Создаём пользователя
    hashed_password = get_password_hash(request.password)
    try:
        new_user = await repo.create(
            username=request.username,
            email=request.email,
            full_name=request.full_name,
            hashed_password=hashed_password,
            is_active=False,
            is_staff=False,
            is_superuser=False,
        )
    except Exception as e:
        logger.error("User registration failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка создания пользователя: {str(e)}"
        )

    return new_user


@users_router.get("/me/", response_model=UserResponse)
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Получить данные текущего пользователя
    """
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен"
        )

    username = payload.get("sub")
    user = await repo.get_by_username(username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден"
        )

    return user


@users_router.put("/me/", response_model=UserResponse)
async def update_current_user(
    request: UserUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Обновить данные текущего пользователя
    """
    # TODO: Реализовать обновление
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Будет реализовано после настройки БД"
    )


@users_router.post("/set_password/", status_code=status.HTTP_204_NO_CONTENT)
async def set_password(
    request: SetPasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Сменить пароль текущего пользователя
    """
    # TODO: Реализовать смену пароля
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Будет реализовано после настройки БД"
    )


@users_router.get("/pending/", response_model=list[UserResponse])
async def get_pending_users(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Получить список пользователей, ожидающих подтверждения (is_active=False)
    Доступно администраторам и пользователям с can_approve_users=True
    """
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен"
        )

    username = payload.get("sub")
    current_user = await repo.get_by_username(username)

    if not current_user or not (current_user.is_superuser or current_user.can_approve_users):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав"
        )

    # Получаем неактивных пользователей
    pending_users = await repo.get_pending_users()
    return pending_users


@users_router.post("/{user_id}/approve/", response_model=UserResponse)
async def approve_user(
    user_id: int,
    can_approve_users: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Подтвердить регистрацию пользователя (установить is_active=True)
    Опционально дать право подтверждать других пользователей
    Доступно только администраторам и пользователям с can_approve_users=True
    """
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен"
        )

    username = payload.get("sub")
    current_user = await repo.get_by_username(username)

    if not current_user or not (current_user.is_superuser or current_user.can_approve_users):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав"
        )

    # Активируем пользователя
    user_to_approve = await repo.update_activation(
        user_id=user_id,
        is_active=True,
        can_approve_users=can_approve_users,
    )

    if not user_to_approve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    return user_to_approve


@users_router.post("/{user_id}/reject/", status_code=status.HTTP_200_OK)
async def reject_user(
    user_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    repo: UserRepository = Depends(get_user_repo),
):
    """
    Отклонить заявку пользователя (удалить из БД)
    Доступно администраторам и пользователям с can_approve_users=True
    """
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен"
        )

    username = payload.get("sub")
    current_user = await repo.get_by_username(username)

    if not current_user or not (current_user.is_superuser or current_user.can_approve_users):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав"
        )

    # Удаляем пользователя
    deleted = await repo.delete(user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    return {"status": "rejected", "user_id": user_id}
