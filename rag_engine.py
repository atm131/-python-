"""
本地 RAG 知识库与大语言模型引擎
封装：文本解析 → 分块 → 向量化 → 检索 → LLM 流式调用
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass

import requests

from config import LLMConfig, RAGConfig
from plugin_manager import EventBus


# ─── 文档分块结构 ─────────────────────────────────────────

@dataclass
class Chunk:
    """知识库中的一个文本块"""
    id: str
    source: str
    text: str
    embedding: list[float] | None = None


# ─── 本地向量存储（基于 numpy，零外部数据库依赖）──────────

class VectorStore:
    """
    轻量级本地向量存储。
    用 numpy 做余弦相似度检索，数据持久化到 JSON 文件。
    适合 < 5 万条的桌面场景。

    如需更大规模，可替换为 ChromaDB / FAISS。
    """

    def __init__(self, config: RAGConfig):
        self.config = config
        self.chunks: list[Chunk] = []
        self._storage_path = os.path.join(config.db_path, "vectors.json")
        self._model = None  # lazy load sentence-transformers
        self._ensure_dir()
        self._load()

    def _ensure_dir(self):
        os.makedirs(self.config.db_path, exist_ok=True)

    # ── Embedding 模型 ───────────────────────────

    def _get_model(self):
        """
        延迟加载 sentence-transformers 模型。

        local_files_only=True：只使用本地已缓存的模型。
        否则首次调用会联网下载模型，在无外网环境下会导致界面长时间卡死；
        模型缺失或依赖未安装时统一降级为哈希伪向量，保证离线可用。
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"[RAG] 加载 Embedding 模型: {self.config.embedding_model}")
                self._model = SentenceTransformer(
                    self.config.embedding_model, local_files_only=True)
                print("[RAG] Embedding 模型加载完成")
            except ImportError:
                print("[RAG] ⚠️ sentence-transformers 未安装，使用哈希伪向量（离线降级）")
                self._model = "hash_fallback"
            except Exception as e:
                print(f"[RAG] ⚠️ 本地无可用模型（{type(e).__name__}），"
                      f"使用哈希伪向量（离线降级）")
                self._model = "hash_fallback"
        return self._model

    def _embed(self, text: str) -> list[float]:
        """文本向量化"""
        model = self._get_model()
        if model == "hash_fallback":
            return self._hash_embed(text)
        return model.encode(text, normalize_embeddings=True).tolist()

    def _hash_embed(self, text: str) -> list[float]:
        """哈希伪向量（零依赖降级方案）"""
        import hashlib
        dim = 384
        vec = [0.0] * dim
        for i in range(len(text) - 2):
            h = hashlib.md5(text[i:i + 3].encode()).hexdigest()
            idx = int(h[:8], 16) % dim
            sign = 1 if int(h[8:9], 16) % 2 == 0 else -1
            vec[idx] += sign
        norm = sum(x * x for x in vec) ** 0.5
        return [x / norm for x in vec] if norm > 0 else vec

    # ── 文本分块 ─────────────────────────────────

    def split_text(self, text: str) -> list[str]:
        """按 chunk_size 分块，带重叠"""
        size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        chunks = []
        i = 0
        while i < len(text):
            end = min(i + size, len(text))
            chunks.append(text[i:end])
            if end >= len(text):
                break
            i += size - overlap
        return chunks

    # ── 导入文档 ─────────────────────────────────

    def add_document(self, text: str, source: str = "user") -> int:
        """分块 → 向量化 → 存储，返回新增块数"""
        text_chunks = self.split_text(text)
        for i, chunk_text in enumerate(text_chunks):
            embedding = self._embed(chunk_text)
            chunk = Chunk(
                id=f"{source}_{len(self.chunks)}_{i}",
                source=source,
                text=chunk_text,
                embedding=embedding,
            )
            self.chunks.append(chunk)
        self._save()
        return len(text_chunks)

    def add_file(self, file_path: str) -> int:
        """从文件导入知识库"""
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return self.add_document(text, source=os.path.basename(file_path))

    # ── 语义检索 ─────────────────────────────────

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """余弦相似度检索"""
        top_k = top_k or self.config.top_k
        if not self.chunks:
            return []

        q_vec = self._embed(query)
        results = []
        for chunk in self.chunks:
            if chunk.embedding is None:
                continue
            sim = self._cosine_similarity(q_vec, chunk.embedding)
            results.append({
                "id": chunk.id,
                "source": chunk.source,
                "text": chunk.text,
                "score": round(sim, 4),
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── 持久化 ───────────────────────────────────

    def _save(self):
        data = []
        for c in self.chunks:
            data.append({
                "id": c.id,
                "source": c.source,
                "text": c.text,
                "embedding": c.embedding,
            })
        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def _load(self):
        if not os.path.exists(self._storage_path):
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                self.chunks.append(Chunk(
                    id=item["id"],
                    source=item["source"],
                    text=item["text"],
                    embedding=item.get("embedding"),
                ))
            print(f"[RAG] 已加载 {len(self.chunks)} 个知识块")
        except Exception as e:
            print(f"[RAG] 加载失败: {e}")

    def get_stats(self) -> dict:
        return {"total_chunks": len(self.chunks)}


# ─── LLM 客户端 ──────────────────────────────────────────

class LLMClient:
    """
    大语言模型流式对话客户端。
    支持 OpenAI 兼容 API，通过 EventBus 实时推送 token。
    """

    def __init__(self, config: LLMConfig, bus: EventBus, vector_store: VectorStore):
        self.config = config
        self.bus = bus
        self.vector_store = vector_store
        self.chat_history: list[dict] = []
        self.max_history = 20

    def chat_stream(self, user_input: str, context: str = "") -> str:
        """
        完整 RAG + LLM 流式对话流程。

        1. 向量检索相关知识
        2. 组装带上下文的 prompt
        3. 流式调用 LLM API
        4. 通过 EventBus 逐 token 推送

        返回完整回复文本。
        """
        # 保存用户消息
        self.chat_history.append({"role": "user", "content": user_input})
        self.bus.emit("llm.user_message", {"text": user_input})

        # RAG 检索
        ref_text = ""
        refs = self.vector_store.search(user_input)
        if refs and refs[0]["score"] > self.vector_store.config.score_threshold:
            ref_text = "\n\n【参考知识】\n" + "\n---\n".join(r["text"] for r in refs)

        # 组装消息
        system_content = self.config.system_prompt
        if context:
            system_content += f"\n\n{context}"
        if ref_text:
            system_content += ref_text

        messages = [{"role": "system", "content": system_content}]
        messages.extend(self.chat_history[-self.max_history:])

        # 流式调用
        full_reply: list[str] = []
        try:
            resp = requests.post(
                self.config.api_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "max_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                    "stream": True,
                },
                stream=True,
                timeout=60,
            )
            resp.raise_for_status()

            # 通知开始流式输出
            self.bus.emit("llm.stream_start", {})

            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data = line_str[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"]
                        token = delta.get("content", "")
                        if token:
                            full_reply.append(token)
                            self.bus.emit("llm.stream_token", {"token": token})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        except requests.RequestException as e:
            err = f"\n⚠️ API 调用失败: {e}"
            full_reply.append(err)
            self.bus.emit("llm.stream_token", {"token": err})

        # 收尾
        reply_text = "".join(full_reply)
        self.chat_history.append({"role": "assistant", "content": reply_text})
        self.bus.emit("llm.stream_end", {"full_text": reply_text})

        return reply_text

    def chat_async(self, user_input: str, context: str = ""):
        """在后台线程中执行流式对话"""
        threading.Thread(
            target=self.chat_stream,
            args=(user_input, context),
            daemon=True,
            name="LLMChat",
        ).start()


# ─── 独立演示入口 ─────────────────────────────────────────
# 说明：本模块是可选的知识库扩展，主程序默认不加载。
# 运行 python rag_engine.py 可离线验证「分块 → 向量化 → 检索」流程。

if __name__ == "__main__":
    from config import RAGConfig

    bus = EventBus()
    store = VectorStore(RAGConfig())

    added = store.add_document(
        "桌面宠物是常驻桌面的小助手，可以查询天气、监控系统状态、进行 AI 对话。\n"
        "它支持 DeepSeek、OpenAI、豆包、通义千问、Kimi 等多个 AI 模型。\n"
        "系统监控模块会采集 CPU、内存、磁盘和网络的使用情况。",
        source="demo",
    )
    print(f"已导入 {added} 个知识块，当前共 {store.get_stats()['total_chunks']} 块")

    for query in ["怎么查询天气", "支持哪些 AI 模型"]:
        print(f"\n查询: {query}")
        for r in store.search(query):
            print(f"  [{r['score']:.3f}] {r['text'][:36].strip()}...")
