import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, List

import numpy as np
import pipmaster as pm

from ..base import BaseVectorStorage
from ..utils import compute_mdhash_id, logger
from ..kg.shared_storage import get_data_init_lock, get_storage_lock

if not pm.is_installed("pinecone"):
    pm.install("pinecone")

from pinecone import Pinecone  # type: ignore


ID_FIELD = "id"
CREATED_AT_FIELD = "created_at"


def _compute_storage_id(original_id: str, workspace: str) -> str:
    """Compute a stable storage ID for Pinecone based on original id and workspace."""
    # Use general mdhash to avoid special formatting requirements
    return compute_mdhash_id(original_id, prefix=workspace)


@dataclass
class PineconeVectorDBStorage(BaseVectorStorage):
    """LightRAG Pinecone vector storage adapter.

    This adapter uses a single Pinecone index (provided by `PINECONE_URL`) and
    separates different logical stores via Pinecone namespaces. Each LightRAG
    vector store instance uses namespace pattern: `<workspace>_<namespace>`.
    """

    def __post_init__(self):
        kwargs = self.global_config.get("vector_db_storage_cls_kwargs", {})
        cosine_threshold = kwargs.get("cosine_better_than_threshold")
        if cosine_threshold is None:
            raise ValueError(
                "cosine_better_than_threshold must be specified in vector_db_storage_cls_kwargs"
            )
        self.cosine_better_than_threshold = float(cosine_threshold)

        # Pinecone uses index-level host endpoint
        self._api_key = os.environ.get("PINECONE_API_KEY")
        self._host = os.environ.get("PINECONE_URL")
        if not self._api_key or not self._host:
            raise RuntimeError("Missing Pinecone config: set PINECONE_API_KEY and PINECONE_URL")

        # Namespace per workspace+store for isolation
        self._namespace = f"{self.workspace}_{self.namespace}" if self.workspace else self.namespace
        self._pc = None
        self._index = None
        self._initialized = False
        self._max_batch_size = self.global_config.get("embedding_batch_num", 16)

    async def initialize(self):
        async with get_data_init_lock():
            if self._initialized:
                return
            try:
                if self._pc is None:
                    self._pc = Pinecone(api_key=self._api_key)
                if self._index is None:
                    # Connect directly to index via host endpoint
                    self._index = self._pc.Index(host=self._host)
                self._initialized = True
                logger.info(f"[{self.workspace}] Pinecone namespace '{self._namespace}' initialized")
            except Exception as e:
                logger.error(f"[{self.workspace}] Failed to initialize Pinecone index: {e}")
                raise

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        if not data:
            return
        current_time = int(time.time())

        list_data = [
            {
                ID_FIELD: k,
                CREATED_AT_FIELD: current_time,
                **{k1: v1 for k1, v1 in v.items() if k1 in self.meta_fields},
            }
            for k, v in data.items()
        ]
        contents = [v["content"] for v in data.values()]
        batches = [
            contents[i : i + self._max_batch_size]
            for i in range(0, len(contents), self._max_batch_size)
        ]

        embedding_tasks = [self.embedding_func(batch) for batch in batches]
        embeddings_list = await asyncio.gather(*embedding_tasks)
        embeddings = np.concatenate(embeddings_list)

        vectors = []
        for i, d in enumerate(list_data):
            storage_id = _compute_storage_id(d[ID_FIELD], self.workspace)
            # Pinecone expects list of floats for values
            vec = embeddings[i]
            if isinstance(vec, np.ndarray):
                vec = vec.tolist()
            vectors.append({"id": storage_id, "values": vec, "metadata": d})

        try:
            self._index.upsert(vectors=vectors, namespace=self._namespace)
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone upsert error in {self.namespace}: {e}")
            raise

    async def query(
        self, query: str, top_k: int, query_embedding: list[float] = None
    ) -> list[dict[str, Any]]:
        if query_embedding is not None:
            embedding = query_embedding
        else:
            embedding_result = await self.embedding_func([query], _priority=5)
            embedding = embedding_result[0]

        try:
            res = self._index.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True,
                namespace=self._namespace,
            )
            matches = res.matches or []
            # Filter by cosine threshold
            filtered = [m for m in matches if (m.score or 0) >= self.cosine_better_than_threshold]
            return [
                {**(m.metadata or {}), "distance": m.score, CREATED_AT_FIELD: (m.metadata or {}).get(CREATED_AT_FIELD)}
                for m in filtered
            ]
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone query error in {self.namespace}: {e}")
            raise

    async def index_done_callback(self) -> None:
        # Pinecone persists automatically
        pass

    async def delete(self, ids: List[str]) -> None:
        if not ids:
            return
        try:
            storage_ids = [_compute_storage_id(i, self.workspace) for i in ids]
            self._index.delete(ids=storage_ids, namespace=self._namespace)
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone delete error in {self.namespace}: {e}")

    async def delete_entity(self, entity_name: str) -> None:
        try:
            storage_id = _compute_storage_id(entity_name, self.workspace)
            self._index.delete(ids=[storage_id], namespace=self._namespace)
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone delete_entity error: {e}")

    async def delete_entity_relation(self, entity_name: str) -> None:
        try:
            # Delete relations by metadata filter on src_id/tgt_id
            self._index.delete(
                filter={"$or": [{"src_id": entity_name}, {"tgt_id": entity_name}]},
                namespace=self._namespace,
            )
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone delete_entity_relation error: {e}")

    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        try:
            storage_id = _compute_storage_id(id, self.workspace)
            res = self._index.fetch(ids=[storage_id], namespace=self._namespace)
            vec = res.vectors.get(storage_id)
            if not vec:
                return None
            md = dict(vec.metadata or {})
            if CREATED_AT_FIELD not in md:
                md[CREATED_AT_FIELD] = None
            return md
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone get_by_id error: {e}")
            return None

    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        try:
            storage_ids = [_compute_storage_id(i, self.workspace) for i in ids]
            res = self._index.fetch(ids=storage_ids, namespace=self._namespace)
            ordered = []
            for sid in storage_ids:
                vec = res.vectors.get(sid)
                if not vec:
                    ordered.append(None)
                else:
                    md = dict(vec.metadata or {})
                    if CREATED_AT_FIELD not in md:
                        md[CREATED_AT_FIELD] = None
                    ordered.append(md)
            return ordered  # type: ignore
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone get_by_ids error: {e}")
            return []

    async def get_vectors_by_ids(self, ids: list[str]) -> dict[str, list[float]]:
        if not ids:
            return {}
        try:
            storage_ids = [_compute_storage_id(i, self.workspace) for i in ids]
            res = self._index.fetch(ids=storage_ids, namespace=self._namespace)
            out: dict[str, list[float]] = {}
            for orig_id, sid in zip(ids, storage_ids):
                vec = res.vectors.get(sid)
                if vec and vec.values is not None:
                    vals = vec.values
                    if isinstance(vals, np.ndarray):
                        vals = vals.tolist()
                    out[orig_id] = vals  # type: ignore
            return out
        except Exception as e:
            logger.error(f"[{self.workspace}] Pinecone get_vectors_by_ids error: {e}")
            return {}

    async def drop(self) -> dict[str, str]:
        async with get_storage_lock():
            try:
                # Delete all vectors in namespace
                self._index.delete(delete_all=True, namespace=self._namespace)
                logger.info(
                    f"[{self.workspace}] Dropped all data in Pinecone namespace {self._namespace}"
                )
                return {"status": "success", "message": "data dropped"}
            except Exception as e:
                logger.error(
                    f"[{self.workspace}] Error dropping Pinecone namespace {self._namespace}: {e}"
                )
                return {"status": "error", "message": str(e)}