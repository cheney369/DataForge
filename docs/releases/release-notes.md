# DataForge 更新记录

### 2026-08-18

- 重构全局工作台为统一的微光玻璃视觉体系，统一导航层级、卡片边界、排版密度和页面状态反馈，并优化总览、数据、流程、知识、检索和应用页面的一致性。
- 总览页以完整生产链路为核心，集中展示来源、任务、知识资产、可检索状态、运行关注项和环境就绪度，使下一步操作更加明确。
- 将原“AI 应用”和“应用接入”收敛为统一应用配置流程，支持从知识绑定、Prompt、上下文组合和模型参数调试，到验证、发布的一体化操作。
- 发布后的应用配置可通过稳定 `app_key` 读取当前版本或指定历史版本，业务应用能够保持同一套接入代码，只在平台侧调整配置。
- 使用测试知识库完成 Text2QA、Embedding、Milvus、检索、上下文组装、LLM 回答和应用配置发布的完整闭环验证。
- 文档与任务管理页面增加面向大规模数据的搜索、筛选、分页和详情组织方式，避免数据增长后依赖平铺卡片浏览。

### 2026-08-14

- 启动五期更多数据来源扩展，新增 XLSX 上传、预览、标准记录物化与知识生产支持，并保留工作表、表头行和数据行溯源位置。
- 修复 DataFlow 任务详情读取旧共享缓存导致样本预览为空的问题，改为优先读取按任务隔离输出并保留旧路径兼容。
- 配置 `DataForge 多轮对话数据生成` 草稿，组合 `ConsistentChatGenerator` 与统一 Schema 适配器，输出 `messages`、`dialogue_id` 和 `turn_count`；启动不自动消耗模型调用。
- DataFlow 调试台增加嵌入工作台模式，隐藏重复导航并保留 DAG、算子配置与样本执行核心；DataForge 外层统一草稿检查、运行状态和发布入口。
- 放宽 DataFlow WebUI 对注册表 Pipeline `file_path` 和数据集 Metadata 类型的旧版响应约束，修复 DataForge 管理流程导致原生列表接口返回 500 的问题。
- 默认 OpenAI 兼容 LLM 会自动适配为 DataFlow API Serving，密钥不写入 DataFlow 注册表；已使用 `Qwen3-32B` 完成 Text2QA 真实样本验证。
- 修复 DataFlow API Serving 在仅通过环境变量提供密钥时被空配置覆盖的问题，并补充模型型算子的资源分层说明。
- 增加面向内部单机服务器的环境变量模板、构建脚本与 systemd 服务示例，不引入 SaaS 权限或计费体系。
- 增加 `/api/liveness` 和 `/api/readiness`，区分进程存活、核心可服务与可选依赖降级状态。
- CLI 增加 `dataforge doctor --deep` 和 `dataforge smoke`，支持真实模型/存储探测及启动后 HTTP 冒烟检查。
- 增加独立 Reranker 资源配置、连接测试和检索方案级启停开关，默认模型为 `bge-reranker-large`。
- 支持“向量候选召回 → 相关性重排 → 最终 Top K”，同时返回 `vector_score`、`rerank_score` 与模型执行审计。
- 对 Rerank 兼容服务返回超出 `top_n` 的结果执行客户端排序和截断保护。
- 增加稳定 AI Application 与不可变 Application Version，版本固定 Application Binding、LLM、System/User Prompt、Temperature、Max Tokens 和 Top K。
- 应用发布门禁会解析实际知识集合版本并探测 LLM；发布后保存脱敏 LLM 快照，修改配置生成新版本而不覆盖历史。
- 扩展 OpenAI 兼容 Chat Client，支持正式消息列表、生成参数、回答、Finish Reason、Token Usage 和模型耗时。
- 增加 `/api/ai-applications/{app_key}/chat`，自动执行检索、Prompt 渲染、Qwen 生成并返回完整引用证据。
- 增加应用运行记录，保存请求历史、过滤条件、实际集合版本、召回记录、回答、Token、耗时和失败原因。
- 流程开发区新增“AI 应用”页面，覆盖应用创建、版本配置、发布、对话调试、证据查看与运行历史。
- 使用真实 `bce-embedding-base`、Milvus 和 `Qwen3-32B` 完成 768 维知识索引到 RAG 回答的端到端验证。
- 将应用对话页定位为预览调试器，增加独立 `/v1/apps/{app_key}/invoke` 生产调用面和固定发布版本调用接口。
- 应用版本新增 Input/Output JSON Schema、检索问题字段、Prompt 变量映射、过滤字段白名单和引用响应开关。
- 增加应用 API Key 创建、哈希存储、单次明文展示、最近使用时间和独立撤销。
- Invoke API 支持同步 JSON 与真实 OpenAI 兼容 SSE Token 流；每次调用返回 Request ID、结构化 Output、引用、Token 和耗时。
- 使用真实 `bce-embedding-base`、Milvus 和 `Qwen3-32B` 验证当前版本调用、固定版本调用和 SSE 事件链。

### 2026-08-13

- 增加 Knowledge Collection 稳定容器和不可变 Collection Version，版本锁定 Retrieval Profile、Index Profile、知识库成员及其具体 Knowledge Index。
- 发布前重新校验成员索引可用性和方案兼容性；新发布版本可以切换为集合当前版本，历史发布版继续保留。
- 增加 Application Binding，提供唯一稳定接入标识、跟随当前发布版与固定版本两种策略，以及创建和版本调整审计记录。
- 增加 `/api/application-access/{binding_key}/query`，跨集合成员检索后执行全局排序，并返回成员来源、记录溯源和最终上下文。
- 业务工作区新增“知识集合”，流程开发区新增“应用接入”；集合成员筛选、版本发布、绑定策略和检索联调均可通过界面配置。
- 使用真实 `bce-embedding-base` 和本地 Milvus 完成两个独立知识库的 768 维索引、集合发布与跨库召回验证。

### 2026-08-12

- 完成二期索引基础闭环：可配置 OpenAI 兼容 LLM/Embedding、Milvus 和可选 Neo4j 资源，并提供连接测试和脱敏发布快照。
- 增加版本化 Index Profile，支持向量模板、Stored Fields、Metadata、标量过滤字段、样本预览、发布、默认切换和停用。
- 增加独立 Knowledge Index 与索引任务，支持自动创建、分批检查点、内容指纹幂等、取消、重试、重启恢复和新版本重建。
- 增加 Milvus Standalone Compose，并使用 `bce-embedding-base` 真实服务跑通知识资产入库、768 维向量化、完整性校验和语义检索。
- 增加版本化 Retrieval Profile 和统一查询 API，可配置 Top K、阈值、返回字段、过滤条件及应用上下文模板。
- 流程开发区新增“模型与存储、索引方案、检索方案”，业务区新增“索引任务”，知识资产展示待索引、索引中、可检索和失败状态。
- 接入 DataFlow 稳定适配层，标准流程发布保存冻结快照、配置哈希和样本任务。
- 打通基础文本标准化分块通道，并配置 Text2QA 文档转 FAQ 通道与 Serving 激活门禁。
- 增加知识生产任务的逐文档状态、取消、独立重试尝试和服务重启中断恢复。
- 重构前端为业务工作区与流程开发区，并补充任务执行详情和状态操作。
- 增加 DataFlow 运行健康报告、正式任务预检和任务事件时间线。
- 标准流程支持不可变递增版本、默认切换和停用治理。
- 知识类型 Schema 支持不可变版本和继承关系，旧契约继续服务历史引用。
- 记录溯源补齐 PDF 页码、CSV 行号、Word 段落/表格行和字符范围。
- 预留 MinerU 本地解析能力探测，支持配置 CLI、后端与探测开关；未安装或未激活时稳定回退到原生解析。

### 2026-07-30

- 重写项目说明，明确业务工作区与流程开发区的职责边界。
- 增加模块开发状态，区分现有原型、开发中能力和待开发模块。
- 补充关系库入库、向量或图索引、知识集合与应用访问的阶段规划。
- 增加 DataForge 数据加工全流程视觉图。
