"""КТ-1: пользователи, поездки, участники, дни, места, активности, кэш внешних API

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-19
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE trip_role      AS ENUM ('owner', 'editor', 'viewer');
CREATE TYPE place_category AS ENUM ('sight', 'food', 'accommodation', 'transport',
                                    'shopping', 'nature', 'entertainment', 'other');

CREATE TABLE users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         CITEXT       NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE trips (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title            VARCHAR(120) NOT NULL,
    description      TEXT,
    destination_name VARCHAR(200) NOT NULL,
    center_lat       NUMERIC(9,6) CHECK (center_lat BETWEEN -90 AND 90),
    center_lng       NUMERIC(9,6) CHECK (center_lng BETWEEN -180 AND 180),
    start_date       DATE NOT NULL,
    end_date         DATE NOT NULL,
    travelers_count  SMALLINT NOT NULL DEFAULT 1 CHECK (travelers_count BETWEEN 1 AND 20),
    budget_limit     NUMERIC(12,2) CHECK (budget_limit >= 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date),
    CHECK (end_date - start_date < 60)
);

CREATE TABLE trip_members (
    trip_id   BIGINT    NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    user_id   BIGINT    NOT NULL REFERENCES users (id),
    role      trip_role NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at   TIMESTAMPTZ,
    PRIMARY KEY (trip_id, user_id)
);
CREATE UNIQUE INDEX ux_one_owner_per_trip ON trip_members (trip_id) WHERE role = 'owner';
CREATE INDEX ix_trip_members_user ON trip_members (user_id);

CREATE TABLE itinerary_days (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id  BIGINT NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    day_date DATE   NOT NULL,
    title    VARCHAR(120),
    UNIQUE (trip_id, day_date),
    UNIQUE (id, trip_id)
);

CREATE TABLE places (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id     BIGINT NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL,
    address     TEXT,
    lat         NUMERIC(9,6) NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng         NUMERIC(9,6) NOT NULL CHECK (lng BETWEEN -180 AND 180),
    category    place_category NOT NULL DEFAULT 'other',
    source      VARCHAR(20) NOT NULL DEFAULT 'manual',
    external_id VARCHAR(100),
    note        TEXT,
    created_by  BIGINT REFERENCES users (id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, trip_id),
    UNIQUE (trip_id, source, external_id)
);
CREATE INDEX ix_places_trip ON places (trip_id);

CREATE TABLE activities (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id        BIGINT NOT NULL REFERENCES trips (id) ON DELETE CASCADE,
    day_id         BIGINT,
    place_id       BIGINT,
    title          VARCHAR(200) NOT NULL,
    start_time     TIME,
    position       INT NOT NULL DEFAULT 0,
    note           TEXT,
    url            TEXT,
    estimated_cost NUMERIC(12,2) CHECK (estimated_cost >= 0),
    is_done        BOOLEAN NOT NULL DEFAULT false,
    created_by     BIGINT REFERENCES users (id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (day_id, trip_id)   REFERENCES itinerary_days (id, trip_id) ON DELETE SET NULL (day_id),
    FOREIGN KEY (place_id, trip_id) REFERENCES places (id, trip_id)         ON DELETE SET NULL (place_id)
);
CREATE INDEX ix_activities_day  ON activities (day_id, position);
CREATE INDEX ix_activities_trip ON activities (trip_id);

CREATE TABLE external_cache (
    cache_key  VARCHAR(64) PRIMARY KEY,
    response   JSONB       NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_external_cache_expires ON external_cache (expires_at);
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS external_cache, activities, places, itinerary_days, trip_members, trips, users;
DROP TYPE IF EXISTS place_category;
DROP TYPE IF EXISTS trip_role;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
