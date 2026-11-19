import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from tests.conftest import make_trip


def _add(client, auth, trip_id, title, **kw):
    r = client.post(f"/api/v1/trips/{trip_id}/activities", headers=auth, json={"title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_place_crud_and_duplicates(client, auth):
    trip = make_trip(client, auth)
    url = f"/api/v1/trips/{trip['id']}/places"
    place = {
        "name": "Кафедральный собор",
        "lat": "54.706",
        "lng": "20.511",
        "category": "sight",
        "source": "osm",
        "external_id": "way/1234",
    }
    r = client.post(url, headers=auth, json=place)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.post(url, headers=auth, json=place).status_code == 409
    r = client.patch(f"{url}/{pid}", headers=auth, json={"note": "Орган в 12:00"})
    assert r.json()["note"] == "Орган в 12:00"
    assert len(client.get(url, headers=auth).json()) == 1


def test_activities_order_and_move(client, auth):
    trip = make_trip(client, auth)
    tid = trip["id"]
    d1, d2 = trip["days"][0]["id"], trip["days"][1]["id"]
    a = _add(client, auth, tid, "Собор", day_id=d1)
    b = _add(client, auth, tid, "Музей янтаря", day_id=d1)
    c = _add(client, auth, tid, "Рыбная деревня", day_id=d1)
    assert [a["position"], b["position"], c["position"]] == [0, 1, 2]

    r = client.put(
        f"/api/v1/trips/{tid}/days/{d1}/order", headers=auth, json={"activity_ids": [c["id"], a["id"], b["id"]]}
    )
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [c["id"], a["id"], b["id"]]

    r = client.put(f"/api/v1/trips/{tid}/days/{d1}/order", headers=auth, json={"activity_ids": [a["id"]]})
    assert r.status_code == 409

    r = client.patch(f"/api/v1/trips/{tid}/activities/{a['id']}", headers=auth, json={"day_id": d2})
    assert r.json()["day_id"] == d2 and r.json()["position"] == 0

    detail = client.get(f"/api/v1/trips/{tid}", headers=auth).json()
    day1 = detail["days"][0]["activities"]
    assert [x["title"] for x in day1] == ["Рыбная деревня", "Музей янтаря"]
    assert [x["position"] for x in day1] == [0, 1]

    r = client.patch(f"/api/v1/trips/{tid}/activities/{b['id']}", headers=auth, json={"day_id": None})
    assert r.json()["day_id"] is None
    assert client.get(f"/api/v1/trips/{tid}", headers=auth).json()["unassigned"][0]["title"] == "Музей янтаря"

    assert client.delete(f"/api/v1/trips/{tid}/activities/{c['id']}", headers=auth).status_code == 204


def test_insert_at_position(client, auth):
    trip = make_trip(client, auth)
    tid, d1 = trip["id"], trip["days"][0]["id"]
    _add(client, auth, tid, "A", day_id=d1)
    _add(client, auth, tid, "C", day_id=d1)
    _add(client, auth, tid, "B", day_id=d1, position=1)
    titles = [x["title"] for x in client.get(f"/api/v1/trips/{tid}", headers=auth).json()["days"][0]["activities"]]
    assert titles == ["A", "B", "C"]


def test_deleting_place_keeps_activity(client, auth):
    trip = make_trip(client, auth)
    tid = trip["id"]
    pid = client.post(
        f"/api/v1/trips/{tid}/places", headers=auth, json={"name": "Собор", "lat": "54.7", "lng": "20.5"}
    ).json()["id"]
    act = _add(client, auth, tid, "Собор", day_id=trip["days"][0]["id"], place_id=pid)
    assert client.delete(f"/api/v1/trips/{tid}/places/{pid}", headers=auth).status_code == 204
    detail = client.get(f"/api/v1/trips/{tid}", headers=auth).json()
    kept = detail["days"][0]["activities"][0]
    assert kept["id"] == act["id"] and kept["place_id"] is None


def test_cannot_use_day_of_another_trip(client, auth):
    t1, t2 = make_trip(client, auth), make_trip(client, auth)
    r = client.post(
        f"/api/v1/trips/{t1['id']}/activities", headers=auth, json={"title": "x", "day_id": t2["days"][0]["id"]}
    )
    assert r.status_code == 404


def test_db_blocks_cross_trip_day_even_without_api(client, auth):
    t1, t2 = make_trip(client, auth), make_trip(client, auth)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO activities (trip_id, day_id, title) VALUES (:t, :d, 'x')"),
                {"t": t1["id"], "d": t2["days"][0]["id"]},
            )


def test_estimated_cost_is_string(client, auth):
    trip = make_trip(client, auth)
    a = _add(client, auth, trip["id"], "Музей", estimated_cost="450.00")
    assert a["estimated_cost"] == "450.00"
