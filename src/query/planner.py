"""
LLM-powered retrieval planner.

Takes a broad candidate set (from FTS5 / vector search) with their full rich metadata,
and uses a fast LLM to semantically rank and select the most relevant documents for
the user's question — going far beyond keyword matching.
"""

import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from config.settings import settings
from src.index.reader import SearchResult

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the retrieval planner for a trend analysis chatbot.

You will receive:
1. A user question
2. Optional selected industries
3. A list of document metadata objects

Your task is to identify the most relevant documents for answering the question.

Do not rely only on exact keyword matches.
Instead, infer the deeper semantic structure of the question.

STEP 1 — PARSE THE QUESTION
Extract:
- primary topic
- adjacent topics
- industry
- subsector
- entities/brands
- demographics/audiences
- geography
- behaviors
- technologies
- business model patterns
- strategic lens
- time horizon

STEP 2 — EXPAND THE QUESTION SEMANTICALLY
Generate related terms, narrower terms, adjacent sector terms, synonymous phrases,
behavioral and demographic variants, and likely implied concepts.

Example:
Question: "What trends are shaping the future of trucks?"
Expand into: commercial vehicles, freight, logistics, heavy-duty mobility, delivery fleets,
electrification, autonomous trucking, fleet management, telematics, charging infrastructure,
decarbonization, driver experience, last-mile delivery, fleet operators

STEP 3 — MATCH AGAINST METADATA FIELDS
Score each document against:
- industries_primary, industries_secondary
- subsectors, product_categories
- brands_companies
- demographics (age_groups, psychographics, life_stages)
- geographies
- behaviors, behavioral_shifts
- consumer_needs
- trend_drivers, technologies, themes
- likely_questions, retrieval_phrases
- summary

STEP 4 — RANK
Prioritize documents that match:
1. Direct topical fit
2. Subsector fit
3. Behavior / use-case fit
4. Demographic fit
5. Entity fit
6. Geography fit
7. Strategic relevance

De-prioritize documents that only match on very broad industry tags.

STEP 5 — OUTPUT
Return valid JSON with exactly this structure:
{
  "parsed_question": {
    "primary_topic": "string",
    "adjacent_topics": ["string"],
    "industry": "string or null",
    "subsector": "string or null",
    "entities": ["string"],
    "demographics": "string or null",
    "geography": "string or null",
    "behaviors": ["string"],
    "technologies": ["string"],
    "strategic_lens": "string or null",
    "time_horizon": "string or null"
  },
  "semantic_expansion_terms": ["string"],
  "selected_documents": ["gcs_name"],
  "score_per_document": {"gcs_name": 0.0},
  "explanation_per_document": {"gcs_name": "why it matched"},
  "rejected_but_close_documents": ["gcs_name"]
}

Select between 5 and 10 documents. Scores should be between 0.0 and 1.0.
Only include gcs_name values that appear in the input document list.
Do not answer the user's question — only perform retrieval planning and ranking.
"""


@dataclass
class PlannerResult:
    selected_gcs_names: list[str]
    score_per_document: dict[str, float]
    explanation_per_document: dict[str, str]
    rejected_but_close: list[str]
    semantic_expansion_terms: list[str]
    parsed_question: dict


def _build_doc_metadata(doc: SearchResult) -> dict:
    """Build a compact metadata object for the planner — rich but token-efficient."""
    demo = doc.demographics or {}
    geo = doc.geographies or {}
    return {
        "gcs_name": doc.gcs_name,
        "doc_name": doc.doc_name,
        "summary": doc.summary or "",
        "industries_primary": doc.industries_primary or [],
        "subsectors": doc.subsectors or [],
        "themes": doc.themes or [],
        "consumer_needs": doc.consumer_needs or [],
        "behavioral_shifts": doc.behavioral_shifts or [],
        "trend_drivers": doc.trend_drivers or [],
        "technologies": doc.technologies or [],
        "brands_companies": (doc.brands_companies or [])[:10],
        "demographics": {
            "age_groups": demo.get("age_groups", []),
            "psychographics": demo.get("psychographics", []),
            "life_stages": demo.get("life_stages", []),
        },
        "geographies": {
            "countries": geo.get("countries", []),
            "regions": geo.get("regions", []),
            "market_scope": geo.get("market_scope", "global"),
        },
        "likely_questions": doc.likely_questions or [],
        "retrieval_phrases": doc.retrieval_phrases or [],
        "time_horizon": doc.time_horizon or "short-term",
        "publish_date": doc.publish_date,
    }


def plan_retrieval(
    question: str,
    candidates: list[SearchResult],
    industry_filter: list[str] | None = None,
) -> PlannerResult:
    """
    Given a question and a broad set of candidate SearchResults,
    use an LLM to semantically score and select the best documents.
    """
    if not candidates:
        return PlannerResult(
            selected_gcs_names=[],
            score_per_document={},
            explanation_per_document={},
            rejected_but_close=[],
            semantic_expansion_terms=[],
            parsed_question={},
        )

    doc_list = [_build_doc_metadata(d) for d in candidates]

    user_content = {
        "question": question,
        "selected_industries": industry_filter or [],
        "documents": doc_list,
    }

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_content)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"Retrieval planner LLM call failed: {e} — falling back to candidate order")
        return _fallback_result(candidates)

    # Validate gcs_names are real candidates (guard against hallucination)
    valid_names = {d.gcs_name for d in candidates}
    selected = [n for n in data.get("selected_documents", []) if n in valid_names]
    rejected = [n for n in data.get("rejected_but_close_documents", []) if n in valid_names]

    if not selected:
        logger.warning("Planner returned no valid selections — falling back to candidate order")
        return _fallback_result(candidates)

    scores = {k: v for k, v in data.get("score_per_document", {}).items() if k in valid_names}
    explanations = {k: v for k, v in data.get("explanation_per_document", {}).items() if k in valid_names}

    logger.info(f"Planner selected {len(selected)} docs from {len(candidates)} candidates")
    for name in selected:
        score = scores.get(name, 0.0)
        reason = explanations.get(name, "")[:100]
        logger.debug(f"  [{score:.2f}] {name}: {reason}")

    return PlannerResult(
        selected_gcs_names=selected,
        score_per_document=scores,
        explanation_per_document=explanations,
        rejected_but_close=rejected,
        semantic_expansion_terms=data.get("semantic_expansion_terms", []),
        parsed_question=data.get("parsed_question", {}),
    )


def _fallback_result(candidates: list[SearchResult]) -> PlannerResult:
    """Return top candidates in their existing order as a safe fallback."""
    top = candidates[:8]
    return PlannerResult(
        selected_gcs_names=[d.gcs_name for d in top],
        score_per_document={d.gcs_name: 1.0 - (i * 0.1) for i, d in enumerate(top)},
        explanation_per_document={d.gcs_name: "Fallback: ranked by initial retrieval score" for d in top},
        rejected_but_close=[],
        semantic_expansion_terms=[],
        parsed_question={},
    )
