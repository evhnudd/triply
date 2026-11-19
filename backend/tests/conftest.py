"""Тесты гоняются на настоящем PostgreSQL (база TEST_DATABASE_URL), схема — миграциями Alembic."""

import os

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://triply:triply@localhost:5432/triply_test"),
)
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.geo import GeoProvider, get_geo_provider  # noqa: E402

TABLES = "external_cache, activities, places, itinerary_days, trip_members, trips, users"


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield


class FakeGeo(GeoProvider):
    calls = 0

    def search(self, query, lat, lng, limit):
        FakeGeo.calls += 1
        return [
            {
                "name": "Кафедральный собор",
                "address": "Калининград, Россия",
                "lat": 54.706,
                "lng": 20.511,
                "category": "sight",
                "source": "osm",
                "external_id": "way/1234",
            },
        ][:limit]

    def reverse(self, lat, lng):
        FakeGeo.calls += 1
        return [
            {
                "name": "Точка",
                "address": None,
                "lat": lat,
                "lng": lng,
                "category": "other",
                "source": "osm",
                "external_id": "node/1",
            }
        ]


@pytest.fixture
def client():
    FakeGeo.calls = 0
    app.dependency_overrides[get_geo_provider] = lambda: FakeGeo()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email="anna@example.com", name="Анна"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "secret123", "display_name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


def make_trip(client, headers, start="2026-05-12", end="2026-05-15", **extra):
    body = {
        "title": "Калининград",
        "destination_name": "Калининград",
        "start_date": start,
        "end_date": end,
        "center_lat": "54.7104",
        "center_lng": "20.4522",
        **extra,
    }
    r = client.post("/api/v1/trips", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()
