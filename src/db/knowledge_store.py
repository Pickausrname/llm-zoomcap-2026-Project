"""
Knowledge base storage layer for the MOSFET Selection RAG application.

Owns the SQLite-backed knowledge base (``data/knowledge.db``): schema
creation for ``master_table``, the FTS5 lexical index (``master_fts``),
the sqlite-vec vector index (``master_vec``), and the triggers that
keep both indexes automatically synchronized with ``master_table``. It
also exposes the connection-management helpers used by every other
layer (ingestion, retrieval, evaluation) that needs to talk to the
knowledge base.

This module is intentionally limited to connection management and
schema initialization. Search/retrieval query logic lives in
``src/retrieval/``, not here.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import sqlite_vec

from src.config import EMBEDDING_DIM, KNOWLEDGE_DB

logger = logging.getLogger(__name__)

__all__ = ["EMBEDDING_DIM", "get_connection", "connect", "init_db"]

# Special SQLite DSN for an ephemeral, on-disk-free database (tests, etc.).
_MEMORY_DB: Final[str] = ":memory:"

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_CREATE_MASTER_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS master_table (
    id                INTEGER PRIMARY KEY,
    component_type    TEXT,
    manufacturer_name TEXT,
    part_number       TEXT,
    search_text       TEXT,
    search_vector     BLOB
);
"""

# ---------------------------------------------------------------------------
# Future-proofing (spec.md section 5.2): `master_table` itself must never be
# altered to bolt on new MOSFET attributes. Instead, additional
# component-attribute tables (e.g. electrical_specs, thermal_specs,
# packaging) are appended later, each declaring a FOREIGN KEY column that
# references master_table.id so the extra data can be joined in without
# ever touching this schema. Example of the expected 1-to-many pattern:
#
#   CREATE TABLE electrical_specs (
#       id        INTEGER PRIMARY KEY,
#       master_id INTEGER NOT NULL REFERENCES master_table (id)
#                  ON DELETE CASCADE,
#       vds_max   REAL,
#       id_max    REAL,
#       rds_on    REAL
#   );
#
# `master_id` is the FOREIGN KEY back to `master_table.id`. Foreign-key
# enforcement is turned on for every connection in get_connection() below
# (PRAGMA foreign_keys = ON), so such tables get referential integrity and
# cascading deletes for free.
# ---------------------------------------------------------------------------

_CREATE_MASTER_FTS_SQL: Final[str] = """
CREATE VIRTUAL TABLE IF NOT EXISTS master_fts USING fts5(
    search_text,
    part_number,
    manufacturer_name,
    content='master_table',
    content_rowid='id'
);
"""

_CREATE_MASTER_VEC_SQL: Final[str] = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS master_vec USING vec0(
    id INTEGER PRIMARY KEY,
    search_vector FLOAT[{EMBEDDING_DIM}]
);
"""

# `master_fts` is an FTS5 "external content" table (see
# https://sqlite.org/fts5.html#external_content_tables): it stores no data
# of its own, so it must be kept in sync with master_table via triggers.
# The `('delete', ...)` first-column form is FTS5's required syntax for
# deleting/replacing rows in an external-content table.
_FTS_TRIGGER_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TRIGGER IF NOT EXISTS master_fts_after_insert
    AFTER INSERT ON master_table
    BEGIN
        INSERT INTO master_fts (rowid, search_text, part_number, manufacturer_name)
        VALUES (new.id, new.search_text, new.part_number, new.manufacturer_name);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS master_fts_after_delete
    AFTER DELETE ON master_table
    BEGIN
        INSERT INTO master_fts (master_fts, rowid, search_text, part_number, manufacturer_name)
        VALUES ('delete', old.id, old.search_text, old.part_number, old.manufacturer_name);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS master_fts_after_update
    AFTER UPDATE ON master_table
    BEGIN
        INSERT INTO master_fts (master_fts, rowid, search_text, part_number, manufacturer_name)
        VALUES ('delete', old.id, old.search_text, old.part_number, old.manufacturer_name);
        INSERT INTO master_fts (rowid, search_text, part_number, manufacturer_name)
        VALUES (new.id, new.search_text, new.part_number, new.manufacturer_name);
    END;
    """,
)

# `master_vec` (sqlite-vec vec0) has no built-in upsert and its indexed
# vector column cannot be NULL, so inserts/updates are skipped whenever a
# row has not been embedded yet (spec.md section 8.5, graceful handling of
# incomplete records).
_VEC_TRIGGER_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TRIGGER IF NOT EXISTS master_vec_after_insert
    AFTER INSERT ON master_table
    BEGIN
        INSERT INTO master_vec (id, search_vector)
        SELECT new.id, new.search_vector
        WHERE new.search_vector IS NOT NULL;
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS master_vec_after_delete
    AFTER DELETE ON master_table
    BEGIN
        DELETE FROM master_vec WHERE id = old.id;
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS master_vec_after_update
    AFTER UPDATE ON master_table
    BEGIN
        DELETE FROM master_vec WHERE id = old.id;
        INSERT INTO master_vec (id, search_vector)
        SELECT new.id, new.search_vector
        WHERE new.search_vector IS NOT NULL;
    END;
    """,
)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _load_vector_extension(conn: sqlite3.Connection) -> None:
    """
    Load the ``sqlite-vec`` native extension into an open connection.

    Extension loading is enabled only for the duration of the load call
    (the security-conscious pattern recommended by sqlite-vec), so the
    connection cannot load arbitrary native extensions afterward.

    Args:
        conn: An open SQLite connection.

    Raises:
        RuntimeError: If the interpreter's ``sqlite3`` build does not
            support loadable extensions, or the extension fails to load.
    """
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    except AttributeError as exc:
        raise RuntimeError(
            "This Python build's sqlite3 module does not support loadable "
            "extensions (Connection.enable_load_extension is missing). "
            "Use a CPython build compiled with SQLITE_ENABLE_LOAD_EXTENSION."
        ) from exc
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "Failed to load the sqlite-vec extension. Ensure the "
            "'sqlite-vec' package is installed and is compatible with the "
            "current platform/architecture."
        ) from exc
    finally:
        conn.enable_load_extension(False)


def get_connection(db_path: str | Path = KNOWLEDGE_DB) -> sqlite3.Connection:
    """
    Open a fully configured connection to the knowledge base.

    Configures the connection with row access by column name,
    foreign-key enforcement (for the extension tables described in
    spec.md section 5.2), WAL journaling (safer for the concurrent
    Streamlit/ingestion/evaluation access patterns of this project), and
    the ``sqlite-vec`` extension loaded so ``master_vec`` (vec0) queries
    work.

    Args:
        db_path: Path to the knowledge base SQLite file. Defaults to
            ``config.KNOWLEDGE_DB``. Pass ``":memory:"`` for an
            ephemeral in-memory database (useful in tests).

    Returns:
        A ready-to-use ``sqlite3.Connection``. The caller owns the
        connection and must close it (or use :func:`connect` instead).
    """
    if str(db_path) != _MEMORY_DB:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    # WAL still serializes writers; without this, a second concurrent writer
    # (e.g. ingestion running alongside an evaluation/retrieval read) fails
    # immediately instead of waiting for the first short transaction to commit.
    conn.execute("PRAGMA busy_timeout = 5000;")

    try:
        _load_vector_extension(conn)
    except Exception:
        conn.close()
        raise

    return conn


@contextmanager
def connect(db_path: str | Path = KNOWLEDGE_DB) -> Iterator[sqlite3.Connection]:
    """
    Context-managed knowledge base connection that closes itself.

    Args:
        db_path: Path to the knowledge base SQLite file. Defaults to
            ``config.KNOWLEDGE_DB``.

    Yields:
        A ready-to-use ``sqlite3.Connection``, closed automatically on
        exit (including on exception).

    Example:
        >>> with connect() as conn:
        ...     conn.execute("SELECT COUNT(*) FROM master_table").fetchone()
    """
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def _create_master_table(conn: sqlite3.Connection) -> None:
    """Create ``master_table`` if it does not already exist (spec.md 5.1)."""
    conn.execute(_CREATE_MASTER_TABLE_SQL)


def _create_fts_index(conn: sqlite3.Connection) -> None:
    """Create the ``master_fts`` FTS5 (BM25) lexical index."""
    try:
        conn.execute(_CREATE_MASTER_FTS_SQL)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "Failed to create the master_fts FTS5 virtual table. This "
            "Python build's SQLite library may be compiled without FTS5 "
            "support."
        ) from exc


def _create_vector_index(conn: sqlite3.Connection) -> None:
    """Create the ``master_vec`` sqlite-vec (vec0) vector index."""
    conn.execute(_CREATE_MASTER_VEC_SQL)


def _create_sync_triggers(conn: sqlite3.Connection) -> None:
    """
    Create the AFTER INSERT/UPDATE/DELETE triggers that keep
    ``master_fts`` and ``master_vec`` synchronized with ``master_table``.
    """
    for statement in (*_FTS_TRIGGER_STATEMENTS, *_VEC_TRIGGER_STATEMENTS):
        conn.execute(statement)


def init_db(db_path: str | Path = KNOWLEDGE_DB) -> None:
    """
    Create the knowledge base file (if needed) and apply the full schema.

    Creates ``master_table``, the ``master_fts`` FTS5 index, the
    ``master_vec`` sqlite-vec index, and the six sync triggers that keep
    both indexes up to date. Every statement uses ``IF NOT EXISTS`` (or
    the trigger equivalent), so this function is idempotent and safe to
    call on every application/container startup.

    Args:
        db_path: Path to the knowledge base SQLite file. Defaults to
            ``config.KNOWLEDGE_DB``.
    """
    with connect(db_path) as conn:
        _create_master_table(conn)
        _create_fts_index(conn)
        _create_vector_index(conn)
        _create_sync_triggers(conn)
        conn.commit()

    logger.info("Knowledge base schema initialized at %s", db_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
