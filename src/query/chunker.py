from pathlib import Path

import pymupdf4llm
from langchain_text_splitters import RecursiveCharacterTextSplitter

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_pdf(local_path: Path) -> list[str]:
    try:
        md_text = pymupdf4llm.to_markdown(str(local_path))
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from {local_path.name}: {e}") from e

    if not md_text or len(md_text.strip()) < 50:
        return []

    return _splitter.split_text(md_text)
