from __future__ import annotations

import re


SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


def _hard_split(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def chunk_text(text: str, max_chars: int, max_chunks: int) -> list[str]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []

    fragments: list[str] = []
    for sentence in SENTENCE_BOUNDARY.split(normalized):
        sentence = sentence.strip()
        if not sentence:
            continue
        fragments.extend(
            [sentence] if len(sentence) <= max_chars else _hard_split(sentence, max_chars)
        )

    chunks: list[str] = []
    current = ""
    for fragment in fragments:
        candidate = f"{current} {fragment}".strip() if current else fragment
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = fragment
    if current:
        chunks.append(current)

    return chunks[:max_chunks]

