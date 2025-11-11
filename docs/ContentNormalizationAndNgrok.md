# 服务返回文本规范化与 ngrok 请求示例

本文档说明近期在 OpenAI 绑定上的改动，以及通过 ngrok 访问 API 的请求示例，便于你快速验证与集成。

## 变更摘要
- 统一将模型返回的 `message.content` 与 `reasoning_content` 规范化为纯文本字符串。
- 覆盖非流式与流式两条分支：当返回为列表（多模态文本/图片混合）、字节或其他类型时，会被安全转换为纯文本。
- 下游正则处理与清洗（如移除 `<think>...</think>` 标签）不会再因为非字符串导致报错。

## 使用建议（通过 ngrok 访问）
- 访问 `https://<your-ngrok-domain>/query` 时，建议添加请求头：`ngrok-skip-browser-warning: true` 以跳过警告页。
- 如果仍出现警告，可附加自定义 `User-Agent`（例如 `User-Agent: TraeAI-Client`）。

## 请求示例

### PowerShell（bypass 模式，非流式）
```powershell
$uri = 'https://<your-ngrok-domain>/query'
$headers = @{ 'ngrok-skip-browser-warning' = 'true' }
$body = @{ question = '你好，请用一句话回答：LightRAG是什么？'; mode = 'bypass'; stream = $false } | ConvertTo-Json
$resp = Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$resp | ConvertTo-Json -Depth 6
```

### PowerShell（local 模式，非流式）
```powershell
$uri = 'https://<your-ngrok-domain>/query'
$headers = @{ 'ngrok-skip-browser-warning' = 'true' }
$body = @{ question = '用一句话说明LightRAG用途'; mode = 'local'; stream = $false } | ConvertTo-Json
Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 6
```

### curl（bypass 模式，非流式）
```bash
curl -X POST "https://<your-ngrok-domain>/query" \
  -H "Content-Type: application/json" \
  -H "ngrok-skip-browser-warning: true" \
  -d '{"question":"你好，请用一句话回答：LightRAG是什么？","mode":"bypass","stream":false}'
```

### curl（bypass 模式，流式）
> 如果需要流式输出，请显式设置 `stream=true`，有些终端需要 `--no-buffer` 以便更及时地显示数据。
```bash
curl --no-buffer -X POST "https://<your-ngrok-domain>/query" \
  -H "Content-Type: application/json" \
  -H "ngrok-skip-browser-warning: true" \
  -d '{"question":"一句话说明LightRAG用途","mode":"bypass","stream":true}'
```

## 返回内容保证
- 非流式与流式分支均返回纯文本内容（如模型包含 `<think>` 推理片段，可在后处理阶段移除）。
- 多模态返回将自动提取文本部分并按行拼接；字节流会按 UTF-8 解码（忽略无法解码的片段）。

## 常见问题
- 超时或无法连接：确认你的 RAG 服务已启动，并且 ngrok 正在正确转发到本地服务端口；使用 `https` 地址；必要时添加自定义 `User-Agent`。
- 仍出现警告页：已添加 `ngrok-skip-browser-warning` 请求头；如仍然出现，补充 `User-Agent`。

## 备注
- 如果你偏好稳定的纯文本输出，可选择纯文本聊天模型（如 `gpt-4o-mini` 或同类供应商的文本模型）。当前改动已兼容多模态返回，不是必须。