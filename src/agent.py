from typing import Callable

from .store import EmbeddingStore


class KnowledgeBaseAgent:
    """
    An agent that answers questions using a vector knowledge base.

    Retrieval-augmented generation (RAG) pattern:
        1. Retrieve top-k relevant chunks from the store.
        2. Build a prompt with the chunks as context.
        3. Call the LLM to generate an answer.
    """

    def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3) -> str:
        if not question or not question.strip():
            return "Vui lòng nhập câu hỏi."

        if self.store.get_collection_size() == 0:
            return "Không tìm thấy thông tin trong cơ sở tri thức vì kho lưu trữ đang trống."

        results = self.store.search(question, top_k=top_k)
        if not results:
            return "Không tìm thấy tài liệu phù hợp để trả lời câu hỏi."

        context_blocks = []
        for i, r in enumerate(results, start=1):
            source = r.get("metadata", {}).get("source") or r.get("metadata", {}).get("doc_id") or r.get("id", "unknown")
            context_blocks.append(f"[{i}] (Nguồn: {source})\n{r['content']}")

        context_str = "\n\n".join(context_blocks)

        prompt = (
            "Bạn là trợ lý AI trả lời câu hỏi dựa trên tài liệu được cung cấp.\n"
            "Chỉ sử dụng thông tin trong ngữ cảnh dưới đây. Nếu ngữ cảnh không chứa đủ thông tin để trả lời, "
            "hãy nêu rõ là không tìm thấy trong tài liệu, tuyệt đối không suy đoán.\n"
            "Hãy trích dẫn rõ nguồn tương ứng theo số thứ tự [1], [2]... khi đưa ra thông tin.\n\n"
            f"--- NGỮ CẢNH ---\n{context_str}\n\n"
            f"--- CÂU HỎI ---\n{question}\n\n"
            "--- CÂU TRẢ LỜI ---"
        )

        return self.llm_fn(prompt)
