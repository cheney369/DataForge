<script setup>
import { computed } from 'vue'
import AppIcon from '../../../components/AppIcon.vue'
import { useDataForgeWorkspace } from '../../../composables/useDataForgeWorkspace'

const {
  dashboard, sources, knowledgeTypes, knowledgeBases, knowledgeJobs,
  runningJobs, totalRecords, readyKnowledgeTypes, openTaskWizard, openUpload, openJob,
  openKnowledgeBase, formatTime, statusText, navigate
} = useDataForgeWorkspace()

const quickAction = computed(() => {
  if (!sources.value.length) return { title: '上传第一份文档', description: '建立可追溯的数据来源，系统会自动识别格式并保存版本。', label: '上传文档', action: openUpload }
  if (!readyKnowledgeTypes.value.length) return { title: '发布标准生产流程', description: '定义输出结构并验证 DataFlow 流程，让生产能力可以稳定复用。', label: '配置流程', action: () => navigate('types') }
  return { title: '创建知识生产任务', description: '数据与标准能力已就绪，可以直接选择目标知识类型开始生产。', label: '开始生产', action: () => openTaskWizard() }
})

const attentionItems = computed(() => {
  const items = []
  const failed = knowledgeJobs.value.filter(job => job.status === 'failed').length
  const activeTypes = knowledgeTypes.value.filter(type => type.active).length
  const unreadyTypes = Math.max(activeTypes - readyKnowledgeTypes.value.length, 0)
  const bases = dashboard.value.knowledge_counts?.knowledge_bases || knowledgeBases.value.length
  const searchable = dashboard.value.knowledge_counts?.searchable_bases || 0
  const unsearchable = Math.max(bases - searchable, 0)
  if (failed) items.push({ level: 'danger', title: `${failed} 个任务执行失败`, note: '查看错误详情并重新运行', page: 'jobs' })
  if (unreadyTypes) items.push({ level: 'warning', title: `${unreadyTypes} 个知识类型未就绪`, note: '验证并发布对应标准流程', page: 'standard' })
  if (unsearchable) items.push({ level: 'warning', title: `${unsearchable} 个知识库不可检索`, note: '创建索引后即可交付应用', page: 'indexes' })
  if (!items.length) items.push({ level: 'success', title: '生产链路运行正常', note: '当前没有失败任务或阻塞项', page: 'jobs' })
  return items
})

const attentionTitle = computed(() => (
  attentionItems.value.length === 1 && attentionItems.value[0].level === 'success'
    ? '当前运行正常'
    : `${attentionItems.value.length} 项需要处理`
))

const lifecycleModules = computed(() => {
  const counts = dashboard.value.knowledge_counts || {}
  const delivery = dashboard.value.health?.delivery || {}
  const applications = dashboard.value.health?.applications || {}
  const activeTypes = knowledgeTypes.value.filter(type => type.active).length
  const modules = [
    { id: 'data', icon: 'data', title: '数据接入', description: '上传、解析与版本', value: sources.value.length, unit: '份来源', page: 'sources', ready: sources.value.length > 0 },
    { id: 'flow', icon: 'flow', title: '流程定义', description: 'Schema 与算子编排', value: readyKnowledgeTypes.value.length, unit: `/${activeTypes} 种就绪`, page: 'types', ready: readyKnowledgeTypes.value.length > 0 },
    { id: 'knowledge', icon: 'knowledge', title: '知识生产', description: '资产、记录与溯源', value: knowledgeBases.value.length, unit: `${totalRecords.value} 条记录`, page: 'knowledge', ready: knowledgeBases.value.length > 0 },
    { id: 'retrieval', icon: 'retrieval', title: '索引检索', description: '向量入库与召回', value: counts.knowledge_indexes || 0, unit: `${counts.searchable_bases || 0} 个可检索`, page: 'indexes', ready: (counts.searchable_bases || 0) > 0 },
    { id: 'application', icon: 'application', title: '应用交付', description: '稳定接入与 AI 应用', value: (delivery.application_bindings || 0) + (applications.ai_applications || 0), unit: '个接入/应用', page: 'application-access', ready: (delivery.application_bindings || 0) + (applications.ai_applications || 0) > 0 }
  ]
  const firstPending = modules.findIndex(item => !item.ready)
  return modules.map((item, index) => ({ ...item, state: item.ready ? 'ready' : index === firstPending ? 'current' : 'pending', stateLabel: item.ready ? '已完成' : index === firstPending ? '下一步' : '待配置' }))
})

const metrics = computed(() => [
  { label: '来源文档', value: sources.value.length, note: `${dashboard.value.counts?.source_versions || 0} 个版本`, icon: 'sources' },
  { label: '生产任务', value: knowledgeJobs.value.length, note: `${runningJobs.value.length} 个执行中`, icon: 'jobs' },
  { label: '知识资产', value: knowledgeBases.value.length, note: `${totalRecords.value} 条记录`, icon: 'knowledge' },
  { label: '可检索库', value: dashboard.value.knowledge_counts?.searchable_bases || 0, note: `共 ${dashboard.value.knowledge_counts?.knowledge_bases || knowledgeBases.value.length} 个`, icon: 'retrieval' }
])

const readiness = computed(() => {
  const health = dashboard.value.health || {}
  return [
    { label: '文档解析', ready: health.parsers?.native?.available, note: health.parsers?.mineru?.available ? '原生解析 + MinerU' : '原生解析已就绪' },
    { label: '模型服务', ready: (health.indexing?.llm_services || 0) > 0 && (health.indexing?.embedding_services || 0) > 0, note: `${health.indexing?.llm_services || 0} LLM · ${health.indexing?.embedding_services || 0} Embedding` },
    { label: '向量存储', ready: (health.indexing?.vector_stores || 0) > 0, note: `${health.indexing?.vector_stores || 0} 个连接` },
    { label: '检索方案', ready: (health.indexing?.published_profiles || 0) > 0, note: `${health.indexing?.published_profiles || 0} 个已发布` }
  ]
})

const recentActivity = computed(() => {
  const jobs = knowledgeJobs.value.map(job => ({ id: job.id, kind: 'job', icon: 'jobs', title: job.name, note: job.knowledge_type_name || '知识生产任务', time: job.created_at, status: job.status, statusLabel: statusText(job.status) }))
  const bases = knowledgeBases.value.map(base => ({ id: base.id, kind: 'base', icon: 'knowledge', title: base.name, note: `${base.knowledge_type_name || '知识资产'} · ${base.record_count || 0} 条记录`, time: base.created_at || base.updated_at, status: 'available', statusLabel: '已入库' }))
  return [...jobs, ...bases].sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0)).slice(0, 7)
})

function openActivity(item) {
  if (item.kind === 'job') openJob(item.id)
  else openKnowledgeBase(item.id)
}
</script>

<template>
  <section class="page overview-page cockpit-overview">
    <div class="overview-ambient" aria-hidden="true">
      <i class="ambient-bloom bloom-one"></i>
      <i class="ambient-bloom bloom-two"></i>
      <i class="ambient-data-field"></i>
    </div>
    <section class="command-center" aria-labelledby="command-title">
      <div class="command-grid" aria-hidden="true"></div>
      <div class="command-copy">
        <div class="live-label"><i></i><span>DATAFORGE CONTROL CENTER</span><em>ONLINE</em></div>
        <h2 id="command-title">{{ quickAction.title }}</h2>
        <p>{{ quickAction.description }}</p>
        <div class="command-actions">
          <button class="primary-button large" type="button" @click="quickAction.action">{{ quickAction.label }} <span>→</span></button>
          <button class="command-secondary" type="button" @click="navigate('standard')">查看标准链路</button>
        </div>
      </div>
      <div class="command-metrics" aria-label="核心数据指标">
        <article v-for="metric in metrics" :key="metric.label">
          <span class="metric-icon"><AppIcon :name="metric.icon" size="16" /></span>
          <div><small>{{ metric.label }}</small><strong>{{ metric.value }}</strong><em>{{ metric.note }}</em></div>
        </article>
      </div>
    </section>

    <div class="cockpit-grid">
      <section class="lifecycle-console" aria-labelledby="lifecycle-title">
        <header class="console-heading">
          <div><span class="console-kicker">生产链路</span><h2 id="lifecycle-title">从数据接入到应用交付</h2></div>
          <button type="button" @click="navigate('studio')">进入流程工作台 <span>↗</span></button>
        </header>
        <div class="lifecycle-track">
          <button v-for="(item, index) in lifecycleModules" :key="item.id" type="button" :class="item.state" @click="navigate(item.page)">
            <span class="track-index">0{{ index + 1 }}</span>
            <span class="track-icon"><AppIcon :name="item.icon" size="18" /></span>
            <span class="track-copy"><b>{{ item.title }}</b><small>{{ item.description }}</small></span>
            <span class="track-value"><strong>{{ item.value }}</strong><small>{{ item.unit }}</small></span>
            <span class="track-state"><i></i>{{ item.stateLabel }}</span>
          </button>
        </div>
      </section>

      <aside class="focus-console" aria-labelledby="focus-title">
        <header class="console-heading"><div><span class="console-kicker">运行关注</span><h2 id="focus-title">{{ attentionTitle }}</h2></div></header>
        <div class="focus-list">
          <button v-for="item in attentionItems" :key="item.title" type="button" :class="item.level" @click="navigate(item.page)">
            <span class="focus-signal"><i></i></span><span><b>{{ item.title }}</b><small>{{ item.note }}</small></span><em>→</em>
          </button>
        </div>
      </aside>
    </div>

    <div class="operations-grid">
      <section class="activity-console panel" aria-labelledby="activity-title">
        <header class="console-heading"><div><span class="console-kicker">最近活动</span><h2 id="activity-title">生产运行记录</h2></div><button type="button" @click="navigate('jobs')">全部记录 →</button></header>
        <div v-if="recentActivity.length" class="activity-list">
          <button v-for="item in recentActivity" :key="`${item.kind}-${item.id}`" type="button" @click="openActivity(item)">
            <span class="activity-icon"><AppIcon :name="item.icon" size="16" /></span>
            <span><b>{{ item.title }}</b><small>{{ item.note }}</small></span>
            <time>{{ formatTime(item.time) }}</time>
            <span class="status" :class="item.status"><i></i>{{ item.statusLabel }}</span>
          </button>
        </div>
        <div v-else class="empty-state">暂无生产活动</div>
      </section>

      <section class="readiness-console panel" aria-labelledby="readiness-title">
        <header class="console-heading"><div><span class="console-kicker">环境状态</span><h2 id="readiness-title">能力就绪度</h2></div><button type="button" @click="navigate('resources')">管理资源 →</button></header>
        <div class="readiness-matrix">
          <button v-for="item in readiness" :key="item.label" type="button" @click="navigate(item.label === '检索方案' ? 'retrieval-profiles' : 'resources')">
            <span class="readiness-signal" :class="{ ready: item.ready }"><i></i></span><span><b>{{ item.label }}</b><small>{{ item.note }}</small></span><em>{{ item.ready ? 'READY' : 'CONFIG' }}</em>
          </button>
        </div>
      </section>
    </div>

    <section class="config-console panel" aria-labelledby="config-title">
      <header class="console-heading"><div><span class="console-kicker">深度配置</span><h2 id="config-title">构建标准生产链路</h2></div><p>按需控制输出结构、处理算子、索引字段和检索策略。</p></header>
      <div class="config-links">
        <button type="button" @click="navigate('types')"><span>01</span><AppIcon name="types" /><b>定义知识结构</b><small>Schema 与元数据</small><em>→</em></button>
        <button type="button" @click="navigate('studio')"><span>02</span><AppIcon name="studio" /><b>编排处理流程</b><small>DataFlow 算子调试</small><em>→</em></button>
        <button type="button" @click="navigate('index-profiles')"><span>03</span><AppIcon name="index-profiles" /><b>设计索引方案</b><small>向量、过滤与返回字段</small><em>→</em></button>
        <button type="button" @click="navigate('ai-applications')"><span>04</span><AppIcon name="ai-applications" /><b>交付 AI 应用</b><small>Prompt、检索与模型</small><em>→</em></button>
      </div>
    </section>
  </section>
</template>
