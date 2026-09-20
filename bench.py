#!/usr/bin/env python3
"""
Benchmark Runner for Knowledge Base Retrieval Evaluation (UTSC Library Services)

Features:
1. Loads .md documents from data/utsc-library-services/
2. Extracts frontmatter metadata and chunks body content
3. Stores chunk documents in EmbeddingStore
4. Runs 5 benchmark queries with gold answer comparison and A/B filtering
5. Supports caching for OpenAI/Gemini embeddings to avoid redundant cost
6. Outputs results to terminal and saves to ket_qua_benchmark.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.agent import KnowledgeBaseAgent
from src.chunking import (
    FixedSizeChunker,
    HeadingSectionChunker,
    RecursiveChunker,
    SentenceChunker,
)
from src.embeddings import (
    EMBEDDING_PROVIDER_ENV,
    GEMINI_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_MODEL,
    GeminiEmbedder,
    LocalEmbedder,
    MockEmbedder,
    OpenAIEmbedder,
    _mock_embed,
)
from src.models import Document
from src.store import EmbeddingStore

# ==============================================================================
# 1. CẤU HÌNH CHIẾN LƯỢC CHUNKING (Mỗi thành viên chọn 1 chiến lược tại đây)
# Các lựa chọn: "heading" | "recursive" | "by_sentences" | "fixed_size"
# ==============================================================================
DEFAULT_CHUNKER_STRATEGY = "heading"

DATA_DIR = Path("data/utsc-library-services")
CACHE_FILE = Path(".cache_embeddings.json")
OUTPUT_FILE = Path("ket_qua_benchmark.txt")

BENCHMARK_QUERIES = [
    {
        "id": 1,
        "query": "What are the UTSC Library’s regular opening hours from Monday to Friday between September 8 and December 22, 2026?",
        "gold_answer": "The library’s regular weekday hours are 8:00 AM to 10:00 PM. It is closed on October 12, 2026.",
        "evidence_doc": "utsc-library-hours",
        "filter": None,
        "notes": "Tra cứu thời gian và nhận biết ngoại lệ.",
    },
    {
        "id": 2,
        "query": "As an undergraduate student, how long can I borrow regular library items, and what is my item limit?",
        "gold_answer": "Undergraduate students have a regular loan period of 14 days and an item limit of 50.",
        "evidence_doc": "utsc-borrowing-policy",
        "filter": None,
        "notes": "Phân biệt quy định dành cho sinh viên đại học với các nhóm khác.",
    },
    {
        "id": 3,
        "query": "Where should a user return a borrowed laptop from the Technology Loans collection?",
        "gold_answer": "A borrowed laptop should be returned directly to the Info Desk.",
        "evidence_doc": "utsc-technology-loans",
        "filter": None,
        "notes": "Tra cứu địa điểm và quy trình trả thiết bị.",
    },
    {
        "id": 4,
        "query": "A student needs to find a physical course reading placed on reserve. Where is it located?",
        "gold_answer": "Physical course reserves are located 20 steps to the left of the InfoDesk at the UTSC Library.",
        "evidence_doc": "utsc-course-reserves",
        "filter": {"audience": "student"},
        "notes": "A/B test: không lọc so với metadata_filter={'audience': 'student'}.",
        "ab_test": True,
    },
    {
        "id": 5,
        "query": "Which service provides a free and secure University of Toronto repository for disseminating and preserving faculty and graduate-student research?",
        "gold_answer": "TSpace – University of Toronto Research Repository.",
        "evidence_doc": "utsc-research-publishing",
        "filter": None,
        "notes": "Định danh dịch vụ theo chức năng.",
    },
]


def get_chunker(strategy_name: str, chunk_size: int = 500):
    name = strategy_name.lower().strip()
    if name == "fixed_size":
        return FixedSizeChunker(chunk_size=chunk_size, overlap=50)
    elif name == "by_sentences":
        return SentenceChunker(max_sentences_per_chunk=3)
    elif name == "recursive":
        return RecursiveChunker(chunk_size=chunk_size)
    elif name == "heading":
        return HeadingSectionChunker(max_chunk_size=chunk_size)
    else:
        raise ValueError(f"Chiến lược không hợp lệ: {strategy_name}. Chọn: fixed_size | by_sentences | recursive | heading")


def parse_markdown(path: Path) -> tuple[dict[str, str], str]:
    """Tách YAML frontmatter và content phần thân."""
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].strip()
            metadata = {}
            for line in fm_text.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    metadata[k.strip()] = v.strip().strip('"').strip("'")
            return metadata, body
    return {}, raw.strip()


class CachedEmbedder:
    """Wrapper cache vector embedding theo hash nội dung để tiết kiệm chi phí gọi API."""

    def __init__(self, base_embedder, cache_path: Path = CACHE_FILE) -> None:
        self.base_embedder = base_embedder
        self.cache_path = cache_path
        self._cache: dict[str, list[float]] = {}
        if self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def __call__(self, text: str) -> list[float]:
        key = hashlib.md5(text.encode("utf-8")).hexdigest()
        if key in self._cache:
            return self._cache[key]
        vector = self.base_embedder(text)
        self._cache[key] = vector
        return vector

    def save(self) -> None:
        try:
            self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
        except Exception:
            pass


def get_embedder():
    load_dotenv(override=False)
    provider = os.getenv(EMBEDDING_PROVIDER_ENV, "mock").strip().lower()
    if provider == "local":
        try:
            embedder = LocalEmbedder(model_name=os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        except Exception as e:
            print(f"Warning: Không thể nạp LocalEmbedder ({e}), chuyển sang MockEmbedder.", file=sys.stderr)
            embedder = _mock_embed
    elif provider == "openai":
        try:
            embedder = OpenAIEmbedder(model_name=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
        except Exception as e:
            print(f"Warning: Không thể nạp OpenAIEmbedder ({e}), chuyển sang MockEmbedder.", file=sys.stderr)
            embedder = _mock_embed
    elif provider == "gemini":
        try:
            embedder = GeminiEmbedder(model_name=os.getenv("GEMINI_EMBEDDING_MODEL", GEMINI_EMBEDDING_MODEL))
        except Exception as e:
            print(f"Warning: Không thể nạp GeminiEmbedder ({e}), chuyển sang MockEmbedder.", file=sys.stderr)
            embedder = _mock_embed
    else:
        embedder = _mock_embed

    return CachedEmbedder(embedder)


def build_corpus_documents(data_dir: Path, chunker) -> list[Document]:
    documents: list[Document] = []
    files = sorted(data_dir.glob("*.md"))
    for file_path in files:
        fm, body = parse_markdown(file_path)
        doc_id = fm.get("doc_id") or file_path.stem
        chunks = chunker.chunk(body)
        for idx, ch in enumerate(chunks):
            chunk_id = f"{doc_id}#{idx}"
            chunk_metadata = {
                **fm,
                "doc_id": doc_id,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "source_file": str(file_path),
            }
            documents.append(Document(id=chunk_id, content=ch, metadata=chunk_metadata))
    return documents


def run_benchmark(strategy_name: str = DEFAULT_CHUNKER_STRATEGY, chunk_size: int = 500) -> str:
    lines: list[str] = []

    def log(msg: str = ""):
        print(msg)
        lines.append(msg)

    log("=" * 80)
    log(f"CHẠY ĐÁNH GIÁ TRUY XUẤT (BENCHMARK) — CHIẾN LƯỢC: {strategy_name.upper()}")
    log("=" * 80)

    chunker = get_chunker(strategy_name, chunk_size=chunk_size)
    embedder = get_embedder()
    backend_name = getattr(embedder.base_embedder, "_backend_name", embedder.base_embedder.__class__.__name__)
    log(f"Backend Embedding: {backend_name}")
    log(f"Thư mục tài liệu : {DATA_DIR}")

    docs = build_corpus_documents(DATA_DIR, chunker)
    log(f"Số lượng file .md: {len(list(DATA_DIR.glob('*.md')))}")
    log(f"Tổng số chunk nạp: {len(docs)} chunks")
    avg_len = sum(len(d.content) for d in docs) / len(docs) if docs else 0
    log(f"Độ dài chunk TB  : {avg_len:.1f} ký tự")
    log("-" * 80)

    store = EmbeddingStore(collection_name="benchmark_collection", embedding_fn=embedder)
    store.add_documents(docs)

    for item in BENCHMARK_QUERIES:
        qid = item["id"]
        query = item["query"]
        gold = item["gold_answer"]
        target_doc = item["evidence_doc"]
        m_filter = item["filter"]

        log(f"\n[CÂU HỎI #{qid}] {query}")
        log(f"  • Gold Answer : {gold}")
        log(f"  • Bằng chứng  : {target_doc}")
        if m_filter:
            log(f"  • Bộ lọc meta : {m_filter}")

        # Tìm kiếm với bộ lọc (nếu có)
        results = store.search_with_filter(query, top_k=3, metadata_filter=m_filter)
        log("  • Top-3 kết quả truy xuất:")
        hit = False
        for rank, r in enumerate(results, start=1):
            r_doc = r["metadata"].get("doc_id")
            score = r["score"]
            preview = r["content"][:100].replace("\n", " ")
            is_match = (r_doc == target_doc)
            if is_match and not hit:
                hit = True
            tag = " [KHỚP NGUỒN CHUẨN]" if is_match else ""
            log(f"    {rank}. [{score:.4f}] doc_id={r_doc} (id={r['id']}){tag}")
            log(f"       Preview: \"{preview}...\"")

        log(f"  • Đánh giá Top-3: {'ĐẠT (chứa tài liệu chuẩn)' if hit else 'CHƯA ĐẠT'}")

        # A/B testing cho câu 4 nếu có
        if item.get("ab_test"):
            log("  --- [A/B TEST CHO CÂU HỎI #4: CÓ LỌC vs KHÔNG LỌC] ---")
            no_filter_res = store.search_with_filter(query, top_k=3, metadata_filter=None)
            log("  > Khi KHÔNG lọc metadata:")
            for rank, r in enumerate(no_filter_res, start=1):
                r_doc = r["metadata"].get("doc_id")
                aud = r["metadata"].get("audience")
                log(f"    {rank}. [{r['score']:.4f}] doc_id={r_doc} | audience={aud}")
            log(f"  > Khi CÓ lọc metadata_filter={m_filter}:")
            for rank, r in enumerate(results, start=1):
                r_doc = r["metadata"].get("doc_id")
                aud = r["metadata"].get("audience")
                log(f"    {rank}. [{r['score']:.4f}] doc_id={r_doc} | audience={aud}")

    embedder.save()
    output_text = "\n".join(lines)
    OUTPUT_FILE.write_text(output_text, encoding="utf-8")
    log(f"\nĐã lưu toàn bộ kết quả benchmark vào: {OUTPUT_FILE}")
    return output_text


def main():
    parser = argparse.ArgumentParser(description="Chạy benchmark retrieval cho K4-L3A")
    parser.add_argument(
        "--strategy",
        default=DEFAULT_CHUNKER_STRATEGY,
        choices=["heading", "recursive", "by_sentences", "fixed_size"],
        help="Chiến lược chunking (mặc định: heading)",
    )
    parser.add_argument("--chunk-size", type=int, default=500, help="Kích thước chunk (mặc định: 500)")
    args = parser.parse_args()

    run_benchmark(strategy_name=args.strategy, chunk_size=args.chunk_size)


if __name__ == "__main__":
    main()
