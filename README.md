# DataForge 数据加工与知识资产平台

![DataForge：从源文档到可追溯知识资产](docs/assets/dataforge-hero.png)

DataForge 以 [OpenDCAI DataFlow](https://github.com/OpenDCAI/DataFlow) 为数据处理引擎，面向不熟悉数据工程的业务人员提供简洁的文档加工流程，并为技术人员保留标准流程配置和调试能力。

> [!IMPORTANT]
> DataForge 目前处于持续开发阶段，现有版本已经打通知识生产、向量索引、版本化知识集合、应用发布和服务化调用闭环，但仍不是生产就绪版本。限流、配额、混合检索、评测、用户权限与多租户等模块尚待开发。

## 项目目标

平台希望建立一条完整且可追溯的数据链路：

```text
PDF / CSV / XLSX / Markdown / DOCX / TXT / JSON / JSONL
  → 源文档与不可变版本
  → 可配置的知识类型
  → 已发布的 DataFlow 标准流程
  → 并行加工与逐条格式校验
  → 关系数据库中的知识资产
  → 向量或图索引
  → 知识集合与应用访问
```

业务用户只需要完成“上传文档、选择知识类型、启动处理、查看结果”等操作。知识类型结构、DataFlow 流程、模型服务、索引规则和数据库连接等复杂配置统一放在流程开发区。

## 当前开发状态

| 模块 | 当前状态 | 说明 |
|---|---|---|
| 源文档中心 | 五期扩展中 | 支持 PDF、CSV、XLSX、Markdown、DOCX、TXT、JSON、JSONL 的上传、解析、版本管理和重复内容识别 |
| 动态知识类型 | 一期闭环已实现 | 支持字段结构、不可变版本、继承关系和历史契约保留 |
| 标准流程 | 一期闭环已实现 | 支持类型绑定、样本验证、运行预检、冻结快照、版本哈希、递增版本、默认流程和停用治理 |
| 知识生产 | 一期闭环已实现 | 支持多文档任务、逐文档状态、事件时间线、取消、独立重试、重启中断恢复、结构校验和事务化入库 |
| 知识资产 | 原型已实现 | 可以查看知识库和标准记录，列表、筛选、批量操作和大规模数据浏览仍需优化 |
| 记录级溯源 | 一期闭环已实现 | 支持源版本、原始记录、分块、PDF 页码、CSV 行号、Word 段落/表格行和字符范围 |
| DataFlow 调试台 | 一期集成已实现 | 以嵌入工作台模式复用 DAG、算子配置和样本执行核心，并由 DataForge 统一草稿检查与发布入口 |
| 向量与图索引 | 二期闭环已实现 | 支持 Embedding/Milvus/Neo4j 资源配置、索引投影、不可变版本、自动索引、批处理、取消、断点重试、校验和切换；Neo4j 按方案可选 |
| 知识集合与应用交付 | 三期基础闭环已实现 | 支持同类型知识库组合、兼容性校验、不可变版本、当前发布版、固定版本、稳定调用标识与跨库检索 |
| AI 应用与调用服务 | 四期服务化闭环已实现 | 支持版本化输入输出 Schema、知识接入、Prompt、LLM、不可变发布、API Key、当前/固定版本 Invoke API、SSE、引用和运行审计 |
| 统一检索服务 | 基础闭环已实现 | 支持版本化检索方案、Top K、阈值、标量过滤、可选 Reranker、返回字段、上下文模板和统一查询 API；混合检索待后续增强 |
| 登录与权限 | 暂不开发 | 当前优先完成数据生产主流程，后续再设计用户、角色和租户能力 |

完整阶段规划参见 [plan.md](plan.md)。

## 当前可以体验的流程

1. 在“源文档”上传 PDF、CSV、XLSX、Markdown、DOCX、TXT、JSON 或 JSONL。
2. 在“知识生产”选择一个或多个文档版本和目标知识类型。
3. 系统匹配兼容且已验证的默认标准流程。
4. 启动任务，等待文档加工、逐条校验和关系数据库入库。
5. 在“知识资产”中查看知识库和知识记录。
6. 在“流程开发区 / 模型与存储”测试 Embedding 和 Milvus，在“索引方案”发布默认投影。
7. 新知识资产会自动创建独立索引任务；也可在“索引任务”中手动重建、取消或重试。
8. 在“检索方案”选择返回字段、按需开启 Reranker、配置上下文模板，并通过统一接口联调。
9. 在“知识集合”选择兼容知识库，生成不可变成员快照并发布当前版本。
10. 在“应用接入”创建稳定标识，选择跟随当前发布版或固定版本，并用统一端点跨库检索。
11. 在“AI 应用”配置输入输出 Schema、知识接入、Prompt 和 LLM，预览并发布不可变应用版本。
12. 在“业务系统接入”创建环境独立的 API Key，业务应用通过稳定 `/v1/apps/{app_key}/invoke` 调用当前版本，或固定到指定发布版本。

“知识资产已入库”只表示标准记录已经写入关系数据库。只有匹配已发布的默认索引方案、完成向量或图索引并通过完整性校验后，状态才会变为“可检索”。索引失败不会破坏事实资产。

技术人员可以进入“流程开发区 / DataFlow 调试台”配置知识类型、编排流程、运行样本、检查中间结果并发布标准流程。当前调试台仍是过渡实现，部分 DataFlow 原生功能和界面会继续调整。

DataFlow 能力复用范围、适配边界和发布语义参见 [DataFlow 集成与适配设计](docs/dataflow-integration.md)。
索引 Schema、Metadata、版本和统一检索契约参见 [索引与检索配置](docs/indexing-and-retrieval.md)。
知识集合版本、应用绑定与跨库交付语义参见 [知识集合与应用交付](docs/knowledge-collections-and-delivery.md)。
RAG 应用版本、输入输出契约、API Key、Invoke/SSE API 与运行审计参见 [AI 应用发布与服务化调用](docs/ai-applications.md)。

## 已具备的基础能力

- 文件内容校验和不可变版本管理
- PDF、CSV、XLSX、Markdown、DOCX、TXT、JSON、JSONL 解析
- 可配置知识类型及输出字段
- 知识类型 Schema 的不可变版本、继承和历史契约保留
- 标准流程与知识类型兼容校验
- 标准流程运行预检、不可变发布版本、默认切换和停用治理
- 一条可在 DataFlow Studio 编辑、样本验证并冻结发布的文本标准化分块基准通道
- DataFlow Text2QA 文档转 FAQ 通道已自动绑定默认 `Qwen3-32B` API Serving，并通过真实样本验证
- 多文档知识生产任务
- 逐文档执行状态、任务取消、独立重试尝试和重启中断恢复
- 任务事件时间线和逐文档 DataFlow 算子执行摘要
- 知识库和知识记录持久化
- 记录到源文档版本的关联与溯源
- PDF 页码、CSV 行号、Word 段落/表格行及分块字符范围
- DataForge 文件版本向 DataFlow 数据集桥接
- DataFlow 任务结果发布为 DataForge 数据资产
- 快速处理、预览、下载和基础接口
- OpenAI 兼容 LLM/Embedding/Reranker 服务、Milvus 和可选 Neo4j 的页面化配置与连接测试
- 文本块、FAQ、知识三元组和多轮对话的默认索引投影草稿
- 向量文本模板、Stored Fields、Metadata、标量过滤字段和缺失值策略配置
- 索引方案样本预览、真实服务验证、发布、默认版本、停用与重建
- 独立索引任务、分批检查点、内容指纹幂等、取消、重试和重启恢复
- 记录数、向量维度、映射关系校验及索引记录到源文档位置的完整溯源
- 检索方案的 Top K、阈值、可选 Reranker、候选数、返回字段、上下文模板、过滤条件和统一查询接口
- 同类型知识库的集合组合、索引兼容性筛选和精确物理索引锁定
- 知识集合不可变版本、当前发布版本切换和历史版本保留
- 应用稳定接入标识、跟随最新版/固定版本策略、变更审计和跨库结果排序
- AI 应用稳定标识、不可变版本、Prompt 模板、LLM 快照、对话历史和运行审计
- RAG 检索增强生成、引用证据、Token 用量和模型耗时记录
- 版本化 Input/Output JSON Schema、检索字段和 Prompt 输入映射
- 应用级哈希 API Key、当前/固定版本 Invoke API 和 SSE 流式响应

## 项目结构

```text
DataForge/
├── src/dataforge/                 # Python 后端、任务、存储与 DataFlow 桥接
├── frontend/                      # 面向业务用户的 Vue 中文界面
├── third_party/dataflow_webui/    # DataFlow 调试台前后端
├── infra/milvus/                  # Milvus Standalone 本地部署
├── tests/                         # 核心流程和接口测试
├── examples/                      # 示例文档与流程
├── docs/assets/                   # README 等文档资源
└── plan.md                        # 产品流程与阶段规划
```

运行数据默认保存在 `.dataforge/`，该目录不会提交到 Git：

```text
.dataforge/
├── metadata.sqlite3
├── blobs/
├── runs/
└── dataflow-studio/
    ├── data/
    ├── imports/
    └── cache/
```

## 安装与运行

环境要求：

- Python 3.11 或 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 与 npm
- 本地 DataFlow 源码

如果 DataFlow 与 DataForge 位于同一个父目录，系统会自动发现；其他目录请设置 `DATAFORGE_DATAFLOW_PATH`。

```bash
git clone https://github.com/cheney369/DataForge.git
cd DataForge

export DATAFORGE_DATAFLOW_PATH=/path/to/DataFlow

uv sync --extra dataflow --extra web --extra studio --extra indexing

# 启动本地 Milvus Standalone（etcd + MinIO + Milvus）
docker compose -f infra/milvus/docker-compose.yml up -d

cd frontend
npm install
npm run build

cd ../third_party/dataflow_webui/frontend
npm install
npm run build

cd ../../..
uv run --extra dataflow --extra web --extra studio --extra indexing dataforge-web
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，接口文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

内部服务器部署提供环境变量模板、systemd 示例、就绪探针、依赖诊断和 HTTP 冒烟命令，参见 [内部服务器部署](infra/deploy/README.md)。部署完成后建议执行：

```bash
dataforge doctor --deep
dataforge smoke --url http://127.0.0.1:8000
```

## 验证

```bash
uv run --with pytest --extra dataflow --extra web --extra studio --extra indexing pytest -q
```

前端构建：

```bash
cd frontend
npm run build

cd ../third_party/dataflow_webui/frontend
npm run build
```

## 已知边界

- Word 当前只支持 DOCX，旧版 `.doc` 尚未提供格式转换。
- 扫描版 PDF 尚未接入 OCR，只读取已有文字层。
- MinerU 本地解析已预留可选运行时探测；默认不安装模型、不引入重依赖，也不会替换当前原生解析。服务启动后可通过 `/api/parser-capabilities` 查看探测结果。
- 大型文档产生数万条知识记录时，跨进程任务队列、水平扩容和吞吐压测仍需加强。
- FAQ、三元组和多轮对话已有可配置索引投影；基础 Reranker 已可按检索方案启停，图谱混合召回和对话窗口自动生成仍需增强。
- 当前 AI 应用已经提供同步和 SSE 生产调用；限流、配额、密钥到期、租户权限、工具调用、Agent 编排和自动评测尚未实现。
- 部分 DataFlow 算子依赖本地模型、GPU、音频、OCR 或第三方服务，需自行安装对应可选依赖。

MinerU 预留配置：

```bash
# auto：探测 CLI；disabled：完全禁用探测
export DATAFORGE_MINERU_MODE=auto
export DATAFORGE_MINERU_COMMAND=/opt/mineru/bin/mineru
export DATAFORGE_MINERU_BACKEND=hybrid-auto-engine
```

当前探测只确认 CLI 是否存在且能正常响应，并对外声明 PDF 为候选增强格式。即使探测成功，正式解析仍保持原生通道；完成结构化结果与页码、区块坐标适配后再启用 MinerU，避免仅因服务器安装了命令就改变生产结果。

## 最新更新

### 2026-08-18

- 全局工作台升级为统一的微光玻璃视觉体系，重新整理导航层级、卡片边界、字体和页面状态反馈。
- 应用调试与接入收敛为统一配置流程，可以完成知识绑定、Prompt、上下文组合、模型调试、验证和发布。
- 发布配置支持通过稳定 `app_key` 读取，业务应用保持同一套接入代码即可消费平台侧最新或指定历史配置。
- 已使用测试知识库跑通 Text2QA、Embedding、Milvus、检索、上下文组装、LLM 回答和配置发布的完整链路。

完整历史参见 [更新记录](docs/releases/release-notes.md)。
