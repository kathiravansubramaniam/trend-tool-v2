import sqlite3
from config.settings import settings


CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    gcs_name            TEXT UNIQUE NOT NULL,
    doc_name            TEXT,
    -- Legacy single-value fields (kept for backwards compat)
    industry            TEXT,
    market_scope        TEXT,
    topics              TEXT,
    forecasts           TEXT,
    -- Rich taxonomy
    summary             TEXT,
    industries_primary  TEXT,
    industries_secondary TEXT,
    subsectors          TEXT,
    product_categories  TEXT,
    brands_companies    TEXT,
    -- Audience
    demographics        TEXT,
    geographies         TEXT,
    -- Behavioral
    consumer_needs      TEXT,
    behaviors           TEXT,
    behavioral_shifts   TEXT,
    -- Trend intelligence
    trend_drivers       TEXT,
    technologies        TEXT,
    themes              TEXT,
    -- Classification
    time_horizon        TEXT,
    document_type       TEXT,
    publish_date        TEXT,
    -- Retrieval optimization
    likely_questions    TEXT,
    retrieval_phrases   TEXT,
    -- System fields
    parsed_at           DATETIME,
    gcs_updated_at      DATETIME,
    parse_status        TEXT DEFAULT 'pending',
    error_msg           TEXT,
    token_count         INTEGER
);
"""

CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    doc_name,
    industry,
    topics,
    forecasts,
    summary,
    subsectors,
    consumer_needs,
    behavioral_shifts,
    trend_drivers,
    technologies,
    themes,
    retrieval_phrases,
    likely_questions,
    content='documents',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 1'
);
"""

CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(
        rowid, doc_name, industry, topics, forecasts,
        summary, subsectors, consumer_needs, behavioral_shifts,
        trend_drivers, technologies, themes, retrieval_phrases, likely_questions
    ) VALUES (
        new.id, new.doc_name, new.industry, new.topics, new.forecasts,
        new.summary, new.subsectors, new.consumer_needs, new.behavioral_shifts,
        new.trend_drivers, new.technologies, new.themes, new.retrieval_phrases, new.likely_questions
    );
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, doc_name, industry, topics, forecasts,
        summary, subsectors, consumer_needs, behavioral_shifts,
        trend_drivers, technologies, themes, retrieval_phrases, likely_questions
    ) VALUES (
        'delete', old.id, old.doc_name, old.industry, old.topics, old.forecasts,
        old.summary, old.subsectors, old.consumer_needs, old.behavioral_shifts,
        old.trend_drivers, old.technologies, old.themes, old.retrieval_phrases, old.likely_questions
    );
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, doc_name, industry, topics, forecasts,
        summary, subsectors, consumer_needs, behavioral_shifts,
        trend_drivers, technologies, themes, retrieval_phrases, likely_questions
    ) VALUES (
        'delete', old.id, old.doc_name, old.industry, old.topics, old.forecasts,
        old.summary, old.subsectors, old.consumer_needs, old.behavioral_shifts,
        old.trend_drivers, old.technologies, old.themes, old.retrieval_phrases, old.likely_questions
    );
    INSERT INTO documents_fts(
        rowid, doc_name, industry, topics, forecasts,
        summary, subsectors, consumer_needs, behavioral_shifts,
        trend_drivers, technologies, themes, retrieval_phrases, likely_questions
    ) VALUES (
        new.id, new.doc_name, new.industry, new.topics, new.forecasts,
        new.summary, new.subsectors, new.consumer_needs, new.behavioral_shifts,
        new.trend_drivers, new.technologies, new.themes, new.retrieval_phrases, new.likely_questions
    );
END;
"""

# New columns to add when migrating an existing DB
_NEW_COLUMNS = [
    ("summary", "TEXT"),
    ("industries_primary", "TEXT"),
    ("industries_secondary", "TEXT"),
    ("subsectors", "TEXT"),
    ("product_categories", "TEXT"),
    ("brands_companies", "TEXT"),
    ("demographics", "TEXT"),
    ("geographies", "TEXT"),
    ("consumer_needs", "TEXT"),
    ("behaviors", "TEXT"),
    ("behavioral_shifts", "TEXT"),
    ("trend_drivers", "TEXT"),
    ("technologies", "TEXT"),
    ("themes", "TEXT"),
    ("time_horizon", "TEXT"),
    ("document_type", "TEXT"),
    ("publish_date", "TEXT"),
    ("likely_questions", "TEXT"),
    ("retrieval_phrases", "TEXT"),
]


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


def migrate_db() -> None:
    """Add new rich-metadata columns to an existing DB and rebuild FTS index."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        # 1. Add new columns (safe to run multiple times — skips existing)
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        for col_name, col_type in _NEW_COLUMNS:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}")
                print(f"  Added column: {col_name}")

        # 2. Rebuild FTS with new column set
        conn.executescript("""
            DROP TRIGGER IF EXISTS documents_ai;
            DROP TRIGGER IF EXISTS documents_ad;
            DROP TRIGGER IF EXISTS documents_au;
            DROP TABLE IF EXISTS documents_fts;
        """)
        conn.executescript(CREATE_FTS)
        conn.executescript(CREATE_TRIGGERS)

        # 3. Repopulate FTS from existing documents
        conn.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")

    print("Migration complete. FTS index rebuilt.")
