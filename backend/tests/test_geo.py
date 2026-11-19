from app.services.geo import guess_category, parse_photon
from tests.conftest import FakeGeo, make_trip


def test_search_uses_cache(client, auth):
    r1 = client.get("/api/v1/geo/search", params={"q": "Собор"}, headers=auth)
    r2 = client.get("/api/v1/geo/search", params={"q": "  собор "}, headers=auth)
    assert r1.status_code == 200 and r1.json()[0]["name"] == "Кафедральный собор"
    assert r2.json() == r1.json()
    assert FakeGeo.calls == 1


def test_search_needs_3_chars_and_auth(client, auth):
    assert client.get("/api/v1/geo/search", params={"q": "ab"}, headers=auth).status_code == 422
    assert client.get("/api/v1/geo/search", params={"q": "abc"}).status_code == 401


def test_reverse(client, auth):
    r = client.get("/api/v1/geo/reverse", params={"lat": 54.7, "lng": 20.5}, headers=auth)
    assert r.status_code == 200 and r.json()[0]["lat"] == 54.7


def test_parse_photon():
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [20.511, 54.706]},
                "properties": {
                    "name": "Кафедральный собор",
                    "osm_type": "W",
                    "osm_id": 1234,
                    "osm_key": "amenity",
                    "osm_value": "place_of_worship",
                    "city": "Калининград",
                    "country": "Россия",
                },
            },
            {
                "geometry": {"coordinates": [20.5, 54.7]},
                "properties": {"name": "Кафе", "osm_type": "N", "osm_id": 5, "osm_key": "amenity", "osm_value": "cafe"},
            },
            {"geometry": {"coordinates": [1, 2]}, "properties": {}},
        ]
    }
    items = parse_photon(payload)
    assert len(items) == 2
    assert items[0]["external_id"] == "way/1234" and items[0]["lat"] == 54.706
    assert items[0]["address"] == "Калининград, Россия"
    assert items[1]["category"] == "food"
    assert guess_category("leisure", "park").value == "nature"


def test_map_geojson(client, auth):
    trip = make_trip(client, auth)
    tid, d2 = trip["id"], trip["days"][1]["id"]
    p1 = client.post(
        f"/api/v1/trips/{tid}/places",
        headers=auth,
        json={"name": "Собор", "lat": "54.706", "lng": "20.511", "category": "sight"},
    ).json()
    client.post(
        f"/api/v1/trips/{tid}/places", headers=auth, json={"name": "Музей янтаря", "lat": "54.719", "lng": "20.519"}
    )
    client.post(
        f"/api/v1/trips/{tid}/activities",
        headers=auth,
        json={"title": "Экскурсия в собор", "day_id": d2, "place_id": p1["id"]},
    )

    fc = client.get(f"/api/v1/trips/{tid}/map", headers=auth).json()
    assert fc["type"] == "FeatureCollection"
    assert fc["center"] == [20.4522, 54.7104]
    kinds = sorted(f["properties"]["kind"] for f in fc["features"])
    assert kinds == ["activity", "place"]
    act = next(f for f in fc["features"] if f["properties"]["kind"] == "activity")
    assert act["geometry"]["coordinates"] == [20.511, 54.706]
    assert act["properties"]["day_number"] == 2

    one_day = client.get(f"/api/v1/trips/{tid}/map", params={"day_id": d2}, headers=auth).json()
    assert len(one_day["features"]) == 1
