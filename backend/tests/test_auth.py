from tests.conftest import register


def test_register_login_me(client):
    headers = register(client)
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["display_name"] == "Анна"

    r = client.post("/api/v1/auth/login", json={"email": "ANNA@example.com", "password": "secret123"})
    assert r.status_code == 200, "email не зависит от регистра"
    assert r.json()["access_token"]


def test_duplicate_email(client):
    register(client)
    r = client.post(
        "/api/v1/auth/register", json={"email": "anna@example.com", "password": "secret123", "display_name": "Ещё"}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "email_taken"


def test_wrong_password(client):
    register(client)
    r = client.post("/api/v1/auth/login", json={"email": "anna@example.com", "password": "wrong-pass"})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_credentials"


def test_password_is_hashed(client):
    from sqlalchemy import text

    from app.db import engine

    register(client)
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert stored.startswith("$argon2")


def test_requires_token(client):
    assert client.get("/api/v1/me").status_code == 401
    r = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_token"


def test_short_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": "a@b.ru", "password": "123", "display_name": "A"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
