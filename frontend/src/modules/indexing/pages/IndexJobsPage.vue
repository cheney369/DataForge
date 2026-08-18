<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../../../api'

const busy = ref('')
const message = ref(null)
const bases = ref([])
const profiles = ref([])
const indexes = ref([])
const jobs = ref([])
const selectedBaseId = ref('')
const selectedProfileId = ref('')
const detail = ref(null)
let refreshTimer

const selectedBase = computed(() => bases.value.find(item => item.id === selectedBaseId.value))
const compatibleProfiles = computed(() => profiles.value.filter(item => item.active && item.validation_status === 'validated' && item.knowledge_type_id === selectedBase.value?.knowledge_type_id))
const running = computed(() => jobs.value.some(item => ['pending', 'running'].includes(item.status)))
function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 4200) }
function statusText(status) { return { pending: '等待中', indexing: '索引中', running: '索引中', validating: '校验中', available: '可检索', completed: '已完成', failed: '失败', cancelled: '已取消' }[status] || status }
function formatTime(value) { return value ? new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—' }
async function load(silent = false) { try { [bases.value, profiles.value, indexes.value, jobs.value] = await Promise.all([api.knowledgeBases(), api.indexProfiles(), api.knowledgeIndexes(), api.indexJobs()]); if (!selectedBaseId.value) selectedBaseId.value = bases.value[0]?.id || ''; if (!compatibleProfiles.value.some(item => item.id === selectedProfileId.value)) selectedProfileId.value = compatibleProfiles.value.find(item => item.is_default)?.id || compatibleProfiles.value[0]?.id || ''; if (detail.value) detail.value = await api.indexJob(detail.value.job.id) } catch (error) { if (!silent) flash(error.message, true) } }
async function createIndex() { busy.value = 'create'; try { const created = await api.createKnowledgeIndex({ knowledge_base_id: selectedBaseId.value, index_profile_id: selectedProfileId.value }); await load(); detail.value = await api.indexJob(created.index_job.id); flash('索引任务已创建，后台开始执行') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function showDetail(id) { busy.value = `detail-${id}`; try { detail.value = await api.indexJob(id); document.querySelector('#index-detail')?.scrollIntoView({ behavior: 'smooth' }) } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function cancel(job) { busy.value = `cancel-${job.id}`; try { await api.cancelIndexJob(job.id); await load(); flash('索引任务已取消，已完成批次会保留用于重试') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function retry(job) { busy.value = `retry-${job.id}`; try { const next = await api.retryIndexJob(job.id); await load(); detail.value = await api.indexJob(next.id); flash(`已创建第 ${next.attempt_no} 次尝试`) } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
onMounted(async () => { await load(); refreshTimer = window.setInterval(() => load(true), 2500) })
onBeforeUnmount(() => window.clearInterval(refreshTimer))
</script>

<template>
  <section class="page indexing-page">
    <div class="section-command"><div><span class="eyebrow">Knowledge indexing</span><b>知识资产是事实源，索引是可重建的应用投影</b></div><span class="status" :class="running ? 'pending' : 'available'"><i></i>{{ running ? '有任务执行中' : '服务空闲' }}</span></div>
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>
    <article id="create-index" class="panel create-index-card"><div class="panel-heading"><div><span class="eyebrow">Create index</span><h2>创建知识索引</h2></div><span class="step-label">配置驱动 · 异步执行</span></div><form @submit.prevent="createIndex"><label><span>知识资产</span><select v-model="selectedBaseId" required><option v-for="base in bases" :key="base.id" :value="base.id">{{ base.name }} · {{ base.record_count }} 条</option></select></label><div class="route-arrow">→</div><label><span>兼容的发布方案</span><select v-model="selectedProfileId" required><option v-for="profile in compatibleProfiles" :key="profile.id" :value="profile.id">{{ profile.name }} · V{{ profile.version }}{{ profile.is_default ? ' · 默认' : '' }}</option></select></label><div class="route-arrow">→</div><div class="index-destination"><span>目标</span><b>Milvus Collection</b><small>自动建表、批量向量化、计数校验</small></div><button class="primary-button" :disabled="!!busy || !compatibleProfiles.length">创建索引</button></form><div v-if="selectedBaseId && !compatibleProfiles.length" class="blocking-note">该知识类型尚无已发布的索引方案，请到开发者工作区完成配置和验证。</div></article>

    <div class="index-operations"><article class="panel index-inventory"><div class="panel-heading"><div><span class="eyebrow">Index inventory</span><h2>可重建索引</h2></div><span class="resource-count">{{ indexes.length }}</span></div><div class="index-table"><div class="table-head"><span>知识资产 / 方案</span><span>版本</span><span>记录</span><span>状态</span></div><div v-for="item in indexes" :key="item.id" class="table-row"><span><b>{{ item.knowledge_base_name }}</b><small>{{ item.index_profile_name }}</small></span><span>V{{ item.version }}<small>{{ item.collection_name }}</small></span><span>{{ item.record_count }} / {{ item.expected_count }}</span><span class="status" :class="item.status"><i></i>{{ statusText(item.status) }}</span></div><div v-if="!indexes.length" class="compact-empty">尚未创建索引。</div></div></article>
      <article class="panel job-queue"><div class="panel-heading"><div><span class="eyebrow">Execution queue</span><h2>索引任务</h2></div><span class="resource-count">{{ jobs.length }}</span></div><div class="job-list"><article v-for="job in jobs" :key="job.id"><button class="job-main" @click="showDetail(job.id)"><span class="job-state" :class="job.status">{{ job.progress }}%</span><span><b>{{ job.knowledge_base_name }}</b><small>{{ job.index_profile_name }} · 第 {{ job.attempt_no }} 次尝试 · {{ formatTime(job.created_at) }}</small></span><span class="status" :class="job.status"><i></i>{{ statusText(job.status) }}</span></button><div class="job-control"><button v-if="['pending','running'].includes(job.status)" class="text-button danger-text" :disabled="!!busy" @click="cancel(job)">取消</button><button v-if="['failed','cancelled'].includes(job.status)" class="text-button" :disabled="!!busy" @click="retry(job)">从检查点重试</button></div></article><div v-if="!jobs.length" class="compact-empty">任务队列为空。</div></div></article></div>

    <article v-if="detail" id="index-detail" class="panel index-job-detail"><div class="panel-heading"><div><span class="eyebrow">Job checkpoint</span><h2>{{ detail.job.knowledge_base_name }} · 执行详情</h2></div><button class="text-button" @click="detail=null">关闭</button></div><div class="detail-summary"><div><span>进度</span><b>{{ detail.job.progress }}%</b></div><div><span>已向量化</span><b>{{ detail.job.stats.embedded_records || 0 }}</b></div><div><span>Token 估算</span><b>{{ detail.job.stats.token_count || 0 }}</b></div><div><span>批次</span><b>{{ detail.job.stats.completed_batches || 0 }} / {{ detail.job.stats.total_batches || detail.batches.length }}</b></div></div><div class="progress-track"><i :style="{ width: `${detail.job.progress}%` }"></i></div><div v-if="detail.job.error" class="error-box"><b>失败原因</b><span>{{ detail.job.error }}</span></div><div class="batch-grid"><article v-for="batch in detail.batches" :key="batch.id"><span class="batch-number">B{{ batch.batch_no }}</span><span><b>{{ batch.record_count }} / {{ batch.record_limit }} 条</b><small>offset {{ batch.record_offset }} · {{ batch.token_count }} tokens</small></span><span class="status" :class="batch.status"><i></i>{{ statusText(batch.status) }}</span></article></div></article>
  </section>
</template>
