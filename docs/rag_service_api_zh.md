# RAGAnything/LightRAG 服务接口文档（自建 FastAPI）

本接口文档针对仓库根目录下的 `rag_service_api.py` 启动的 FastAPI 服务，区别于 `lightrag/api` 子模块的官方服务接口。本文档涵盖入库（自动扫描/上传）、查询与向量检索等端点，并提供请求示例与返回格式说明。

- 基本地址（本地）：`http://127.0.0.1:8000`
- 基本地址（公网）：`https://unlaunched-cephalothoracic-shenita.ngrok-free.dev`
- 启动命令：`uvicorn rag_service_api:app --host 0.0.0.0 --port 8000`

## 环境与依赖

- 必需环境变量：
  - 聊天模型：`CHAT_API_KEY`, `CHAT_BASE_URL`, `CHAT_MODEL`
  - 嵌入模型：`EMBED_API_KEY`, `EMBED_BASE_URL`, `EMBED_MODEL`, `EMBED_DIM`
  - 外部向量库（Qdrant）：`QDRANT_URL`（必填）, `QDRANT_API_KEY`（若服务端需要鉴权则必填）, `COSINE_THRESHOLD`（可选，默认 `0.2`）
- 可选环境变量：
  - `COSINE_THRESHOLD`, `LIGHTRAG_WORKING_DIR`, `DEFAULT_IMPORT_DIR`, `UPLOAD_TARGET_DIR`, `SERVICE_VERSION`, `WORKSPACE`, `EMBED_DIM_AUTODETECT`, `EMBED_DIM_COERCE`
  - 目录监听（自动入库）：`FILE_WATCH_ENABLED`（默认 `true`）、`FILE_WATCH_EXTS`（默认 `.pdf,.md,.docx`）、`FILE_WATCH_RECURSIVE`（默认 `true`）、`FILE_WATCH_DEBOUNCE_MS`（默认 `1000`）
- 默认工作目录：`./existing_lightrag_storage_openai_3072`（可通过 `LIGHTRAG_WORKING_DIR` 覆盖）
- 上传保存目录：`UPLOAD_TARGET_DIR`（默认：`d:/yuki/LightRAG/hire_document`）
- 默认扫描目录：`DEFAULT_IMPORT_DIR`（默认：`d:/yuki/LightRAG/hire_document`），自动扫描仅处理扩展名：`.pdf`、`.md`、`.docx`

### 极简 .env 示例（OpenAI 兼容接口 + Qdrant，3072 维度嵌入）

```bash
# 统一的 OpenAI 兼容接口（聊天与嵌入共用）
OPENAI_API_KEY=替换为你的API密钥
OPENAI_BASE_URL=https://www.dmxapi.cn/v1
CHAT_MODEL=deepseek-chat

# 嵌入模型（3072 维）
EMBED_MODEL=text-embedding-3-large
EMBED_DIM=3072
EMBED_DIM_AUTODETECT=false
EMBED_DIM_COERCE=false

# Qdrant 服务
QDRANT_URL=替换为你的Qdrant地址  # 例如 http://localhost:6333 或 https://<your-qdrant-host>
QDRANT_API_KEY=如需鉴权则填写，否则留空
COSINE_THRESHOLD=0.2

# 目录（建议使用新的目录以区分 3072 维数据）
LIGHTRAG_WORKING_DIR=./existing_lightrag_storage_openai_3072
UPLOAD_TARGET_DIR=d:/yuki/LightRAG/hire_document
DEFAULT_IMPORT_DIR=d:/yuki/LightRAG/hire_document
FILE_WATCH_ENABLED=true
FILE_WATCH_EXTS=.pdf,.md,.docx
FILE_WATCH_RECURSIVE=true
FILE_WATCH_DEBOUNCE_MS=1000
```

提示：切换嵌入模型或维度（例如从 1024 到 3072）时，请更换或清空 `LIGHTRAG_WORKING_DIR` 并重新入库，避免向量维度不一致导致检索异常；使用 Qdrant 时集合维度在创建时固定，维度变更需删除旧集合或更换命名空间后重建。可选：启用 `EMBED_DIM_AUTODETECT=true` 在启动时自动探测维度，或启用 `EMBED_DIM_COERCE=true` 在维度不一致时自动截断/填充，但最佳实践仍是与集合维度完全一致。

## 公共约定

- 返回内容类型：`application/json; charset=utf-8`
- 出错约定：
  - `400`：无可入库文件、路径不存在等调用问题
  - `422`：请求体验证失败（例如上传字段错误）
  - `500`：服务未初始化或模型/向量库相关内部错误
- 安全建议：如通过 ngrok 暴露公网访问，建议配置 IP 白名单、ngrok 访问保护或在上游网关加鉴权。
- ngrok 公网访问建议在请求头加入：`ngrok-skip-browser-warning: true`。

### 目录监听（可选）

- 行为：服务启动后自动监听 `DEFAULT_IMPORT_DIR` 与 `UPLOAD_TARGET_DIR`，当检测到新文件创建且扩展名匹配时，自动调用解析与入库流程。
- 过滤扩展名：默认 `.pdf`、`.md`、`.docx`（可通过 `FILE_WATCH_EXTS` 配置）。
- 开关：`FILE_WATCH_ENABLED=true|false`（默认启用）。
- 递归监听：`FILE_WATCH_RECURSIVE=true|false`（默认启用，监听子目录）。
- 去抖：`FILE_WATCH_DEBOUNCE_MS` 简单去重与抖动控制（默认 `1000` 毫秒）。

---

## POST /ingest_auto

自动扫描默认目录并入库（无请求体）。

- 查询参数：

  - `callback_url`（可选）：如果提供，服务会在扫描与入库完成后异步向该地址 `POST` 同结构的 JSON 状态，方便调用方自动接收结果。
- 返回：

```json
{
  "status": "success",
  "ingested_count": 2,
  "errors": [],
  "scanned_files": ["d:/yuki/LightRAG/hire_document/a.pdf", "d:/yuki/LightRAG/hire_document/b.pdf"],
  "ingested_files": ["d:/yuki/LightRAG/hire_document/a.pdf", "d:/yuki/LightRAG/hire_document/b.pdf"]
}
```

- 示例：

  - 本地：`curl -X POST "http://127.0.0.1:8000/ingest_auto?callback_url=https://your-host.example.com/ingest_callback"`
  - 公网：`curl -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_auto?callback_url=https://your-host.example.com/ingest_callback"`
- 错误：

  - `400`：`{"message":"No files to ingest","errors":[...]}`

---

## POST /ingest_upload

上传文件并入库（`multipart/form-data`）。字段名必须为 `files`，支持多文件。所有上传文件会保存到 `UPLOAD_TARGET_DIR`（默认 `d:/yuki/LightRAG/hire_document`），随后调用 `process_document_complete` 入库。

- 表单字段：

  - `files`: 文件数组（必须）
  - `output_dir`: 字符串（可选，默认 `./output`）
  - `callback_url`: 字符串（可选）。若提供，服务在完成入库后会异步向该地址 `POST` 一份同结构 JSON 状态，便于对端自动接收结果。
- 返回：

```json
{
  "status": "success",
  "uploaded_count": 1,
  "ingested_count": 1,
  "errors": [],
  "uploaded_files": ["d:/yuki/LightRAG/hire_document/example.pdf"],
  "ingested_files": ["d:/yuki/LightRAG/hire_document/example.pdf"]
}
```

- 示例（Windows 路径注意不要加前导斜杠）：

  - 本地：
    ```bash
    curl -X POST \
      -F "files=@d:/yuki/LightRAG/example.pdf;type=application/pdf" \
      -F "callback_url=https://your-host.example.com/ingest_callback" \
      "http://127.0.0.1:8000/ingest_upload"
    ```
  - 公网：
    ```bash
    curl -X POST \
      -F "files=@d:/yuki/LightRAG/example.pdf;type=application/pdf" \
      -F "callback_url=https://your-host.example.com/ingest_callback" \
      -H "ngrok-skip-browser-warning: true" \
      "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload"
    ```
- Windows 上传示例（PowerShell）

  - PowerShell 7+（支持 `-Form`）：
    ```powershell
    $uri = 'https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload'
    $headers = @{ 'ngrok-skip-browser-warning' = 'true' }
    $form = @{ files = Get-Item 'C:\\path\\example.pdf'; output_dir = './output' }
    $resp = Invoke-WebRequest -Uri $uri -Method Post -Headers $headers -Form $form
    Write-Output $resp.Content
    ```
  - PowerShell 5（不支持 `-Form`，改用 `curl.exe -F`）：
    ```powershell
    curl.exe -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" \
      -H "ngrok-skip-browser-warning: true" \
      -F "files=@C:\\path\\example.pdf;type=application/pdf" \
      -F "output_dir=./output"
    ```
- 常见错误：

  - `422`：`{"detail":[{"loc":["body","files"],"msg":"Field required"}]}`（字段名不是 `files`）

---

## POST /query

RAG 查询接口，支持模式选择。

- 请求体（JSON）：

```json
{
  "question": "请总结上传文档的核心内容",
  "mode": "hybrid"
}
```

- 模式可选值：`local`、`global`、`hybrid`、`naive`、`mix`、`bypass`
- 查询参数：`callback_url`（可选）。若提供，服务会在完成检索后以相同 JSON 结构异步 `POST` 到该地址。
- 返回：

```json
{
  "result": "答案或结构化结果"
}
```

- 示例：
  - 本地：

    ```bash
    curl -X POST "http://127.0.0.1:8000/query?callback_url=https://your-host.example.com/query_callback" \
      -H "Content-Type: application/json" \
      -d "{\"question\":\"请总结上传文档的核心内容\",\"mode\":\"hybrid\"}"
    ```
  - 公网：

    ```bash
    curl -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query?callback_url=https://your-host.example.com/query_callback" \
      -H "Content-Type: application/json; charset=utf-8" \
      -H "ngrok-skip-browser-warning: true" \
      -d "{\"question\":\"请总结上传文档的核心内容\",\"mode\":\"hybrid\"}"
    ```
  - Windows PowerShell 示例（避免转义问题，推荐 `--data-raw` + 单引号）：

    ```powershell
    curl.exe -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" \
      -H "Content-Type: application/json; charset=utf-8" \
      -H "ngrok-skip-browser-warning: true" \
      --data-raw '{"question":"请总结上传文档的核心内容","mode":"bypass"}'
    ```

---

## POST /search_vectors

仅向量检索接口，返回命中的 `chunks` 与 `references`，用于轻量级检索与前端展示。

- 请求体（JSON）：

```json
{
  "query": "关键词",
  "top_k": 5
}
```

- 返回（示例结构）：

```json
{
  "status": "success",
  "message": "",
  "chunks": [ /* 命中片段数组 */ ],
  "references": [ /* 参考信息数组 */ ],
  "metadata": { /* 额外元信息 */ }
}
```

- 字段含义：`chunks` 为检索命中的文档片段，`references` 为片段来源与页码等参考信息。
- 示例：

  - 本地：

    ```bash
    curl -X POST "http://127.0.0.1:8000/search_vectors?callback_url=https://your-host.example.com/search_callback" \
      -H "Content-Type: application/json" \
      -d "{\"query\":\"关键词\",\"top_k\":5}"
    ```
  - 公网：

    ```bash
    curl -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors?callback_url=https://your-host.example.com/search_callback" \
      -H "Content-Type: application/json; charset=utf-8" \
      -H "ngrok-skip-browser-warning: true" \
      -d "{\"query\":\"关键词\",\"top_k\":5}"
    ```
  - Windows PowerShell 示例（推荐 `--data-raw` + 单引号）：

    ```powershell
    curl.exe -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" \
      -H "Content-Type: application/json; charset=utf-8" \
      -H "ngrok-skip-browser-warning: true" \
      --data-raw '{"query":"关键词","top_k":5}'
    ```

---

## 备忘与注意事项

- 上传路径：所有上传文件统一保存到 `UPLOAD_TARGET_DIR`；如未配置则使用默认目录 `d:/yuki/LightRAG/hire_document`。
- 自动扫描扩展名：仅处理 `.pdf`、`.md`、`.docx`。
- 对外暴露：通过 ngrok 暴露公网访问时，请关注安全与带宽限制。
- 依赖初始化：首次启动会初始化若干存储（KV、Qdrant 集合等），启动日志可查看加载进度与状态。
- 回调机制：`callback_url` 为可选参数；回调失败不会影响主请求响应（异步发送且忽略错误）。

### 维度一致性与 Qdrant 集合

- 嵌入向量的维度必须与 Qdrant 集合的维度一致。服务会在嵌入阶段先行校验，维度不一致返回 `500`（包含明确错误信息）；若绕过服务校验直接写入 Qdrant，可能出现 `400 Bad Request: vector dimension error`。
- 本服务已在入库前加入维度校验：当嵌入模型输出维度与 `EMBED_DIM` 不一致时会立即报错；可选地，设置 `EMBED_DIM_COERCE=true` 自动截断或零填充到目标维度。
- 维度变更处理建议：
  - 保持现有集合维度不变：将 `EMBED_MODEL` 与 `EMBED_DIM` 配成一致（例如 `text-embedding-3-large` + `EMBED_DIM=3072`）。
  - 需要改为另一维度：删除或更换命名空间以重建 Qdrant 集合，再重启服务并重新入库。
  - 可启用 `EMBED_DIM_AUTODETECT=true` 在启动时自动探测维度并覆盖配置。
  - 为避免影响旧数据，建议更换 `WORKSPACE` 或 `LIGHTRAG_WORKING_DIR` 来创建新的命名空间与目录。

---

## 常见问题排查

- 422 Unprocessable Entity / JSON decode error：
  - PowerShell 中请用单引号包裹整体 JSON，并使用 `--data-raw`，避免双引号与反斜杠被误解析。
  - 不要在 URL 上使用反引号（`）或错误转义；保持纯文本 URL。
- 中文被替换为 `?`：
  - 明确设置 `Content-Type: application/json; charset=utf-8`。
  - 客户端需以 UTF-8 发送；建议在 PowerShell 中使用 `curl.exe` 或 `Invoke-RestMethod`（PS7）。
- ngrok 浏览器警告页：
  - 添加请求头 `ngrok-skip-browser-warning: true`。
- PowerShell 5 与 7 差异：
  - PS5 的 `Invoke-WebRequest` 不支持 `-Form`；文件上传请使用 `curl.exe -F` 或升级至 PowerShell 7+。
- 历史归档：
  - `query`/`search_vectors` 会记录请求与响应；`ingest_auto`/`ingest_upload` 记录响应。统一写入 `history/query_history.json`（UTF-8，`ensure_ascii=false`），便于审计与回溯。
