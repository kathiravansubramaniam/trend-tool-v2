from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from config.settings import settings
from src.utils.rate_limiter import retry_with_backoff

SYSTEM_PROMPT = """You are a document analysis expert. Extract structured metadata from the given document text.

Be SPECIFIC, not generic:
- Industry: name the exact sector (e.g. "Semiconductor", "Consumer Electronics", "Healthcare IT", "Electric Vehicles", "Investment Banking"). Use "Cross-Industry" only if the document genuinely spans many unrelated sectors.
- Topics: pick specific, named topics discussed in depth (e.g. "RISC-V adoption", "memory pricing cycles", "AI chip demand", "GLP-1 drug market"). Avoid vague terms like "technology", "market", "growth".
- Forecasts: extract specific predictions with timeframes (e.g. "Global EV battery market to reach $200B by 2030", "Semiconductor revenue to grow 15% in 2025"). Avoid vague statements.
- doc_name: extract the actual report/document title from the content, not the filename.
"""


class DocumentMetadata(BaseModel):
    doc_name: str
    industry: str
    market_scope: Literal["specific_industry", "whole_market"]
    topics: list[str]
    forecasts: list[str]


@retry_with_backoff
def extract_metadata(text: str, filename: str) -> DocumentMetadata:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.beta.chat.completions.parse(
        model=settings.parse_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Document filename: {filename}\n\n{text}",
            },
        ],
        response_format=DocumentMetadata,
        temperature=0,
        max_tokens=1000,
    )
    result = response.choices[0].message.parsed
    if result is None:
        raise ValueError(f"OpenAI returned null parsed result for {filename}")
    # Trim to reasonable limits
    result.topics = result.topics[:8]
    result.forecasts = result.forecasts[:10]
    return result
