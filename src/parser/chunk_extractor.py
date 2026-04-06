"""
Section-aware Markdown chunker.

Uses pymupdf4llm's Markdown output and splits at heading boundaries first,
then at paragraph boundaries if a section is too large.
This preserves semantic meaning and keeps section context attached to each chunk.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf4llm

# Target chunk size bounds in characters (~150–300 tokens)
MIN_CHARS = 200
MAX_CHARS = 1200

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)", re.MULTILINE)


@dataclass
class ChunkSegment:
    section_title: str   # nearest heading above the chunk (empty string if none)
    text: str            # the actual chunk text (includes section_title prefix)
    order: int           # 0-based position in document


def _split_large_section(title: str, body: str, start_order: int) -> list[ChunkSegment]:
    """Split a section that exceeds MAX_CHARS at paragraph then sentence boundaries."""
    segments: list[ChunkSegment] = []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]

    current_parts: list[str] = []
    current_len = 0
    order = start_order

    def flush() -> None:
        nonlocal current_len, order
        if not current_parts:
            return
        chunk_body = "\n\n".join(current_parts)
        prefix = f"**{title}**\n\n" if title else ""
        segments.append(ChunkSegment(
            section_title=title,
            text=(prefix + chunk_body).strip(),
            order=order,
        ))
        current_parts.clear()
        current_len = 0
        order += 1

    for para in paragraphs:
        # If a single paragraph exceeds max, split at sentence level
        if len(para) > MAX_CHARS:
            if current_parts:
                flush()
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sent in sentences:
                if current_len + len(sent) > MAX_CHARS and current_parts:
                    flush()
                current_parts.append(sent)
                current_len += len(sent)
            if current_parts:
                flush()
        elif current_len + len(para) > MAX_CHARS and current_parts:
            flush()
            current_parts.append(para)
            current_len = len(para)
        else:
            current_parts.append(para)
            current_len += len(para)

    if current_parts:
        flush()

    return segments


def chunk_markdown(md_text: str) -> list[ChunkSegment]:
    """
    Split a Markdown string into semantically coherent chunks.
    Returns an ordered list of ChunkSegment objects.
    """
    if not md_text or len(md_text.strip()) < MIN_CHARS:
        return []

    # Find all heading positions
    heading_matches = list(_HEADING_RE.finditer(md_text))

    if not heading_matches:
        # No headings — fall back to paragraph-level splitting
        return _split_large_section("", md_text, start_order=0)

    segments: list[ChunkSegment] = []

    # Handle preamble before first heading
    preamble = md_text[: heading_matches[0].start()].strip()
    if len(preamble) >= MIN_CHARS:
        segments.extend(_split_large_section("", preamble, start_order=0))

    # Process each section (heading + its content)
    for i, match in enumerate(heading_matches):
        title = match.group(2).strip()
        body_start = match.end()
        body_end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(md_text)
        body = md_text[body_start:body_end].strip()

        if not body or len(body) < MIN_CHARS:
            # Too short — merge with next or skip
            continue

        start_order = len(segments)
        if len(body) <= MAX_CHARS:
            prefix = f"**{title}**\n\n" if title else ""
            segments.append(ChunkSegment(
                section_title=title,
                text=(prefix + body).strip(),
                order=start_order,
            ))
        else:
            segments.extend(_split_large_section(title, body, start_order=start_order))

    # Re-number orders to be sequential (section merging may create gaps)
    for idx, seg in enumerate(segments):
        seg.order = idx

    return segments


def chunk_pdf(local_path: Path) -> list[ChunkSegment]:
    """Extract Markdown from PDF and return semantic chunks."""
    try:
        md_text = pymupdf4llm.to_markdown(str(local_path))
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from {local_path.name}: {e}") from e

    return chunk_markdown(md_text)
