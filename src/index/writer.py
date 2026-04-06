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
    # Rich metadata fields
    summary: str = "",
    industries_primary: list[str] | None = None,
    industries_secondary: list[str] | None = None,
    subsectors: list[str] | None = None,
    product_categories: list[str] | None = None,
    brands_companies: list[str] | None = None,
    demographics: dict | None = None,
    geographies: dict | None = None,
    consumer_needs: list[str] | None = None,
    behaviors: list[str] | None = None,
    behavioral_shifts: list[str] | None = None,
    trend_drivers: list[str] | None = None,
    technologies: list[str] | None = None,
    themes: list[str] | None = None,
    time_horizon: str = "short-term",
    document_type: str = "report",
    publish_date: str | None = None,
    likely_questions: list[str] | None = None,
    retrieval_phrases: list[str] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    def _j(v: list | dict | None) -> str | None:
        return json.dumps(v) if v is not None else None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents (
                gcs_name, doc_name, industry, market_scope, topics, forecasts,
                summary, industries_primary, industries_secondary, subsectors,
                product_categories, brands_companies, demographics, geographies,
                consumer_needs, behaviors, behavioral_shifts, trend_drivers,
                technologies, themes, time_horizon, document_type, publish_date,
                likely_questions, retrieval_phrases,
                parsed_at, gcs_updated_at, parse_status, token_count
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?,
                ?, ?, 'done', ?
            )
            ON CONFLICT(gcs_name) DO UPDATE SET
                doc_name             = excluded.doc_name,
                industry             = excluded.industry,
                market_scope         = excluded.market_scope,
                topics               = excluded.topics,
                forecasts            = excluded.forecasts,
                summary              = excluded.summary,
                industries_primary   = excluded.industries_primary,
                industries_secondary = excluded.industries_secondary,
                subsectors           = excluded.subsectors,
                product_categories   = excluded.product_categories,
                brands_companies     = excluded.brands_companies,
                demographics         = excluded.demographics,
                geographies          = excluded.geographies,
                consumer_needs       = excluded.consumer_needs,
                behaviors            = excluded.behaviors,
                behavioral_shifts    = excluded.behavioral_shifts,
                trend_drivers        = excluded.trend_drivers,
                technologies         = excluded.technologies,
                themes               = excluded.themes,
                time_horizon         = excluded.time_horizon,
                document_type        = excluded.document_type,
                publish_date         = excluded.publish_date,
                likely_questions     = excluded.likely_questions,
                retrieval_phrases    = excluded.retrieval_phrases,
                parsed_at            = excluded.parsed_at,
                gcs_updated_at       = excluded.gcs_updated_at,
                parse_status         = 'done',
                error_msg            = NULL,
                token_count          = excluded.token_count
            """,
            (
                gcs_name, doc_name, industry, market_scope,
                json.dumps(topics), json.dumps(forecasts),
                summary,
                _j(industries_primary), _j(industries_secondary), _j(subsectors),
                _j(product_categories), _j(brands_companies),
                _j(demographics), _j(geographies),
                _j(consumer_needs), _j(behaviors), _j(behavioral_shifts),
                _j(trend_drivers), _j(technologies), _j(themes),
                time_horizon, document_type, publish_date,
                _j(likely_questions), _j(retrieval_phrases),
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
