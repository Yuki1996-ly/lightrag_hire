# 项目启动指南（按环境分类）

本文档整理当前项目中所有用于启动应用程序的命令与脚本，涵盖根目录自建 FastAPI 服务（`rag_service_api.py`）、官方 LightRAG API 服务（`lightrag/api`）、WebUI、Docker/K8s 与公网暴露（ngrok）。内容包括主启动命令、开发/生产/测试环境启动方式、依赖服务启动顺序、环境变量要求以及常见问题与解决方案。

- 适用系统：Windows（PowerShell）、Linux/Mac（Bash）
- 默认端口：自建服务 `8000`，LightRAG API 服务 `9621`

---

## 主启动命令（总览）

- 自建 FastAPI（RAGAnything/LightRAG 集成）
  - 命令：
    - `uvicorn rag_service_api:app --host 0.0.0.0 --port 8000`
- 适用场景：轻量自建 API，固定上传目录与 Pinecone 外部向量库集成
  - 预期输出（节选）：
    ```text
    INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
    INFO:     Application startup complete.
    ```

- 官方 LightRAG API（单进程开发模式）
  - 命令：
    - `lightrag-server`
    - 或：`uvicorn lightrag.api.lightrag_server:app --reload`
  - 适用场景：提供完整 WebUI、API、Ollama 兼容接口
  - 预期输出（节选）：
    ```text
    Starting Uvicorn server in single-process mode on 0.0.0.0:9621
    LightRAG log file: <...>/lightrag.log
    Server is ready to accept connections! 🚀
    ```

- 官方 LightRAG API（Gunicorn 生产模式）
  - 命令：
    - `lightrag-gunicorn`
    - 或（源码模式）：`python -m lightrag.api.run_with_gunicorn`
  - 适用场景：多进程生产部署，支持 `workers`、`ssl` 等参数
  - 预期输出（节选）：
    ```text
    🚀 Starting LightRAG with Gunicorn
    🔄 Worker management: Gunicorn (workers=4)
    Starting Gunicorn with direct Python API...
    ```

- WebUI（前端）
  - 开发模式：在 `lightrag_webui/` 目录
    - `bun install`
    - `bun run dev`
  - 生产构建（静态产物由 API 服务托管）：
    - `bun run build`

- 公网暴露（ngrok HTTP 隧道到本地 8000）
  - 命令（Windows 示例）：
    - `& 'C:\Users\<you>\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe' http 8000 --config 'D:\yuki\LightRAG\ngrok_v2.yml' --authtoken <YOUR_TOKEN> --log=stdout`
  - 适用场景：临时对外测试、自测接口回调

---

## 开发环境启动（含调试）

### 1) 自建 FastAPI（`rag_service_api.py`）

- 调试模式（自动重载）：
  - `uvicorn rag_service_api:app --host 0.0.0.0 --port 8000 --reload`
- 适用场景与注意事项：
- 需要外部 Pinecone 服务：`PINECONE_API_KEY`、`PINECONE_URL` 必填
  - 上传保存目录可通过 `UPLOAD_TARGET_DIR` 配置（默认：`d:/yuki/LightRAG/hire_document`）
  - 端点说明：参考 `docs/rag_service_api_zh.md`

- 关键环境变量（必须）：
  - 聊天模型：`CHAT_API_KEY`, `CHAT_BASE_URL`, `CHAT_MODEL`
  - 嵌入模型：`EMBED_API_KEY`, `EMBED_BASE_URL`, `EMBED_MODEL`, `EMBED_DIM`
- 外部向量库：`PINECONE_API_KEY`、`PINECONE_URL`
- 可选：`COSINE_THRESHOLD`、`WORKING_DIR`、`UPLOAD_TARGET_DIR`、`DEFAULT_IMPORT_DIR`、`SERVICE_VERSION`、`CHAT_MODEL`、`EMBED_MODEL`、`EMBED_DIM`
 - 目录监听（自动入库）：`FILE_WATCH_ENABLED`、`FILE_WATCH_EXTS`（默认 `.pdf,.md,.docx`）、`FILE_WATCH_RECURSIVE`、`FILE_WATCH_DEBOUNCE_MS`

- 预期输出（节选）：
  ```text
  INFO:     Waiting for application startup.
[hire] Pinecone namespace initialized successfully
[hire] Storages initialized successfully
  INFO:     Application startup complete.
  INFO:     Uvicorn running on http://0.0.0.0:8000
  ```

### 2) 官方 LightRAG API 开发模式

- 单进程开发：
  - `lightrag-server`
  - 或：`uvicorn lightrag.api.lightrag_server:app --reload`
- 前端联调：
  - 在 `lightrag_webui/` 运行 `bun run dev`（默认开发端口）
- 关键环境变量：在项目根目录 `.env` 中配置（从 `env.example` 拷贝）
  - LLM/Embedding 后端：`LLM_BINDING_HOST`、各后端密钥
  - `LIGHTRAG_API_KEY`（启用服务端鉴权）
  - `HOST`、`PORT`（默认 `0.0.0.0:9621`）
  - 可选：`SSL`、`SSL_CERTFILE`、`SSL_KEYFILE`

---

## 生产环境启动

### 1) 官方 LightRAG API（Gunicorn 多进程）

- CLI 启动（推荐）：
  - `lightrag-gunicorn`  
    环境变量控制：`WORKERS`、`HOST`、`PORT`、`LOG_LEVEL`、`TIMEOUT`、`SSL*`
- 源码方式：
  - `python -m lightrag.api.run_with_gunicorn`
- Systemd 服务（Linux）：
  - 参考 `lightrag.service.example`，核心字段：
    - `WorkingDirectory=/path/to/LightRAG`
    - `Environment="PATH=/path/to/venv/bin"`
    - `ExecStart=/path/to/venv/bin/lightrag-gunicorn`（或 `lightrag-server`）
  - 安装命令：
    ```bash
    sudo cp lightrag.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl start lightrag.service
    sudo systemctl enable lightrag.service
    ```

### 2) 自建 FastAPI（`rag_service_api.py`）生产建议

- 单机：
  - `uvicorn rag_service_api:app --host 0.0.0.0 --port 8000 --workers 2`
- 反向代理：
  - 建议前置 Nginx/Traefik，配置 `/health` 免鉴权，其他端点加上网关鉴权（如 IP 白名单 或 API-Key）

### 3) Docker Compose

- 在项目根目录：
  ```bash
  cp env.example .env
  docker compose up
  ```

### 4) Kubernetes（Helm）

- 参考 `k8s-deploy/lightrag/`，按 `README.md` 部署。需准备存储与外部 LLM/向量服务。

---

## 测试环境启动

### 1) 轻量测试（自建 FastAPI）

- 建议在本地回环与独立端口运行：
  ```powershell
  $env:CHAT_API_KEY = "<deepseek-key>"
  $env:CHAT_BASE_URL = "https://api.deepseek.com"
  $env:CHAT_MODEL = "deepseek-chat"

  $env:EMBED_API_KEY = "<embed-key>"
  $env:EMBED_BASE_URL = "https://www.dmxapi.com/v1"
  $env:EMBED_MODEL = "text-embedding-3-large"
  $env:EMBED_DIM = "3072"

$env:PINECONE_API_KEY = "<pinecone-key>"
$env:PINECONE_URL = "https://YOUR-INDEX.svc.YOUR-REGION.pinecone.io"
  uvicorn rag_service_api:app --host 127.0.0.1 --port 8001 --reload
  ```
- 适用场景：接口联调、端到端上传/查询验证（可配合 ngrok 暴露临时公网）

### 2) 官方 LightRAG API 测试服务

- 以不同端口与临时工作目录运行：
  ```bash
  HOST=127.0.0.1 PORT=9622 WORKING_DIR=./rag_storage_test lightrag-server
  ```
- 或：
  ```bash
  uvicorn lightrag.api.lightrag_server:app --host 127.0.0.1 --port 9622 --reload
  ```

---

## 依赖服务启动顺序

- 自建 FastAPI（`rag_service_api.py`）
- 1) 配置并验证环境变量（至少 `CHAT_*`、`EMBED_*` 与 `PINECONE_API_KEY/PINECONE_URL`）
- 2) 确保 Pinecone 服务可达（确保已创建索引并获取 Host URL）
  - 3) 启动应用（`uvicorn rag_service_api:app ...`）
  - 4) 可选：启动 ngrok 暴露公网地址

- 官方 LightRAG API
  - 1) 拷贝并配置 `.env`（`cp env.example .env`）
  - 2) 构建 WebUI 产物（生产部署）：`bun run build`
  - 3) 启动 API（开发：`lightrag-server`；生产：`lightrag-gunicorn`）
- 4) 可选：外部 LLM/Embedding 服务（Ollama、Azure/OpenAI 等）与外部向量服务（如 Pinecone）

---

## 环境变量配置要求（摘要）

- 自建 FastAPI（必须）
  - `CHAT_API_KEY`, `CHAT_BASE_URL`, `CHAT_MODEL`
  - `EMBED_API_KEY`, `EMBED_BASE_URL`, `EMBED_MODEL`, `EMBED_DIM`
- `PINECONE_API_KEY`、`PINECONE_URL`
- 自建 FastAPI（常见可选）
- `COSINE_THRESHOLD`, `WORKING_DIR`, `UPLOAD_TARGET_DIR`, `DEFAULT_IMPORT_DIR`, `SERVICE_VERSION`, `CHAT_MODEL`, `EMBED_MODEL`, `EMBED_DIM`
 - `FILE_WATCH_ENABLED`, `FILE_WATCH_EXTS`, `FILE_WATCH_RECURSIVE`, `FILE_WATCH_DEBOUNCE_MS`
- 官方 LightRAG API（在 `.env` 中）
  - `LLM_BINDING_HOST` 与相关密钥
  - `LIGHTRAG_API_KEY`（启用鉴权）
  - `HOST`, `PORT`, `SSL`, `SSL_CERTFILE`, `SSL_KEYFILE`

---

## 常见启动问题与解决方案

- 问题：启动时报错 `Missing API key` 或 `Missing Pinecone config`
  - 说明：自建服务严格要求上述环境变量
- 解决：设置 `OPENAI_API_KEY/OPENAI_BASE_URL/LLM_BINDING_HOST` 与 `PINECONE_API_KEY/PINECONE_URL`

- 问题：`/ingest_upload` 返回 `422 Field required`
  - 说明：上传字段名错误
  - 解决：使用 `files` 字段，例如：
    ```bash
    curl -X POST -F "files=@d:/yuki/LightRAG/example.pdf;type=application/pdf" \
      "http://127.0.0.1:8000/ingest_upload"
    ```

- 问题：`/ingest` 返回 `400 No files to ingest`
  - 说明：未提供 `file_paths`，且默认目录为空或不可用
  - 解决：传入有效路径或将文件放入 `DEFAULT_IMPORT_DIR`

- 问题：ngrok 报错 `ERR_NGROK_8012` 或无法连接 `127.0.0.1:4040`
  - 说明：本地服务未启动或端口不通；ngrok 本地 API 未开启
  - 解决：确保应用已在目标端口运行；确认 ngrok 版本与配置（v2 配置文件或升级代理到 v3.32+）

- 问题：Windows 上传路径失败 `curl: (26) Failed to open/read local data`
  - 说明：路径格式错误（前缀 `/d:/...` 会失败）
  - 解决：使用 `d:/...` 或用双引号包裹路径

- 问题：`ModuleNotFoundError: raganything`
  - 说明：模块名大小写不一致
  - 解决：已在代码中修正为 `from ragAnything import RAGAnything`；如本地私有修改，请确保一致

- 问题：端口占用或进程退出
  - 说明：已有进程占用端口或异常退出
  - 解决：更换端口（如 `8001`/`9622`），或终止占用进程；查看日志定位错误

---

## 注意事项

- 自建服务的上传保存目录可通过 `UPLOAD_TARGET_DIR` 配置（默认：`d:/yuki/LightRAG/hire_document`）。
- 自动扫描仅处理 `.pdf`、`.md`、`.docx`。
- 公网暴露建议开启鉴权（API-Key）与访问保护；避免在公网开放管理型端点。
- 官方 LightRAG API 的完整接口与使用请参考 `lightrag/api/README-zh.md` 与路由源码。