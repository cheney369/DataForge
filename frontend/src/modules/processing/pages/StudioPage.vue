<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../../../api'
import { useDataForgeWorkspace } from '../../../composables/useDataForgeWorkspace'

const {
  studioStatus, dataflowHealth, dataflowTasks, publishForm,
  navigate, refreshAll
} = useDataForgeWorkspace()

const frameReady = ref(false)
const healthOpen = ref(false)
const validating = ref(false)
const validation = ref(null)
const editorState = ref({
  ready: false,
  pipeline: null,
  operator_count: 0,
  dataset_name: '',
  execution: null
})

const runtimeReady = computed(() => (dataflowHealth.value.runtime || []).every(item => item.status === 'ready'))
const currentTaskCount = computed(() => {
  const pipelineId = editorState.value.pipeline?.id
  return pipelineId ? dataflowTasks.value.filter(task => task.pipeline_id === pipelineId && task.status === 'completed').length : 0
})
const editorStatusText = computed(() => {
  if (!editorState.value.pipeline) return '请选择或创建一个流程草稿'
  const name = editorState.value.pipeline.name
  const count = editorState.value.operator_count || 0
  return `${name} · ${count} 个算子`
})
const executionText = computed(() => {
  const execution = editorState.value.execution
  if (!execution?.task_id) return currentTaskCount.value ? `${currentTaskCount.value} 个成功样本` : '尚未运行样本'
  return ({ running: '样本运行中', completed: '样本运行完成', failed: '样本运行失败', cancelled: '样本已取消' })[execution.status] || '任务状态同步中'
})

function receiveStudioState(event) {
  if (event.origin !== window.location.origin || event.data?.source !== 'dataflow-studio') return
  if (event.data.type === 'ready') {
    frameReady.value = true
    editorState.value.ready = true
    return
  }
  if (event.data.type !== 'state') return
  const previousStatus = editorState.value.execution?.status
  editorState.value = { ...editorState.value, ...event.data.payload, ready: true }
  frameReady.value = true
  if (event.data.payload?.pipeline?.id !== validation.value?.pipeline_id) validation.value = null
  const nextStatus = event.data.payload?.execution?.status
  if (nextStatus && nextStatus !== previousStatus && ['completed', 'failed', 'cancelled'].includes(nextStatus)) {
    refreshAll(true)
  }
}

async function validateDraft() {
  const pipeline = editorState.value.pipeline
  if (!pipeline?.id || pipeline.is_template) {
    validation.value = { status: 'warning', message: pipeline?.is_template ? '请先把模板保存为自定义流程' : '请先选择一个流程' }
    return
  }
  validating.value = true
  try {
    const result = await api.validateDataflowPipeline(pipeline.id)
    const errors = result.errors || []
    const warnings = result.warnings || []
    validation.value = {
      pipeline_id: pipeline.id,
      status: errors.length ? 'failed' : warnings.length ? 'warning' : 'validated',
      message: errors.length
        ? `发现 ${errors.length} 个阻断问题`
        : warnings.length
          ? `检查通过，另有 ${warnings.length} 条提示`
          : '静态检查通过，可以运行样本'
    }
  } catch (error) {
    validation.value = { pipeline_id: pipeline.id, status: 'failed', message: error.message }
  } finally {
    validating.value = false
  }
}

function goToPublish() {
  const pipeline = editorState.value.pipeline
  if (pipeline?.id && !pipeline.is_template) publishForm.dataflow_pipeline_id = pipeline.id
  navigate('standard')
}

function openStandalone() {
  window.open('/studio/#/m/', '_blank', 'noopener,noreferrer')
}

onMounted(() => window.addEventListener('message', receiveStudioState))
onBeforeUnmount(() => window.removeEventListener('message', receiveStudioState))
</script>

<template>
  <section class="studio-page">
    <header class="studio-workbench-bar">
      <div class="studio-engine-context">
        <span class="studio-engine-mark" aria-hidden="true">DF</span>
        <span><b>Pipeline Workbench</b><small>{{ editorStatusText }}</small></span>
        <span class="status" :class="studioStatus.available && runtimeReady ? 'validated' : 'failed'"><i></i>{{ studioStatus.available && runtimeReady ? '引擎已连接' : '引擎异常' }}</span>
      </div>
      <div class="studio-actions">
        <span v-if="validation" class="studio-validation" :class="validation.status" role="status">{{ validation.message }}</span>
        <button class="ghost-button" type="button" :aria-expanded="healthOpen" @click="healthOpen = !healthOpen">运行环境</button>
        <button class="ghost-button" type="button" :disabled="validating" @click="validateDraft">{{ validating ? '检查中…' : '检查草稿' }}</button>
        <button class="primary-button" type="button" @click="goToPublish">去验证发布</button>
      </div>
    </header>

    <section v-if="healthOpen" class="studio-health-drawer" aria-label="DataFlow 运行环境">
      <header><span><b>运行依赖与标准流程状态</b><small>{{ dataflowHealth.summary?.available_operators || 0 }} 个算子 · {{ dataflowHealth.summary?.ready_servings || 0 }} 个模型服务就绪</small></span><button type="button" aria-label="关闭运行环境面板" @click="healthOpen = false">×</button></header>
      <div class="health-grid">
        <article v-for="check in dataflowHealth.runtime" :key="check.id">
          <span class="health-indicator" :class="check.status" aria-hidden="true"></span>
          <span><b>{{ check.name }}</b><small>{{ check.message }}</small></span>
        </article>
        <article v-for="pipeline in dataflowHealth.pipelines" :key="pipeline.id">
          <span class="health-indicator" :class="pipeline.status"></span>
          <span><b>{{ pipeline.name }}</b><small v-if="pipeline.issues?.length">已登记版本：{{ pipeline.issues.map(issue => issue.message).join('；') }}</small><small v-else>已发布版本：{{ pipeline.operator_count }} 个算子，当前可执行</small></span>
        </article>
      </div>
    </section>

    <div v-if="studioStatus.available" class="studio-frame-shell">
      <div class="studio-frame-meta">
        <span><i class="draft-dot"></i><b>DataFlow 当前草稿</b><small>{{ editorStatusText }}</small></span>
        <span><b>样本状态</b><small>{{ executionText }}</small></span>
        <button class="text-button" type="button" @click="openStandalone">独立打开原工作台 ↗</button>
      </div>
      <div v-if="!frameReady" class="studio-frame-loading"><span></span><b>正在连接 DataFlow 编辑器…</b></div>
      <iframe class="studio-frame" src="/studio/?embedded=1&theme=glass-v1#/m/" title="DataFlow Pipeline 编辑器" @load="frameReady = true"></iframe>
    </div>
    <div v-else class="studio-unavailable"><b>DataFlow 调试台未启动</b><span>{{ studioStatus.message || '请检查 DataFlow 环境配置。' }}</span></div>
  </section>
</template>
