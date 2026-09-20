from __future__ import annotations

import math
import re


class FixedSizeChunker:
    """
    Split text into fixed-size chunks with optional overlap.

    Rules:
        - Each chunk is at most chunk_size characters long.
        - Consecutive chunks share overlap characters.
        - The last chunk contains whatever remains.
        - If text is shorter than chunk_size, return [text].
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        step = self.chunk_size - self.overlap
        chunks: list[str] = []
        for start in range(0, len(text), step):
            chunk = text[start : start + self.chunk_size]
            chunks.append(chunk)
            if start + self.chunk_size >= len(text):
                break
        return chunks


class SentenceChunker:
    """
    Split text into chunks of at most max_sentences_per_chunk sentences.

    Sentence detection: split on ". ", "! ", "? " or ".\n".
    Strip extra whitespace from each chunk.
    """

    def __init__(self, max_sentences_per_chunk: int = 3) -> None:
        self.max_sentences_per_chunk = max(1, max_sentences_per_chunk)

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        chunks: list[str] = []
        for i in range(0, len(sentences), self.max_sentences_per_chunk):
            group = sentences[i : i + self.max_sentences_per_chunk]
            chunks.append(" ".join(group).strip())
        return chunks


class RecursiveChunker:
    """
    Recursively split text using separators in priority order.

    Default separator priority:
        ["\n\n", "\n", ". ", " ", ""]
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, separators: list[str] | None = None, chunk_size: int = 500) -> None:
        self.separators = self.DEFAULT_SEPARATORS if separators is None else list(separators)
        self.chunk_size = chunk_size

    def chunk(self, text: str) -> list[str]:
        if not text:
            return []
        return self._split(text, self.separators)

    def _merge_splits(self, splits: list[str], sep: str) -> list[str]:
        merged: list[str] = []
        current: list[str] = []
        current_len = 0
        for s in splits:
            if not s:
                continue
            add_len = len(s) if not current else len(sep) + len(s)
            if current_len + add_len <= self.chunk_size:
                current.append(s)
                current_len += add_len
            else:
                if current:
                    merged.append(sep.join(current))
                current = [s]
                current_len = len(s)
        if current:
            merged.append(sep.join(current))
        return merged

    def _split(self, current_text: str, remaining_separators: list[str]) -> list[str]:
        if not current_text:
            return []
        if len(current_text) <= self.chunk_size:
            return [current_text]
        if not remaining_separators:
            return [current_text[i : i + self.chunk_size] for i in range(0, len(current_text), self.chunk_size)]

        sep = remaining_separators[0]
        next_seps = remaining_separators[1:]

        if sep == "":
            return [current_text[i : i + self.chunk_size] for i in range(0, len(current_text), self.chunk_size)]

        if sep not in current_text:
            return self._split(current_text, next_seps)

        splits = current_text.split(sep)
        final_chunks: list[str] = []
        good_splits: list[str] = []

        for s in splits:
            if len(s) <= self.chunk_size:
                good_splits.append(s)
            else:
                if good_splits:
                    final_chunks.extend(self._merge_splits(good_splits, sep))
                    good_splits = []
                sub_chunks = self._split(s, next_seps)
                final_chunks.extend(sub_chunks)

        if good_splits:
            final_chunks.extend(self._merge_splits(good_splits, sep))

        return final_chunks


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def compute_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    cosine_similarity = dot(a, b) / (||a|| * ||b||)

    Returns 0.0 if either vector has zero magnitude.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(x * x for x in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return _dot(vec_a, vec_b) / (norm_a * norm_b)


class ChunkingStrategyComparator:
    """Run all built-in chunking strategies and compare their results."""

    def compare(self, text: str, chunk_size: int = 200) -> dict:
        fixed_overlap = min(50, chunk_size // 5 if chunk_size < 100 else 50)
        fixed_chunker = FixedSizeChunker(chunk_size=chunk_size, overlap=fixed_overlap)
        sentence_chunker = SentenceChunker(max_sentences_per_chunk=3)
        recursive_chunker = RecursiveChunker(chunk_size=chunk_size)

        fixed_chunks = fixed_chunker.chunk(text)
        sentence_chunks = sentence_chunker.chunk(text)
        recursive_chunks = recursive_chunker.chunk(text)

        def _stats(chunks: list[str]) -> dict:
            count = len(chunks)
            avg_len = (sum(len(c) for c in chunks) / count) if count > 0 else 0.0
            return {
                "count": count,
                "avg_length": avg_len,
                "chunks": chunks,
            }

        return {
            "fixed_size": _stats(fixed_chunks),
            "by_sentences": _stats(sentence_chunks),
            "recursive": _stats(recursive_chunks),
        }


class HeadingSectionChunker:
    """
    Chunk Markdown documents by headings (sections).

    Preserves semantic boundaries defined by section headers (#, ##, ###).
    If a section exceeds max_chunk_size, it splits using RecursiveChunker
    and re-attaches the heading to each sub-chunk to preserve context.
    """

    def __init__(self, max_chunk_size: int = 500) -> None:
        self.max_chunk_size = max_chunk_size
        self.recursive_chunker = RecursiveChunker(chunk_size=max_chunk_size)

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        # Split before headings (#, ##, ###)
        pattern = r"(?m)(?=^#{1,4}\s+)"
        sections = re.split(pattern, text)
        sections = [s.strip() for s in sections if s.strip()]

        chunks: list[str] = []
        for sec in sections:
            if len(sec) <= self.max_chunk_size:
                chunks.append(sec)
            else:
                lines = sec.split("\n", 1)
                heading = lines[0].strip() if lines[0].startswith("#") else ""
                body = lines[1] if len(lines) > 1 else ""

                if not body:
                    chunks.extend(self.recursive_chunker.chunk(sec))
                else:
                    sub_chunks = self.recursive_chunker.chunk(body)
                    for sub in sub_chunks:
                        if heading and not sub.startswith(heading):
                            chunks.append(f"{heading}\n{sub}")
                        else:
                            chunks.append(sub)
        return chunks
