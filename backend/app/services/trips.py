"""Бизнес-логика поездок: дни маршрута и порядок активностей."""

from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.models import Activity, ItineraryDay, Place, Trip


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def create_days(db: Session, trip: Trip) -> None:
    for d in date_range(trip.start_date, trip.end_date):
        db.add(ItineraryDay(trip_id=trip.id, day_date=d))


def sync_days_with_dates(db: Session, trip: Trip) -> None:
    """После смены дат: дни внутри диапазона сохраняются, недостающие добавляются,
    лишние удаляются. Их активности БД переводит в «нераспределённые» (day_id = NULL),
    а мы дописываем их в конец списка нераспределённых, чтобы порядок не сломался."""
    wanted = set(date_range(trip.start_date, trip.end_date))
    existing = {d.day_date: d for d in db.scalars(select(ItineraryDay).where(ItineraryDay.trip_id == trip.id))}

    removed_ids = [d.id for dt, d in existing.items() if dt not in wanted]
    if removed_ids:
        orphan_ids = list(
            db.scalars(
                select(Activity.id)
                .where(Activity.trip_id == trip.id, Activity.day_id.in_(removed_ids))
                .order_by(Activity.day_id, Activity.position)
            )
        )
        start = _next_position(db, trip.id, None)  # до удаления: сироты ещё не в «нераспределённых»
        db.execute(delete(ItineraryDay).where(ItineraryDay.id.in_(removed_ids)))
        db.expire_all()
        for offset, aid in enumerate(orphan_ids):
            db.get(Activity, aid).position = start + offset

    for dt in sorted(wanted - existing.keys()):
        db.add(ItineraryDay(trip_id=trip.id, day_date=dt))


def get_day(db: Session, trip_id: int, day_id: int) -> ItineraryDay:
    day = db.scalar(select(ItineraryDay).where(ItineraryDay.id == day_id, ItineraryDay.trip_id == trip_id))
    if day is None:
        raise not_found("День не найден")
    return day


def get_place(db: Session, trip_id: int, place_id: int) -> Place:
    place = db.scalar(select(Place).where(Place.id == place_id, Place.trip_id == trip_id))
    if place is None:
        raise not_found("Место не найдено")
    return place


def get_activity(db: Session, trip_id: int, activity_id: int) -> Activity:
    act = db.scalar(select(Activity).where(Activity.id == activity_id, Activity.trip_id == trip_id))
    if act is None:
        raise not_found("Активность не найдена")
    return act


def _day_filter(trip_id: int, day_id: int | None):
    cond = [Activity.trip_id == trip_id]
    cond.append(Activity.day_id.is_(None) if day_id is None else Activity.day_id == day_id)
    return cond


def list_day(db: Session, trip_id: int, day_id: int | None) -> list[Activity]:
    return list(
        db.scalars(select(Activity).where(*_day_filter(trip_id, day_id)).order_by(Activity.position, Activity.id))
    )


def _next_position(db: Session, trip_id: int, day_id: int | None) -> int:
    current = db.scalar(select(func.max(Activity.position)).where(*_day_filter(trip_id, day_id)))
    return 0 if current is None else current + 1


def place_activity(db: Session, act: Activity, day_id: int | None, position: int | None) -> None:
    """Ставит активность в день (или в «нераспределённые») на позицию и перенумеровывает 0..n."""
    old_day = act.day_id
    if old_day != day_id:
        others_old = [a for a in list_day(db, act.trip_id, old_day) if a.id != act.id]
        for i, a in enumerate(others_old):
            a.position = i
    target = [a for a in list_day(db, act.trip_id, day_id) if a.id != act.id]
    idx = len(target) if position is None else min(position, len(target))
    target.insert(idx, act)
    act.day_id = day_id
    for i, a in enumerate(target):
        a.position = i


def reorder_day(db: Session, trip_id: int, day_id: int, ordered_ids: list[int]) -> list[Activity]:
    current = list_day(db, trip_id, day_id)
    if sorted(ordered_ids) != sorted(a.id for a in current) or len(set(ordered_ids)) != len(ordered_ids):
        raise ApiError(
            409,
            "order_mismatch",
            "Список не совпадает с активностями дня — обновите страницу и попробуйте снова",
            {"expected": sorted(a.id for a in current)},
        )
    by_id = {a.id: a for a in current}
    for i, aid in enumerate(ordered_ids):
        by_id[aid].position = i
    return [by_id[aid] for aid in ordered_ids]
