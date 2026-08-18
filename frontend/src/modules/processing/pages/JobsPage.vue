<script setup>
import { useDataForgeWorkspace } from '../../../composables/useDataForgeWorkspace'

const {
  jobMode, wizardStep, latestVersions, selectedVersionIds, readyKnowledgeTypes, jobForm,
  selectedType, selectedStandardPipeline, filteredJobs, selectedJobId, selectedJob,
  jobDetailLoading, jobQuery, jobStatus, busy, returnLabel, toggleVersion, nextWizardStep,
  previousWizardStep, startKnowledgeJob, closeTaskWizard, openUpload, openKnowledgeBase,
  cancelKnowledgeJob, retryKnowledgeJob, openJob, selectJob, formatSize, formatTime, statusText
} = useDataForgeWorkspace()

function engineText(engine) {
  return ({ dataflow: 'DataFlow Runtime', 'dataflow-studio': 'DataFlow Studio Pipeline', native: '本地兼容引擎' })[engine] || engine || '—'
}

function executionFor(versionId) {
  return selectedJob.value?.executions?.find(item => item.source_version_id === versionId)
}

function itemFor(versionId) {
  return selectedJob.value?.items?.find(item => item.source_version_id === versionId)
}

function eventTone(eventType) {
  if (['failed', 'source_failed'].includes(eventType)) return 'failed'
  if (['cancelled', 'cancel_requested', 'source_cancelled'].includes(eventType)) return 'cancelled'
  if (['published', 'validation_completed', 'source_completed'].includes(eventType)) return 'completed'
  if (['started', 'source_started', 'validating'].includes(eventType)) return 'running'
  return 'pending'
}
</script>

<template>
  <section class="page">
    <template v-if="jobMode === 'create'">
      <div class="wizard-heading">
        <button class="back-button" type="button" @click="closeTaskWizard">← 返回{{ returnLabel || '任务列表' }}</button>
        <div class="wizard-steps"><div v-for="(label, index) in ['选择文档', '选择知识类型', '确认生产']" :key="label" :class="{ active: wizardStep >= index + 1 }"><span>{{ index + 1 }}</span><b>{{ label }}</b></div></div>
      </div>
      <article class="panel wizard-panel">
        <template v-if="wizardStep === 1">
          <span class="eyebrow">Step 01</span><h2>选择源文档版本</h2><p class="help-text">可以选择多份文档，系统会为每个版本创建独立的 DataFlow 执行。</p>
          <div v-if="latestVersions.length" class="document-grid"><button v-for="version in latestVersions" :key="version.id" type="button" :class="{ selected: selectedVersionIds.includes(version.id) }" @click="toggleVersion(version.id)"><span class="selection">{{ selectedVersionIds.includes(version.id) ? '✓' : '' }}</span><span><b>{{ version.source_name }}</b><small>{{ version.original_filename }} · {{ formatSize(version.size_bytes) }}</small></span></button></div>
          <div v-else class="empty-state"><p>暂无可选文档</p><button class="ghost-button" type="button" @click="openUpload">去上传</button></div>
        </template>
        <template v-if="wizardStep === 2">
          <span class="eyebrow">Step 02</span><h2>选择知识类型</h2><p class="help-text">知识类型会自动匹配一条已经过样本验证并发布的标准流程。</p>
          <div class="type-grid"><button v-for="type in readyKnowledgeTypes" :key="type.id" type="button" :class="{ selected: jobForm.knowledge_type_id === type.id }" @click="jobForm.knowledge_type_id = type.id"><span class="selection">{{ jobForm.knowledge_type_id === type.id ? '✓' : '' }}</span><b>{{ type.name }}</b><small>{{ type.description }}</small></button></div>
        </template>
        <template v-if="wizardStep === 3">
          <span class="eyebrow">Step 03</span><h2>确认处理任务</h2>
          <label class="form-field"><span>知识库名称</span><input v-model="jobForm.name" placeholder="例如：临床指南知识库"></label>
          <div class="confirmation"><div><span>源文档</span><b>{{ selectedVersionIds.length }} 份</b></div><div><span>知识类型</span><b>{{ selectedType?.name }}</b></div><div><span>标准流程</span><b>{{ selectedStandardPipeline?.name || '—' }}</b><small>V{{ selectedStandardPipeline?.version }} · {{ engineText(selectedStandardPipeline?.engine) }}</small></div></div>
          <div v-if="selectedStandardPipeline" class="pipeline-route"><span class="dataflow-mark">DF</span><div><b>{{ selectedStandardPipeline.pipeline_ref }}</b><small>业务任务将锁定该已验证版本；后续默认流程更新不会改变本次任务。</small></div></div>
        </template>
        <footer class="wizard-footer"><button v-if="wizardStep > 1" class="ghost-button" type="button" @click="previousWizardStep">上一步</button><span></span><button v-if="wizardStep < 3" class="primary-button" type="button" @click="nextWizardStep">下一步</button><button v-else class="primary-button" type="button" :disabled="busy" @click="startKnowledgeJob">{{ busy ? '正在创建…' : '开始处理' }}</button></footer>
      </article>
    </template>

    <div v-else class="content-split jobs-split">
      <article class="panel list-panel">
        <div class="panel-heading"><div><span class="eyebrow">生产任务</span><h2>{{ filteredJobs.length }} 个任务</h2></div></div>
        <div class="job-toolbar" role="search"><label><span>搜索任务</span><input v-model="jobQuery" type="search" placeholder="任务、类型或流程"></label><label><span>运行状态</span><select v-model="jobStatus"><option value="">全部状态</option><option value="running">处理中</option><option value="completed">已完成</option><option value="failed">处理失败</option><option value="cancelled">已取消</option><option value="pending">等待处理</option></select></label></div>
        <div v-if="filteredJobs.length" class="entity-list"><button v-for="job in filteredJobs" :key="job.id" class="entity-row" type="button" :class="{ selected: selectedJobId === job.id }" :aria-pressed="selectedJobId === job.id" @click="selectJob(job.id)"><span class="status-dot" :class="job.status"></span><span><b>{{ job.name }}</b><small>{{ job.standard_pipeline_name }} · 第 {{ job.attempt_no || 1 }} 次 · {{ formatTime(job.created_at) }}</small></span><span class="status" :class="job.status"><i></i>{{ statusText(job.status) }}</span></button></div>
        <div v-else class="empty-state">没有符合条件的任务</div>
      </article>

      <article class="panel detail-panel job-detail">
        <template v-if="selectedJob">
          <div class="panel-heading"><div><span class="eyebrow">任务详情</span><h2>{{ selectedJob.name }}</h2></div><span class="status" :class="selectedJob.status"><i></i>{{ statusText(selectedJob.status) }}</span></div>
          <div class="progress" :aria-label="`任务进度 ${selectedJob.progress || 0}%`"><i :style="{ width: `${selectedJob.progress || 0}%` }"></i></div>
          <div class="detail-summary"><div><span>进度</span><b>{{ selectedJob.progress || 0 }}%</b></div><div><span>执行尝试</span><b>第 {{ selectedJob.attempt_no || 1 }} 次</b></div><div><span>输入版本</span><b>{{ selectedJob.source_version_ids?.length || 0 }}</b></div><div><span>知识类型</span><b>{{ selectedJob.knowledge_type_name }}</b></div></div>

          <section v-if="selectedJob.standard_pipeline" class="job-section pipeline-card">
            <div class="section-heading"><div><span class="eyebrow">执行路线</span><h3>实际使用的 DataFlow 流程</h3></div><span class="status validated"><i></i>样本已验证</span></div>
            <div class="pipeline-route"><span class="dataflow-mark">DF</span><div><b>{{ selectedJob.standard_pipeline.name }} · V{{ selectedJob.standard_pipeline.version }}</b><small>{{ engineText(selectedJob.standard_pipeline.engine) }} / {{ selectedJob.standard_pipeline.pipeline_ref }}</small></div></div>
          </section>

          <section v-if="selectedJob.sources?.length" class="job-section">
            <div class="section-heading"><div><span class="eyebrow">Inputs</span><h3>输入与执行结果</h3></div><span v-if="jobDetailLoading" class="detail-loading">正在同步…</span></div>
            <div class="job-inputs"><div v-for="source in selectedJob.sources" :key="source.source_version_id"><span class="file-badge">V{{ source.version_no }}</span><span><b>{{ source.source_name }}</b><small>{{ source.original_filename }} · {{ formatSize(source.size_bytes) }}</small></span><span v-if="executionFor(source.source_version_id)" class="execution-result"><b>{{ executionFor(source.source_version_id).record_count }} 条</b><small>{{ engineText(executionFor(source.source_version_id).engine) }}</small></span><span v-else class="status" :class="itemFor(source.source_version_id)?.status || selectedJob.status"><i></i>{{ statusText(itemFor(source.source_version_id)?.status || selectedJob.status) }}</span></div></div>
          </section>

          <section v-if="selectedJob.validation?.checked_records" class="job-section validation-card">
            <div class="section-heading"><div><span class="eyebrow">Output gate</span><h3>输出格式验证</h3></div><span class="status" :class="selectedJob.validation.passed ? 'validated' : 'failed'"><i></i>{{ selectedJob.validation.passed ? '全部通过' : '存在异常' }}</span></div>
            <div class="validation-metrics"><div><span>检查记录</span><b>{{ selectedJob.validation.checked_records }}</b></div><div><span>有效记录</span><b>{{ selectedJob.validation.valid_records }}</b></div><div><span>异常记录</span><b>{{ selectedJob.validation.invalid_records }}</b></div></div>
          </section>

          <section v-if="selectedJob.events?.length" class="job-section">
            <div class="section-heading"><div><span class="eyebrow">Activity</span><h3>处理动态</h3></div><small class="event-count">{{ selectedJob.events.length }} 条事件</small></div>
            <ol class="job-timeline" aria-label="任务处理动态">
              <li v-for="event in [...selectedJob.events].reverse()" :key="event.id">
                <span class="status-dot" :class="eventTone(event.event_type)" aria-hidden="true"></span>
                <span><b>{{ event.message }}</b><small>{{ formatTime(event.created_at) }}</small></span>
              </li>
            </ol>
          </section>

          <div v-if="selectedJob.error" class="error-box" role="alert"><b>任务执行失败</b><span>{{ selectedJob.error }}</span></div>
          <div class="job-actions"><button v-if="selectedJob.retry_of_job_id" class="ghost-button" type="button" @click="openJob(selectedJob.retry_of_job_id)">查看上一次尝试</button><button v-if="selectedJob.retry_job" class="ghost-button" type="button" @click="openJob(selectedJob.retry_job.id)">查看第 {{ selectedJob.retry_job.attempt_no }} 次尝试</button><button v-if="['pending', 'running'].includes(selectedJob.status)" class="ghost-button cancel-button" type="button" :disabled="busy" @click="cancelKnowledgeJob">{{ busy ? '正在取消…' : '取消任务' }}</button><button v-else-if="!selectedJob.retry_job && ['failed', 'cancelled'].includes(selectedJob.status)" class="primary-button" type="button" :disabled="busy" @click="retryKnowledgeJob">{{ busy ? '正在创建重试…' : '重新尝试' }}</button><button v-if="selectedJob.knowledge_base_id" class="primary-button" type="button" @click="openKnowledgeBase(selectedJob.knowledge_base_id)">查看知识资产</button></div>
        </template>
        <div v-else class="empty-state">选择任务查看执行详情</div>
      </article>
    </div>
  </section>
</template>
