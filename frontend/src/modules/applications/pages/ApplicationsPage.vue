<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../../api'

const busy = ref('')
const message = ref(null)
const applications = ref([])
const bindings = ref([])
const collections = ref([])
const collectionVersions = ref([])
const llmServices = ref([])
const selectedApplicationId = ref('')
const detail = ref(null)
const selectedVersion = ref(null)
const activeStage = ref('configure')
const showCreate = ref(false)
const showBindingBuilder = ref(false)
const publishedConfig = ref(null)
const conversation = ref([])
const chatInput = ref('')
const filters = ref('{}')
const previewInputs = ref('{}')
const showEvidence = ref(true)
const lastRetrieval = ref(null)
const chatScroll = ref(null)
const appForm = reactive({ app_key: '', name: '', description: '' })
const bindingForm = reactive({ binding_key: '', name: '', description: '', collection_id: '', follow_latest: true, collection_version_id: '' })
const defaultInputSchema = JSON.stringify({
  type: 'object', properties: { query: { type: 'string', title: '用户问题', minLength: 1 } },
  required: ['query'], additionalProperties: true
}, null, 2)
const defaultOutputSchema = JSON.stringify({
  type: 'object', properties: { answer: { type: 'string', title: '生成结果' } },
  required: ['answer'], additionalProperties: false
}, null, 2)
const versionForm = reactive({
  application_binding_id: '', llm_service_id: '',
  system_prompt: '你是一个严谨的知识助手。请仅依据以下知识上下文回答；没有依据时明确说明不知道。\n\n知识上下文：\n{{ context }}',
  user_prompt: '请回答用户问题：{{ question }}', temperature: 0.2, max_tokens: 1024, top_k: 5,
  query_field: 'query', prompt_variables: JSON.stringify({ question: 'query' }, null, 2),
  input_schema: defaultInputSchema, output_schema: defaultOutputSchema,
  allowed_filter_fields: '', include_citations: true
})

const selectedApplication = computed(() => applications.value.find(item => item.id === selectedApplicationId.value))
const readyBindings = computed(() => bindings.value.filter(item => item.active))
const readyLLMs = computed(() => llmServices.value.filter(item => item.active))
const readyCollections = computed(() => collections.value.filter(item => item.current_version_id))
const bindingVersions = computed(() => collectionVersions.value.filter(item => item.collection_id === bindingForm.collection_id && item.status === 'published'))
const currentVersion = computed(() => detail.value?.versions?.find(item => item.is_current))
const canPublish = computed(() => selectedVersion.value?.status === 'draft')
const configEndpoint = computed(() => selectedApplication.value ? `${window.location.origin}/v1/application-configs/${selectedApplication.value.app_key}` : '')
const configJson = computed(() => publishedConfig.value ? JSON.stringify(publishedConfig.value, null, 2) : '')
const fetchExample = computed(() => `const config = await fetch('${configEndpoint.value}').then(response => response.json())\n\n// 应用代码保持不变；平台发布新版本后，这里自动读取当前配置。\nconst { knowledge, retrieval, prompt, generation, model, contract } = config`)

function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 4400) }
function usageText(usage = {}) { return usage.total_tokens ? `${usage.total_tokens} tokens` : 'Token 未返回' }
function normalizeKey(value) {
  return String(value || '').trim().toLowerCase().replace(/[_\s]+/g, '-').replace(/[^a-z0-9-]/g, '').replace(/-+/g, '-').replace(/^-|-$/g, '')
}
async function load() {
  try {
    [applications.value, bindings.value, llmServices.value, collections.value, collectionVersions.value] = await Promise.all([api.aiApplications(), api.applicationBindings(), api.llmServices(), api.knowledgeCollections(), api.collectionVersions()])
    if (!versionForm.application_binding_id) versionForm.application_binding_id = readyBindings.value[0]?.id || ''
    if (!versionForm.llm_service_id) versionForm.llm_service_id = readyLLMs.value[0]?.id || ''
    if (!bindingForm.collection_id) bindingForm.collection_id = readyCollections.value[0]?.id || ''
    if (!selectedApplicationId.value && applications.value.length) selectedApplicationId.value = applications.value[0].id
    if (selectedApplicationId.value) await selectApplication(selectedApplicationId.value, true)
    showCreate.value = !applications.value.length
  } catch (error) { flash(error.message, true) }
}
async function selectApplication(id, silent = false) {
  selectedApplicationId.value = id
  showCreate.value = false
  if (!silent) { conversation.value = []; lastRetrieval.value = null }
  try {
    detail.value = await api.aiApplication(id)
    selectedVersion.value = detail.value.versions.find(item => item.is_current) || detail.value.versions[0] || null
    if (!bindingForm.binding_key) bindingForm.binding_key = `${selectedApplication.value?.app_key || 'application'}-knowledge`.slice(0, 64)
    if (!bindingForm.name) bindingForm.name = `${selectedApplication.value?.name || '应用'}知识接入`
    await loadPublishedConfig()
  } catch (error) { flash(error.message, true) }
}
async function createBinding() {
  busy.value = 'binding'
  try {
    const binding_key = normalizeKey(bindingForm.binding_key)
    if (!/^[a-z][a-z0-9-]{2,63}$/.test(binding_key)) throw new Error('知识接入标识需以小写字母开头，长度为 3–64 位')
    const created = await api.createApplicationBinding({
      ...bindingForm,
      binding_key,
      collection_version_id: bindingForm.follow_latest ? null : bindingForm.collection_version_id
    })
    versionForm.application_binding_id = created.id
    Object.assign(bindingForm, { binding_key: '', name: '', description: '', follow_latest: true, collection_version_id: '' })
    showBindingBuilder.value = false
    await load()
    flash('知识接入已创建，并已选入当前草稿')
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function loadPublishedConfig() {
  publishedConfig.value = null
  if (!selectedApplication.value?.current_version) return
  try { publishedConfig.value = await api.publishedApplicationConfig(selectedApplication.value.app_key) }
  catch (error) { flash(error.message, true) }
}
async function createApplication() {
  busy.value = 'application'
  try {
    const app_key = normalizeKey(appForm.app_key)
    if (!/^[a-z][a-z0-9-]{2,63}$/.test(app_key)) throw new Error('应用标识需以小写字母开头，长度为 3–64 位')
    const created = await api.createAIApplication({ ...appForm, app_key })
    Object.assign(appForm, { app_key: '', name: '', description: '' })
    selectedApplicationId.value = created.id
    showCreate.value = false
    await load()
    flash(`应用配置已创建，稳定标识为 ${app_key}`)
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function createVersion() {
  busy.value = 'version'
  try {
    const created = await api.createAIApplicationVersion(selectedApplicationId.value, {
      application_binding_id: versionForm.application_binding_id,
      llm_service_id: versionForm.llm_service_id,
      config: {
        system_prompt: versionForm.system_prompt, user_prompt: versionForm.user_prompt,
        temperature: versionForm.temperature, max_tokens: versionForm.max_tokens, top_k: versionForm.top_k,
        query_field: versionForm.query_field, prompt_variables: JSON.parse(versionForm.prompt_variables),
        input_schema: JSON.parse(versionForm.input_schema), output_schema: JSON.parse(versionForm.output_schema),
        allowed_filter_fields: versionForm.allowed_filter_fields.split(',').map(item => item.trim()).filter(Boolean),
        include_citations: versionForm.include_citations
      }
    })
    await load()
    selectedVersion.value = created
    activeStage.value = 'debug'
    flash(`V${created.version} 草稿已保存，可以开始 RAG 调试`)
  } catch (error) { flash(error instanceof SyntaxError ? '调用契约必须是合法 JSON' : error.message, true) } finally { busy.value = '' }
}
function editFromVersion(version) {
  selectedVersion.value = version
  Object.assign(versionForm, {
    application_binding_id: version.application_binding_id, llm_service_id: version.llm_service_id,
    system_prompt: version.config.system_prompt, user_prompt: version.config.user_prompt,
    temperature: version.config.temperature, max_tokens: version.config.max_tokens, top_k: version.config.top_k,
    query_field: version.config.query_field || 'query',
    prompt_variables: JSON.stringify(version.config.prompt_variables || { question: 'query' }, null, 2),
    input_schema: JSON.stringify(version.config.input_schema || JSON.parse(defaultInputSchema), null, 2),
    output_schema: JSON.stringify(version.config.output_schema || JSON.parse(defaultOutputSchema), null, 2),
    allowed_filter_fields: (version.config.allowed_filter_fields || []).join(', '),
    include_citations: version.config.include_citations !== false
  })
}
async function publishVersion() {
  if (!canPublish.value) return
  busy.value = 'publish'
  try {
    const published = await api.publishAIApplicationVersion(selectedVersion.value.id)
    await load()
    selectedVersion.value = published
    activeStage.value = 'release'
    flash(`检查通过，V${published.version} 已成为当前发布配置`)
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function copyText(text, label) {
  try { await navigator.clipboard.writeText(text); flash(`${label}已复制`) }
  catch (_) { flash('浏览器未授权剪贴板，请手动复制', true) }
}
async function sendMessage() {
  const text = chatInput.value.trim()
  if (!text || !selectedVersion.value) return
  const history = conversation.value.map(item => ({ role: item.role, content: item.content }))
  conversation.value.push({ role: 'user', content: text })
  chatInput.value = ''; busy.value = 'chat'; await scrollChat()
  try {
    const inputs = JSON.parse(previewInputs.value || '{}')
    setInputPath(inputs, selectedVersion.value.config.query_field || 'query', text)
    const response = await api.previewAIApplicationVersion(selectedVersion.value.id, { inputs, history, filters: JSON.parse(filters.value || '{}') })
    conversation.value.push({ role: 'assistant', content: response.answer, usage: response.usage, latency: response.llm_latency_ms, run_id: response.run_id })
    lastRetrieval.value = response.retrieval
    detail.value = await api.aiApplication(selectedApplicationId.value)
  } catch (error) {
    conversation.value.push({ role: 'assistant', content: `运行失败：${error instanceof SyntaxError ? '附加输入或过滤条件必须是合法 JSON' : error.message}`, failed: true })
  } finally { busy.value = ''; await scrollChat() }
}
function setInputPath(target, path, value) {
  const parts = path.split('.'); let current = target
  parts.slice(0, -1).forEach(part => { if (!current[part] || typeof current[part] !== 'object') current[part] = {}; current = current[part] })
  current[parts.at(-1)] = value
}
async function scrollChat() { await nextTick(); if (chatScroll.value) chatScroll.value.scrollTop = chatScroll.value.scrollHeight }

watch(() => bindingForm.collection_id, () => { bindingForm.collection_version_id = bindingVersions.value[0]?.id || '' })
watch(() => bindingForm.follow_latest, latest => { if (!latest && !bindingForm.collection_version_id) bindingForm.collection_version_id = bindingVersions.value[0]?.id || '' })
onMounted(load)
</script>

<template>
  <section class="page developer-page ai-app-page app-config-page">
    <div class="developer-notice"><b>一份配置，完成调试与交付</b><span>业务应用只保存稳定的 app_key，并读取平台当前发布配置；知识集合、检索、Prompt 与模型都在这里演进。</span></div>
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>

    <div class="app-config-shell">
      <aside class="panel ai-app-catalog">
        <div class="panel-heading"><div><span class="eyebrow">Application configs</span><h2>应用配置</h2></div><button v-if="applications.length" class="text-button" type="button" @click="showCreate = !showCreate">{{ showCreate ? '取消' : '+ 新建' }}</button></div>
        <button v-for="item in applications" :key="item.id" type="button" :class="{ active: item.id === selectedApplicationId }" @click="selectApplication(item.id)"><span class="app-symbol">CFG</span><span><b>{{ item.name }}</b><code>{{ item.app_key }}</code><small>{{ item.version_count }} 个配置版本</small></span><span class="status" :class="item.current_version ? 'available' : 'configured'"><i></i>{{ item.current_version ? `线上 V${item.current_version}` : '未发布' }}</span></button>
        <div v-if="!applications.length" class="compact-empty">还没有应用配置，从稳定标识开始。</div>
      </aside>

      <main class="ai-app-main">
        <article v-if="showCreate" class="panel app-identity-card">
          <div class="panel-heading"><div><span class="eyebrow">Stable identity</span><h2>新建应用配置</h2></div><span class="step-label">代码长期只使用这个标识</span></div>
          <form class="config-form" @submit.prevent="createApplication"><label><span>应用标识 app_key</span><input v-model="appForm.app_key" required placeholder="chronic-care-assistant"><small>下划线和空格会自动转成连字符。</small></label><label><span>应用名称</span><input v-model="appForm.name" required placeholder="例如 慢病随访助手"></label><label class="wide"><span>用途说明</span><input v-model="appForm.description" placeholder="面向哪些用户，解决什么问题"></label><div class="wide form-action"><small>之后的修改都会创建新版本，不改变业务应用中的接入代码。</small><button class="primary-button" :disabled="!!busy">创建配置</button></div></form>
        </article>

        <template v-if="selectedApplication && !showCreate">
          <nav class="panel config-stage-nav" aria-label="应用配置流程">
            <button type="button" :class="{ active: activeStage === 'configure' }" @click="activeStage = 'configure'"><span>01</span><b>配置草稿</b><small>知识、Prompt 与模型</small></button>
            <button type="button" :class="{ active: activeStage === 'debug' }" :disabled="!selectedVersion" @click="activeStage = 'debug'"><span>02</span><b>RAG 调试</b><small>召回、上下文与回答</small></button>
            <button type="button" :class="{ active: activeStage === 'release' }" @click="activeStage = 'release'"><span>03</span><b>校验发布</b><small>当前配置与版本历史</small></button>
          </nav>

          <template v-if="activeStage === 'configure'">
            <article class="panel knowledge-binding-card">
              <div class="panel-heading"><div><span class="eyebrow">Knowledge access</span><h2>知识接入与版本策略</h2></div><button v-if="readyBindings.length" type="button" class="text-button" @click="showBindingBuilder = !showBindingBuilder">{{ showBindingBuilder ? '收起' : '+ 新建知识接入' }}</button></div>
              <div v-if="readyBindings.length && !showBindingBuilder" class="binding-summary-grid"><button v-for="binding in readyBindings" :key="binding.id" type="button" :class="{ active: versionForm.application_binding_id === binding.id }" @click="versionForm.application_binding_id = binding.id"><span>API</span><b>{{ binding.name }}</b><small>{{ binding.collection_name }} · {{ binding.follow_latest ? '跟随当前发布版' : `固定 V${binding.pinned_version}` }}</small></button></div>
              <form v-else class="config-form binding-inline-form" @submit.prevent="createBinding"><label><span>接入标识</span><input v-model="bindingForm.binding_key" required placeholder="application-knowledge"><small>下划线和空格会自动转成连字符。</small></label><label><span>显示名称</span><input v-model="bindingForm.name" required placeholder="应用知识接入"></label><label><span>知识集合</span><select v-model="bindingForm.collection_id" required><option v-for="collection in readyCollections" :key="collection.id" :value="collection.id">{{ collection.name }} · 当前 V{{ collection.current_version }}</option></select></label><fieldset class="version-policy"><legend>版本策略</legend><label><input v-model="bindingForm.follow_latest" type="radio" :value="true"><span><b>跟随当前发布版</b><small>集合发布新版后自动生效</small></span></label><label><input v-model="bindingForm.follow_latest" type="radio" :value="false"><span><b>固定集合版本</b><small>适合回归与灰度</small></span></label></fieldset><label v-if="!bindingForm.follow_latest" class="wide"><span>固定版本</span><select v-model="bindingForm.collection_version_id" required><option v-for="version in bindingVersions" :key="version.id" :value="version.id">V{{ version.version }} · {{ version.retrieval_profile_name }}</option></select></label><div class="wide form-action"><small v-if="readyCollections.length">创建后会自动选为当前应用草稿的知识来源。</small><small v-else>请先在“知识集合”发布至少一个集合版本。</small><button class="primary-button" :disabled="busy === 'binding' || !readyCollections.length">创建并选用</button></div></form>
            </article>
            <article class="panel app-version-builder">
              <div class="panel-heading"><div><span class="eyebrow">Draft configuration</span><h2>{{ selectedApplication.name }} · 新配置草稿</h2></div><span class="status configured"><i></i>保存后生成不可变版本</span></div>
              <div v-if="!readyBindings.length || !readyLLMs.length" class="config-prerequisite"><b>还缺少可用的基础能力</b><span v-if="!readyBindings.length">在上方创建知识接入后即可选择。</span><span v-if="!readyLLMs.length">请先配置并启用 LLM 服务。</span><div><router-link to="/business/collections">管理知识集合</router-link><router-link to="/developer/resources">管理模型服务</router-link></div></div>
              <form @submit.prevent="createVersion">
                <section class="runtime-route"><label><span>知识接入</span><select v-model="versionForm.application_binding_id" required><option v-for="binding in readyBindings" :key="binding.id" :value="binding.id">{{ binding.name }} · {{ binding.follow_latest ? '跟随最新' : `固定 V${binding.pinned_version}` }}</option></select></label><span class="route-node">检索</span><i>→</i><label><span>LLM 服务</span><select v-model="versionForm.llm_service_id" required><option v-for="llm in readyLLMs" :key="llm.id" :value="llm.id">{{ llm.name }} · {{ llm.model }}</option></select></label><span class="route-node answer">生成</span></section>
                <section class="prompt-editor"><label><span>System Prompt</span><textarea v-model="versionForm.system_prompt" rows="7" required spellcheck="false"></textarea><small><code v-text="'{{ context }}'"></code> 会注入最终检索上下文。</small></label><label><span>User Prompt</span><textarea v-model="versionForm.user_prompt" rows="7" required spellcheck="false"></textarea><small>变量由下方映射到稳定输入字段。</small></label></section>
                <section class="contract-editor"><header><div><span class="eyebrow">Runtime contract</span><h3>上下文与调用契约</h3></div><p>同一套应用代码只提交 inputs；字段、过滤条件和输出格式都随配置版本发布。</p></header><div class="contract-routing"><label><span>检索问题字段</span><input v-model="versionForm.query_field" required spellcheck="false"></label><label><span>Prompt 变量映射 JSON</span><textarea v-model="versionForm.prompt_variables" rows="4" required spellcheck="false"></textarea></label><label><span>允许的过滤字段</span><input v-model="versionForm.allowed_filter_fields" placeholder="department, document_type"></label><label class="contract-check"><input v-model="versionForm.include_citations" type="checkbox"><span>返回引用证据</span></label></div><div class="contract-schemas"><label><span>输入 JSON Schema</span><textarea v-model="versionForm.input_schema" rows="11" required spellcheck="false"></textarea></label><label><span>输出 JSON Schema</span><textarea v-model="versionForm.output_schema" rows="11" required spellcheck="false"></textarea></label></div></section>
                <section class="generation-settings"><label><span>Temperature</span><input v-model.number="versionForm.temperature" type="number" min="0" max="2" step="0.1"></label><label><span>最大生成 Token</span><input v-model.number="versionForm.max_tokens" type="number" min="1" max="32768"></label><label><span>默认 Top K</span><input v-model.number="versionForm.top_k" type="number" min="1" max="100"></label><div><span>发布门禁</span><b>配置合法 · 知识可解析 · 模型可调用</b><small>发布前执行真实连接检查。</small></div></section>
                <footer><span>保存后自动进入调试，不会影响当前线上版本。</span><button class="primary-button" :disabled="!!busy || !readyBindings.length || !readyLLMs.length">保存草稿并调试</button></footer>
              </form>
            </article>
          </template>

          <template v-if="activeStage === 'debug'">
            <article class="panel app-release-card"><div class="panel-heading"><div><span class="eyebrow">Select version</span><h2>选择调试版本</h2></div><span class="status" :class="selectedVersion ? 'available' : 'configured'"><i></i>{{ selectedVersion ? `V${selectedVersion.version} · ${selectedVersion.status === 'draft' ? '草稿' : '已发布'}` : '等待草稿' }}</span></div><div class="app-version-list"><button v-for="version in detail?.versions" :key="version.id" type="button" :class="{ active: selectedVersion?.id === version.id }" @click="editFromVersion(version)"><span class="version-number">V{{ version.version }}</span><span><b>{{ version.binding_name }} → {{ version.llm_model }}</b><small>Top {{ version.config.top_k }} · Temp {{ version.config.temperature }}</small></span><span class="status" :class="version.status === 'published' ? 'available' : 'configured'"><i></i>{{ version.is_current ? '当前线上' : version.status === 'published' ? '已发布' : '草稿' }}</span></button></div></article>
            <article class="panel rag-playground"><div class="panel-heading"><div><span class="eyebrow">RAG playground</span><h2>召回与回答调试</h2></div><button v-if="canPublish" class="primary-button compact" :disabled="!!busy" @click="activeStage = 'release'">调试完成，准备发布</button></div><div class="playground-layout"><section class="chat-stage"><div ref="chatScroll" class="chat-messages"><div v-if="!conversation.length" class="chat-welcome"><span>DF</span><b>{{ selectedApplication.name }}</b><p>发送真实问题，检查输入契约、召回片段、最终上下文和模型回答。</p></div><article v-for="(item,index) in conversation" :key="index" :class="[item.role, { failed: item.failed }]"><span class="message-role">{{ item.role === 'user' ? '你' : 'AI' }}</span><div><pre>{{ item.content }}</pre><small v-if="item.usage">{{ usageText(item.usage) }} · LLM {{ item.latency }} ms · {{ item.run_id }}</small></div></article><div v-if="busy === 'chat'" class="thinking"><i></i><span>正在检索知识并生成回答…</span></div></div><form @submit.prevent="sendMessage"><textarea v-model="chatInput" rows="3" :disabled="!selectedVersion" placeholder="输入一个需要知识库回答的问题…" @keydown.ctrl.enter.prevent="sendMessage"></textarea><div><small>Ctrl + Enter 发送</small><button class="primary-button" :disabled="busy === 'chat' || !selectedVersion || !chatInput.trim()">发送</button></div></form></section><aside class="evidence-panel"><header><div><b>输入、召回与上下文</b><small>草稿预览不影响线上版本</small></div><button class="text-button" type="button" @click="showEvidence = !showEvidence">{{ showEvidence ? '收起' : '展开' }}</button></header><template v-if="showEvidence"><label><span>附加 Inputs JSON</span><input v-model="previewInputs" spellcheck="false"></label><label><span>过滤条件 JSON</span><input v-model="filters" spellcheck="false"></label><div v-if="lastRetrieval" class="evidence-list"><div class="evidence-summary"><span>{{ lastRetrieval.collection.name }}</span><b>V{{ lastRetrieval.collection.version }} · {{ lastRetrieval.results.length }} 条</b></div><article v-for="(item,index) in lastRetrieval.results" :key="item.index_record_id"><header><span>#{{ index + 1 }} · {{ item.collection_member.knowledge_base_name }}</span><b>{{ item.score.toFixed(4) }}</b></header><p>{{ item.context }}</p><small>{{ item.source.original_filename }}</small></article></div><div v-else class="evidence-empty">完成一次预览后，这里显示召回来源、得分和实际注入的上下文。</div></template></aside></div></article>
            <article class="panel run-history"><div class="panel-heading"><div><span class="eyebrow">Debug traces</span><h2>调试记录</h2></div><span class="resource-count">{{ detail?.runs?.length || 0 }}</span></div><div class="run-table"><div class="table-head"><span>问题</span><span>版本</span><span>知识快照</span><span>状态</span></div><div v-for="run in detail?.runs" :key="run.id" class="table-row"><span><b>{{ run.question }}</b><small>{{ run.id }}</small></span><span>V{{ run.application_version }}</span><span>{{ run.collection_version_id || '—' }}</span><span class="status" :class="run.status === 'completed' ? 'available' : 'failed'"><i></i>{{ run.status === 'completed' ? '完成' : '失败' }}</span></div><div v-if="!detail?.runs?.length" class="compact-empty">尚无调试记录。</div></div></article>
          </template>

          <template v-if="activeStage === 'release'">
            <article class="panel release-gate"><div><span class="eyebrow">Release gate</span><h2>{{ canPublish ? `V${selectedVersion.version} 已准备校验` : currentVersion ? `线上配置 V${currentVersion.version}` : '等待可发布草稿' }}</h2><p>发布会固定知识解析结果、模型信息和调用契约，并把该版本切换为 app_key 的当前配置。</p></div><button v-if="canPublish" class="primary-button" :disabled="!!busy" @click="publishVersion">校验并发布 V{{ selectedVersion.version }}</button><span v-else class="status" :class="currentVersion ? 'available' : 'configured'"><i></i>{{ currentVersion ? '当前配置可读取' : '先保存并调试草稿' }}</span></article>
            <article class="panel app-release-card"><div class="panel-heading"><div><span class="eyebrow">Immutable history</span><h2>配置版本</h2></div><span class="resource-count">{{ detail?.versions?.length || 0 }}</span></div><div class="app-version-list"><button v-for="version in detail?.versions" :key="version.id" type="button" :class="{ active: selectedVersion?.id === version.id }" @click="editFromVersion(version)"><span class="version-number">V{{ version.version }}</span><span><b>{{ version.binding_name }} → {{ version.llm_model }}</b><small>{{ version.published_at || version.created_at }}</small></span><span class="status" :class="version.status === 'published' ? 'available' : 'configured'"><i></i>{{ version.is_current ? '当前线上' : version.status === 'published' ? '历史发布' : '草稿' }}</span></button></div></article>
            <article class="panel config-delivery-card"><div class="panel-heading"><div><span class="eyebrow">Stable configuration endpoint</span><h2>业务应用读取配置</h2></div><span class="status" :class="currentVersion ? 'available' : 'configured'"><i></i>{{ currentVersion ? `GET · 当前 V${currentVersion.version}` : '等待发布' }}</span></div><div class="config-delivery-grid"><section><span class="field-label">稳定地址</span><div class="endpoint-value"><code>GET {{ configEndpoint }}</code><button class="text-button" type="button" @click="copyText(configEndpoint, '配置地址')">复制</button></div><p>需要回归旧配置时读取 <code>{{ configEndpoint }}/versions/{version}</code>。接口不返回密钥值，只返回模型服务地址和环境变量引用。</p><div class="code-sample"><header><span>业务应用代码</span><button class="text-button" type="button" @click="copyText(fetchExample, '读取示例')">复制</button></header><pre>{{ fetchExample }}</pre></div></section><section><span class="field-label">当前发布清单</span><pre v-if="configJson" class="config-manifest">{{ configJson }}</pre><div v-else class="console-empty"><b>尚无发布配置</b><small>校验并发布一个草稿后即可读取。</small></div></section></div></article>
          </template>
        </template>
      </main>
    </div>
  </section>
</template>
