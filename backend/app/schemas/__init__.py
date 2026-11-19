from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import PlaceCategory, TripRole

MAX_TRIP_DAYS = 60

# Деньги и координаты в JSON идут строками ("1250.00"), чтобы JS не терял точность.
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, examples=["1250.00"])]
Lat = Annotated[Decimal, Field(ge=-90, le=90, examples=["54.710400"])]
Lng = Annotated[Decimal, Field(ge=-180, le=180, examples=["20.452200"])]
MoneyOut = Annotated[Decimal, Field(examples=["1250.00"])]
LatOut = Annotated[Decimal, Field(examples=["54.710400"])]
LngOut = Annotated[Decimal, Field(examples=["20.452200"])]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Аккаунт ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    email: str
    display_name: str


class UserUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Поездки ----------
class _TripDates(BaseModel):
    @model_validator(mode="after")
    def _check_dates(self):
        start, end = getattr(self, "start_date", None), getattr(self, "end_date", None)
        if start and end:
            if end < start:
                raise ValueError("end_date не может быть раньше start_date")
            if (end - start).days >= MAX_TRIP_DAYS:
                raise ValueError(f"Поездка не может быть длиннее {MAX_TRIP_DAYS} дней")
        return self


class TripCreate(_TripDates):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = None
    destination_name: str = Field(min_length=1, max_length=200)
    center_lat: Lat | None = None
    center_lng: Lng | None = None
    start_date: date
    end_date: date
    travelers_count: int = Field(default=1, ge=1, le=20)
    budget_limit: Money | None = None


class TripUpdate(_TripDates):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    destination_name: str | None = Field(default=None, min_length=1, max_length=200)
    center_lat: Lat | None = None
    center_lng: Lng | None = None
    start_date: date | None = None
    end_date: date | None = None
    travelers_count: int | None = Field(default=None, ge=1, le=20)
    budget_limit: Money | None = None


class TripOut(ORM):
    id: int
    title: str
    description: str | None
    destination_name: str
    center_lat: LatOut | None
    center_lng: LngOut | None
    start_date: date
    end_date: date
    travelers_count: int
    budget_limit: MoneyOut | None
    created_at: datetime


class TripListItem(TripOut):
    my_role: TripRole
    days_count: int


# ---------- Места ----------
class PlaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = None
    lat: Lat
    lng: Lng
    category: PlaceCategory = PlaceCategory.other
    source: str = Field(default="manual", max_length=20)
    external_id: str | None = Field(default=None, max_length=100)
    note: str | None = None


class PlaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = None
    category: PlaceCategory | None = None
    note: str | None = None


class PlaceOut(ORM):
    id: int
    trip_id: int
    name: str
    address: str | None
    lat: LatOut
    lng: LngOut
    category: PlaceCategory
    source: str
    external_id: str | None
    note: str | None
    created_by: int | None


# ---------- Активности ----------
class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    day_id: int | None = None
    place_id: int | None = None
    start_time: time | None = None
    note: str | None = None
    url: str | None = None
    estimated_cost: Money | None = None
    position: int | None = Field(default=None, ge=0, description="Куда вставить; по умолчанию в конец дня")


class ActivityUpdate(BaseModel):
    """Все поля необязательны. Чтобы перенести в «нераспределённые», передайте day_id: null."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    day_id: int | None = None
    place_id: int | None = None
    start_time: time | None = None
    note: str | None = None
    url: str | None = None
    estimated_cost: Money | None = None
    is_done: bool | None = None
    position: int | None = Field(default=None, ge=0)


class ActivityOut(ORM):
    id: int
    trip_id: int
    day_id: int | None
    place_id: int | None
    title: str
    start_time: time | None
    position: int
    note: str | None
    url: str | None
    estimated_cost: MoneyOut | None
    is_done: bool
    created_by: int | None


class DayUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class DayOrderIn(BaseModel):
    activity_ids: list[int] = Field(description="Все активности дня в новом порядке")


class DayOut(ORM):
    id: int
    day_date: date
    day_number: int
    title: str | None
    activities: list[ActivityOut]


class TripDetail(TripOut):
    my_role: TripRole
    days: list[DayOut]
    unassigned: list[ActivityOut]
    places: list[PlaceOut]


# ---------- Гео ----------
class GeoResult(BaseModel):
    name: str
    address: str | None
    lat: float
    lng: float
    category: PlaceCategory
    source: str = "osm"
    external_id: str | None
