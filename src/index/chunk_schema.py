import sqlite3
from config.settings import settings


CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id          TEXT UNIQUE NOT NULL,   -- "{gcs_name}__c{order:04d}"
    gcs_name          TEXT NOT NULL,
    chunk_order       INTEGER NOT NULL,
    section_title     TEXT DEFAULT '',
    chunk_text        TEXT NOT NULL,
    chunk_summary     TEXT DEFAULT '',
    topics            TEXT DEFAULT '[]',
    themes            TEXT DEFAULT '[]',
    behavioral_shifts TEXT DEFAULT '[]',
    trend_drivers     TEXT DEFAULT '[]',
    technologies      TEXT DEFAULT '[]',
    brands_companies  TEXT DEFAULT '[]',
    consumer_needs    TEXT DEFAULT '[]',
    retrieval_phrases TEXT DEFAULT '[]',
    evidence_type     TEXT DEFAULT 'claim',
    evidence_strength TEXT DEFAULT 'moderate',
    token_count       INTEGER DEFAULT 0,
    FOREIGN KEY (gcs_name) REFERENCES documents(gcs_name) ON DELETE CASCADE
);
"""

CREATE_CHUNKS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chunks_gcs_name ON chunks(gcs_name);
CREATE INDEX IF NOT EXISTS idx_chunks_order    ON chunks(gcs_name, chunk_order);
"""

CREATE_CHUNKS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    section_title,
    chunk_summary,
    topics,
    behavioral_shifts,
    trend_drivers,
    retrieval_phrases,
    chunk_text,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 1'
);
"""

CREATE_CHUNKS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, section_title, chunk_summary, topics,
        behavioral_shifts, trend_drivers, retrieval_phrases, chunk_text)
    VALUES (new.id, new.section_title, new.chunk_summary, new.topics,
        new.behavioral_shifts, new.trend_drivers, new.retrieval_phrases, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, section_title, chunk_summary, topics,
        behavioral_shifts, trend_drivers, retrieval_phrases, chunk_text)
    VALUES ('delete', old.id, old.section_title, old.chunk_summary, old.topics,
        old.behavioral_shifts, old.trend_drivers, old.retrieval_phrases, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, section_title, chunk_summary, topics,
        behavioral_shifts, trend_drivers, retrieval_phrases, chunk_text)
    VALUES ('delete', old.id, old.section_title, old.chunk_summary, old.topics,
        old.behavioral_shifts, old.trend_drivers, old.retrieval_phrases, old.chunk_text);
    INSERT INTO chunks_fts(rowid, section_title, chunk_summary, topics,
        behavioral_shifts, trend_drivers, retrieval_phrases, chunk_text)
    VALUES (new.id, new.section_title, new.chunk_summary, new.topics,
        new.behavioral_shifts, new.trend_drivers, new.retrieval_phrases, new.chunk_text);
END;
"""


def get_connection() -> sqlite3.Connection:
    """Re-use the same connection factory as the main schema."""
    from src.index.schema import get_connection as _main_conn
    return _main_conn()


def init_chunks_db() -> None:
    """Create the chunks table, indexes, FTS table, and triggers if they don't exist."""
    with get_connection() as conn:
        conn.executescript(CREATE_CHUNKS)
        conn.executescript(CREATE_CHUNKS_INDEX)
        conn.executescript(CREATE_CHUNKS_FTS)
        conn.executescript(CREATE_CHUNKS_TRIGGERS)
    print("Chunks table initialized.")


def get_chunk_count() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
