# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** [Tên sinh viên]
**Nhóm:** [Tên nhóm]
**Ngày:** [Ngày nộp]

> **Nộp 1 bản / sinh viên.** Phần nhóm (lựa chọn tài liệu, thiết kế chiến lược, bộ câu hỏi đánh giá, demo) nộp chung 1 bản trong `REPORT_NHOM.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) + Kết quả truy xuất của tôi (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### Độ tương tự Cosine (Cosine Similarity) (Bài tập 1.1)

**Độ tương tự cosine cao (High cosine similarity) nghĩa là gì?**
> Độ tương tự cosine cao (tiến gần về 1.0) biểu thị hai vector embedding chỉ về cùng một hướng trong không gian biểu diễn ngữ nghĩa nhiều chiều, chứng minh hai văn bản có độ tương đồng ngữ nghĩa rất lớn dù câu chữ bề mặt hay độ dài có thể khác biệt.

**Ví dụ có độ tương tự CAO:**
- Câu A: "Sinh viên có thể gia hạn mượn sách giáo trình trực tuyến qua hệ thống."
- Câu B: "Người học được phép kéo dài thời gian giữ tài liệu học tập bằng cổng thông tin điện tử."
- Tại sao tương đồng: Dù hai câu dùng từ vựng hoàn toàn khác nhau ("sinh viên" vs "người học", "gia hạn" vs "kéo dài thời gian giữ", "sách giáo trình" vs "tài liệu học tập", "hệ thống" vs "cổng thông tin điện tử"), mô hình embedding hiểu được ý nghĩa khái niệm tương đương (semantic equivalence) và định vị chúng sát nhau trong không gian vector.

**Ví dụ có độ tương tự THẤP:**
- Câu A: "Sinh viên có thể gia hạn mượn sách giáo trình trực tuyến qua hệ thống."
- Câu B: "Hệ thống phanh ABS của xe ô tô giúp chống bó cứng bánh xe khi phanh gấp."
- Tại sao khác: Dù cả hai câu đều xuất hiện từ khóa "hệ thống", chúng thuộc hai lĩnh vực ngữ cảnh hoàn toàn tách biệt (dịch vụ thư viện đại học vs nguyên lý kỹ thuật cơ khí ô tô), khiến hướng vector gần như vuông góc nhau và điểm tương đồng rất thấp (tiệm cận 0).

**Tại sao độ tương tự cosine (cosine similarity) được ưu tiên hơn khoảng cách Euclid (Euclidean distance) cho text embeddings?**
> Khoảng cách Euclid ($L_2$) phụ thuộc vào độ lớn (magnitude) của vector — vốn bị chi phối bởi độ dài văn bản hoặc tần suất từ vựng, khiến hai văn bản cùng chủ đề nhưng khác độ dài bị xem là xa nhau. Ngược lại, Cosine similarity chỉ đo góc giữa hai vector ($\cos \theta$), phản ánh thuần túy hướng ngữ nghĩa mà không bị biến dạng bởi độ dài văn bản, đặc biệt tối ưu khi vector đã được chuẩn hóa ($||v|| = 1$).

### Bài toán tính toán Chunking (Bài tập 1.2)

**Tài liệu 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**
> *Trình bày phép tính:* Với độ dài $N = 10000$, $chunk\_size = 500$, $overlap = 50$, bước nhảy giữa các chunk là $step = 500 - 50 = 450$. Áp dụng công thức: $\lceil(10000 - 50) / (500 - 50)\rceil = \lceil 9950 / 450 \rceil = \lceil 22.111\dots \rceil = 23$. Kiểm chứng thực tế qua mã nguồn: `len(FixedSizeChunker(chunk_size=500, overlap=50).chunk('a'*10000)) == 23`.
> *Đáp án:* 23 chunks.

**Nếu độ chồng chéo (overlap) tăng lên 100, số lượng chunk thay đổi thế nào? Tại sao muốn độ chồng chéo nhiều hơn?**
> Khi overlap tăng lên 100, bước nhảy giảm xuống còn 400, số chunk tăng lên thành $\lceil(10000 - 100) / (500 - 100)\rceil = \lceil 9900 / 400 \rceil = 25$ chunks (tăng 2 chunk). Ta muốn overlap lớn hơn nhằm bảo toàn tính liên tục của ngữ cảnh (context continuity), tránh tình trạng một điều khoản hay mối quan hệ logic quan trọng bị xé đôi tại ranh giới cắt, giúp thông tin luôn xuất hiện trọn vẹn trong ít nhất một chunk.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

Giải thích cách tiếp cận của bạn khi lập trình (implement) các phần chính trong gói `src`.

### Các hàm chia nhỏ (Chunking Functions)

**`SentenceChunker.chunk`** — hướng tiếp cận:
> Sử dụng regex lookbehind `r'(?<=[.!?])\s+'` để nhận diện điểm ngắt câu tại khoảng trắng ngay sau dấu câu mà không làm mất dấu câu ở cuối câu. Sau khi làm sạch các câu, gom tối đa `max_sentences_per_chunk` câu vào mỗi chunk và strip khoảng trắng. Xử lý text rỗng bằng cách trả về `[]`.
> *Edge cases đã nhận diện:* Chưa xử lý được các từ viết tắt có dấu chấm (như "TS.", "v.v.", "e.g.") và số thập phân ("3.14"), các trường hợp này sẽ bị cắt nhầm thành câu mới.

**`RecursiveChunker.chunk` / `_split`** — hướng tiếp cận:
> Áp dụng thuật toán chia để trị hai chiều (two-way split & merge) với danh sách phân cách ưu tiên `["\n\n", "\n", ". ", " ", ""]`. Nếu mảnh văn bản lớn hơn `chunk_size`, đệ quy sâu hơn với separator nhỏ hơn; sau đó gom gộp (merge) các mảnh nhỏ liền kề cho tới sát ngưỡng `chunk_size` để chống phân mảnh văn bản.
> *Base cases:* (1) Chuỗi rỗng trả `[]`; (2) Độ dài chuỗi $\le chunk\_size$ trả `[current_text]`; (3) Khi hết danh sách separator (`remaining_separators == []` hoặc `sep == ""`), cắt lát cố định theo `chunk_size` để kết thúc an toàn.

### Lớp EmbeddingStore

**`add_documents` + `search`** — hướng tiếp cận:
> Lưu trữ in-memory dưới dạng danh sách các dictionary record chuẩn hóa thông qua helper `_make_record()`. Mỗi record sao chép an toàn `metadata`, tự động bổ sung khóa `doc_id` trỏ về tài liệu gốc và tính sẵn vector embedding. Hàm `search()` tái sử dụng helper `_search_records()`, tính cosine similarity giữa vector truy vấn và toàn bộ vector trong store, sắp xếp giảm dần và lấy ra top-k kết quả mà không kèm vector thô nhằm giữ dữ liệu trả về gọn gàng.

**`search_with_filter` + `delete_document`** — hướng tiếp cận:
> Áp dụng cơ chế lọc trước (pre-filtering) thay vì lọc sau: duyệt qua kho lưu trữ để chọn ra các record thỏa mãn toàn bộ điều kiện `metadata_filter` trước, sau đó mới chạy `_search_records()` trên tập ứng viên này. Điều này ngăn chặn triệt để lỗi mất kết quả (nếu lấy top-k trước rồi mới lọc, k slot có thể bị chiếm hết bởi các tài liệu không hợp lệ). Hàm `delete_document()` lọc bỏ mọi record có `metadata['doc_id']` hoặc `id` trùng khớp với `doc_id` cần xóa và trả về `True` nếu số lượng phần tử giảm xuống, ngược lại trả `False`.

### Tác tử KnowledgeBaseAgent

**`answer`** — hướng tiếp cận:
> Triển khai quy trình RAG 3 nhịp: (1) Truy xuất top-k chunk từ `EmbeddingStore` theo câu hỏi; nếu store rỗng trả về thông báo phù hợp thay vì gọi LLM vô ích; (2) Dựng prompt có cấu trúc chặt chẽ, đánh số từng đoạn ngữ cảnh `[1]`, `[2]`, `[3]` kèm nguồn tài liệu cụ thể và kèm chỉ dẫn bắt buộc LLM chỉ dùng ngữ cảnh được cung cấp (anti-hallucination) cũng như trích dẫn nguồn số tương ứng; (3) Gọi hàm `llm_fn(prompt)` để sinh câu trả lời có tính truy vết cao (Source Traceability).

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử (Test Results)

```text
============================= test session starts ==============================
platform darwin -- Python 3.11.16, pytest-9.1.1, pluggy-1.6.0 -- /Users/thai/Vinuni/Lab07-Day7/K4-DAY07-TranNguyenThaiDuy-2A202602991/.venv/bin/python3.11
cachedir: .pytest_cache
rootdir: /Users/thai/Vinuni/Lab07-Day7/K4-DAY07-TranNguyenThaiDuy-2A202602991
collecting ... collected 42 items

tests/test_solution.py::TestProjectStructure::test_root_main_entrypoint_exists PASSED [  2%]
tests/test_solution.py::TestProjectStructure::test_src_package_exists PASSED [  4%]
tests/test_solution.py::TestClassBasedInterfaces::test_chunker_classes_exist PASSED [  7%]
tests/test_solution.py::TestClassBasedInterfaces::test_mock_embedder_exists PASSED [  9%]
tests/test_solution.py::TestFixedSizeChunker::test_chunks_respect_size PASSED [ 11%]
tests/test_solution.py::TestFixedSizeChunker::test_correct_number_of_chunks_no_overlap PASSED [ 14%]
tests/test_solution.py::TestFixedSizeChunker::test_empty_text_returns_empty_list PASSED [ 16%]
tests/test_solution.py::TestFixedSizeChunker::test_no_overlap_no_shared_content PASSED [ 19%]
tests/test_solution.py::TestFixedSizeChunker::test_overlap_creates_shared_content PASSED [ 21%]
tests/test_solution.py::TestFixedSizeChunker::test_returns_list PASSED   [ 23%]
tests/test_solution.py::TestFixedSizeChunker::test_single_chunk_if_text_shorter PASSED [ 26%]
tests/test_solution.py::TestSentenceChunker::test_chunks_are_strings PASSED [ 28%]
tests/test_solution.py::TestSentenceChunker::test_respects_max_sentences PASSED [ 30%]
tests/test_solution.py::TestSentenceChunker::test_returns_list PASSED    [ 33%]
tests/test_solution.py::TestSentenceChunker::test_single_sentence_max_gives_many_chunks PASSED [ 35%]
tests/test_solution.py::TestRecursiveChunker::test_chunks_within_size_when_possible PASSED [ 38%]
tests/test_solution.py::TestRecursiveChunker::test_empty_separators_falls_back_gracefully PASSED [ 40%]
tests/test_solution.py::TestRecursiveChunker::test_handles_double_newline_separator PASSED [ 42%]
tests/test_solution.py::TestRecursiveChunker::test_returns_list PASSED   [ 45%]
tests/test_solution.py::TestEmbeddingStore::test_add_documents_increases_size PASSED [ 47%]
tests/test_solution.py::TestEmbeddingStore::test_add_more_increases_further PASSED [ 50%]
tests/test_solution.py::TestEmbeddingStore::test_initial_size_is_zero PASSED [ 52%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_content_key PASSED [ 54%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_score_key PASSED [ 57%]
tests/test_solution.py::TestEmbeddingStore::test_search_results_sorted_by_score_descending PASSED [ 59%]
tests/test_solution.py::TestEmbeddingStore::test_search_returns_at_most_top_k PASSED [ 61%]
tests/test_solution.py::TestEmbeddingStore::test_search_returns_list PASSED [ 64%]
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_non_empty PASSED [ 66%]
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_returns_string PASSED [ 69%]
tests/test_solution.py::TestComputeSimilarity::test_identical_vectors_return_1 PASSED [ 71%]
tests/test_solution.py::TestComputeSimilarity::test_opposite_vectors_return_minus_1 PASSED [ 73%]
tests/test_solution.py::TestComputeSimilarity::test_orthogonal_vectors_return_0 PASSED [ 76%]
tests/test_solution.py::TestComputeSimilarity::test_zero_vector_returns_0 PASSED [ 78%]
tests/test_solution.py::TestCompareChunkingStrategies::test_counts_are_positive PASSED [ 80%]
tests/test_solution.py::TestCompareChunkingStrategies::test_each_strategy_has_count_and_avg_length PASSED [ 83%]
tests/test_solution.py::TestCompareChunkingStrategies::test_returns_three_strategies PASSED [ 85%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_filter_by_department PASSED [ 88%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_no_filter_returns_all_candidates PASSED [ 90%]
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_returns_at_most_top_k PASSED [ 92%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_reduces_collection_size PASSED [ 95%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_false_for_nonexistent_doc PASSED [ 97%]
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_true_for_existing_doc PASSED [100%]

============================== 42 passed in 0.02s ==============================
```

**Số lượng bài test vượt qua (pass):** 42 / 42

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

| Cặp | Câu A | Câu B | Dự đoán | Điểm thực tế | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | | | cao / thấp | | |
| 2 | | | cao / thấp | | |
| 3 | | | cao / thấp | | |
| 4 | | | cao / thấp | | |
| 5 | | | cao / thấp | | |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**
> *Viết 2-3 câu:*

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Chạy **5 câu hỏi đánh giá của nhóm** trên mã nguồn cá nhân của bạn trong gói `src`. **5 câu hỏi này phải trùng với các thành viên cùng nhóm** (xem `REPORT_NHOM.md`).

| # | Câu hỏi (Query) | Top-1 Chunk truy xuất được (tóm tắt) | Điểm Score | Có liên quan không? (Relevant) | Câu trả lời của Agent (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** __ / 5

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**
> *Viết 2-3 câu:*

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Khởi động (Warm-up) | / 5 |
| Hướng tiếp cận của tôi (My Approach) | / 10 |
| Hoàn thiện code (Core Implementation — tests) | / 30 |
| Dự đoán độ tương tự (Similarity Predictions) | / 5 |
| Kết quả truy xuất của tôi (Competition Results) | / 10 |
| **Tổng phần cá nhân** | **/ 60** |
