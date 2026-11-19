from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, ViewerAccess
from app.core.errors import ApiError
from app.models import Activity, ItineraryDay, Place
from app.schemas import GeoResult
from app.services.geo import CachedGeo, GeoProvider, get_geo_provider

router = APIRouter(tags=["Карта и поиск мест"])

Provider = Annotated[GeoProvider, Depends(get_geo_provider)]


@router.get("/geo/search", response_model=list[GeoResult], summary="Поиск мест (Photon / OpenStreetMap, с кэшем)")
def geo_search(
    user: CurrentUser,
    db: DbSession,
    provider: Provider,
    q: Annotated[str, Query(min_length=3, max_length=200, description="Название или адрес")],
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Искать рядом с точкой")] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
):
    return CachedGeo(db, provider).search(q, lat, lng, limit)


@router.get("/geo/reverse", response_model=list[GeoResult], summary="Что находится в точке (клик по карте)")
def geo_reverse(
    user: CurrentUser,
    db: DbSession,
    provider: Provider,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
):
    return CachedGeo(db, provider).reverse(lat, lng)


@router.get("/trips/{trip_id}/map", summary="Точки поездки в формате GeoJSON для Leaflet")
def trip_map(
    access: ViewerAccess,
    db: DbSession,
    day_id: Annotated[int | None, Query(description="Только один день")] = None,
):
    trip = access.trip
    days = {d.id: d for d in db.scalars(select(ItineraryDay).where(ItineraryDay.trip_id == trip.id))}
    if day_id is not None and day_id not in days:
        raise ApiError(404, "not_found", "День не найден")

    stmt = (
        select(Activity, Place)
        .join(Place, Place.id == Activity.place_id)
        .where(Activity.trip_id == trip.id)
        .order_by(Activity.day_id.nulls_last(), Activity.position)
    )
    if day_id is not None:
        stmt = stmt.where(Activity.day_id == day_id)

    features, scheduled_places = [], set()
    for act, place in db.execute(stmt).all():
        scheduled_places.add(place.id)
        day = days.get(act.day_id)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(place.lng), float(place.lat)]},
                "properties": {
                    "kind": "activity",
                    "activity_id": act.id,
                    "place_id": place.id,
                    "title": act.title,
                    "place_name": place.name,
                    "category": place.category.value,
                    "day_id": act.day_id,
                    "day_number": (day.day_date - trip.start_date).days + 1 if day else None,
                    "position": act.position,
                    "start_time": act.start_time.isoformat() if act.start_time else None,
                },
            }
        )

    if day_id is None:
        for place in db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.id)):
            if place.id in scheduled_places:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(place.lng), float(place.lat)]},
                    "properties": {
                        "kind": "place",
                        "activity_id": None,
                        "place_id": place.id,
                        "title": place.name,
                        "place_name": place.name,
                        "category": place.category.value,
                        "day_id": None,
                        "day_number": None,
                        "position": None,
                        "start_time": None,
                    },
                }
            )

    center = (
        [float(trip.center_lng), float(trip.center_lat)]
        if trip.center_lat is not None and trip.center_lng is not None
        else None
    )
    return {"type": "FeatureCollection", "center": center, "features": features}
