"""Поиск мест через Photon (геокодер на данных OpenStreetMap) с кэшем в БД.

Провайдер спрятан за классом GeoProvider, чтобы его можно было заменить
(Nominatim, 2ГИС) или подменить фейком в тестах."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models import ExternalCache, PlaceCategory

_OSM_TYPES = {"N": "node", "W": "way", "R": "relation"}

_CATEGORY_BY_KEY = {
    "tourism": PlaceCategory.sight,
    "historic": PlaceCategory.sight,
    "amenity": PlaceCategory.other,
    "shop": PlaceCategory.shopping,
    "leisure": PlaceCategory.entertainment,
    "natural": PlaceCategory.nature,
    "railway": PlaceCategory.transport,
    "aeroway": PlaceCategory.transport,
    "public_transport": PlaceCategory.transport,
}
_FOOD = {"restaurant", "cafe", "fast_food", "bar", "pub", "food_court", "ice_cream", "bakery"}
_STAY = {"hotel", "hostel", "guest_house", "motel", "apartment", "camp_site"}
_NATURE_LEISURE = {"park", "garden", "nature_reserve", "beach_resort"}


def guess_category(osm_key: str | None, osm_value: str | None) -> PlaceCategory:
    if osm_value in _FOOD:
        return PlaceCategory.food
    if osm_value in _STAY:
        return PlaceCategory.accommodation
    if osm_key == "leisure" and osm_value in _NATURE_LEISURE:
        return PlaceCategory.nature
    return _CATEGORY_BY_KEY.get(osm_key or "", PlaceCategory.other)


def _address(props: dict) -> str | None:
    street = " ".join(p for p in [props.get("street"), props.get("housenumber")] if p)
    parts = [street, props.get("city") or props.get("town") or props.get("village"), props.get("country")]
    text = ", ".join(p for p in parts if p)
    return text or None


def parse_photon(payload: dict) -> list[dict]:
    results = []
    for f in payload.get("features", []):
        props = f.get("properties", {})
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
        name = props.get("name") or props.get("street") or props.get("city")
        if not name or coords[0] is None:
            continue
        osm_type = _OSM_TYPES.get(props.get("osm_type", ""), props.get("osm_type"))
        ext = f"{osm_type}/{props['osm_id']}" if props.get("osm_id") and osm_type else None
        results.append(
            {
                "name": name,
                "address": _address(props),
                "lat": coords[1],
                "lng": coords[0],
                "category": guess_category(props.get("osm_key"), props.get("osm_value")).value,
                "source": "osm",
                "external_id": ext,
            }
        )
    return results


class GeoProvider:
    def search(self, query: str, lat: float | None, lng: float | None, limit: int) -> list[dict]:
        raise NotImplementedError

    def reverse(self, lat: float, lng: float) -> list[dict]:
        raise NotImplementedError


class PhotonProvider(GeoProvider):
    def _get(self, path: str, params: dict) -> dict:
        try:
            resp = httpx.get(
                f"{settings.photon_url}{path}",
                params=params,
                headers={"User-Agent": settings.geo_user_agent},
                timeout=settings.geo_timeout_seconds,
            )
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(503, "geo_unavailable", "Сервис поиска мест сейчас недоступен") from exc

    def search(self, query, lat, lng, limit):
        params = {"q": query, "limit": limit}
        if lat is not None and lng is not None:
            params |= {"lat": lat, "lon": lng}
        return parse_photon(self._get("/api/", params))

    def reverse(self, lat, lng):
        return parse_photon(self._get("/reverse", {"lat": lat, "lon": lng}))


class CachedGeo:
    """Обёртка с кэшем в таблице external_cache."""

    def __init__(self, db: Session, provider: GeoProvider):
        self.db = db
        self.provider = provider

    def _key(self, kind: str, params: dict) -> str:
        raw = json.dumps({"p": "photon", "k": kind, **params}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cached(self, kind: str, params: dict, fetch) -> list[dict]:
        key = self._key(kind, params)
        now = datetime.now(UTC)
        row = self.db.get(ExternalCache, key)
        if row is not None and row.expires_at > now:
            return row.response["items"]
        items = fetch()
        self.db.execute(delete(ExternalCache).where(ExternalCache.cache_key == key))
        self.db.add(
            ExternalCache(
                cache_key=key, response={"items": items}, expires_at=now + timedelta(days=settings.geo_cache_days)
            )
        )
        self.db.commit()
        return items

    def search(self, query: str, lat: float | None, lng: float | None, limit: int) -> list[dict]:
        q = " ".join(query.lower().split())
        near = (round(lat, 2), round(lng, 2)) if lat is not None and lng is not None else None
        return self._cached(
            "search", {"q": q, "near": near, "limit": limit}, lambda: self.provider.search(q, lat, lng, limit)
        )

    def reverse(self, lat: float, lng: float) -> list[dict]:
        lat, lng = round(lat, 5), round(lng, 5)
        return self._cached("reverse", {"lat": lat, "lng": lng}, lambda: self.provider.reverse(lat, lng))


def get_geo_provider() -> GeoProvider:
    return PhotonProvider()
