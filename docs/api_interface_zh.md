# LightRAG 服务 API 接口文档（中文）

本服务封装了两个核心能力：
- 上传文件到现有 LightRAG 存储并完成入库（existing_lightrag_storage）
- 查询向量知识库（纯向量检索）以及综合检索+生成

此外，服务会自动把每次请求与响应写入 `history/query_history.json`（单一 .json 文件，按数组追加），便于审计与回溯。

## 基础信息
- 基础路径：`http://<host>:<port>`（示例：`http://0.0.0.0:8000`）
- 统一返回头：`application/json; charset=utf-8`
 - 工作目录：`LIGHTRAG_WORKING_DIR`（Windows 推荐绝对路径：`d:/yuki/LightRAG/existing_lightrag_storage`）
- 工作空间：`WORKSPACE`（默认：`hire`）

### 环境与依赖（关键变量）
- 嵌入模型与维度：`EMBED_MODEL`, `EMBED_DIM`（必须与向量库集合维度一致）
- 可选：`EMBED_DIM_AUTODETECT`（默认 `false`，启动时自动探测维度）、`EMBED_DIM_COERCE`（默认 `false`，维度不一致时截断/零填充）
- 工作目录：`LIGHTRAG_WORKING_DIR`（示例：`./existing_lightrag_storage_openai_3072` 或 `./existing_lightrag_storage_bge_m3`）
- 工作空间：`WORKSPACE`（默认 `hire`）
- Qdrant：`QDRANT_URL`（必填）、`QDRANT_API_KEY`（如需鉴权）、`COSINE_THRESHOLD`（默认 `0.2`）

 推荐 .env 片段（示例为 3072 维，Windows 路径示例）：
```bash
EMBED_MODEL=text-embedding-3-large
EMBED_DIM=3072
EMBED_DIM_AUTODETECT=false
EMBED_DIM_COERCE=false
LIGHTRAG_WORKING_DIR=d:/yuki/LightRAG/existing_lightrag_storage
WORKSPACE=hire
QDRANT_URL=<your-qdrant-url>
QDRANT_API_KEY=
COSINE_THRESHOLD=0.2
```

维度一致性说明：服务在入库阶段会先行校验嵌入维度；若与 `EMBED_DIM` 不一致，返回 `500` 并给出明确提示。如绕过服务层直接写入 Qdrant，可能出现 `400 Bad Request: vector dimension error`。切换模型或维度时请更换/清空 `LIGHTRAG_WORKING_DIR` 并重建集合（或命名空间）。

已验证可选配置（跨主机/异构环境）：
```bash
EMBED_DIM_AUTODETECT=true
COSINE_THRESHOLD=0.05
```
说明：在无法确定现有集合维度或需要提高召回率时，可开启自动探测并适当降低相似度阈值。仍需确保集合维度与所用嵌入模型一致。

## 健康检查
- 方法：`GET /health`
- 返回：服务版本、工作目录、向量库配置等信息
 - 注意：部分部署可能未暴露 `/health`，若返回 `404` 或 `{"detail":"Not Found"}` 属正常。可直接调用 `/ingest_upload` 或 `/query` 进行连通性校验。

## 文档入库（JSON 文件路径或自动扫描）
### 1) `POST /ingest`
- 说明：基于 JSON 的入库，传入本地文件路径（不支持 multipart）
- 请求体：
```json
{
  "file_paths": ["d:/path/a.pdf", "d:/path/b.pdf"],
  "output_dir": "./output"
}
```
- 返回：已入库的文件路径与错误列表
- 历史归档：自动写入 `history/query_history.json`，类型 `ingest`

### 2) `POST /ingest_auto`
- 说明：自动扫描固定目录 `d:/yuki/LightRAG/hire_document` 并入库
- 请求体：无
- 返回：同上
- 历史归档：自动写入，类型 `ingest_auto`

## 文档入库（文件上传）
### `POST /ingest_upload`
- 说明：通过 multipart 上传文件，服务会保存到固定目录 `d:/yuki/LightRAG/hire_document` 并入库
 - 支持类型：优先支持 PDF；其他类型（如 Markdown）取决于部署的解析/切分插件支持情况。
- 参数：
  - `files`: 多文件（`multipart/form-data`）
  - `output_dir`: 可选，默认 `./output`（`Form` 字段）
- cURL 示例：
```bash
curl -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" \
  -F "files=@d:/docs/a.pdf" \
  -F "files=@d:/docs/b.pdf" \
  -F "output_dir=./output"
```
- 返回：上传数量、入库数量、存储路径与错误列表
- 历史归档：自动写入，类型 `ingest_upload`

## 向量检索（纯向量匹配，不调用 LLM）
### `POST /search_vectors`
- 说明：仅进行向量检索，返回相关的文本 `chunks` 与 `references`
- 请求体：
```json
{
  "query": "谁应聘的职位是新媒体运营",
  "top_k": 20
}
```
- 返回：
```json
{
  "status": "success",
  "message": "",
  "chunks": [
    {
      "content": "...",
      "file_path": "...",
      "chunk_id": "...",
      "reference_id": "..."
    }
  ],
  "references": [
    {
      "reference_id": "1",
      "file_path": "/documents/a.pdf"
    }
  ],
  "metadata": {"query_mode": "naive", "keywords": {"high_level": [], "low_level": []}}
}
```
- 字段含义：`chunks` 为检索命中的文档片段，`references` 为片段来源与页码等参考信息。
- 历史归档：自动写入，类型 `search_vectors`

## 综合检索 + 生成（RAGAnything）
### `POST /query`
- 说明：调用 RAGAnything 的查询（可选模式：`local|global|hybrid|naive|mix|bypass`）
- 请求体：
```json
{
  "question": "谁应聘的职位是新媒体运营",
  "mode": "hybrid"
}
```
- 返回：
```json
{
  "result": "张雷应聘的新媒体运营..."
}
```
- 历史归档：自动写入，类型 `query`

## 历史归档约定
- 路径：`history/query_history.json`
- 结构：单个 `.json` 文件，数组格式，每次调用追加一个对象，包含：
  - `timestamp`: ISO 时间戳
  - `type`: 事件类型，如 `query`、`search_vectors`、`ingest_upload`
  - `request`（如有）：请求参数
  - `response`: 响应数据
- 编码：UTF-8，`ensure_ascii=false`，中文不转义

（面向客户版本已省略 PowerShell 建议、错误管理细节与环境变量说明。）

---
如需扩展：可以为 `/search_vectors` 增加 `namespace/workspace`、`include_chunk_content`、`rerank` 开关等参数，以满足更细粒度的检索需求。

---

## 公网访问（ngrok）与编码注意事项

- 公网地址示例：`https://unlaunched-cephalothoracic-shenita.ngrok-free.dev`
- 通过 ngrok 访问时，建议在请求头中加入：`ngrok-skip-browser-warning: true`，以跳过浏览器警告页（如 `ERR_NGROK_6024`）。
 - 该头的值可为 `true` 或 `1`；只要带上此请求头即可。
- 所有 JSON 请求请使用 `Content-Type: application/json; charset=utf-8`，并确保客户端以 UTF-8 编码发送中文，避免中文被替换为 `?`。
- 历史归档文件写入采用 UTF-8 且 `ensure_ascii=false`，中文不转义，路径：`history/query_history.json`。

## Windows 上传示例（PowerShell 与 cURL）

- PowerShell 7+（Invoke-WebRequest 支持 `-Form`）：
```powershell
 $uri = 'https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload'
$headers = @{ 'ngrok-skip-browser-warning' = 'true' }
$form = @{ files = Get-Item 'C:\path\a.pdf'; output_dir = './output' }
$resp = Invoke-WebRequest -Uri $uri -Method Post -Headers $headers -Form $form
Write-Output $resp.Content
```

- PowerShell 5：请使用 `curl.exe -F`（PS5 的 Invoke-WebRequest 不支持 `-Form`）
- cURL（curl.exe）：
```powershell
curl.exe -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" \
  -H "ngrok-skip-browser-warning: true" \
  -F "files=@C:\path\a.pdf;type=application/pdf" \
  -F "output_dir=./output"
```

## Windows 查询示例（PowerShell 管道）

- PowerShell 7+ 推荐使用管道配合 `--data-binary '@-'` 以避免编码/转义问题：
```powershell
$body = @{ question = '徐中天的工作经历如何'; mode = 'bypass' } | ConvertTo-Json -Compress
$body | curl.exe -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "ngrok-skip-browser-warning: 1" \
  --data-binary "@-"
```

## 常见问题排查

- 422 Unprocessable Entity：检查 JSON 是否合法（PowerShell 中使用 `ConvertTo-Json`），或是否错误地对 URL/引号进行了转义。
- 中文被替换为问号：客户端编码问题。明确设置 `charset=utf-8`，建议使用 `Invoke-RestMethod` 或 `curl.exe --data-binary` 并确保本地文件为 UTF-8。
- ngrok 浏览器警告：添加 `ngrok-skip-browser-warning: true` 请求头或自定义 `User-Agent`。
 - 查询报错 `JSON decode error`：通常是请求体编码或引号转义问题。使用 PowerShell 7 管道 + `--data-binary '@-'`，并设置 `Content-Type: application/json; charset=utf-8`。
 - 查询报错 `expected string or bytes-like object`：可能由检索阶段未命中或服务端解析参数异常引起。先用 `mode: "bypass"` 验证生成能力，再降低 `COSINE_THRESHOLD`（如 `0.05`）、增大 `top_k`，或将中文查询改写为更具体的语义句。
 - `No relevant document chunks found.`：检索未命中。检查嵌入维度与集合是否一致，降低 `COSINE_THRESHOLD`、增大 `top_k`，或按语义改写查询。