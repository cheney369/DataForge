export const modules = [
  {
    id: 'documents',
    label: '文档与数据源',
    phase: 1,
    status: 'available',
    pages: [{ id: 'sources', label: '文档管理', note: '上传、版本与来源' }]
  },
  {
    id: 'processing',
    label: '数据处理',
    phase: 1,
    status: 'available',
    pages: [
      { id: 'jobs', label: '处理任务', note: '生产与运行状态' },
      { id: 'types', label: '知识类型', note: '定义输出结构', audience: 'developer' },
      { id: 'standard', label: '标准流程', note: '验证与发布', audience: 'developer' },
      { id: 'studio', label: 'DataFlow 调试台', note: '编排与样本调试', audience: 'developer' }
    ]
  },
  {
    id: 'assets',
    label: '数据资产',
    phase: 1,
    status: 'available',
    pages: [{ id: 'knowledge', label: '知识资产', note: '知识库、记录与溯源' }]
  },
  {
    id: 'indexing',
    label: '索引与知识服务',
    phase: 2,
    status: 'available',
    pages: [
      { id: 'indexes', label: '索引任务', note: '进度、重试与可检索状态' },
      { id: 'resources', label: '模型与存储', note: 'Embedding、Milvus 与图数据库', audience: 'developer' },
      { id: 'index-profiles', label: '索引方案', note: '字段投影、Metadata 与版本', audience: 'developer' },
      { id: 'retrieval-profiles', label: '检索方案', note: '召回、返回字段与上下文', audience: 'developer' }
    ]
  },
  {
    id: 'delivery',
    label: '集合与应用交付',
    phase: 3,
    status: 'available',
    pages: [
      { id: 'collections', label: '知识集合', note: '组合、版本与发布' },
      { id: 'application-access', label: '应用配置', note: '配置、调试与发布', audience: 'developer' }
    ]
  }
]

export const lifecycleStages = [
  {
    id: 'overview',
    label: '总览',
    note: '进度与下一步',
    defaultPage: 'overview',
    pages: [{ id: 'overview', label: '总览', note: '运行概览与下一步' }]
  },
  {
    id: 'data',
    label: '数据',
    note: '接入与处理',
    defaultPage: 'sources',
    pages: [
      { id: 'sources', label: '文档管理', note: '上传、版本与来源' },
      { id: 'jobs', label: '处理任务', note: '生产与运行状态' }
    ]
  },
  {
    id: 'flow',
    label: '流程',
    note: '定义生产能力',
    defaultPage: 'types',
    pages: [
      { id: 'types', label: '知识类型', note: '定义输出结构' },
      { id: 'standard', label: '标准流程', note: '验证与发布' },
      { id: 'studio', label: 'DataFlow 调试台', note: '编排与样本调试' },
      { id: 'resources', label: '模型与存储', note: '模型、Milvus 与图数据库' }
    ]
  },
  {
    id: 'knowledge',
    label: '知识',
    note: '资产与集合',
    defaultPage: 'knowledge',
    pages: [
      { id: 'knowledge', label: '知识资产', note: '知识库、记录与溯源' },
      { id: 'indexes', label: '索引任务', note: '入库进度与可检索状态' },
      { id: 'collections', label: '知识集合', note: '组合、版本与发布' }
    ]
  },
  {
    id: 'retrieval',
    label: '检索',
    note: '索引与召回',
    defaultPage: 'index-profiles',
    pages: [
      { id: 'index-profiles', label: '索引方案', note: '字段投影、Metadata 与版本' },
      { id: 'retrieval-profiles', label: '检索方案', note: '召回、返回字段与上下文' }
    ]
  },
  {
    id: 'application',
    label: '应用',
    note: '接入与交付',
    defaultPage: 'application-access',
    pages: [
      { id: 'application-access', label: '应用配置', note: '配置、调试与发布' }
    ]
  }
]

// Keep these exports temporarily for extensions that still consume the old registry.
// The application shell now uses lifecycleStages as its single information architecture.
export const businessNav = lifecycleStages.flatMap(stage => stage.pages.filter(page => ['overview', 'sources', 'jobs', 'knowledge', 'indexes', 'collections'].includes(page.id)))
export const developerNav = lifecycleStages.flatMap(stage => stage.pages.filter(page => !businessNav.some(item => item.id === page.id)))

export const pageMeta = {
  overview: { workspace: 'business', title: '总览', description: '掌握知识生产链路、运行状态与下一步行动' },
  sources: { workspace: 'business', title: '文档管理', description: '管理来源、文件与不可变版本', action: '上传文档' },
  jobs: { workspace: 'business', title: '处理任务', description: '把源文档转化为经过验证的知识资产', action: '新建处理任务' },
  knowledge: { workspace: 'business', title: '知识资产', description: '查看标准记录、资产状态与逐条溯源' },
  indexes: { workspace: 'business', title: '索引任务', description: '把知识资产转换为经过校验、可追溯的检索索引', action: '创建索引' },
  collections: { workspace: 'business', title: '知识集合', description: '把多个兼容知识库组合成可发布、可回滚的应用知识版本', action: '新建知识集合' },
  types: { workspace: 'developer', title: '知识类型', description: '定义业务可以生产的输出数据结构', action: '新建知识类型' },
  standard: { workspace: 'developer', title: '标准流程', description: '验证并发布业务可用的数据处理能力', action: '进入调试台' },
  studio: { workspace: 'developer', title: 'DataFlow 调试台', description: '编排流程、运行样本并检查中间结果' },
  resources: { workspace: 'developer', title: '模型与存储', description: '配置并验证 Embedding、Milvus 和图数据库连接' },
  'index-profiles': { workspace: 'developer', title: '索引方案', description: '配置向量文本、过滤字段、Metadata 与不可变版本' },
  'retrieval-profiles': { workspace: 'developer', title: '检索方案', description: '配置召回参数、返回字段与应用上下文模板' },
  'application-access': { workspace: 'developer', title: '应用配置', description: '调试并发布业务应用按稳定标识读取的运行配置' },
  'ai-applications': { workspace: 'developer', title: '应用配置', description: '调试并发布业务应用按稳定标识读取的运行配置' }
}
