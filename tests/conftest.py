import os
import pytest
import sqlalchemy
from sqlalchemy import text

_ORIG_CREATE_ENGINE = sqlalchemy.create_engine
PG_TEST_DB_NAME = "professor_discovery_pytest"
PG_ADMIN_URL = "postgresql://postgres@localhost:5432/postgres"
PG_TEST_URL = f"postgresql://postgres@localhost:5432/{PG_TEST_DB_NAME}"


def _ensure_pg_test_db():
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    conn = psycopg2.connect(host="localhost", port=5432, user="postgres", dbname="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_TEST_DB_NAME,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {PG_TEST_DB_NAME} ENCODING 'UTF8'")
    cur.close()
    conn.close()


def _reset_pg_test_schema(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(autouse=True)
def maybe_route_in_memory_sqlite_to_postgres(monkeypatch):
    """
    When `TEST_USE_POSTGRES=1` is set, routes `create_engine('sqlite:///:memory:')` in unit tests
    to an isolated PostgreSQL database (`professor_discovery_pytest`) so the entire test suite
    is verified against real PostgreSQL as well as SQLite.
    """
    if os.getenv("TEST_USE_POSTGRES") != "1":
        yield
        return

    _ensure_pg_test_db()
    created_engines = []

    def _patched_create_engine(url, *args, **kwargs):
        if str(url) == "sqlite:///:memory:":
            eng = _ORIG_CREATE_ENGINE(PG_TEST_URL)
            _reset_pg_test_schema(eng)
            created_engines.append(eng)
            return eng
        return _ORIG_CREATE_ENGINE(url, *args, **kwargs)

    monkeypatch.setattr(sqlalchemy, "create_engine", _patched_create_engine)
    for mod_name in (
        "tests.test_api_endpoints",
        "tests.test_database_and_models",
        "tests.test_publication_visibility",
        "tests.test_review_and_idempotency",
        "tests.test_alembic_and_search_foundation",
    ):
        mod = __import__(mod_name, fromlist=["create_engine"])
        if hasattr(mod, "create_engine"):
            monkeypatch.setattr(mod, "create_engine", _patched_create_engine)

    yield

    for eng in created_engines:
        try:
            _reset_pg_test_schema(eng)
            eng.dispose()
        except Exception:
            pass
