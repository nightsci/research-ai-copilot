"""轻量本地 TF-IDF 向量化；无外部 embedding 服务和向量数据库。"""
import re
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rag.models import Chunk, Evidence, RagError


def tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
             if w not in ENGLISH_STOP_WORDS]
    # 中文用连续二字特征；避免引入分词模型下载。
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


class LocalIndex:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise RagError("没有可建立索引的论文文字。")
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(tokenizer=tokens, token_pattern=None,
                                         lowercase=False, sublinear_tf=True, max_features=60000)
        try:
            self.matrix = self.vectorizer.fit_transform(c.text for c in chunks)
        except ValueError as exc:
            raise RagError("论文缺少可检索词语，请检查文字提取结果。") from exc

    def search(self, question: str, top_k: int = 5, min_score: float = 0.08) -> list[Evidence]:
        if not 1 <= top_k <= 8 or not 0 < min_score <= 1:
            raise ValueError("检索参数超出范围")
        query = self.vectorizer.transform([question])
        if query.nnz == 0:
            return []
        scores = cosine_similarity(query, self.matrix).ravel()
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        evidence = []
        for i in order:
            if scores[i] < min_score:
                break
            c = self.chunks[i]
            # 重叠超过一半的候选只保留得分最高者，减少重复上下文。
            if any(c.document_id == e.chunk.document_id and c.page == e.chunk.page
                   and max(0, min(c.end, e.chunk.end) - max(c.start, e.chunk.start))
                   > min(len(c.text), len(e.chunk.text)) / 2 for e in evidence):
                continue
            evidence.append(Evidence(f"E{len(evidence) + 1}", c, float(scores[i])))
            if len(evidence) == top_k:
                break
        return evidence

    def diagnostics(self, question: str) -> dict:
        query = self.vectorizer.transform([question])
        scores = cosine_similarity(query, self.matrix).ravel()
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:5]
        return {"indexed": True, "chunks": len(self.chunks), "vocabulary_size": self.matrix.shape[1],
                "token_count": len(tokens(question)), "query_nonzero": query.nnz,
                "threshold": 0.08, "top_k_before_threshold": [
                    {"page": self.chunks[i].page, "score": float(scores[i])} for i in order]}

    def needs_english_query(self, question: str) -> bool:
        if not re.search(r"[\u4e00-\u9fff]", question):
            return False
        sample = " ".join(c.text for c in self.chunks)[:20000]
        return len(re.findall(r"[a-zA-Z]", sample)) > 3 * len(re.findall(r"[\u4e00-\u9fff]", sample))
