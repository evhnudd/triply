from sqlalchemy import text

from app.db import engine
from tests.conftest import make_trip, register


def test_create_trip_generates_days(client, auth):
    trip = make_trip(client, auth)
    assert trip["my_role"] == "owner"
    assert [d["day_date"] for d in trip["days"]] == ["2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"]
    assert [d["day_number"] for d in trip["days"]] == [1, 2, 3, 4]

    listing = client.get("/api/v1/trips", headers=auth).json()
    assert len(listing) == 1 and listing[0]["days_count"] == 4


def test_invalid_dates(client, auth):
    r = client.post(
        "/api/v1/trips",
        headers=auth,
        json={"title": "x", "destination_name": "x", "start_date": "2026-05-10", "end_date": "2026-05-01"},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/trips",
        headers=auth,
        json={"title": "x", "destination_name": "x", "start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    assert r.status_code == 422


def test_foreign_trip_is_404(client, auth):
    trip = make_trip(client, auth)
    stranger = register(client, "boris@example.com", "Борис")
    r = client.get(f"/api/v1/trips/{trip['id']}", headers=stranger)
    assert r.status_code == 404
    assert client.get("/api/v1/trips", headers=stranger).json() == []
    assert client.delete(f"/api/v1/trips/{trip['id']}", headers=stranger).status_code == 404


def test_viewer_cannot_edit(client, auth):
    trip = make_trip(client, auth)
    viewer = register(client, "vera@example.com", "Вера")
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO trip_members (trip_id, user_id, role) VALUES (:t, 2, 'viewer')"), {"t": trip["id"]}
        )
    assert client.get(f"/api/v1/trips/{trip['id']}", headers=viewer).status_code == 200
    r = client.post(f"/api/v1/trips/{trip['id']}/activities", headers=viewer, json={"title": "Музей"})
    assert r.status_code == 403
    assert client.patch(f"/api/v1/trips/{trip['id']}", headers=viewer, json={"title": "x"}).status_code == 403


def test_shrinking_dates_moves_activities_to_unassigned(client, auth):
    trip = make_trip(client, auth)
    last_day = trip["days"][-1]["id"]
    for title in ("Куршская коса", "Зеленоградск"):
        client.post(f"/api/v1/trips/{trip['id']}/activities", headers=auth, json={"title": title, "day_id": last_day})

    r = client.patch(f"/api/v1/trips/{trip['id']}", headers=auth, json={"end_date": "2026-05-13"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["days"]) == 2
    assert [a["title"] for a in body["unassigned"]] == ["Куршская коса", "Зеленоградск"]
    assert [a["position"] for a in body["unassigned"]] == [0, 1]

    r = client.patch(f"/api/v1/trips/{trip['id']}", headers=auth, json={"end_date": "2026-05-16"})
    assert len(r.json()["days"]) == 5


def test_delete_trip(client, auth):
    trip = make_trip(client, auth)
    assert client.delete(f"/api/v1/trips/{trip['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/trips/{trip['id']}", headers=auth).status_code == 404


def test_one_owner_per_trip_enforced_by_db(client, auth):
    import pytest
    from sqlalchemy.exc import IntegrityError

    trip = make_trip(client, auth)
    register(client, "boris@example.com", "Борис")
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO trip_members (trip_id, user_id, role) VALUES (:t, 2, 'owner')"), {"t": trip["id"]}
            )
