# 公网 cURL 接口调用速查（含跨主机示例）

本指南整理了从其他主机通过公网访问你在本机部署的 LightRAG 服务的 cURL 调用示例，命令中直接写入中文问题；涉及文件上传时使用模拟路径即可。示例统一使用当前 ngrok 域名：`https://unlaunched-cephalothoracic-shenita.ngrok-free.dev`。

## 前提与约定
- 服务已运行并通过 ngrok 暴露到公网，例如：`uvicorn rag_service_api:app --host 0.0.0.0 --port 8000`。
- 如启用 API-Key，请在所有请求加上：`-H "X-API-Key: <你的 key>"`。
- 为避免 ngrok 浏览器提示，示例均加入：`-H "ngrok-skip-browser-warning: 1"`。
- Windows 使用 `curl.exe`，Linux/macOS 使用 `curl`。下方均提供双平台示例。
- JSON 请求需添加：`-H "content-type: application/json"`。

## 健康检查（/health）
说明：未定义健康路由时返回 `404` 或 `{"detail":"Not Found"}` 属正常。

- Linux/macOS：
```
curl -sS -H "ngrok-skip-browser-warning: 1" https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/health
```
- Windows：
```
curl.exe -sS -H "ngrok-skip-browser-warning: 1" "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/health"
```

## 上传入库（/ingest_upload）
说明：`multipart/form-data`；文件会保存到服务端的 `UPLOAD_TARGET_DIR`（默认 `d:/yuki/LightRAG/hire_document`）并解析入库。其它类型取决于插件支持，PDF 最稳。如下为“模拟路径”示例。

- Linux/macOS：
```
curl -sS -X POST https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload \
  -H "ngrok-skip-browser-warning: 1" \
  -F "files=@/home/you/Documents/sample.pdf" \
  -F "output_dir=./output"
```
- Windows：
```
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_upload" \
  -H "ngrok-skip-browser-warning: 1" \
  -F "files=@C:\\Users\\you\\Documents\\sample.pdf" \
  -F "output_dir=./output"
```
预期输出：`{"status":"success|partial|error","uploaded_count":N,"ingested_count":M,"errors":[...]}`。

## 自动扫描入库（/ingest_auto）
说明：无需请求体；服务端扫描 `DEFAULT_IMPORT_DIR`（默认 `d:/yuki/LightRAG/hire_document`）的 PDF/MD/DOCX 并批量入库。

- Linux/macOS：
```
curl -sS -X POST https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_auto -H "ngrok-skip-browser-warning: 1"
```
- Windows：
```
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/ingest_auto" -H "ngrok-skip-browser-warning: 1"
```

## 问答查询（/query，命令内直接写入中文问题）
说明：JSON 请求；键为 `question`，可选 `mode`（推荐 `bypass` 或 `hybrid`）。

- Linux/macOS（bypass 模式）：
```
curl -sS -X POST https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query \
  -H "content-type: application/json" \
  -H "ngrok-skip-browser-warning: 1" \
  --data-raw '{"question":"徐中天的工作经历如何","mode":"bypass"}'
```
- Windows（bypass 模式）：
```
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query" \
  -H "content-type: application/json" \
  -H "ngrok-skip-browser-warning: 1" \
  -d "{\"question\":\"徐中天的工作经历如何\",\"mode\":\"bypass\"}"
```
- Windows（更稳的 PowerShell 管道方式）：
```
powershell -NoProfile -Command "$b = @{ question = '徐中天的工作经历如何'; mode = 'bypass' } | ConvertTo-Json; curl.exe -sS -X POST 'https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query' -H 'content-type: application/json' -H 'ngrok-skip-browser-warning: 1' -d $b"
```
预期输出：`{"result":"...详细中文回答..."}`；异常时返回 `{"detail":"Query failed: ..."}`。

## 向量检索（/search_vectors，命令内直接写入中文问题）
说明：只做向量检索，不走生成；无命中时返回 `failure` 与 `"No relevant document chunks found"`。

- Linux/macOS：
```
curl -sS -X POST https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors \
  -H "content-type: application/json" \
  -H "ngrok-skip-browser-warning: 1" \
  --data-raw '{"query":"徐中天的工作经历如何","top_k":50}'
```
- Windows：
```
curl.exe -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/search_vectors" \
  -H "content-type: application/json" \
  -H "ngrok-skip-browser-warning: 1" \
  -d "{\"query\":\"徐中天的工作经历如何\",\"top_k\":50}"
```
预期输出：`{"status":"success|failure","chunks":[...],"references":[...],"metadata":{...}}`。

## 可选回调（callback_url）
说明：支持在查询或入库完成后，服务端将结果 POST 到你指定地址（如 webhook.site）。

示例：
```
curl -sS -X POST "https://unlaunched-cephalothoracic-shenita.ngrok-free.dev/query?callback_url=https://webhook.site/xxxx" \
  -H "content-type: application/json" \
  -H "ngrok-skip-browser-warning: 1" \
  --data-raw '{"question":"测试回调","mode":"bypass"}'
```

## 常见问题与建议
- JSON 请求必须带 `content-type: application/json`，并正确转义引号；PowerShell 推荐 `ConvertTo-Json` 或“管道 + `--data-binary '@-'`”。
- 上传失败或入库失败优先试 PDF；其它类型依赖解析插件支持。
- 向量检索无命中属常见情况；可提高 `top_k`（如 50）、优化问题表达或降低 `COSINE_THRESHOLD`（如 0.05）。
- 若出现维度不匹配错误，确认服务端 `EMBED_MODEL`/`EMBED_DIM` 与向量库一致；必要时临时设置 `EMBED_DIM_COERCE=true`。
- Windows 旧版 PowerShell 建议使用文件载荷或管道方式，避免引号与编码问题。