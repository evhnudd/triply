from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import DbSession, EditorAccess, ViewerAccess
from app.core.errors import ApiError
from app.models import Activity, Place
from app.schemas import ActivityCreate, ActivityOut, ActivityUpdate, PlaceCreate, PlaceOut, PlaceUpdate
from app.services import trips as svc

router = APIRouter(tags=["Места и активности"])


@router.get("/trips/{trip_id}/places", response_model=list[PlaceOut], summary="Места поездки")
def list_places(access: ViewerAccess, db: DbSession):
    return list(db.scalars(select(Place).where(Place.trip_id == access.trip.id).order_by(Place.id)))


@router.post(
    "/trips/{trip_id}/places",
    response_model=PlaceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить место (вручную или из результата поиска)",
)
def create_place(data: PlaceCreate, access: EditorAccess, db: DbSession):
    place = Place(**data.model_dump(), trip_id=access.trip.id, created_by=access.user.id)
    db.add(place)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "place_exists", "Это место уже добавлено в поездку") from None
    return place


@router.patch("/trips/{trip_id}/places/{place_id}", response_model=PlaceOut, summary="Изменить место")
def update_place(place_id: int, data: PlaceUpdate, access: EditorAccess, db: DbSession):
    place = svc.get_place(db, access.trip.id, place_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in ("name", "category") and value is None:
            continue
        setattr(place, field, value)
    db.commit()
    return place


@router.delete(
    "/trips/{trip_id}/places/{place_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить место (активности остаются, но без точки на карте)",
)
def delete_place(place_id: int, access: EditorAccess, db: DbSession):
    db.delete(svc.get_place(db, access.trip.id, place_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/trips/{trip_id}/activities",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить активность в день или в «нераспределённые»",
)
def create_activity(data: ActivityCreate, access: EditorAccess, db: DbSession):
    trip_id = access.trip.id
    if data.day_id is not None:
        svc.get_day(db, trip_id, data.day_id)
    if data.place_id is not None:
        svc.get_place(db, trip_id, data.place_id)
    fields = data.model_dump(exclude={"position", "day_id"})
    act = Activity(**fields, trip_id=trip_id, created_by=access.user.id, position=0, day_id=None)
    db.add(act)
    db.flush()
    svc.place_activity(db, act, data.day_id, data.position)
    db.commit()
    return act


@router.patch(
    "/trips/{trip_id}/activities/{activity_id}",
    response_model=ActivityOut,
    summary="Изменить активность или перенести в другой день",
)
def update_activity(activity_id: int, data: ActivityUpdate, access: EditorAccess, db: DbSession):
    trip_id = access.trip.id
    act = svc.get_activity(db, trip_id, activity_id)
    changes = data.model_dump(exclude_unset=True)
    move = "day_id" in changes or "position" in changes
    new_day = changes.pop("day_id", act.day_id)
    new_pos = changes.pop("position", None)
    if new_day is not None:
        svc.get_day(db, trip_id, new_day)
    if changes.get("place_id") is not None:
        svc.get_place(db, trip_id, changes["place_id"])
    if "title" in changes and changes["title"] is None:
        changes.pop("title")
    if "is_done" in changes and changes["is_done"] is None:
        changes.pop("is_done")
    for field, value in changes.items():
        setattr(act, field, value)
    if move:
        svc.place_activity(db, act, new_day, new_pos)
    db.commit()
    return act


@router.delete(
    "/trips/{trip_id}/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить активность"
)
def delete_activity(activity_id: int, access: EditorAccess, db: DbSession):
    act = svc.get_activity(db, access.trip.id, activity_id)
    day_id = act.day_id
    db.delete(act)
    db.flush()
    for i, a in enumerate(svc.list_day(db, access.trip.id, day_id)):
        a.position = i
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
