"""ORM-модели. Таблицы создаются только миграциями Alembic (см. alembic/versions)."""

import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TripRole(enum.StrEnum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class PlaceCategory(enum.StrEnum):
    sight = "sight"
    food = "food"
    accommodation = "accommodation"
    transport = "transport"
    shopping = "shopping"
    nature = "nature"
    entertainment = "entertainment"
    other = "other"


trip_role_enum = ENUM(TripRole, name="trip_role", create_type=False)
place_category_enum = ENUM(PlaceCategory, name="place_category", create_type=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    destination_name: Mapped[str] = mapped_column(String(200))
    center_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    center_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    travelers_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    budget_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TripMember(Base):
    __tablename__ = "trip_members"

    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[TripRole] = mapped_column(trip_role_enum)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItineraryDay(Base):
    __tablename__ = "itinerary_days"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    day_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str | None] = mapped_column(String(120))


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    category: Mapped[PlaceCategory] = mapped_column(place_category_enum, default=PlaceCategory.other)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    external_id: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Activity(Base):
    __tablename__ = "activities"
    # Составные внешние ключи через trip_id: в БД (миграция) у них ON DELETE SET NULL (колонка).
    __table_args__ = (
        ForeignKeyConstraint(["day_id", "trip_id"], ["itinerary_days.id", "itinerary_days.trip_id"]),
        ForeignKeyConstraint(["place_id", "trip_id"], ["places.id", "places.trip_id"]),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    day_id: Mapped[int | None] = mapped_column(BigInteger)
    place_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(200))
    start_time: Mapped[time | None] = mapped_column(Time)
    position: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExternalCache(Base):
    __tablename__ = "external_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
