"""
Trend Analysis Bot - Streamlit UI
Run with: streamlit run ui/app.py
"""
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.index.reader import get_index_stats, get_top_industries
from src.query.answerer import answer_question
from src.query.retriever import retrieve_relevant_docs

st.set_page_config(
    page_title="Trend Analysis Bot",
    page_icon="📊",
    layout="wide",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Trend Analysis Bot")
    st.markdown("---")

    # Index stats
    try:
        stats = get_index_stats()
        st.metric("Documents indexed", stats["done"])
        st.metric("Industries covered", stats["industries"])
        if stats["pending"] > 0:
            st.warning(f"{stats['pending']} documents still parsing...")
        if stats["failed"] > 0:
            st.error(f"{stats['failed']} documents failed to parse")
    except Exception:
        st.warning("Index not initialized. Run `make parse` first.")
        stats = {}

    st.markdown("---")

    # Industry filter
    try:
        industries = get_top_industries(limit=30)
        industry_options = ["All Industries"] + [f"{name} ({count})" for name, count in industries]
    except Exception:
        industry_options = ["All Industries"]

    selected_industry_label = st.selectbox(
        "Filter by Industry",
        industry_options,
        index=0,
    )

    # Extract just the industry name (strip the count)
    if selected_industry_label == "All Industries":
        industry_filter = None
    else:
        industry_filter = selected_industry_label.rsplit(" (", 1)[0]

    st.markdown("---")
    max_docs = st.slider("Max source documents", min_value=2, max_value=15, value=8)

    st.markdown("---")
    st.caption("Powered by OpenAI + Google Cloud Storage")

# ── Main area ─────────────────────────────────────────────────────────────────
st.header("Ask about trends and forecasts")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander(f"📄 Sources ({len(message['sources'])} documents)"):
                for src in message["sources"]:
                    st.markdown(f"- {src}")

# Chat input
if prompt := st.chat_input("e.g. What are the key semiconductor trends for 2025-2026?"):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate answer
    with st.chat_message("assistant"):
        with st.spinner("Searching index and reading documents..."):
            try:
                docs = retrieve_relevant_docs(
                    question=prompt,
                    industry_filter=industry_filter,
                    max_docs=max_docs,
                )

                if not docs:
                    answer_text = (
                        "No relevant documents found in the index for your question. "
                        "Try a different query or check that documents have been parsed (`make parse`)."
                    )
                    sources = []
                else:
                    result = answer_question(
                        question=prompt,
                        docs=docs,
                        max_context_tokens=14000,
                    )
                    answer_text = result.answer
                    sources = result.sources

            except Exception as e:
                answer_text = f"Error: {e}\n\nMake sure your `.env` is configured and the index is populated."
                sources = []

        st.markdown(answer_text)

        if sources:
            with st.expander(f"📄 Sources ({len(sources)} documents used)"):
                for src in sources:
                    st.markdown(f"- {src}")

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer_text,
        "sources": sources,
    })

# Show hint if no messages yet
if not st.session_state.messages:
    st.markdown(
        """
        **Get started:**
        1. Make sure you've run `make parse` to index your PDF library
        2. Optionally filter by industry in the sidebar
        3. Ask any question about trends, forecasts, or market analysis

        **Example questions:**
        - *What are the major forecasts for the EV battery market through 2030?*
        - *Which AI trends are expected to dominate in 2025?*
        - *What do the reports say about semiconductor supply chain risks?*
        """
    )
