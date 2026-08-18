# 索引与检索配置

DataForge 二期把关系数据库中的规范知识记录转换为可重建的 Milvus 或图索引。事实记录、索引投影和应用检索契约分层管理，业务应用不需要写底层入库或上下文拼接代码。

## 配置层次

```text
知识类型 Schema（事实字段）
  → 索引方案 Index Profile（如何投影和存储）
  → 知识索引 Knowledge Index（某知识库的不可变物理版本）
  → 检索方案 Retrieval Profile（如何召回、返回和拼接）
  → POST /api/retrieval/query
```

同一知识资产可以按不同应用发布多套索引方案。索引方案决定 Embedding 文本、随向量保存的字段、Metadata、独立过滤字段和运行资源；检索方案只能使用兼容索引已经保存的字段。

## 运行资源

“流程开发区 / 模型与存储”提供五类配置：

- LLM：OpenAI 兼容地址、模型、超时、重试和 API Key 环境变量名，供 Text2QA 与 AI 应用选择。
- Embedding：OpenAI 兼容地址、模型、维度、批大小、并发上限、超时、重试和 API Key 环境变量名。
- Reranker：兼容 `POST /rerank` 的地址、模型、超时、重试和 API Key 环境变量名；是否使用由检索方案控制。
- Vector Store：Milvus URI、Database、Collection 前缀和 Token 环境变量名。
- Graph Store：可选 Neo4j URI、Database 及用户名、密码环境变量名。

密钥值不写入数据库。发布索引方案时保存脱敏资源快照，使历史版本可以按当时的模型、维度和存储目标重建。

默认 Embedding 为 `bce-embedding-base`，已验证输出为 768 维；默认 Reranker 为 `bge-reranker-large`，默认 Milvus 地址为 `http://127.0.0.1:19530`。模型服务地址均为本地占位值，可在页面修改，也可通过 `DATAFORGE_LLM_BASE_URL`、`DATAFORGE_EMBEDDING_BASE_URL`、`DATAFORGE_RERANKER_BASE_URL` 等环境变量覆盖。本地存储服务可这样启动：

```bash
docker compose -f infra/milvus/docker-compose.yml up -d
docker compose -f infra/milvus/docker-compose.yml ps
```

## 索引方案字段

| 配置 | 作用 |
|---|---|
| `embedding_template` | 用 `{{ field }}` 从知识记录生成向量化文本 |
| `stored_fields` | 随索引保存、可被检索方案返回或拼接的事实字段 |
| `metadata_fields` | 保存页码、行号、段落等溯源 Metadata |
| `filter_fields` | 映射为 Milvus 独立标量字段，支持字符串、整数、小数和布尔过滤 |
| `missing_policy` | 字段缺失时阻止任务或按空值处理 |
| `metric_type` | `COSINE`、`IP` 或 `L2`；公开分数统一为越大越相似 |

系统为文本块、FAQ、知识三元组和多轮对话预置草稿。草稿需执行样本投影、Embedding 维度检查和目标存储连接测试后才能发布。一个知识类型可发布多套方案，但自动索引只使用一个默认发布版。

## 索引任务与一致性

知识资产事务提交后，系统独立创建索引任务。任务按 Embedding 批大小生成检查点，使用“投影文本 + Metadata + 过滤字段”内容指纹实现幂等写入。取消或进程中断后可以创建新的重试尝试；已经完成且内容未变化的记录不会重复 Embedding。

新版本只有同时满足以下条件才切换为可检索：

- 关系库映射记录数等于知识资产记录数；
- Milvus flush 后的实体数等于知识资产记录数；
- 实际 Embedding 维度等于发布快照维度；
- 每条索引记录都保留 `knowledge_record_id`、`source_version_id` 和源位置。

模型、维度或字段规则变更会生成新的 Index Profile 和 Knowledge Index 版本，不覆盖旧 Collection。

## 检索方案与统一接口

检索方案配置 `top_k`、最低分数、可选 Reranker、重排候选数、返回字段、单条上下文模板和多条分隔符。发布时检查返回字段是否已由依赖索引保存，并对启用的 Reranker 做真实连通测试；不兼容配置不能发布。

Reranker 关闭时直接按向量相似度返回。开启时先用向量检索召回 `rerank_candidate_count` 条候选，再调用所选模型重排并截断到最终 `top_k`。最低分数仍作用在向量召回阶段。即使远端服务忽略 `top_n` 返回了更多结果，适配层也会重新按相关分排序并执行本地截断。

```json
POST /api/retrieval/query
{
  "retrieval_profile_id": "retp_...",
  "knowledge_base_id": "kb_...",
  "query": "高血压患者平时要记录什么？",
  "filters": {"department": "cardiology"},
  "top_k": 3
}
```

响应包含字段化结果、分数、引用来源、记录级溯源和已经按模板组装好的 `context`。应用只需要选择已发布检索方案，不需要了解 Milvus Collection、Embedding 模型或字段投影细节。

启用重排后，结果中的 `score` 表示最终 `rerank_score`，同时保留原始 `vector_score`；响应顶层 `reranker` 记录实际模型、候选数、返回数、耗时和 Token 用量。关闭时 `score` 仍是向量分，`reranker.enabled` 为 `false`。
