"""Демо-данные для показа: python -m app.scripts.seed

Создаёт пользователя demo@triply.ru (пароль demo12345) и поездку в Калининград
с местами и планом по дням. Повторный запуск пересоздаёт демо-поездку."""

from datetime import date, time
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Activity, ItineraryDay, Place, PlaceCategory, Trip, TripMember, TripRole, User
from app.services.trips import create_days

DEMO_EMAIL = "demo@triply.ru"
DEMO_PASSWORD = "demo12345"

PLACES = [
    ("Кафедральный собор", 54.706189, 20.511873, PlaceCategory.sight, "Остров Канта"),
    ("Музей Мирового океана", 54.708640, 20.495590, PlaceCategory.sight, "Набережная Петра Великого, 1"),
    ("Рыбная деревня", 54.704670, 20.517210, PlaceCategory.food, "ул. Октябрьская"),
    ("Музей янтаря", 54.719570, 20.519210, PlaceCategory.sight, "пл. Маршала Василевского, 1"),
    ("Куршская коса", 55.150000, 20.850000, PlaceCategory.nature, "Национальный парк"),
    ("Зеленоградск, променад", 54.961500, 20.476700, PlaceCategory.nature, "Зеленоградск"),
]

PLAN = [  # (номер дня, название, место, время, оценка стоимости)
    (1, "Прогулка по острову Канта", 0, time(11, 0), Decimal("0")),
    (1, "Музей Мирового океана", 1, time(14, 0), Decimal("600")),
    (1, "Ужин в Рыбной деревне", 2, time(19, 0), Decimal("2500")),
    (2, "Музей янтаря", 3, time(11, 0), Decimal("400")),
    (3, "Танцующий лес на Куршской косе", 4, time(10, 0), Decimal("600")),
    (3, "Закат в Зеленоградске", 5, time(18, 30), Decimal("0")),
]


def run() -> None:
    db = SessionLocal()
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), display_name="Демо")
        db.add(user)
        db.flush()
    old = db.scalars(
        select(Trip.id).join(TripMember).where(TripMember.user_id == user.id, Trip.title == "Калининград на майские")
    ).all()
    if old:
        db.execute(delete(Trip).where(Trip.id.in_(old)))

    trip = Trip(
        title="Калининград на майские",
        destination_name="Калининград",
        center_lat=Decimal("54.710400"),
        center_lng=Decimal("20.452200"),
        start_date=date(2027, 5, 1),
        end_date=date(2027, 5, 4),
        travelers_count=3,
        budget_limit=Decimal("60000.00"),
        description="Демо-поездка для показа",
    )
    db.add(trip)
    db.flush()
    db.add(TripMember(trip_id=trip.id, user_id=user.id, role=TripRole.owner))
    create_days(db, trip)
    db.flush()

    places = []
    for name, lat, lng, cat, addr in PLACES:
        p = Place(
            trip_id=trip.id,
            name=name,
            lat=Decimal(str(lat)),
            lng=Decimal(str(lng)),
            category=cat,
            address=addr,
            created_by=user.id,
        )
        db.add(p)
        places.append(p)
    db.flush()

    days = {
        (d.day_date - trip.start_date).days + 1: d
        for d in db.scalars(select(ItineraryDay).where(ItineraryDay.trip_id == trip.id))
    }
    positions: dict[int, int] = {}
    for day_no, title, place_idx, start, cost in PLAN:
        pos = positions.get(day_no, 0)
        positions[day_no] = pos + 1
        db.add(
            Activity(
                trip_id=trip.id,
                day_id=days[day_no].id,
                place_id=places[place_idx].id,
                title=title,
                start_time=start,
                position=pos,
                estimated_cost=cost,
                created_by=user.id,
            )
        )
    db.add(Activity(trip_id=trip.id, day_id=None, title="Купить магниты", position=0, created_by=user.id))
    db.commit()
    print(f"Готово: {DEMO_EMAIL} / {DEMO_PASSWORD}, поездка id={trip.id}")


if __name__ == "__main__":
    run()
