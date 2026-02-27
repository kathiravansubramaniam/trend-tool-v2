import sqlite3
from config.settings import settings


CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gcs_name        TEXT UNIQUE NOT NULL,
    doc_name        TEXT,
    industry        TEXT,
    market_scope    TEXT,
    topics          TEXT,
    forecasts       TEXT,
    parsed_at       DATETIME,
    gcs_updated_at  DATETIME,
    parse_status    TEXT DEFAULT 'pending',
    error_msg       TEXT,
    token_count     INTEGER
);
"""

CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    doc_name,
    industry,
    topics,
    forecasts,
    content='documents',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 1'
);
"""

CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, doc_name, industry, topics, forecasts)
    VALUES (new.id, new.doc_name, new.industry, new.topics, new.forecasts);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, doc_name, industry, topics, forecasts)
    VALUES ('delete', old.id, old.doc_name, old.industry, old.topics, old.forecasts);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, doc_name, industry, topics, forecasts)
    VALUES ('delete', old.id, old.doc_name, old.industry, old.topics, old.forecasts);
    INSERT INTO documents_fts(rowid, doc_name, industry, topics, forecasts)
    VALUES (new.id, new.doc_name, new.industry, new.topics, new.forecasts);
END;
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(CREATE_DOCUMENTS)
        conn.executescript(CREATE_FTS)
        conn.executescript(CREATE_TRIGGERS)
    print(f"Database initialized at {settings.db_path}")
