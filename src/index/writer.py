import json
from datetime import datetime, timezone

from src.index.schema import get_connection


def upsert_document(
    gcs_name: str,
    doc_name: str,
    industry: str,
    market_scope: str,
    topics: list[str],
    forecasts: list[str],
    token_count: int = 0,
    gcs_updated_at: datetime | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents
                (gcs_name, doc_name, industry, market_scope, topics, forecasts,
                 parsed_at, gcs_updated_at, parse_status, token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done', ?)
            ON CONFLICT(gcs_name) DO UPDATE SET
                doc_name       = excluded.doc_name,
                industry       = excluded.industry,
                market_scope   = excluded.market_scope,
                topics         = excluded.topics,
                forecasts      = excluded.forecasts,
                parsed_at      = excluded.parsed_at,
                gcs_updated_at = excluded.gcs_updated_at,
                parse_status   = 'done',
                error_msg      = NULL,
                token_count    = excluded.token_count
            """,
            (
                gcs_name,
                doc_name,
                industry,
                market_scope,
                json.dumps(topics),
                json.dumps(forecasts),
                now,
                gcs_updated_at.isoformat() if gcs_updated_at else None,
                token_count,
            ),
        )


def mark_pending(gcs_name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents (gcs_name, parse_status)
            VALUES (?, 'pending')
            ON CONFLICT(gcs_name) DO UPDATE SET parse_status = 'pending', error_msg = NULL
            """,
            (gcs_name,),
        )


def mark_failed(gcs_name: str, error: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE documents SET parse_status = 'failed', error_msg = ?
            WHERE gcs_name = ?
            """,
            (error[:1000], gcs_name),
        )
