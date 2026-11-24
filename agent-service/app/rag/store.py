"""Persistent local Chroma index with explicit Chinese BGE embeddings and provenance."""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL = 'BAAI/bge-small-zh-v1.5'
COLLECTION = 'bankpilot_public_finance_v1'
ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'knowledge' / 'approved_sources.json'
INDEX = Path(os.getenv('BANKPILOT_RAG_DIR', str(ROOT / 'agent-service' / 'data' / 'rag_chroma')))


class RagNotReady(RuntimeError):
    pass


def corpus_hash(path: Path = CORPUS) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL, device='cpu')


def embed(texts: list[str], *, queries: bool = False) -> list[list[float]]:
    values = [('为这个句子生成表示以用于检索相关文章：' + t) if queries else t for t in texts]
    vectors = embedding_model().encode(values, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def client():
    import chromadb
    INDEX.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(INDEX.resolve()))


def load_collection():
    # Do not let Chroma auto-create an empty collection during queries.
    col = client().get_collection(COLLECTION, embedding_function=None)
    meta = col.metadata or {}
    if meta.get('embedding_model') != MODEL or meta.get('corpus_sha256') != corpus_hash():
        raise RagNotReady('知识索引模型或资料版本不匹配，请重新执行构建脚本')
    if col.count() < 1:
        raise RagNotReady('知识索引为空，请先构建')
    return col


def build_index(*, rebuild: bool = False, corpus_path: Path = CORPUS) -> dict[str, Any]:
    import chromadb
    from pathlib import Path
    # Import the source validator from the checked-in corpus directory.
    import sys
    sys.path.insert(0, str(ROOT / 'knowledge'))
    from validate_sources import validate_sources
    sources = validate_sources(corpus_path)
    fingerprint = corpus_hash(corpus_path)
    database = client()
    try:
        old = database.get_collection(COLLECTION, embedding_function=None)
    except (ValueError, chromadb.errors.NotFoundError):
        old = None
    if old is not None:
        if old.metadata and old.metadata.get('embedding_model') == MODEL and old.metadata.get('corpus_sha256') == fingerprint and old.count() > 0:
            return {'sources': len(sources), 'chunks': old.count(), 'model': MODEL, 'reused': True}
        if not rebuild:
            raise RagNotReady('本地索引存在旧版本，请先人工核对，再使用 --rebuild 明确重建')
        database.delete_collection(COLLECTION)
    col = database.create_collection(
        COLLECTION,
        embedding_function=None,
        metadata={'embedding_model': MODEL, 'corpus_sha256': fingerprint, 'scope': 'PUBLIC_OFFICIAL'},
        configuration={'hnsw': {'space': 'cosine'}},
    )
    docs, ids, metas = [], [], []
    for src in sources:
        for section in src['sections']:
            chunk_id = hashlib.sha256(f"{src['source_id']}:{section['section']}".encode()).hexdigest()[:32]
            ids.append(chunk_id)
            docs.append(section['text'])
            metas.append({k: str(src[k]) for k in ('source_id', 'title', 'issuer', 'url', 'published_at', 'checked_at', 'scope', 'category')} | {'section': section['section']})
    vectors = embed(docs)
    col.add(ids=ids, documents=docs, metadatas=metas, embeddings=vectors)
    return {'sources': len(sources), 'chunks': len(docs), 'model': MODEL, 'reused': False}


def search(question: str, *, top_k: int = 3, min_similarity: float | None = None) -> list[dict]:
    from .policy import validate_public_query
    q = validate_public_query(question)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 5:
        raise ValueError('top_k must be 1..5')
    threshold = float(os.getenv('BANKPILOT_RAG_MIN_SIMILARITY', '0.68')) if min_similarity is None else min_similarity
    if not 0 <= threshold <= 1:
        raise ValueError('similarity threshold must be 0..1')
    col = load_collection()
    result = col.query(query_embeddings=embed([q], queries=True), n_results=min(top_k, col.count()),
                       include=['documents', 'metadatas', 'distances'], where={'scope': 'PUBLIC_OFFICIAL'})
    hits = []
    for doc_id, content, meta, distance in zip(result['ids'][0], result['documents'][0],
                                                result['metadatas'][0], result['distances'][0]):
        score = max(0.0, min(1.0, 1.0 - float(distance)))
        if score < threshold:
            continue
        if meta.get('scope') != 'PUBLIC_OFFICIAL':
            continue
        hits.append({'chunkId': doc_id, 'snippet': content, 'similarity': round(score, 4),
                     'sourceId': meta['source_id'], 'title': meta['title'], 'issuer': meta['issuer'],
                     'url': meta['url'], 'section': meta['section'], 'publishedAt': meta['published_at'],
                     'checkedAt': meta['checked_at']})
    return hits
