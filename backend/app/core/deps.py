from typing import Annotated

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, forbidden, not_found
from app.core.security import decode_access_token
from app.db import get_db
from app.models import Trip, TripMember, TripRole, User

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {TripRole.viewer: 1, TripRole.editor: 2, TripRole.owner: 3}


def get_current_user(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if creds is None:
        raise ApiError(401, "not_authenticated", "Нужно войти в аккаунт")
    user_id = decode_access_token(creds.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise ApiError(401, "invalid_token", "Сессия истекла, войдите снова")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class TripAccess:
    """Результат проверки доступа: поездка, участник и его роль."""

    def __init__(self, trip: Trip, member: TripMember, user: User):
        self.trip = trip
        self.member = member
        self.user = user

    @property
    def role(self) -> TripRole:
        return self.member.role


def require_trip_role(min_role: TripRole):
    """Проверка прав на поездку.

    Не участник (или вышел) -> 404, чтобы не раскрывать сам факт существования поездки.
    Роль ниже нужной -> 403.
    """

    def dependency(trip_id: Annotated[int, Path(ge=1)], db: DbSession, user: CurrentUser) -> TripAccess:
        row = db.execute(
            select(Trip, TripMember)
            .join(TripMember, TripMember.trip_id == Trip.id)
            .where(Trip.id == trip_id, TripMember.user_id == user.id, TripMember.left_at.is_(None))
        ).first()
        if row is None:
            raise not_found("Поездка не найдена")
        trip, member = row
        if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
            raise forbidden()
        return TripAccess(trip, member, user)

    return dependency


ViewerAccess = Annotated[TripAccess, Depends(require_trip_role(TripRole.viewer))]
EditorAccess = Annotated[TripAccess, Depends(require_trip_role(TripRole.editor))]
OwnerAccess = Annotated[TripAccess, Depends(require_trip_role(TripRole.owner))]
