# AI 应用发布与服务化调用

DataForge 的 AI 应用不是一个只能在平台里聊天的页面，而是一个可以被业务系统稳定调用的数据应用运行时。平台页面属于配置面（Control Plane），`/v1/apps` 属于生产调用面（Serving Plane）。

## 分层结构

```text
DataForge 配置面
  → AI Application（稳定 app_key）
  → Application Version（不可变运行契约）
      → Input / Output JSON Schema
      → Prompt 变量映射
      → Application Binding
      → LLM Service
      → Temperature / Max Tokens / Top K
  → 发布当前版本

业务应用 A / B
  → Application API Key
  → POST /v1/apps/{app_key}/invoke
  → 当前发布版本或指定历史发布版本
  → Output + Citations + Usage + Request ID
```

业务应用只依赖 `app_key` 和版本化输入输出契约，不需要知道 Milvus Collection、知识库 ID、Embedding、检索方案或 Prompt。

## 调试与生产调用

| 用途 | 接口 | 约束 |
|---|---|---|
| 草稿/版本预览 | `POST /api/ai-application-versions/{version_id}/preview` | 配置面使用，不需要应用密钥，可以验证未发布草稿 |
| 兼容对话调试 | `POST /api/ai-applications/{app_key}/chat` | 仅供现有页面调试当前发布版本 |
| 生产调用 | `POST /v1/apps/{app_key}/invoke` | 必须使用应用 API Key，自动路由当前发布版本 |
| 固定版本调用 | `POST /v1/apps/{app_key}/versions/{version}/invoke` | 仅允许调用已发布版本，用于灰度、回归和结果复现 |

草稿不能通过 `/v1` 对业务系统开放。发布新版本会原子切换当前版本，历史发布版本仍可固定调用。

## 输入与输出契约

每个应用版本保存：

- `input_schema`：业务调用 `inputs` 的 JSON Schema；
- `query_field`：从 `inputs` 中提取检索问题的字段路径；
- `prompt_variables`：Prompt 变量到输入字段路径的映射；
- `allowed_filter_fields`：业务调用可以提交的过滤字段白名单；
- `output_schema`：应用输出对象的 JSON Schema；
- `include_citations`：正式响应是否包含引用证据。

默认契约：

```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "minLength": 1}
    },
    "required": ["query"],
    "additionalProperties": true
  },
  "query_field": "query",
  "prompt_variables": {"question": "query"},
  "output_schema": {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": false
  }
}
```

`{{ context }}` 是运行时保留变量，来自知识检索拼接结果；其他 Prompt 变量必须映射到输入 Schema 中已声明的字段。当前文本生成运行时固定生成 `answer`，更多结构化输出解析将在后续扩展。

## 应用 API Key

在“AI 应用 / 业务系统接入”为不同环境创建独立密钥，例如“应用 A 正式环境”和“应用 A 测试环境”。

- 完整密钥只在创建成功时显示一次；
- 数据库只保存 SHA-256 哈希和可识别前缀；
- 密钥不会进入运行请求、响应或日志；
- 每次成功鉴权更新最近使用时间；
- 撤销后立即不能再调用，其他密钥不受影响。

正式部署时，密钥应只保存在业务应用后端的 Secret Manager 或环境变量中，不能放进浏览器代码。

## 同步调用

```bash
curl -X POST 'https://dataforge.example.com/v1/apps/chronic-care-assistant/invoke' \
  -H 'Authorization: Bearer <APPLICATION_API_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{
    "inputs": {"query": "高血压患者每天要记录什么？"},
    "session_id": "session-001",
    "user_id": "user-123",
    "metadata": {"source": "application-a"}
  }'
```

响应：

```json
{
  "request_id": "aiapp_run_xxx",
  "application": {
    "key": "chronic-care-assistant",
    "name": "慢病随访助手",
    "version": 3
  },
  "output": {"answer": "建议每天早晚记录血压……"},
  "citations": [
    {
      "id": "index_record_xxx",
      "score": 0.91,
      "content": "……",
      "source": {"original_filename": "高血压随访指南.pdf"}
    }
  ],
  "model": "Qwen3-32B",
  "usage": {"total_tokens": 320},
  "llm_latency_ms": 1260
}
```

## SSE 流式调用

请求体增加 `"stream": true`，响应类型为 `text/event-stream`：

```text
event: start
data: {"request_id":"...","application":"chronic-care-assistant","version":3}

event: retrieval
data: {"request_id":"...","result_count":3,"citations":[...]}

event: delta
data: {"text":"建议"}

event: complete
data: {"request_id":"...","output":{"answer":"建议……"},...}
```

运行失败时发送 `error` 事件，并将同一个 `request_id` 对应的运行记录标记为失败。

## 发布门禁与审计

应用发布前验证知识绑定可解析、LLM 可用、Input/Output Schema 有效、检索字段存在、Prompt 变量全部完成映射。发布版本保存脱敏 LLM 和调用契约快照。

每次预览或生产调用都会记录：

- 应用版本、调用模式（预览、当前生产版或固定版本）和密钥 ID；
- `inputs`、会话/用户标识、调用方 Metadata、历史消息与过滤条件；
- 实际知识集合版本、检索方案、引用记录和来源；
- 输出、模型、Token、耗时、完成状态和错误。

运行记录不保存 API Key。敏感输入和回答目前会进入审计库，正式部署前应结合数据分级配置保留、脱敏和删除策略。

## 当前边界

- 已支持同步与 SSE 流式文本生成，但尚未实现客户端主动取消后的上游模型取消。
- API Key 是应用级基础鉴权；用户登录、租户隔离、IP 白名单、限流、配额和密钥到期策略尚未实现。
- 当前结构化输出只支持 `{ "answer": string }`；JSON Mode、字段解析和输出修复待后续扩展。
- 基础 Reranker 已由绑定的检索方案控制；查询改写、混合检索、工具调用、Agent 和自动评测仍在后续阶段。
