import base64
import logging
from pathlib import Path

import pymupdf
import pymupdf4llm
from openai import OpenAI

from config.settings import settings
from src.utils.token_counter import count_tokens, truncate_to_tokens

logger = logging.getLogger(__name__)

# Max pages to send to vision API (cost control: ~$0.02-0.05 per PDF)
VISION_MAX_PAGES = 15
# Resolution for rendering pages to images (higher = more tokens but better OCR)
VISION_DPI = 150


def _vision_extract(pdf_path: Path) -> str:
    """Render pages as images and extract text via gpt-4o vision."""
    client = OpenAI(api_key=settings.openai_api_key)
    doc = pymupdf.open(str(pdf_path))
    n_pages = min(len(doc), VISION_MAX_PAGES)
    pages_text = []

    for i in range(n_pages):
        page = doc[i]
        mat = pymupdf.Matrix(VISION_DPI / 72, VISION_DPI / 72)
        pix = page.get_pixmap(matrix=mat)
        img_b64 = base64.standard_b64encode(pix.tobytes("png")).decode()

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all readable text from this PDF page. "
                            "Preserve headings, bullet points, and data. "
                            "Return text only, no commentary."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                            "detail": "auto",
                        },
                    },
                ],
            }],
            max_tokens=2000,
            temperature=0,
        )
        page_text = response.choices[0].message.content or ""
        if page_text.strip():
            pages_text.append(page_text)

    doc.close()
    return "\n\n".join(pages_text)


def extract_text(pdf_path: Path, max_tokens: int | None = None) -> str:
    if max_tokens is None:
        max_tokens = settings.max_parse_tokens

    # 1. Try pymupdf4llm (fast, free, best for text-native PDFs)
    md_text = None
    try:
        md_text = pymupdf4llm.to_markdown(str(pdf_path))
    except Exception as e:
        logger.debug(f"pymupdf4llm failed for {pdf_path.name}: {e}")

    # 2. Fall back to gpt-4o vision (handles image-based/design-heavy PDFs)
    if not md_text or len(md_text.strip()) < 50:
        logger.info(f"Using vision extraction for {pdf_path.name}")
        try:
            md_text = _vision_extract(pdf_path)
        except Exception as e:
            raise RuntimeError(f"Failed to extract text from {pdf_path.name}: {e}") from e

    if not md_text or len(md_text.strip()) < 50:
        raise RuntimeError(
            f"No text extracted from {pdf_path.name} — may be a fully blank or corrupted PDF"
        )

    token_count = count_tokens(md_text, settings.parse_model)
    if token_count <= max_tokens:
        return md_text

    return truncate_to_tokens(md_text, max_tokens, settings.parse_model)
