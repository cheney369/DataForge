# 知识集合与应用交付

DataForge 三期基础能力把已经可检索的单个知识库组合成稳定的应用知识产品。应用只保存一个接入标识，不直接依赖知识库 ID、Milvus Collection、索引方案或检索方案版本。

## 配置层次

```text
知识库 Knowledge Base（关系库事实资产）
  → 知识索引 Knowledge Index（不可变物理索引）
  → 知识集合 Knowledge Collection（稳定业务容器）
  → 集合版本 Collection Version（成员与检索契约快照）
  → 应用绑定 Application Binding（稳定调用标识）
  → POST /api/application-access/{binding_key}/query
```

知识集合只固定名称、用途和知识类型。每个集合版本固定以下内容：

- 一个已经发布的 Retrieval Profile；
- Retrieval Profile 对应的 Index Profile；
- 一个或多个相同知识类型的 Knowledge Base；
- 每个成员当时具体可用的 Knowledge Index ID；
- Embedding 模型、向量维度、向量库类型和距离度量兼容性快照。

因此，重建某个知识库索引不会悄悄改变已经发布的集合版本。需要采用新索引时，应生成并发布新的集合版本。

## 兼容性与发布

界面只展示满足以下条件的知识库成员：

1. 知识库类型与集合类型一致；
2. 检索方案已经发布且仍然生效；
3. 检索方案依赖的索引方案与集合类型一致；
4. 知识库存在该索引方案的可用 Knowledge Index。

创建版本时即锁定具体索引；发布时再次检查每个索引仍为 `available` 且方案未漂移。发布可以把该版本切换为集合的“当前发布版”，旧版本仍可被固定版本应用继续使用。

## 应用绑定策略

应用绑定使用 3–64 位唯一 `binding_key`，允许小写字母、数字和连字符，并以字母开头。两种版本策略分别适合：

| 策略 | 行为 | 典型用途 |
|---|---|---|
| 跟随当前发布版 | 每次请求解析集合当前版本 | 正式应用、常规内容更新 |
| 固定集合版本 | 始终使用指定的历史发布版 | 回归测试、灰度验证、可复现实验 |

调整版本策略不会修改接入标识或 API 路径。系统保存创建和每次指向调整的审计事件。

## 统一应用查询

```json
POST /api/application-access/chronic-care/query
{
  "query": "高血压患者平时需要记录什么？",
  "filters": {"department": "cardiology"},
  "top_k": 5
}
```

服务先解析绑定对应的集合版本，再对每个被锁定成员索引执行同一 Retrieval Profile，合并结果并按分数全局排序。响应包括：

- 实际解析到的集合及版本；
- 应用绑定名称、标识和版本策略；
- 每条结果所属的知识库及 Knowledge Index；
- Retrieval Profile 允许返回的字段；
- 源文档、源版本和记录位置；
- 按上下文模板和分隔符拼接的最终 `context`。

调用方不需要传 `retrieval_profile_id`、`index_profile_id`、`knowledge_base_id` 或 Milvus Collection 名称。

## 当前边界

- 当前跨库合并采用向量分数全局排序；不同模型、维度或度量不能放进同一集合版本。
- 过滤条件沿用 Retrieval Profile 和 Index Profile 已声明的标量过滤字段。
- 混合检索、Rerank、成员级权重、路由策略和应用鉴权将在后续阶段增加。
- 集合版本一旦发布不能覆盖；更新成员、字段契约或检索参数需要创建新版本。
