<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../../api'

const busy = ref('')
const message = ref(null)
const collections = ref([])
const versions = ref([])
const bindings = ref([])
const selectedBindingId = ref('')
const events = ref([])
const result = ref(null)
const form = reactive({ binding_key: '', name: '', description: '', collection_id: '', follow_latest: true, collection_version_id: '' })
const repoint = reactive({ follow_latest: true, collection_version_id: '' })
const queryForm = reactive({ query: '', top_k: 5, filters: '{}' })

const selectedBinding = computed(() => bindings.value.find(item => item.id === selectedBindingId.value))
const formVersions = computed(() => versions.value.filter(item => item.collection_id === form.collection_id && item.status === 'published'))
const bindingVersions = computed(() => versions.value.filter(item => item.collection_id === selectedBinding.value?.collection_id && item.status === 'published'))

function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 4200) }
async function load() {
  try {
    [collections.value, versions.value, bindings.value] = await Promise.all([api.knowledgeCollections(), api.collectionVersions(), api.applicationBindings()])
    const ready = collections.value.find(item => item.current_version_id)
    if (!form.collection_id) form.collection_id = ready?.id || collections.value[0]?.id || ''
    if (!selectedBindingId.value && bindings.value.length) selectedBindingId.value = bindings.value[0].id
    if (selectedBindingId.value) await selectBinding(selectedBindingId.value)
  } catch (error) { flash(error.message, true) }
}
async function selectBinding(id) {
  selectedBindingId.value = id; result.value = null
  const binding = bindings.value.find(item => item.id === id)
  if (binding) Object.assign(repoint, { follow_latest: binding.follow_latest, collection_version_id: binding.collection_version_id || '' })
  try { events.value = await api.applicationBindingEvents(id) } catch (error) { flash(error.message, true) }
}
async function createBinding() {
  busy.value = 'create'
  try {
    const payload = { ...form, collection_version_id: form.follow_latest ? null : form.collection_version_id }
    const created = await api.createApplicationBinding(payload)
    Object.assign(form, { binding_key: '', name: '', description: '', follow_latest: true, collection_version_id: '' })
    selectedBindingId.value = created.id; await load(); flash('稳定应用接入标识已创建')
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function saveRepoint() {
  busy.value = 'repoint'
  try {
    await api.repointApplicationBinding(selectedBindingId.value, { follow_latest: repoint.follow_latest, collection_version_id: repoint.follow_latest ? null : repoint.collection_version_id })
    await load(); flash(repoint.follow_latest ? '已切换为自动跟随当前发布版' : '已固定到指定集合版本')
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function runQuery() {
  busy.value = 'query'; result.value = null
  try { result.value = await api.queryApplicationBinding(selectedBinding.value.binding_key, { query: queryForm.query, top_k: queryForm.top_k, filters: JSON.parse(queryForm.filters || '{}') }) }
  catch (error) { flash(error instanceof SyntaxError ? '过滤条件必须是合法 JSON' : error.message, true) }
  finally { busy.value = '' }
}

watch(() => form.collection_id, () => { form.collection_version_id = formVersions.value[0]?.id || '' })
watch(() => form.follow_latest, latest => { if (!latest && !form.collection_version_id) form.collection_version_id = formVersions.value[0]?.id || '' })
watch(() => repoint.follow_latest, latest => { if (!latest && !repoint.collection_version_id) repoint.collection_version_id = bindingVersions.value[0]?.id || '' })
onMounted(load)
</script>

<template>
  <section class="page developer-page delivery-page">
    <div class="developer-notice"><b>应用只保存一个稳定标识</b><span>接入标识解析到知识集合的当前发布版或固定版本。集合升级、回滚和成员调整不会改变应用调用路径。</span></div>
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>
    <div class="access-layout">
      <article class="panel access-builder">
        <div class="panel-heading"><div><span class="eyebrow">Application contract</span><h2>创建应用接入</h2></div><span class="status configured"><i></i>配置驱动</span></div>
        <form class="config-form" @submit.prevent="createBinding">
          <label><span>接入标识</span><input v-model="form.binding_key" required pattern="[a-z][a-z0-9-]{2,63}" placeholder="chronic-care"><small>将成为稳定 API 路径，仅小写字母、数字和连字符。</small></label>
          <label><span>显示名称</span><input v-model="form.name" required placeholder="例如 慢病随访助手"></label>
          <label class="wide"><span>用途说明</span><input v-model="form.description" placeholder="描述使用方与上下文用途"></label>
          <label><span>知识集合</span><select v-model="form.collection_id" required><option v-for="collection in collections" :key="collection.id" :value="collection.id" :disabled="!collection.current_version_id">{{ collection.name }} · {{ collection.current_version ? `当前 V${collection.current_version}` : '未发布' }}</option></select></label>
          <fieldset class="version-policy"><legend>版本策略</legend><label><input v-model="form.follow_latest" type="radio" :value="true"><span><b>跟随当前发布版</b><small>集合发布新版后自动生效，适合生产应用。</small></span></label><label><input v-model="form.follow_latest" type="radio" :value="false"><span><b>固定集合版本</b><small>用于回归基线、灰度与可复现实验。</small></span></label></fieldset>
          <label v-if="!form.follow_latest" class="wide"><span>固定版本</span><select v-model="form.collection_version_id" required><option v-for="version in formVersions" :key="version.id" :value="version.id">V{{ version.version }} · {{ version.retrieval_profile_name }} · {{ version.member_count }} 个知识库</option></select></label>
          <div class="wide endpoint-preview"><span>统一查询端点</span><code>POST /api/application-access/{{ form.binding_key || '{binding-key}' }}/query</code></div>
          <div class="wide form-action"><small>应用无需传检索方案、索引方案或知识库 ID。</small><button class="primary-button" :disabled="!!busy || !collections.some(item => item.current_version_id)">创建接入</button></div>
        </form>
      </article>

      <aside class="panel binding-catalog"><div class="panel-heading"><div><span class="eyebrow">Published endpoints</span><h2>已交付接入</h2></div><span class="resource-count">{{ bindings.length }}</span></div><button v-for="binding in bindings" :key="binding.id" type="button" class="binding-row" :class="{ active: binding.id === selectedBindingId }" @click="selectBinding(binding.id)"><span class="binding-symbol">API</span><span><b>{{ binding.name }}</b><code>{{ binding.binding_key }}</code><small>{{ binding.collection_name }}</small></span><span class="status available"><i></i>{{ binding.follow_latest ? '跟随最新' : `固定 V${binding.pinned_version}` }}</span></button><div v-if="!bindings.length" class="compact-empty">尚未向应用交付知识集合。</div></aside>
    </div>

    <template v-if="selectedBinding">
      <div class="access-operations">
        <article class="panel binding-control"><div class="panel-heading"><div><span class="eyebrow">Release control</span><h2>版本指向</h2></div><span class="status available"><i></i>{{ selectedBinding.binding_key }}</span></div><form @submit.prevent="saveRepoint"><fieldset class="version-policy"><legend>当前策略</legend><label><input v-model="repoint.follow_latest" type="radio" :value="true"><span><b>跟随当前发布版</b><small>当前解析到 {{ selectedBinding.collection_name }}</small></span></label><label><input v-model="repoint.follow_latest" type="radio" :value="false"><span><b>固定版本</b><small>手动选择一个已发布快照</small></span></label></fieldset><label v-if="!repoint.follow_latest"><span>目标版本</span><select v-model="repoint.collection_version_id" required><option v-for="version in bindingVersions" :key="version.id" :value="version.id">V{{ version.version }} · {{ version.member_count }} 个知识库</option></select></label><button class="primary-button" :disabled="!!busy">保存版本指向</button></form><div class="audit-list"><header><b>变更记录</b><span>{{ events.length }} 条</span></header><div v-for="event in events" :key="event.id"><span class="audit-dot"></span><span><b>{{ event.event_type === 'created' ? '创建接入' : '调整版本指向' }}</b><small>{{ event.detail.follow_latest ? '跟随当前发布版' : '固定版本' }} · {{ new Date(event.created_at).toLocaleString('zh-CN') }}</small></span></div></div></article>

        <article class="panel application-console"><div class="panel-heading"><div><span class="eyebrow">Live application query</span><h2>应用接口联调</h2></div><code>/{{ selectedBinding.binding_key }}/query</code></div><form @submit.prevent="runQuery"><label class="query-field"><span>用户问题</span><input v-model="queryForm.query" required placeholder="输入实际应用问题"></label><label><span>Top K</span><input v-model.number="queryForm.top_k" type="number" min="1" max="100"></label><label><span>过滤条件 JSON</span><input v-model="queryForm.filters" spellcheck="false"></label><button class="primary-button" :disabled="!!busy">执行检索</button></form><div v-if="result" class="application-result"><section><header><b>跨库召回 {{ result.results.length }} 条</b><span>{{ result.collection.name }} · V{{ result.collection.version }}</span></header><article v-for="(item, index) in result.results" :key="`${item.collection_member.knowledge_index_id}-${item.index_record_id}`"><span class="rank">{{ index + 1 }}</span><div><b>{{ item.collection_member.knowledge_base_name }} · {{ item.score.toFixed(4) }}</b><pre>{{ JSON.stringify(item.fields, null, 2) }}</pre><small>{{ item.source.source_name }} · {{ item.source.original_filename }}</small></div></article></section><section class="context-output"><header><b>最终上下文</b><span>按集合检索契约拼接</span></header><pre>{{ result.context }}</pre></section></div><div v-else class="console-empty"><span>⌁</span><b>等待应用请求</b><small>这里展示跨知识库排序结果和最终上下文。</small></div></article>
      </div>
    </template>
  </section>
</template>
