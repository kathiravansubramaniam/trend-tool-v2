from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from config.settings import settings
from src.utils.rate_limiter import retry_with_backoff

SYSTEM_PROMPT = """You are generating structured retrieval metadata for a trend analysis document.

Your job is NOT to summarize loosely. Your job is to create a high-quality retrieval profile so an AI system can later decide whether this document is relevant to a strategic trend question.

OUTPUT RULES
- Do not invent facts not supported by the text.
- Be precise and specific — prefer concrete tags over broad generic labels.
- Extract tags at multiple levels of specificity.
- Include demographic, psychographic, behavioral, brand, geography, and use-case metadata whenever present or strongly implied.
- If a field is unsupported, return an empty list.

TAGGING PRIORITY
1. Industries: name exact sectors (e.g. "Semiconductor", "Grocery Retail", "Electric Vehicles", "GLP-1 Pharmaceuticals"). Avoid vague terms.
2. Subsectors: go one level deeper (e.g. "fleet electrification", "last-mile logistics", "discount grocery", "private label growth")
3. Product/service categories: specific named categories discussed
4. Companies/brands: extract all named entities
5. Demographics: age groups, income segments, psychographics, life stages (e.g. "Gen Z", "price-sensitive households", "new parents")
6. Behaviors and behavioral shifts: what people are doing differently (e.g. "trading down to private label", "delaying home purchases")
7. Consumer needs / motivations / pain points: the underlying drivers
8. Trend drivers and signals of change: root causes of the shifts
9. Technologies and business models
10. Themes: high-level trend themes this document speaks to

For summary: 2-4 sentences capturing the core argument, key findings, and strategic relevance.
For forecasts: extract specific predictions with timeframes and numbers (e.g. "Global EV battery market to reach $200B by 2030").
For publish_date: extract from document content if available (e.g. "2025 Q1", "March 2025"). Return null if not found.
For doc_name: extract the actual report/document title from the content, not the filename.
For likely_questions: write 5-8 specific questions a researcher would ask that this document directly answers.
For retrieval_phrases: write 8-12 short keyword phrases that best describe this document's content for search matching.
"""


class Demographics(BaseModel):
    age_groups: list[str] = Field(default_factory=list)
    income_segments: list[str] = Field(default_factory=list)
    life_stages: list[str] = Field(default_factory=list)
    psychographics: list[str] = Field(default_factory=list)
    special_interest_groups: list[str] = Field(default_factory=list)


class Geographies(BaseModel):
    countries: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    market_scope: Literal["global", "regional", "country-specific", "city-specific"] = "global"


class DocumentMetadata(BaseModel):
    # Core identity
    doc_name: str
    source: str | None = None
    publish_date: str | None = None
    document_type: Literal["report", "article", "whitepaper", "news roundup", "presentation", "other"] = "report"
    summary: str = ""

    # Industry taxonomy (multi-level)
    industries_primary: list[str] = Field(default_factory=list)
    industries_secondary: list[str] = Field(default_factory=list)
    subsectors: list[str] = Field(default_factory=list)
    product_categories: list[str] = Field(default_factory=list)

    # Entities
    brands_companies: list[str] = Field(default_factory=list)

    # Audience
    demographics: Demographics = Field(default_factory=Demographics)
    geographies: Geographies = Field(default_factory=Geographies)

    # Behavioral signals
    consumer_needs: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    behavioral_shifts: list[str] = Field(default_factory=list)

    # Trend intelligence
    trend_drivers: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    forecasts: list[str] = Field(default_factory=list)

    # Temporal classification
    time_horizon: Literal["emerging", "short-term", "mid-term", "long-term"] = "short-term"

    # Retrieval optimization
    likely_questions: list[str] = Field(default_factory=list)
    retrieval_phrases: list[str] = Field(default_factory=list)

    # --- Backwards-compat helpers (not sent to OpenAI) ---

    @property
    def industry(self) -> str:
        return self.industries_primary[0] if self.industries_primary else "Unknown"

    @property
    def market_scope(self) -> str:
        return self.geographies.market_scope

    @property
    def topics(self) -> list[str]:
        """Combined themes + subsectors for FTS — backwards compat."""
        seen: set[str] = set()
        result: list[str] = []
        for t in self.themes + self.subsectors:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result


@retry_with_backoff
def extract_metadata(text: str, filename: str) -> DocumentMetadata:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.beta.chat.completions.parse(
        model=settings.parse_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Document filename: {filename}\n\n{text}"},
        ],
        response_format=DocumentMetadata,
        temperature=0,
        max_tokens=2000,
    )
    result = response.choices[0].message.parsed
    if result is None:
        raise ValueError(f"OpenAI returned null parsed result for {filename}")

    # Trim lists to reasonable bounds
    result.industries_primary = result.industries_primary[:5]
    result.industries_secondary = result.industries_secondary[:8]
    result.subsectors = result.subsectors[:12]
    result.product_categories = result.product_categories[:10]
    result.brands_companies = result.brands_companies[:20]
    result.consumer_needs = result.consumer_needs[:10]
    result.behaviors = result.behaviors[:10]
    result.behavioral_shifts = result.behavioral_shifts[:10]
    result.trend_drivers = result.trend_drivers[:10]
    result.technologies = result.technologies[:10]
    result.themes = result.themes[:10]
    result.forecasts = result.forecasts[:10]
    result.likely_questions = result.likely_questions[:8]
    result.retrieval_phrases = result.retrieval_phrases[:12]

    return result
