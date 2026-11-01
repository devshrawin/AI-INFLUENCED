"""Split long text into chunks of roughly N words on paragraph/sentence
boundaries, so each chunk can be scored and the most AI-like sections shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


@dataclass
class Chunk:
    index: int
    text: str
    word_count: int
    start_char: int


def chunk_text(text: str, max_words: int = 384, max_chunks: int = 20, min_words: int = 40) -> list[Chunk]:
    """Greedy packing of sentences into chunks of <= max_words words.

    A trailing chunk shorter than `min_words` is merged into the previous one
    (very short pieces give unreliable scores).
    """
    sentences: list[tuple[str, int]] = []
    for para_match in re.finditer(r"[^\n]+", text):
        para, offset = para_match.group(0), para_match.start()
        pos = 0
        for sent in _SENTENCE_END.split(para):
            if sent.strip():
                idx = para.find(sent, pos)
                sentences.append((sent.strip(), offset + max(idx, 0)))
                pos = max(idx, 0) + len(sent)

    chunks: list[Chunk] = []
    cur: list[str] = []
    cur_words = 0
    cur_start = 0
    for sent, start in sentences:
        words = len(sent.split())
        # Very long "sentence" (no punctuation): hard-split by words.
        if words > max_words:
            parts = sent.split()
            for i in range(0, len(parts), max_words):
                piece = parts[i : i + max_words]
                if cur:
                    chunks.append(Chunk(len(chunks), " ".join(cur), cur_words, cur_start))
                    cur, cur_words = [], 0
                chunks.append(Chunk(len(chunks), " ".join(piece), len(piece), start))
            continue
        if cur and cur_words + words > max_words:
            chunks.append(Chunk(len(chunks), " ".join(cur), cur_words, cur_start))
            cur, cur_words = [], 0
        if not cur:
            cur_start = start
        cur.append(sent)
        cur_words += words
    if cur:
        if chunks and cur_words < min_words:
            last = chunks[-1]
            chunks[-1] = Chunk(
                last.index, last.text + " " + " ".join(cur), last.word_count + cur_words, last.start_char
            )
        else:
            chunks.append(Chunk(len(chunks), " ".join(cur), cur_words, cur_start))
    return chunks[:max_chunks]
