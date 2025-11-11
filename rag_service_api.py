import os
import json
import asyncio
from typing import List, Optional, Dict, Any
import numpy as np
from datetime import datetime
try:
    # Lightweight .env loader so you can configure the service via a local .env file
    # OS env vars always take precedence over .env entries when override=False
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.environ.get("DOTENV_PATH", ".env"), override=False)
except Exception:
    # If python-dotenv is not installed, simply skip; service will still read OS env vars
    pass

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi import Body, Query
from fastapi import Request
from pydantic import BaseModel

# Optional installer for runtime dependencies
try:
    import pipmaster as pm  # type: ignore
except Exception:
    pm = None

# Try to import watchdog for directory watching; install if missing
WATCHDOG_AVAILABLE = False
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    try:
        if pm is not None:
            pm.install("watchdog")
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            WATCHDOG_AVAILABLE = True
    except Exception:
        WATCHDOG_AVAILABLE = False

# HTTP client for callbacks
HTTPX_AVAILABLE = False
try:
    import httpx
    HTTPX_AVAILABLE = True
except Exception:
    try:
        if pm is not None:
            pm.install("httpx")
            import httpx
            HTTPX_AVAILABLE = True
    except Exception:
        HTTPX_AVAILABLE = False

# Optional: Qdrant client for admin operations
QDRANT_CLIENT_AVAILABLE = False
try:
    from qdrant_client import QdrantClient, models  # type: ignore
    QDRANT_CLIENT_AVAILABLE = True
except Exception:
    try:
        if pm is not None:
            pm.install("qdrant-client")
            from qdrant_client import QdrantClient, models  # type: ignore
            QDRANT_CLIENT_AVAILABLE = True
    except Exception:
        QDRANT_CLIENT_AVAILABLE = False

from lightrag import LightRAG
from lightrag.base import QueryParam
from lightrag.utils import EmbeddingFunc
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.kg.shared_storage import initialize_pipeline_status
from ragAnything import RAGAnything


# -----------------------------
# Configuration (env-driven)
# -----------------------------
# Separate chat and embedding providers
CHAT_API_KEY = (
    os.environ.get("CHAT_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("LLM_BINDING_API_KEY")
)
CHAT_BASE_URL = (
    os.environ.get("CHAT_BASE_URL")
    or os.environ.get("OPENAI_BASE_URL")
    or os.environ.get("LLM_BINDING_HOST")
)

EMBED_API_KEY = os.environ.get("EMBED_API_KEY") or CHAT_API_KEY
EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL") or CHAT_BASE_URL

WORKING_DIR = os.environ.get("LIGHTRAG_WORKING_DIR", "d:/yuki/LightRAG/existing_lightrag_storage")
WORKSPACE = os.environ.get("WORKSPACE", "hire")
VERSION = os.environ.get("SERVICE_VERSION", "1.0.3")

# Qdrant config (required for external vector DB)
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
COSINE_THRESHOLD = float(os.environ.get("COSINE_THRESHOLD", "0.2"))
DEFAULT_IMPORT_DIR = os.environ.get("DEFAULT_IMPORT_DIR", "d:/yuki/LightRAG/hire_document")
# 上传保存目录，默认指向 hire_document，可用环境变量覆盖
UPLOAD_TARGET_DIR = os.path.normpath(os.environ.get("UPLOAD_TARGET_DIR", "d:/yuki/LightRAG/hire_document"))

# 目录监听配置（可选）
FILE_WATCH_ENABLED = os.environ.get("FILE_WATCH_ENABLED", "true").lower() == "true"
FILE_WATCH_EXTS = set([s.strip().lower() for s in os.environ.get("FILE_WATCH_EXTS", ".pdf,.md,.docx").split(",") if s.strip()])
FILE_WATCH_RECURSIVE = os.environ.get("FILE_WATCH_RECURSIVE", "true").lower() == "true"
FILE_WATCH_DEBOUNCE_MS = int(os.environ.get("FILE_WATCH_DEBOUNCE_MS", "1000"))

# User-specified models
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen3-vl-plus")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-large")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "3072"))
# 可选：自动探测嵌入维度（默认关闭以尊重显式配置）
EMBED_DIM_AUTODETECT = os.environ.get("EMBED_DIM_AUTODETECT", "false").lower() == "true"

if not CHAT_API_KEY:
    raise RuntimeError(
        "Missing chat API key: set CHAT_API_KEY (or OPENAI_API_KEY/LLM_BINDING_API_KEY)."
    )

# Qdrant URL is required when selecting Qdrant storage (API key optional depending on endpoint)
if not QDRANT_URL:
    raise RuntimeError(
        "Missing Qdrant config: set QDRANT_URL (and QDRANT_API_KEY if required by your endpoint)."
    )


# -----------------------------
# App and global instances
# -----------------------------
app = FastAPI(title="LightRAG/RAGAnything Service")

rag_anything: Optional[RAGAnything] = None
lightrag_instance: Optional[LightRAG] = None

# Watcher runtime state
observer_instance: Optional[Observer] = None
_watcher_seen: set[str] = set()
_app_loop: Optional[asyncio.AbstractEventLoop] = None


# -----------------------------
# Middleware: enforce UTF-8 for JSON responses
# -----------------------------
@app.middleware("http")
async def enforce_utf8_charset(request, call_next):
    response = await call_next(request)
    ct = response.headers.get("content-type")
    if ct and "application/json" in ct and "charset" not in ct:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


# -----------------------------
# Pydantic models
# -----------------------------
class IngestRequest(BaseModel):
    file_paths: Optional[List[str]] = None  # optional local file paths
    output_dir: Optional[str] = "./output"


class QueryRequest(BaseModel):
    question: str
    mode: Optional[str] = "hybrid"  # local|global|hybrid|naive|mix|bypass


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 20


class ResetQdrantRequest(BaseModel):
    # Safety switch: must set confirm=true to proceed
    confirm: bool = False
    # If true, recreate collections immediately with current EMBED_DIM
    recreate: bool = False
    # Optional: specify target collections; defaults to all LightRAG collections
    collections: Optional[List[str]] = None


# -----------------------------
# Helper to build instances
# -----------------------------
async def _embed_and_check(texts: List[str]) -> np.ndarray:
    """Call the embedding provider and ensure returned vector dims match EMBED_DIM.

    If the provider dimension differs from EMBED_DIM, optionally coerce by
    trimming or zero-padding when EMBED_DIM_COERCE=true in environment.
    """
    # The underlying OpenAI-compatible embed function is async; await its result
    vectors = await openai_embed(
        texts,
        model=EMBED_MODEL,
        api_key=EMBED_API_KEY,
        base_url=EMBED_BASE_URL,
    )

    # Whether to coerce dimension mismatches instead of failing
    EMBED_DIM_COERCE = os.environ.get("EMBED_DIM_COERCE", "false").lower() == "true"

    # Preferred path: numpy ndarray with shape (n, dim)
    if hasattr(vectors, "shape") and len(vectors.shape) == 2:
        dim = int(vectors.shape[1])
        if dim != EMBED_DIM:
            if EMBED_DIM_COERCE:
                # Coerce by trimming or zero-padding
                if dim > EMBED_DIM:
                    vectors = vectors[:, :EMBED_DIM]
                else:
                    pad_width = ((0, 0), (0, EMBED_DIM - dim))
                    vectors = np.pad(vectors, pad_width, mode="constant")
            else:
                raise RuntimeError(
                    f"Embedding dimension mismatch: configured EMBED_DIM={EMBED_DIM}, got {dim} from model '{EMBED_MODEL}'. "
                    "Set EMBED_DIM to match the model, recreate Qdrant collections, or enable EMBED_DIM_COERCE=true to auto-adjust."
                )
        return vectors

    # Fallback: iterable of vectors → convert to ndarray and validate/adjust
    try:
        vectors = np.array(list(vectors), dtype=float)
        if len(vectors.shape) == 2:
            dim = int(vectors.shape[1])
            if dim != EMBED_DIM:
                if EMBED_DIM_COERCE:
                    if dim > EMBED_DIM:
                        vectors = vectors[:, :EMBED_DIM]
                    else:
                        pad_width = ((0, 0), (0, EMBED_DIM - dim))
                        vectors = np.pad(vectors, pad_width, mode="constant")
                else:
                    raise RuntimeError(
                        f"Embedding dimension mismatch: configured EMBED_DIM={EMBED_DIM}, got {dim} from model '{EMBED_MODEL}'. "
                        "Set EMBED_DIM to match the model, recreate Qdrant collections, or enable EMBED_DIM_COERCE=true to auto-adjust."
                    )
            return vectors
        else:
            raise RuntimeError("Embedding output shape invalid; expected 2D array.")
    except TypeError:
        raise RuntimeError("Embedding output is not iterable; check embedding provider configuration.")

async def build_instances():
    global rag_anything, lightrag_instance

    # 如启用自动探测，则通过一次嵌入调用获取实际维度以避免 500 错误
    if EMBED_DIM_AUTODETECT:
        try:
            test_vecs = await openai_embed(
                ["维度探测"],
                model=EMBED_MODEL,
                api_key=EMBED_API_KEY,
                base_url=EMBED_BASE_URL,
            )
            if hasattr(test_vecs, "shape") and len(test_vecs.shape) == 2:
                detected_dim = int(test_vecs.shape[1])
                if detected_dim != EMBED_DIM:
                    print(
                        f"[EmbedDim] 自动探测到 {detected_dim}，覆盖原配置 {EMBED_DIM}"
                    )
                    # 更新模块内 EMBED_DIM，使后续 _embed_and_check 与存储一致
                    globals()["EMBED_DIM"] = detected_dim
            else:
                print("[EmbedDim] 自动探测失败：返回形状异常，保留原配置")
        except Exception as e:
            print(f"[EmbedDim] 自动探测异常：{e}，保留原配置 {EMBED_DIM}")

    lightrag_instance = LightRAG(
        working_dir=WORKING_DIR,
        workspace=WORKSPACE,
        # Switch external vector storage to Qdrant
        vector_storage="QdrantVectorDBStorage",
        vector_db_storage_cls_kwargs={
            "cosine_better_than_threshold": COSINE_THRESHOLD,
        },
        llm_model_func=lambda prompt, system_prompt=None, history_messages=[], **kwargs: openai_complete_if_cache(
            CHAT_MODEL,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=CHAT_API_KEY,
            base_url=CHAT_BASE_URL,
            **kwargs,
        ),
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBED_DIM,
            func=_embed_and_check,
        ),
    )

    await lightrag_instance.initialize_storages()
    await initialize_pipeline_status()

    rag_anything = RAGAnything(
        lightrag=lightrag_instance,
        vision_model_func=lambda prompt, system_prompt=None, history_messages=[], image_data=None, **kwargs: (
            openai_complete_if_cache(
                # visual branch can reuse chat model name if provider supports images; else fallback to text-only
                CHAT_MODEL,
                "",
                system_prompt=None,
                history_messages=[],
                messages=[
                    (
                        {"role": "system", "content": system_prompt}
                        if system_prompt
                        else None
                    ),
                    (
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                                },
                            ],
                        }
                        if image_data
                        else {"role": "user", "content": prompt}
                    ),
                ],
                api_key=CHAT_API_KEY,
                base_url=CHAT_BASE_URL,
                **kwargs,
            )
            if image_data
            else openai_complete_if_cache(
                CHAT_MODEL,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=CHAT_API_KEY,
                base_url=CHAT_BASE_URL,
                **kwargs,
            )
        ),
    )


# -----------------------------
# History utils
# -----------------------------
HISTORY_DIR = os.path.join(os.getcwd(), "history")
HISTORY_FILE = os.path.join(HISTORY_DIR, "query_history.json")


def _ensure_history_dir() -> None:
    try:
        os.makedirs(HISTORY_DIR, exist_ok=True)
    except Exception:
        pass


def _append_history(event_type: str, payload: Dict[str, Any]) -> None:
    """Append an entry to a single JSON file as an array.

    If file does not exist, create it with an array. If exists but invalid,
    recreate safely. Always ensure ASCII disabled for Chinese.
    """
    _ensure_history_dir()
    # Use Asia/Shanghai timezone for timestamps; fallback to +08:00 if zoneinfo unavailable
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        tz = ZoneInfo("Asia/Shanghai")
    except Exception:
        from datetime import timezone, timedelta
        tz = timezone(timedelta(hours=8))
    entry = {
        "timestamp": datetime.now(tz).isoformat(),
        "type": event_type,
        **payload,
    }
    try:
        if os.path.isfile(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
                except Exception:
                    data = []
        else:
            data = []
        data.append(entry)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # Non-blocking: history write failure must not break API
        pass


# -----------------------------
# Directory watcher (auto-ingest on new files)
# -----------------------------
class IngestEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        try:
            if event.is_directory:
                return
            path = os.path.normpath(event.src_path)
            _, ext = os.path.splitext(path)
            if ext.lower() not in FILE_WATCH_EXTS:
                return
            # Debounce simple: avoid double-processing same path
            if path in _watcher_seen:
                return
            _watcher_seen.add(path)
            if rag_anything is not None and _app_loop is not None:
                asyncio.run_coroutine_threadsafe(
                    rag_anything.process_document_complete(file_path=path, output_dir="./output"),
                    _app_loop,
                )
        except Exception:
            # watcher must not crash service
            pass


def _start_watcher():
    """Initialize and start filesystem watcher if enabled and available."""
    global observer_instance
    if observer_instance is not None:
        return
    if not FILE_WATCH_ENABLED or not WATCHDOG_AVAILABLE:
        return
    # Prepare handler and directories
    handler = IngestEventHandler()
    dirs = []
    for d in {os.path.normpath(DEFAULT_IMPORT_DIR), os.path.normpath(UPLOAD_TARGET_DIR)}:
        try:
            if d and os.path.isdir(d):
                dirs.append(d)
        except Exception:
            continue
    if not dirs:
        return
    try:
        observer_instance = Observer()
        for d in dirs:
            observer_instance.schedule(handler, d, recursive=FILE_WATCH_RECURSIVE)
        observer_instance.start()
    except Exception:
        observer_instance = None


def _stop_watcher():
    global observer_instance
    try:
        if observer_instance is not None:
            observer_instance.stop()
            observer_instance.join(timeout=5)
            observer_instance = None
        _watcher_seen.clear()
    except Exception:
        pass
# Lifespan events
# -----------------------------
@app.on_event("startup")
async def on_startup():
    await build_instances()
    # Start directory watcher after instances built
    try:
        global _app_loop
        _app_loop = asyncio.get_running_loop()
        _start_watcher()
    except Exception:
        pass


@app.on_event("shutdown")
async def on_shutdown():
    try:
        _stop_watcher()
    except Exception:
        pass


# -----------------------------
# Helpers
# -----------------------------
def _status(ingested_count: int, errors: List[str]) -> str:
    if ingested_count > 0 and not errors:
        return "success"
    if ingested_count > 0 and errors:
        return "partial"
    return "error"


# Note: JSON-based ingest endpoint removed per privacy requirements.


# -----------------------------
# Ingest auto-scan API (no files, no body)
# -----------------------------
@app.post("/ingest_auto")
async def ingest_auto(callback_url: Optional[str] = Query(None)):
    if rag_anything is None:
        raise HTTPException(status_code=500, detail="Service not initialized")

    saved_paths: List[str] = []
    errors: List[str] = []

    # Scan DEFAULT_IMPORT_DIR
    try:
        if not os.path.isdir(DEFAULT_IMPORT_DIR):
            raise FileNotFoundError("Default import dir not found")
        allowed_ext = {".pdf", ".md", ".docx"}
        for name in os.listdir(DEFAULT_IMPORT_DIR):
            p = os.path.join(DEFAULT_IMPORT_DIR, name)
            _, ext = os.path.splitext(name.lower())
            if os.path.isfile(p) and ext in allowed_ext:
                saved_paths.append(p)
    except Exception as e:
        errors.append("Scan default import dir failed")

    if not saved_paths:
        raise HTTPException(status_code=400, detail={"message": "No files to ingest", "errors": errors})

    # Ingest documents
    ingested: List[str] = []
    for p in saved_paths:
        try:
            await rag_anything.process_document_complete(file_path=p, output_dir="./output")
            ingested.append(p)
        except Exception as e:
            errors.append("Failed to process a file")
    result = {
        "status": _status(len(ingested), errors),
        "ingested_count": len(ingested),
        "errors": errors,
        "scanned_files": saved_paths,
        "ingested_files": ingested,
    }
    _append_history("ingest_auto", {"response": result})
    # Optional callback: POST result to external URL
    if callback_url and HTTPX_AVAILABLE:
        async def _send_callback(url: str, payload: Dict[str, Any]):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.post(url, json=payload, headers={"content-type": "application/json; charset=utf-8"})
            except Exception:
                # Swallow callback errors and continue
                pass
        try:
            asyncio.create_task(_send_callback(callback_url, result))
        except Exception:
            pass
        return result


# -----------------------------
# Query API
# -----------------------------
@app.post("/query")
async def query(req: QueryRequest, callback_url: Optional[str] = Query(None)):
    if rag_anything is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    try:
        result = await rag_anything.aquery(req.question, mode=req.mode)
        response = {"result": result}
        _append_history("query", {"request": req.dict(), "response": response})
        # Optional callback: POST result to external URL
        if callback_url and HTTPX_AVAILABLE:
            async def _send_callback(url: str, payload: Dict[str, Any]):
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        await client.post(url, json=payload, headers={"content-type": "application/json; charset=utf-8"})
                except Exception:
                    # Swallow callback errors and continue
                    pass
            try:
                asyncio.create_task(_send_callback(callback_url, response))
            except Exception:
                pass
        return response
    except Exception as e:
        # Propagate model/provider errors in a controlled manner
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


# -----------------------------
# Ingest upload API (multipart)
# -----------------------------
@app.post("/ingest_upload")
async def ingest_upload(
    files: List[UploadFile] = File(...),
    output_dir: str = Form("./output"),
    callback_url: Optional[str] = Form(None),
):
    if rag_anything is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    # Save uploaded files ONLY to UPLOAD_TARGET_DIR (hire_document)
    uploads_dir = UPLOAD_TARGET_DIR
    os.makedirs(uploads_dir, exist_ok=True)

    saved: List[str] = []
    errors: List[str] = []

    for uf in files:
        try:
            # Sanitize filename
            fname = os.path.basename(uf.filename)
            target_path = os.path.join(uploads_dir, fname)
            content = await uf.read()
            with open(target_path, "wb") as f:
                f.write(content)
            saved.append(target_path)
        except Exception as e:
            errors.append("Save failed for a file")

    ingested: List[str] = []
    for p in saved:
        try:
            await rag_anything.process_document_complete(file_path=p, output_dir=output_dir)
            ingested.append(p)
        except Exception as e:
            errors.append("Process failed for a file")

    result = {
        "status": _status(len(ingested), errors),
        "uploaded_count": len(saved),
        "ingested_count": len(ingested),
        "errors": errors,
        "uploaded_files": saved,
        "ingested_files": ingested,
    }
    _append_history("ingest_upload", {"response": result})
    # Optional callback: POST result to external URL
    if callback_url and HTTPX_AVAILABLE:
        async def _send_callback(url: str, payload: Dict[str, Any]):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    await client.post(url, json=payload, headers={"content-type": "application/json; charset=utf-8"})
            except Exception:
                # Swallow callback errors and continue
                pass
        try:
            asyncio.create_task(_send_callback(callback_url, result))
        except Exception:
            pass
    return result


# -----------------------------
# Vector-only search API
# -----------------------------
@app.post("/search_vectors")
async def search_vectors(req: SearchRequest, callback_url: Optional[str] = Query(None)):
    if lightrag_instance is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    try:
        param = QueryParam(mode="naive", chunk_top_k=req.top_k, top_k=req.top_k)
        data = await lightrag_instance.aquery_data(req.query, param)
        # Only return chunks and references for clarity
        chunks = data.get("data", {}).get("chunks", [])
        references = data.get("data", {}).get("references", [])
        response = {
            "status": data.get("status", "success"),
            "message": data.get("message", ""),
            "chunks": chunks,
            "references": references,
            "metadata": data.get("metadata", {}),
        }
        _append_history("search_vectors", {"request": req.dict(), "response": response})
        # Optional callback: POST result to external URL
        if callback_url and HTTPX_AVAILABLE:
            async def _send_callback(url: str, payload: Dict[str, Any]):
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        await client.post(url, json=payload, headers={"content-type": "application/json; charset=utf-8"})
                except Exception:
                    # Swallow callback errors and continue
                    pass
            try:
                asyncio.create_task(_send_callback(callback_url, response))
            except Exception:
                pass
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {e}")


# -----------------------------
# Callback receiver endpoints
# -----------------------------
@app.post("/ingest_callback")
async def ingest_callback(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    # Persist callback payload for auditing
    try:
        _append_history("callback_ingest", {"payload": payload})
    except Exception:
        pass
    return {"status": "ok"}


@app.post("/query_callback")
async def query_callback(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        _append_history("callback_query", {"payload": payload})
    except Exception:
        pass
    return {"status": "ok"}


@app.post("/search_callback")
async def search_callback(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        _append_history("callback_search", {"payload": payload})
    except Exception:
        pass
    return {"status": "ok"}


# -----------------------------
# Admin: reset Qdrant collections (方案A)
# -----------------------------
@app.post("/admin/reset_qdrant")
async def admin_reset_qdrant(req: ResetQdrantRequest = Body(...)):
    """
    删除（并可选重建）LightRAG使用的 Qdrant 集合，使其与当前 EMBED_DIM 对齐。

    注意：该操作会清空向量数据，需要重建索引（/ingest_auto 或 /ingest_upload）。
    """
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Refused: set confirm=true to proceed.")
    if not QDRANT_CLIENT_AVAILABLE:
        raise HTTPException(status_code=500, detail="qdrant-client not available for admin operation")
    if not QDRANT_URL:
        raise HTTPException(status_code=500, detail="Missing QDRANT_URL for admin operation")

    # Default target collections based on LightRAG naming convention
    default_collections = [
        "lightrag_vdb_chunks",
        "lightrag_vdb_entities",
        "lightrag_vdb_relationships",
    ]
    target_collections = req.collections or default_collections

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    results: Dict[str, Any] = {"deleted": {}, "recreated": {}, "embed_dim": EMBED_DIM}

    # Delete existing collections if present
    for name in target_collections:
        try:
            exists = False
            try:
                exists = client.collection_exists(name)
            except Exception:
                exists = False
            if exists:
                client.delete_collection(name)
                results["deleted"][name] = "ok"
            else:
                results["deleted"][name] = "not_found"
        except Exception as e:
            results["deleted"][name] = f"error: {e}"

    # Optionally recreate with current EMBED_DIM
    if req.recreate:
        for name in target_collections:
            try:
                client.create_collection(
                    name,
                    vectors_config=models.VectorParams(
                        size=EMBED_DIM,
                        distance=models.Distance.COSINE,
                    ),
                    hnsw_config=models.HnswConfigDiff(payload_m=16, m=0),
                )
                # Create workspace payload index
                try:
                    client.create_payload_index(
                        collection_name=name,
                        field_name="workspace_id",
                        field_schema=models.KeywordIndexParams(
                            type=models.KeywordIndexType.KEYWORD,
                            is_tenant=True,
                        ),
                    )
                except Exception:
                    pass
                results["recreated"][name] = "ok"
            except Exception as e:
                results["recreated"][name] = f"error: {e}"

    # 提示需要重启服务以确保 LightRAG 内部状态与集合匹配（或继续使用无需重启但需重新索引）
    results["next_steps"] = [
        "如果未选择 recreate=true，请重启服务后再执行索引（ingest），集合会在首次使用时按 EMBED_DIM 自动创建。",
        "如选择了 recreate=true，可以直接执行 /ingest_auto 或 /ingest_upload 重建索引。",
    ]
    _append_history("admin_reset_qdrant", {"request": req.dict(), "response": results})
    return results


# -----------------------------
# Notes
# -----------------------------
# - To run: `uvicorn rag_service_api:app --host 0.0.0.0 --port 8000`
# - Required env vars:
#   CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL
#   EMBED_API_KEY, EMBED_BASE_URL, EMBED_MODEL, EMBED_DIM
#   QDRANT_URL, QDRANT_API_KEY (when using QdrantVectorDBStorage)
# - Optional:
#   COSINE_THRESHOLD, LIGHTRAG_WORKING_DIR, WORKSPACE,
#   EMBED_DIM_AUTODETECT, EMBED_DIM_COERCE,
#   SERVICE_VERSION, DEFAULT_IMPORT_DIR, UPLOAD_TARGET_DIR,
#   FILE_WATCH_ENABLED, FILE_WATCH_EXTS, FILE_WATCH_RECURSIVE, FILE_WATCH_DEBOUNCE_MS
# - Supports: upload PDFs/MD/DOCX (parsed via mineru in RAGAnything), and direct file paths; if none provided, scans DEFAULT_IMPORT_DIR
# - Vector DB: configured to use QdrantVectorDBStorage via env variables