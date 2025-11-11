# LightRAG API cURL 使用指南（Windows）

本指南整理了在 Windows 环境下使用 `curl.exe` 调用 LightRAG 服务的常用方法，重点展示如何通过“文件载荷”避免 PowerShell 5 的引号/编码问题，并提供若干中文问题范例以便直接测试。

## 前置条件
- 服务已通过 ngrok 暴露为 `https://unlaunched-cephalothoracic-shenita.ngrok-free.dev`（本地启动示例：`uvicorn rag_service_api:app --host 0.0.0.0 --port 8000`）。
- 已配置 `.env`（示例重点）：
  - `COSINE_THRESHOLD=0.05`
  - `EMBED_MODEL=text-embedding-3-large`
  - `EMBED_DIM=3072`
  - `EMBED_DIM_AUTODETECT=true`
  - `LIGHTRAG_WORKING_DIR=./existing_lightrag_storage_openai_3072`
  - `WORKSPACE=hire`
- 建议使用 `curl.exe`（Windows 自带或通过安装）。
- 若你使用 PowerShell 7+，可以尝试内联 JSON，但为兼容性与稳定性，推荐统一使用“文件载荷”。

注意：使用 ngrok 免费域名时，建议在所有 cURL 请求中添加 `-H "ngrok-skip-browser-warning: 1"` 以绕过浏览器警告页；或设置自定义 User-Agent。

## 跨主机实测命令与排错记录（2025-11-10）

以下命令在 PowerShell 7+（Windows）下针对 `https://unlaunched-cephalothoracic-shenita.ngrok-free.dev` 实测，包含成功与失败的典型返回，便于快速复现与排错。

- 建议：涉及中文的 JSON，优先使用“管道 + `--data-binary '@-'`”发送，避免引号与编码问题。
- 提醒：ngrok 免费域名请在请求头加入 `ngrok-skip-browser-warning: 1`。

1）上传并入库（POST /ingest_upload）

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" \
  -H "ngrok-skip-browser-warning: 1" \
  -F "files=@C:\\Users\\admin\\Desktop\\简历test\\零售、快销行业相关测试简历\\简历文件\\0dd9dd30d74e4aa9a45a804dc1af90c0.pdf;type=application/pdf" \
  -F "output_dir=./output"
```

返回（示例）：

```json
{
  "status": "success",
  "uploaded_count": 1,
  "ingested_count": 1,
  "errors": [],
  "uploaded_files": [
    "d:\\yuki\\LightRAG\\hire_document\\0dd9dd30d74e4aa9a45a804dc1af90c0.pdf"
  ],
  "ingested_files": [
    "d:\\yuki\\LightRAG\\hire_document\\0dd9dd30d74e4aa9a45a804dc1af90c0.pdf"
  ]
}
```

2）综合检索+生成（POST /query）

- bypass 模式（直答）成功：

```powershell
$json = '{"question":"徐中天的工作经历如何","mode":"bypass"}';
$json | curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" \
  -H "ngrok-skip-browser-warning: 1" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary '@-'
```

- hybrid 模式在个别部署可能返回：`{"detail":"Query failed: expected string or bytes-like object"}`。建议：先用 `bypass` 验证通路，或切换为 `local/hybrid` 并确保以 UTF-8 发送（推荐“管道 + `--data-binary '@-'`”）。

3）向量检索（POST /search_vectors）

```powershell
$json = '{"query":"徐中天的工作经历如何","top_k":50}';
$json | curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" \
  -H "ngrok-skip-browser-warning: 1" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary '@-'
```

返回：`{"status":"failure","message":"No relevant document chunks found."}` 表示当前问题未命中文档片段；可降低 `COSINE_THRESHOLD` 或改写问题为更贴近文档内容（如文件名、公司名、技能、项目等）。

4）健康检查（GET /health）

```powershell
curl.exe -sS -X GET "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/health" -H "ngrok-skip-browser-warning: 1"
```

返回：`{"detail":"Not Found"}`。说明当前部署未暴露 `/health` 路由；并不影响其他接口使用。

---

## 从其他主机访问（跨主机调用）

无论你在本机还是其他主机调用，只需将示例中的基础地址替换为服务端可达的地址：
- 公网域名（推荐）：`https://<你的公网域名>` 或 ngrok 域名 `https://<your-subdomain>.ngrok-free.dev`。使用 ngrok 时请加 `-H "ngrok-skip-browser-warning: 1"`。
- 局域网地址：`http://<服务端IP>:<端口>`（例如 `http://192.168.1.10:8000`）。

必要条件：
- 服务端以 `--host 0.0.0.0` 启动并监听对外端口，例如：`uvicorn rag_service_api:app --host 0.0.0.0 --port 8000`。
- 防火墙/安全组开放该端口；若在路由器/NAT 后，需要端口转发或使用 ngrok/反向代理。
- 证书问题仅调试时可加 `-k` 忽略验证，不建议在生产使用。

载荷与路径注意：
- `--data-binary "@..."` 的文件路径是“调用端本机路径”，不是服务端路径。请在你的机器上准备好 JSON 载荷文件，或在 PowerShell 7+ 使用内联 JSON（见下文“备用”）。
- 上传文件同理，`-F "files=@..."` 指向调用端本机的文件路径。

示例（公网域名）：

```powershell
curl.exe -sS -X POST "https://your-public-domain.example/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@C:\path\to\requests\query_hybrid.json"
```

示例（局域网 IP）：

```powershell
curl.exe -sS -X POST "http://192.168.1.10:8000/search_vectors" `
  -H "Content-Type: application/json" `
  --data-binary "@C:\path\to\requests\search.json"
```

示例（局域网上传）：

```powershell
curl.exe -sS -X POST "http://192.168.1.10:8000/ingest_upload" `
  -F "files=@C:\Users\admin\Desktop\resume.pdf" `
  -F "output_dir=./output"
```

---

## 快速验证（跨主机，已测试）

以下命令已在跨主机场景下验证可用，适合快速排查“网络/证书/别名/编码”问题。推荐优先使用“管道 + `--data-binary '@-'`”。

- /query（推荐：文件载荷，避免 PowerShell 5 编码/引号问题）

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@requests/query.json"
```

说明：`requests/query.json` 示例内容如下（问题已直接写在载荷文件中）：

```json
{
  "question": "当前有哪些简历",
  "mode": "bypass"
}
```

- /search_vectors（文件载荷）

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@requests/search.json"
```

说明：`requests/search.json` 示例内容如下：

```json
{
  "query": "当前已入库的简历文件名有哪些？",
  "top_k": 50
}
```

提示：如需“把问题直接写进命令中”（内联 JSON），请在 PowerShell 7+ 或兼容环境下使用以下示例；PowerShell 5 建议统一使用“文件载荷”。

```powershell
# 内联 JSON（PowerShell 7+ 推荐）
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-raw '{"question":"当前已入库的简历文件名有哪些？","mode":"bypass"}'

curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-raw '{"query":"当前已入库的简历文件名有哪些？","top_k":50}'
```

注意：
- 使用 ngrok 免费域名时，务必保留 `-H "ngrok-skip-browser-warning: 1"` 以绕过浏览器警告页。
- 如果你仍在 PowerShell 5 环境且内联 JSON 报 `422 JSON decode error`，请改用“文件载荷”方式（如上）。
- `/search_vectors` 若返回 `No relevant document chunks found.`，说明当前问题未命中内容片段，可降低 `COSINE_THRESHOLD` 或调整问题语义；统计类问题建议改用 `/query`。
 - 若出现 `Query failed: expected string or bytes-like object`，改用 `bypass` 模式或“管道 + `--data-binary '@-'`”，并确保 `Content-Type: application/json; charset=utf-8`。

### PS 7.5 内联 JSON（跨主机，实测通过）

你已经升级到 PowerShell 7.5，以下两条命令在跨主机（ngrok 域名）环境下实测可用，问题直接写在命令中：

```powershell
# /query（bypass，直接问：当前已入库的简历文件名有哪些？）
$json = '{"question":"当前已入库的简历文件名有哪些？","mode":"bypass"}';
$json | curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" \
  -H "ngrok-skip-browser-warning: 1" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary '@-'

# /search_vectors（检索片段，不返回总数）
$json = '{"query":"当前已入库的简历文件名有哪些？","top_k":50}';
$json | curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" \
  -H "ngrok-skip-browser-warning: 1" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary '@-'
```

说明：
- 以上使用“管道 + `--data-binary '@-'`”方式可避免引号与编码问题，同时在 PS 7.5 下也能正常工作。
- `/query` 将返回直接回答内容；`/search_vectors` 若提示 `no_results`，说明暂未命中内容片段，并不代表接口失败。

## 1）上传与入库（/ingest_upload）

接口：`POST /ingest_upload`（multipart/form-data）

示例命令：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" `
  -H "ngrok-skip-browser-warning: 1" `
  -F "files=@C:\\path\\to\\your\\resume.pdf" `
  -F "output_dir=./output"
```

说明：
- 支持文件类型默认包含 `.pdf,.md,.docx`。
- 文件将保存并入库到服务端配置的目录（示例默认：`d:/yuki/LightRAG/hire_document`）。
- 成功返回中包含 `uploaded_files` 与 `ingested_files` 列表。

Tips：如果你要上传具体文件（例如你的本地路径）：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" `
  -H "ngrok-skip-browser-warning: 1" `
  -F "files=@C:\\Users\\admin\\Desktop\\简历test\\零售、快销行业相关测试简历\\简历文件\\0b51280804da4b20bfc97b518cdcfa40.pdf" `
  -F "output_dir=./output"
```

---

## 2）查询（/query，使用文件载荷避免引号问题）

接口：`POST /query`

先在项目目录创建载荷文件（示例路径：`requests/query_hybrid.json`）：

```json
{
  "question": "当前已入库的简历文件名有哪些？",
  "mode": "hybrid"
}
```

调用命令：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@requests/query_hybrid.json"
```

示例：直接在命令中包含中文问题（内联 JSON）

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-raw '{"question":"当前已入库的简历文件名有哪些？","mode":"hybrid"}'

示例：PS 7+ 管道发送（bypass 模式，推荐直答验证通路）

```powershell
$json = '{"question":"徐中天的工作经历如何","mode":"bypass"}';
$json | curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" \
  -H "ngrok-skip-browser-warning: 1" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary '@-'
```
```

注意：
- 在 PowerShell 5 环境下，务必使用单引号包裹整段 JSON（如上示例），并显式调用 `curl.exe`（避免被 `Invoke-WebRequest` 别名接管）。
- 若遇到编码或引号解析问题，优先改用“文件载荷”方式（`--data-binary "@..."`）。
- 跨主机调用时，将域名替换为你的公网域名或局域网地址（如 `http://192.168.1.10:8000`）。

示例：统计入库简历总数（推荐 /query）

先在项目目录创建载荷文件（示例路径：`requests/query_count.json`）：

```json
{
  "question": "现在入库的简历总数是多少？",
  "mode": "hybrid"
}
```

调用命令：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@requests/query_count.json"
```

提示：跨主机调用时，将基础地址替换为你的公网域名或局域网 IP（例如 `http://192.168.1.10:8000`），并确保 `@requests/query_count.json` 是“调用端本机路径”。

说明：
- `mode` 可选：`local|global|hybrid|naive|mix|bypass`。
- 为了得到更贴近入库数据的答案，推荐使用 `hybrid` 或 `local`。
- 如需最简单的模型直答（不依赖检索），可用 `bypass`。

---

## 3）向量检索（/search_vectors，使用文件载荷避免引号问题）

接口：`POST /search_vectors`

先在项目目录创建载荷文件（示例路径：`requests/search.json`）：

```json
{
  "query": "当前已入库的简历文件名有哪些？",
  "top_k": 50
}
```

调用命令：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@requests/search.json"
```

示例：直接在命令中包含中文问题（内联 JSON）

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-raw '{"query":"当前已入库的简历文件名有哪些？","top_k":50}'
```

注意：`/search_vectors` 返回的是命中的内容片段与引用，不会直接返回“总数”。若需要得到明确的统计答案，请使用上面的 `/query` 示例（`hybrid` 或 `local` 模式）。

示例：以“总数”问题进行检索（用于命中相关片段）

先在项目目录创建载荷文件（示例路径：`requests/search_count.json`）：

```json
{
  "query": "现在入库的简历总数是多少？",
  "top_k": 50
}
```

调用命令：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-binary "@requests/search_count.json"
```

提示：`/search_vectors` 返回的是命中的内容片段与引用，不会直接返回“总数”。若需要得到明确的统计答案，请使用上面的 `/query` 示例（`hybrid` 或 `local` 模式）。

说明：
- 返回仅包含 `chunks` 与 `references`（若命中），以及 `metadata`。
- 如遇 `No relevant document chunks found.`，可尝试：
  - 降低 `COSINE_THRESHOLD`（已在示例设置为 `0.05`）。
  - 将问题改得更具体、贴近文档内容（文件名、公司名、技能、项目等）。
  - 增大 `top_k`。

---

## 4）中文问题范例（可直接用于 /query 或 /search_vectors）

- 列出文件与数量
  - 当前已入库的简历文件名有哪些？
  - 现在入库的简历总数是多少？
- 提取关键信息
  - 该简历的候选人姓名是什么？
  - 简历中提到的工作公司有哪些？
  - 候选人的教育背景是什么？毕业时间与学校？
  - 简历中的核心技能有哪些？请按重要性排序。
  - 项目经验里涉及到的技术栈与职责分别是什么？
- 筛选与适配
  - 这份简历是否适合零售/快销行业？理由是什么？
  - 简历是否包含数据分析或电商运营经验？
  - 候选人是否有团队管理经验？具体体现在哪里？
- 摘要与对比
  - 请为该简历生成一段 100 字的专业摘要。
  - 对比两份简历，谁更适合店铺运营岗位？请给出依据。

---

## 备用：PowerShell 7+ 内联 JSON（仅在你确认兼容时使用）

在 PowerShell 7+ 环境下，部分场景可以直接使用内联 JSON（注意双引号与编码）：

```powershell
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" `
  -H "ngrok-skip-browser-warning: 1" `
  -H "Content-Type: application/json" `
  --data-raw '{"question":"当前已入库的简历文件名有哪些？","mode":"hybrid"}'
```

但为避免兼容性问题，推荐优先使用“文件载荷”方式。

---

## 参考
- 接口字段与环境变量说明：`docs/api_interface_zh.md`
- 服务说明与中文教程：`docs/rag_service_api_zh.md`