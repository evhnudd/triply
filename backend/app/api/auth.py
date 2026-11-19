from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.errors import ApiError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut, UserUpdate

router = APIRouter(tags=["Аккаунт"])


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED, summary="Регистрация")
def register(data: RegisterIn, db: DbSession):
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise ApiError(409, "email_taken", "Этот email уже зарегистрирован")
    user = User(email=data.email, password_hash=hash_password(data.password), display_name=data.display_name)
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenOut, summary="Вход")
def login(data: LoginIn, db: DbSession):
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None or not verify_password(data.password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Неверный email или пароль")
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut, summary="Изменить имя")
def update_me(data: UserUpdate, user: CurrentUser, db: DbSession):
    user.display_name = data.display_name
    db.commit()
    return user
