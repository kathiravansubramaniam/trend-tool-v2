"""
Batch LLM metadata extraction for individual chunks.

Sends chunks in batches of 5 to gpt-4o-mini for cost efficiency.
Each chunk gets a focused, specific metadata profile — not a copy of document metadata.
"""

import logging
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from config.settings import settings
from src.utils.rate_limiter import retry_with_backoff

logger = logging.getLogger(__name__)

BATCH_SIZE = 5  # chunks per API call

SYSTEM_PROMPT = """You are generating retrieval metadata for individual chunks from a trend analysis document.

Each chunk is a section or paragraph from a report. Your task is to extract metadata that describes ONLY what is actually in that specific chunk — not the whole document.

RULES:
- Be specific to the content of THIS chunk only.
- Do not copy or guess document-level tags that don't appear in the chunk.
- retrieval_phrases should be 3–6 short keyword phrases that a researcher would type to find this chunk.
- chunk_summary: 1–2 sentences capturing the core idea of this chunk.
- evidence_type: choose the best fit — "statistic" | "forecast" | "case_study" | "claim" | "example"
- evidence_strength: "weak" (unsupported opinion) | "moderate" (general insight) | "strong" (data, named example, or cited source)
- If a field doesn't apply to this chunk, return an empty array.
- Never hallucinate facts not in the chunk text.

You will receive a JSON array of chunks, each with a "section_title" and "chunk_text".
Return a JSON object with a "chunks" array containing one metadata object per input chunk, in the same order.
"""


class ChunkMeta(BaseModel):
    chunk_summary: str = ""
    topics: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    behavioral_shifts: list[str] = Field(default_factory=list)
    trend_drivers: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    brands_companies: list[str] = Field(default_factory=list)
    consumer_needs: list[str] = Field(default_factory=list)
    retrieval_phrases: list[str] = Field(default_factory=list)
    evidence_type: Literal["statistic", "forecast", "case_study", "claim", "example"] = "claim"
    evidence_strength: Literal["weak", "moderate", "strong"] = "moderate"


class ChunkMetaBatch(BaseModel):
    chunks: list[ChunkMeta]


@retry_with_backoff
def _extract_batch(
    batch: list[dict],  # list of {section_title, chunk_text}
) -> list[ChunkMeta]:
    """Send one batch of up to BATCH_SIZE chunks and return their metadata."""
    import json

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.beta.chat.completions.parse(
        model=settings.parse_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(batch)},
        ],
        response_format=ChunkMetaBatch,
        temperature=0,
        max_tokens=1500,
    )
    result = response.choices[0].message.parsed
    if result is None:
        raise ValueError("OpenAI returned null for chunk batch")

    # Trim each chunk's lists to reasonable sizes
    for m in result.chunks:
        m.topics = m.topics[:6]
        m.themes = m.themes[:4]
        m.behavioral_shifts = m.behavioral_shifts[:4]
        m.trend_drivers = m.trend_drivers[:4]
        m.technologies = m.technologies[:4]
        m.brands_companies = m.brands_companies[:8]
        m.consumer_needs = m.consumer_needs[:4]
        m.retrieval_phrases = m.retrieval_phrases[:6]

    return result.chunks


def extract_chunk_metadata(
    chunks: list[tuple[str, str]],  # list of (section_title, chunk_text)
) -> list[ChunkMeta]:
    """
    Extract metadata for a list of (section_title, chunk_text) pairs.
    Processes in batches of BATCH_SIZE.
    Returns one ChunkMeta per input chunk, in the same order.
    Falls back to empty metadata on per-batch errors.
    """
    results: list[ChunkMeta] = []

    for i in range(0, len(chunks), BATCH_SIZE):
        batch_input = chunks[i : i + BATCH_SIZE]
        batch_payload = [
            {"section_title": title, "chunk_text": text[:1000]}  # cap to avoid token overflow
            for title, text in batch_input
        ]
        try:
            batch_results = _extract_batch(batch_payload)
            # Pad if LLM returned fewer results than input
            while len(batch_results) < len(batch_input):
                batch_results.append(ChunkMeta())
            results.extend(batch_results[: len(batch_input)])
        except Exception as e:
            logger.warning(f"Chunk metadata batch {i//BATCH_SIZE} failed: {e} — using empty metadata")
            results.extend([ChunkMeta() for _ in batch_input])

    return results
