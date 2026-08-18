<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../../api'

const loading = ref(true)
const busy = ref('')
const message = ref(null)
const knowledgeTypes = ref([])
const knowledgeBases = ref([])
const embeddings = ref([])
const vectors = ref([])
const graphs = ref([])
const profiles = ref([])
const preview = ref(null)
const form = reactive({
  logical_key: '', name: '', description: '', knowledge_type_id: '',
  embedding_service_id: '', vector_store_id: '', graph_store_id: '',
  embedding_template: '', stored_fields: [], metadata_fields: ['source_locator'],
  missing_policy: 'error', metric_type: 'COSINE', filter_fields: []
})

const activeTypes = computed(() => knowledgeTypes.value.filter(item => item.active))
const selectedType = computed(() => knowledgeTypes.value.find(item => item.id === form.knowledge_type_id))
const fields = computed(() => Object.keys(selectedType.value?.schema?.properties || {}))

function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 4200) }
function toggle(list, field) { const index = list.indexOf(field); index >= 0 ? list.splice(index, 1) : list.push(field) }
function addFilter() { form.filter_fields.push({ source: fields.value[0] || '', target: fields.value[0] || '', type: 'string', default: '' }) }
function removeFilter(index) { form.filter_fields.splice(index, 1) }
function seedTemplate() {
  const templates = { text_chunk: '{{ content }}', faq: '{{ question }}', knowledge_triple: '{{ subject }} | {{ predicate }} | {{ object }}', multi_turn_dialogue: '{{ messages }}' }
  form.embedding_template = templates[form.knowledge_type_id] || fields.value.map(field => `{{ ${field} }}`).join('\n')
  form.stored_fields = [...fields.value]
  if (!form.name) form.name = `${selectedType.value?.name || '知识'}语义索引`
}
function loadVersion(profile) {
  const config = profile.config || {}
  Object.assign(form, {
    logical_key: profile.logical_key, name: profile.name, description: profile.description || '',
    knowledge_type_id: profile.knowledge_type_id, embedding_service_id: profile.embedding_service_id,
    vector_store_id: profile.vector_store_id, graph_store_id: profile.graph_store_id || '',
    embedding_template: config.embedding_template || '', stored_fields: [...(config.stored_fields || [])],
    metadata_fields: [...(config.metadata_fields || [])], missing_policy: config.missing_policy || 'error',
    metric_type: config.metric_type || 'COSINE', filter_fields: (config.filter_fields || []).map(item => ({ ...item }))
  })
  preview.value = null
  document.querySelector('#profile-builder')?.scrollIntoView({ behavior: 'smooth' })
}
async function load() {
  loading.value = true
  try {
    [knowledgeTypes.value, knowledgeBases.value, embeddings.value, vectors.value, graphs.value, profiles.value] = await Promise.all([
      api.knowledgeTypes(), api.knowledgeBases(), api.embeddingServices(), api.vectorStores(), api.graphStores(), api.indexProfiles()
    ])
    if (!form.knowledge_type_id) form.knowledge_type_id = activeTypes.value[0]?.id || ''
    if (!form.embedding_service_id) form.embedding_service_id = embeddings.value[0]?.id || ''
    if (!form.vector_store_id) form.vector_store_id = vectors.value[0]?.id || ''
    if (!form.embedding_template) seedTemplate()
  } catch (error) { flash(error.message, true) } finally { loading.value = false }
}
async function createProfile() {
  busy.value = 'create'
  try {
    const created = await api.createIndexProfile({
      logical_key: form.logical_key || undefined, name: form.name, description: form.description,
      knowledge_type_id: form.knowledge_type_id, embedding_service_id: form.embedding_service_id,
      vector_store_id: form.vector_store_id, graph_store_id: form.graph_store_id || undefined,
      config: {
        embedding_template: form.embedding_template, stored_fields: form.stored_fields,
        metadata_fields: form.metadata_fields, filter_fields: form.filter_fields.map(item => ({ ...item, default: item.default === '' ? null : item.default })),
        missing_policy: form.missing_policy, metric_type: form.metric_type
      }
    })
    await load(); await showPreview(created.id); flash(`索引方案 V${created.version} 草稿已创建`)
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function showPreview(id) { busy.value = `preview-${id}`; try { preview.value = { id, ...(await api.previewIndexProfile(id)) }; document.querySelector('#profile-preview')?.scrollIntoView({ behavior: 'smooth' }) } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function publish(profile) { busy.value = `publish-${profile.id}`; try { await api.publishIndexProfile(profile.id, { make_default: true }); await load(); flash('验证通过，索引方案已发布并设为该知识类型的默认方案') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function deactivate(profile) { busy.value = `deactivate-${profile.id}`; try { await api.deactivateIndexProfile(profile.id); await load(); flash('索引方案已停用，新任务不再使用它') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }

watch(() => form.knowledge_type_id, (next, previous) => { if (previous && next !== previous) { form.name = ''; form.logical_key = ''; seedTemplate() } })
onMounted(load)
</script>

<template>
  <section class="page developer-page indexing-page">
    <div class="developer-notice"><b>一个知识类型可以发布多套索引投影</b><span>事实数据保持统一；向量文本、随索引保存的字段和可过滤标量由版本化方案决定。</span></div>
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>
    <div class="index-flow" aria-label="索引配置流程"><span>知识资产 Schema</span><i>→</i><strong>索引投影</strong><i>→</i><span>Milvus Collection</span><i>→</i><span>检索方案</span></div>

    <div class="profile-layout">
      <article id="profile-builder" class="panel profile-builder">
        <div class="panel-heading"><div><span class="eyebrow">Index profile builder</span><h2>配置索引投影</h2></div><span class="status configured"><i></i>草稿可编辑</span></div>
        <form class="profile-form" @submit.prevent="createProfile">
          <fieldset><legend>01 · 基础与运行资源</legend><div class="config-form">
            <label><span>方案名称</span><input v-model="form.name" required></label>
            <label><span>知识类型</span><select v-model="form.knowledge_type_id" required><option v-for="item in activeTypes" :key="item.id" :value="item.id">{{ item.name }} · V{{ item.version }}</option></select></label>
            <label class="wide"><span>说明</span><input v-model="form.description" placeholder="这套投影适用于什么检索场景"></label>
            <label><span>Embedding 服务</span><select v-model="form.embedding_service_id" required><option v-for="item in embeddings" :key="item.id" :value="item.id">{{ item.name }} · {{ item.model }}</option></select></label>
            <label><span>向量库</span><select v-model="form.vector_store_id" required><option v-for="item in vectors" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
            <label><span>图数据库（可选）</span><select v-model="form.graph_store_id"><option value="">不写入图数据库</option><option v-for="item in graphs" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
            <label><span>相似度</span><select v-model="form.metric_type"><option>COSINE</option><option>IP</option><option>L2</option></select></label>
          </div></fieldset>

          <fieldset><legend>02 · 向量文本</legend><label class="template-field"><span>模板</span><textarea v-model="form.embedding_template" rows="4" required></textarea><small>用 <code v-pre>{{ field }}</code> 引用字段。只有模板生成的文本会送入 Embedding。</small></label><div class="field-inserter"><span>插入字段</span><button v-for="field in fields" :key="field" type="button" @click="form.embedding_template += `{{ ${field} }}`">+ {{ field }}</button></div></fieldset>

          <fieldset><legend>03 · 随索引保存的字段</legend><p class="fieldset-note">勾选后可由检索方案选择返回并拼接上下文；源事实仍保存在知识资产库。</p><div class="check-grid"><label v-for="field in fields" :key="field"><input type="checkbox" :checked="form.stored_fields.includes(field)" @change="toggle(form.stored_fields, field)"><span>{{ field }}</span><small>{{ selectedType?.schema?.properties?.[field] }}</small></label></div><label class="source-checkbox"><input type="checkbox" :checked="form.metadata_fields.includes('source_locator')" @change="toggle(form.metadata_fields, 'source_locator')"><span>保存 source_locator（页码、行号、段落等溯源定位）</span></label></fieldset>

          <fieldset><div class="fieldset-heading"><div><legend>04 · 可过滤标量字段</legend><p class="fieldset-note">映射为 Milvus 独立字段，供业务检索条件使用。</p></div><button type="button" class="text-button" @click="addFilter">+ 添加映射</button></div><div class="filter-list"><div v-for="(item, index) in form.filter_fields" :key="index"><label><span>知识字段</span><select v-model="item.source"><option v-for="field in fields" :key="field">{{ field }}</option></select></label><label><span>索引字段名</span><input v-model="item.target" pattern="[A-Za-z_][A-Za-z0-9_]{0,63}" required></label><label><span>类型</span><select v-model="item.type"><option value="string">字符串</option><option value="integer">整数</option><option value="number">小数</option><option value="boolean">布尔</option></select></label><label><span>缺省值</span><input v-model="item.default"></label><button type="button" class="icon-button danger-text" aria-label="删除过滤字段" @click="removeFilter(index)">×</button></div><div v-if="!form.filter_fields.length" class="compact-empty">当前方案不配置业务过滤字段。</div></div></fieldset>

          <div class="publish-strip"><label><span>缺失字段策略</span><select v-model="form.missing_policy"><option value="error">阻止发布 / 入库</option><option value="empty">按空值处理</option></select></label><button class="primary-button" :disabled="!!busy" type="submit">保存为新版本草稿</button></div>
        </form>
      </article>

      <aside class="panel version-catalog"><div class="panel-heading"><div><span class="eyebrow">Immutable versions</span><h2>方案版本</h2></div><span class="resource-count">{{ profiles.length }}</span></div><div class="profile-list"><article v-for="profile in profiles" :key="profile.id" :class="{ inactive: !profile.active }"><header><span><b>{{ profile.name }}</b><small>{{ profile.knowledge_type_name }} · V{{ profile.version }}</small></span><span class="status" :class="profile.validation_status"><i></i>{{ profile.validation_status === 'validated' ? (profile.is_default ? '默认发布版' : '已发布') : profile.validation_status === 'inactive' ? '已停用' : '草稿' }}</span></header><p>{{ profile.config.embedding_template }}</p><div class="profile-tags"><span v-for="field in profile.config.stored_fields" :key="field">{{ field }}</span></div><footer><button class="text-button" :disabled="!!busy" @click="showPreview(profile.id)">预览</button><button class="text-button" :disabled="!!busy" @click="loadVersion(profile)">新建版本</button><button v-if="profile.validation_status === 'configured'" class="primary-button compact" :disabled="!!busy" @click="publish(profile)">验证并发布</button><button v-else-if="profile.active" class="text-button danger-text" :disabled="!!busy" @click="deactivate(profile)">停用</button></footer></article></div></aside>
    </div>

    <article v-if="preview" id="profile-preview" class="panel projection-preview"><div class="panel-heading"><div><span class="eyebrow">Projection preview</span><h2>实际投影预览</h2></div><button class="text-button" @click="preview=null">关闭</button></div><div class="projection-grid"><section><span>原始知识记录</span><pre>{{ JSON.stringify(preview.sample, null, 2) }}</pre></section><section class="projected"><span>Embedding 文本</span><pre>{{ preview.indexed_text }}</pre><span>Metadata / Stored fields</span><pre>{{ JSON.stringify(preview.metadata, null, 2) }}</pre><span>Milvus 过滤字段</span><pre>{{ JSON.stringify(preview.filter_fields, null, 2) }}</pre></section></div></article>
    <div v-if="loading" class="page-loader"><span></span><p>正在读取索引配置…</p></div>
  </section>
</template>
