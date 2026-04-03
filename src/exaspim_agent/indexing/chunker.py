from __future__ import annotations


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks
