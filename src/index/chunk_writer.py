import json

from src.index.chunk_schema import get_connection
from src.parser.chunk_extractor import ChunkSegment
from src.parser.chunk_metadata_extractor import ChunkMeta
from src.utils.token_counter import count_tokens
from config.settings import settings


def make_chunk_id(gcs_name: str, order: int) -> str:
    return f"{gcs_name}__c{order:04d}"


def upsert_chunks(
    gcs_name: str,
    doc_name: str,
    segments: list[ChunkSegment],
    metadata: list[ChunkMeta],
) -> int:
    """
    Upsert all chunks for a document.
    Returns the number of chunks written.
    Deletes existing chunks for this gcs_name first (full refresh).
    """
    assert len(segments) == len(metadata), "segments and metadata must be same length"

    with get_connection() as conn:
        # Delete existing chunks for this document
        conn.execute("DELETE FROM chunks WHERE gcs_name = ?", (gcs_name,))

        rows_written = 0
        for seg, meta in zip(segments, metadata):
            chunk_id = make_chunk_id(gcs_name, seg.order)
            token_count = count_tokens(seg.text, settings.parse_model)

            conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, gcs_name, chunk_order, section_title, chunk_text,
                    chunk_summary, topics, themes, behavioral_shifts, trend_drivers,
                    technologies, brands_companies, consumer_needs, retrieval_phrases,
                    evidence_type, evidence_strength, token_count
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
                ON CONFLICT(chunk_id) DO UPDATE SET
                    section_title     = excluded.section_title,
                    chunk_text        = excluded.chunk_text,
                    chunk_summary     = excluded.chunk_summary,
                    topics            = excluded.topics,
                    themes            = excluded.themes,
                    behavioral_shifts = excluded.behavioral_shifts,
                    trend_drivers     = excluded.trend_drivers,
                    technologies      = excluded.technologies,
                    brands_companies  = excluded.brands_companies,
                    consumer_needs    = excluded.consumer_needs,
                    retrieval_phrases = excluded.retrieval_phrases,
                    evidence_type     = excluded.evidence_type,
                    evidence_strength = excluded.evidence_strength,
                    token_count       = excluded.token_count
                """,
                (
                    chunk_id, gcs_name, seg.order, seg.section_title, seg.text,
                    meta.chunk_summary,
                    json.dumps(meta.topics),
                    json.dumps(meta.themes),
                    json.dumps(meta.behavioral_shifts),
                    json.dumps(meta.trend_drivers),
                    json.dumps(meta.technologies),
                    json.dumps(meta.brands_companies),
                    json.dumps(meta.consumer_needs),
                    json.dumps(meta.retrieval_phrases),
                    meta.evidence_type,
                    meta.evidence_strength,
                    token_count,
                ),
            )
            rows_written += 1

    return rows_written


def delete_chunks_for_doc(gcs_name: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM chunks WHERE gcs_name = ?", (gcs_name,))
