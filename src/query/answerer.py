from dataclasses import dataclass, field

from openai import OpenAI

from config.settings import settings
from src.query.chunker import chunk_pdf
from src.query.retriever import RetrievedDoc
from src.utils.rate_limiter import retry_with_backoff
from src.utils.token_counter import count_tokens

SYSTEM_PROMPT = """You are a trend analysis expert. Your job is to answer questions about industry trends, market forecasts, and strategic insights.

Rules:
1. Answer ONLY based on the provided source documents. Do not use general knowledge.
2. Cite which document each piece of information comes from using [Document Name] in your answer.
3. If the documents don't contain relevant information for the question, say so clearly.
4. Be specific: include numbers, timeframes, and named companies/technologies when they appear in the sources.
5. Structure your answer with clear paragraphs. Use bullet points for lists of forecasts or trends.
"""


@dataclass
class AnswerResult:
    answer: str
    sources: list[str]
    chunk_count: int
    all_chunks: list[tuple[str, str]] = field(default_factory=list)


def _score_chunk(chunk: str, question: str) -> float:
    question_words = set(question.lower().split())
    chunk_words = set(chunk.lower().split())
    overlap = question_words & chunk_words
    return len(overlap) / max(len(question_words), 1)


def _select_chunks(
    doc_chunks: list[tuple[str, str]],  # (doc_name, chunk_text)
    question: str,
    max_tokens: int,
) -> list[tuple[str, str]]:
    scored = [
        (score, doc_name, chunk)
        for doc_name, chunk in doc_chunks
        for score in [_score_chunk(chunk, question)]
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    selected = []
    used_tokens = 0
    for _, doc_name, chunk in scored:
        chunk_tokens = count_tokens(chunk, settings.query_model)
        if used_tokens + chunk_tokens > max_tokens:
            break
        selected.append((doc_name, chunk))
        used_tokens += chunk_tokens

    return selected


def _call_llm(question: str, selected: list[tuple[str, str]]) -> AnswerResult:
    sources_text = ""
    used_doc_names: list[str] = []
    for doc_name, chunk in selected:
        sources_text += f"\n\n--- SOURCE: {doc_name} ---\n{chunk}"
        if doc_name not in used_doc_names:
            used_doc_names.append(doc_name)

    user_message = f"Question: {question}\n\nSOURCE DOCUMENTS:{sources_text}"

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.query_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    answer_text = response.choices[0].message.content or "No answer generated."
    return AnswerResult(answer=answer_text, sources=used_doc_names, chunk_count=len(selected))


@retry_with_backoff
def answer_question(
    question: str,
    docs: list[RetrievedDoc],
    max_context_tokens: int | None = None,
) -> AnswerResult:
    if max_context_tokens is None:
        max_context_tokens = settings.max_context_tokens

    if not docs:
        return AnswerResult(
            answer="No relevant documents were found in the index for your question. Try rephrasing or broadening your query.",
            sources=[],
            chunk_count=0,
        )

    # Chunk all retrieved PDFs
    all_chunks: list[tuple[str, str]] = []
    for doc in docs:
        try:
            chunks = chunk_pdf(doc.local_path)
            for chunk in chunks:
                all_chunks.append((doc.doc_name, chunk))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not chunk {doc.doc_name}: {e}")

    if not all_chunks:
        return AnswerResult(
            answer="The relevant documents could not be read. They may be scanned image PDFs.",
            sources=[doc.doc_name for doc in docs],
            chunk_count=0,
        )

    selected = _select_chunks(all_chunks, question, max_context_tokens)
    result = _call_llm(question, selected)
    result.all_chunks = all_chunks  # expose for caching
    return result


@retry_with_backoff
def answer_from_chunks(
    question: str,
    all_chunks: list[tuple[str, str]],
    max_context_tokens: int | None = None,
) -> AnswerResult:
    """Answer using pre-chunked content — skips all PDF reading for fast follow-ups."""
    if max_context_tokens is None:
        max_context_tokens = settings.max_context_tokens

    if not all_chunks:
        return AnswerResult(
            answer="No chunk context available.",
            sources=[],
            chunk_count=0,
            all_chunks=[],
        )

    selected = _select_chunks(all_chunks, question, max_context_tokens)
    result = _call_llm(question, selected)
    result.all_chunks = all_chunks  # pass through so it stays cached
    return result
