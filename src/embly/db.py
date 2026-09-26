from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

# NOTE (Postgres migration): TEXT timestamps below map to TIMESTAMPTZ
# DEFAULT now(), BLOB vectors map to pgvector vector(dim), and
# INTEGER PRIMARY KEY maps to BIGINT GENERATED ALWAYS AS IDENTITY.
# SQLite keeps TEXT/BLOB/INTEGER so the local daemon stays dependency-free.
SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL CHECK(length(name) > 0),
    slug         TEXT NOT NULL UNIQUE CHECK(length(slug) > 0),
    description  TEXT NOT NULL CHECK(length(description) > 0),
    status       TEXT NOT NULL CHECK(status IN ('active','removed')),
    auto_created INTEGER NOT NULL DEFAULT 0 CHECK(auto_created IN (0,1)),
    centroid     BLOB,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY,
    sha256          TEXT NOT NULL UNIQUE,
    original_name   TEXT NOT NULL CHECK(length(original_name) > 0),
    original_path   TEXT NOT NULL,
    current_path    TEXT,
    ext             TEXT,
    size            INTEGER CHECK(size IS NULL OR size >= 0),
    first_seen      TEXT NOT NULL,
    doc_date        TEXT CHECK(doc_date IS NULL OR doc_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    text_extractor  TEXT,
    vec             BLOB,
    status          TEXT NOT NULL
                    CHECK(status IN ('pending','processing','classified','review','novel','error')),
    category_id     INTEGER,
    confidence      REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    routing_model   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY(category_id) REFERENCES categories(id)
        ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS decisions (
    id             INTEGER PRIMARY KEY,
    file_id        INTEGER NOT NULL,
    category_id    INTEGER,
    confidence     REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    shortlist_json TEXT,
    routing_model  TEXT,
    trigger        TEXT NOT NULL CHECK(trigger IN ('ingest','reclassify','correction')),
    created_at     TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES files(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY(category_id) REFERENCES categories(id)
        ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS corrections (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    source      TEXT NOT NULL CHECK(source IN ('cli','review')),
    created_at  TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES files(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY(category_id) REFERENCES categories(id)
        ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category_id);
CREATE INDEX IF NOT EXISTS idx_files_status_created ON files(status, created_at);
CREATE INDEX IF NOT EXISTS idx_files_doc_date ON files(doc_date);
CREATE INDEX IF NOT EXISTS idx_categories_status_slug ON categories(status, slug);
CREATE INDEX IF NOT EXISTS idx_decisions_file ON decisions(file_id);
CREATE INDEX IF NOT EXISTS idx_decisions_category ON decisions(category_id);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_file_created ON decisions(file_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_corrections_file ON corrections(file_id);
CREATE INDEX IF NOT EXISTS idx_corrections_category ON corrections(category_id);
CREATE INDEX IF NOT EXISTS idx_corrections_created ON corrections(created_at);
"""


def now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring pre-v2 databases forward without a rebuild.

    SQLite cannot ADD CONSTRAINT, so CHECK/FK clauses only apply to tables
    created fresh at v2. For existing tables we backfill what is additive:
    the new ``files.vec`` column (docs described it, v1 DDL omitted it) and
    the new indexes (``executescript`` above already issues CREATE INDEX
    IF NOT EXISTS, this is belt-and-braces for clarity).
    """
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    try:
        version = int(row["value"]) if row is not None else SCHEMA_VERSION
    except (TypeError, ValueError):
        version = SCHEMA_VERSION
    if version >= SCHEMA_VERSION:
        return
    if version < 2:
        if "files" in {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()} and "vec" not in _table_columns(conn, "files"):
            conn.execute("ALTER TABLE files ADD COLUMN vec BLOB")
    conn.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),))


def _ensure_vec_column(conn: sqlite3.Connection) -> None:
    """Additive pre-step so new indexes have their columns.

    Runs before the main executescript: v1 tables lack ``files.vec`` and
    ``CREATE INDEX ... ON files(...)`` would otherwise fail on upgrade.
    No-op on fresh databases (no files table yet) and on v2 databases.
    """
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "files" in tables and "vec" not in _table_columns(conn, "files"):
        conn.execute("ALTER TABLE files ADD COLUMN vec BLOB")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_vec_column(conn)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    _migrate(conn)
    conn.commit()
    return conn
