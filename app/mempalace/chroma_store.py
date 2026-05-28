from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from app.config import settings

COLLECTION_NAME = "mempalace"

_client = chromadb.PersistentClient(
    path=settings.chroma_path,
    settings=ChromaSettings(anonymized_telemetry=False),
)
_coll = None


def _build_embedding_function() -> OpenAIEmbeddingFunction:
    key = settings.embedding_api_key.strip()
    base = settings.embedding_base_url.strip().rstrip("/")
    model = settings.embedding_model
    if not key:
        raise ValueError("请在 .env 中配置 EMBEDDING_API_KEY。")
    if not base:
        raise ValueError("请在 .env 中配置 EMBEDDING_BASE_URL。")
    if not model:
        raise ValueError("请在 .env 中配置 EMBEDDING_MODEL_NAME。")
    return OpenAIEmbeddingFunction(
        api_key=key,
        api_base=base,
        model_name=model,
        dimensions=settings.embedding_dimensions,
    )


def _init_collection():
    ef = _build_embedding_function()
    try:
        return _client.get_or_create_collection(
            COLLECTION_NAME,
            embedding_function=ef,
        )
    except ValueError as exc:
        if "Embedding function conflict" not in str(exc):
            raise
        try:
            _client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        return _client.create_collection(
            COLLECTION_NAME,
            embedding_function=ef,
        )


def _get_collection():
    global _coll
    if _coll is None:
        _coll = _init_collection()
    return _coll


def add(memory_id: str, text: str, metadata: dict) -> None:
    _get_collection().upsert(ids=[memory_id], documents=[text], metadatas=[metadata])


def search(query: str, k: int = 3, where: dict | None = None):
    res = _get_collection().query(query_texts=[query], n_results=k, where=where or None)
    ids = res["ids"][0]
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    return list(zip(ids, docs, metas))


def delete_by_user(user_id: str) -> None:
    _get_collection().delete(where={"user_id": user_id})
