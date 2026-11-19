from fastapi import APIRouter, Response, status
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, EditorAccess, OwnerAccess, ViewerAccess
from app.core.errors import ApiError
from app.models import Activity, ItineraryDay, Place, Trip, TripMember, TripRole
from app.schemas import (
    ActivityOut,
    DayOrderIn,
    DayOut,
    DayUpdate,
    PlaceOut,
    TripCreate,
    TripDetail,
    TripListItem,
    TripOut,
    TripUpdate,
)
from app.services import trips as svc

router = APIRouter(tags=["Поездки и дни"])


def build_detail(db, trip: Trip, role: TripRole) -> TripDetail:
    days = list(db.scalars(select(ItineraryDay).where(ItineraryDay.trip_id == trip.id).order_by(ItineraryDay.day_date)))
    acts = list(
        db.scalars(select(Activity).where(Activity.trip_id == trip.id).order_by(Activity.position, Activity.id))
    )
    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.id)))
    by_day: dict[int | None, list] = {}
    for a in acts:
        by_day.setdefault(a.day_id, []).append(ActivityOut.model_validate(a))
    return TripDetail(
        **TripOut.model_validate(trip).model_dump(),
        my_role=role,
        days=[
            DayOut(
                id=d.id,
                day_date=d.day_date,
                day_number=(d.day_date - trip.start_date).days + 1,
                title=d.title,
                activities=by_day.get(d.id, []),
            )
            for d in days
        ],
        unassigned=by_day.get(None, []),
        places=[PlaceOut.model_validate(p) for p in places],
    )


@router.get("/trips", response_model=list[TripListItem], summary="Мои поездки")
def list_trips(user: CurrentUser, db: DbSession):
    days_count = (
        select(func.count(ItineraryDay.id)).where(ItineraryDay.trip_id == Trip.id).correlate(Trip).scalar_subquery()
    )
    rows = db.execute(
        select(Trip, TripMember.role, days_count)
        .join(TripMember, TripMember.trip_id == Trip.id)
        .where(TripMember.user_id == user.id, TripMember.left_at.is_(None))
        .order_by(Trip.start_date.desc(), Trip.id.desc())
    ).all()
    return [
        TripListItem(**TripOut.model_validate(t).model_dump(), my_role=role, days_count=cnt) for t, role, cnt in rows
    ]


@router.post(
    "/trips",
    response_model=TripDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать поездку (дни создаются автоматически)",
)
def create_trip(data: TripCreate, user: CurrentUser, db: DbSession):
    trip = Trip(**data.model_dump())
    db.add(trip)
    db.flush()
    db.add(TripMember(trip_id=trip.id, user_id=user.id, role=TripRole.owner))
    svc.create_days(db, trip)
    db.commit()
    return build_detail(db, trip, TripRole.owner)


@router.get("/trips/{trip_id}", response_model=TripDetail, summary="Поездка целиком: дни, активности, места")
def get_trip(access: ViewerAccess, db: DbSession):
    return build_detail(db, access.trip, access.role)


@router.patch("/trips/{trip_id}", response_model=TripDetail, summary="Изменить поездку (только владелец)")
def update_trip(data: TripUpdate, access: OwnerAccess, db: DbSession):
    trip = access.trip
    changes = data.model_dump(exclude_unset=True)
    for field in ("title", "destination_name", "start_date", "end_date", "travelers_count"):
        if field in changes and changes[field] is None:
            raise ApiError(422, "validation_error", f"Поле {field} не может быть пустым")
    old_dates = (trip.start_date, trip.end_date)
    for field, value in changes.items():
        setattr(trip, field, value)
    if trip.end_date < trip.start_date or (trip.end_date - trip.start_date).days >= 60:
        raise ApiError(422, "validation_error", "Некорректные даты поездки")
    if (trip.start_date, trip.end_date) != old_dates:
        db.flush()
        svc.sync_days_with_dates(db, trip)
    db.commit()
    return build_detail(db, trip, access.role)


@router.delete("/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить поездку (только владелец)")
def delete_trip(access: OwnerAccess, db: DbSession):
    db.delete(access.trip)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/trips/{trip_id}/days/{day_id}", response_model=DayOut, summary="Название дня")
def update_day(day_id: int, data: DayUpdate, access: EditorAccess, db: DbSession):
    day = svc.get_day(db, access.trip.id, day_id)
    day.title = data.title
    db.commit()
    return DayOut(
        id=day.id,
        day_date=day.day_date,
        day_number=(day.day_date - access.trip.start_date).days + 1,
        title=day.title,
        activities=[ActivityOut.model_validate(a) for a in svc.list_day(db, access.trip.id, day.id)],
    )


@router.put(
    "/trips/{trip_id}/days/{day_id}/order",
    response_model=list[ActivityOut],
    summary="Новый порядок активностей дня (после drag-and-drop)",
)
def reorder_day(day_id: int, data: DayOrderIn, access: EditorAccess, db: DbSession):
    svc.get_day(db, access.trip.id, day_id)
    result = svc.reorder_day(db, access.trip.id, day_id, data.activity_ids)
    db.commit()
    return result
