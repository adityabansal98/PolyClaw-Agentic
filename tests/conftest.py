"""Shared pytest fixtures for Phase 1 multi-tenant PaperTrader tests.

The `engine` fixture is parametrized across SQLite and Postgres when Docker is
available. This gives us the "SQLite + Postgres parity" test (mandatory test #9)
for free — every test that takes `engine` as a fixture runs against both dialects.

Postgres is provided via `testcontainers`. If Docker isn't running, the postgres
side is skipped with a clear reason. Locally this means `pytest` covers SQLite
always and Postgres when Docker is up; CI always runs both.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from polyclaw.storage.db import make_engine

# Detect whether to attempt Postgres at all. CI sets POLYCLAW_TEST_POSTGRES=1; locally
# we try Docker and skip gracefully if it isn't there.
_POSTGRES_ENABLED = os.environ.get("POLYCLAW_TEST_POSTGRES", "").lower() in ("1", "true", "yes")


def _postgres_available() -> bool:
    if not _POSTGRES_ENABLED:
        return False
    try:
        import docker  # noqa: F401

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


# Session-scoped Postgres container, lazily started only if a test actually wants it.
# Stored on the pytest session to avoid a fixture dependency cycle with `engine`.
_PG_CONTAINER: object | None = None
_PG_URL: str | None = None


def _get_postgres_url() -> str | None:
    """Return a Postgres URL if testcontainers+docker are available, else None.

    Starts the container on first call, reuses it for the rest of the test session.
    Returning None (instead of skipping) lets the sqlite param run unaffected when
    Postgres isn't available.
    """
    global _PG_CONTAINER, _PG_URL
    if _PG_URL is not None:
        return _PG_URL
    if not _postgres_available():
        return None
    try:
        from testcontainers.postgres import PostgresContainer

        pg = PostgresContainer("postgres:16-alpine", driver="psycopg")
        pg.start()
        url = pg.get_connection_url()
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        _PG_CONTAINER = pg
        _PG_URL = url
        return url
    except Exception:
        return None


def pytest_sessionfinish(session, exitstatus):
    global _PG_CONTAINER
    if _PG_CONTAINER is not None:
        try:
            _PG_CONTAINER.stop()  # type: ignore[attr-defined]
        except Exception:
            pass
        _PG_CONTAINER = None


@pytest.fixture(
    params=[
        pytest.param("sqlite", id="sqlite"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.postgres),
    ]
)
def engine(request, tmp_path) -> Iterator[Engine]:
    """Parametrized engine fixture — every test using this runs on both dialects.

    SQLite is always available; Postgres is gated on the docker/testcontainers path.
    When Postgres isn't available, only the postgres param is skipped — sqlite still
    runs.
    """
    if request.param == "sqlite":
        db_path = tmp_path / "test.db"
        eng = make_engine(f"sqlite:///{db_path}")
        yield eng
        eng.dispose()
        return

    url = _get_postgres_url()
    if url is None:
        pytest.skip("Postgres testcontainer not available (set POLYCLAW_TEST_POSTGRES=1 + Docker)")
    eng = make_engine(url)
    try:
        yield eng
    finally:
        from sqlalchemy import text as _text

        with eng.begin() as conn:
            conn.execute(
                _text(
                    "DROP TABLE IF EXISTS portfolio_snapshots, audit_log, "
                    "orderbook_snapshots, paper_open_orders, paper_positions, "
                    "paper_trades, paper_config CASCADE"
                )
            )
        eng.dispose()
