<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../../api'

const busy = ref('')
const message = ref(null)
const collections = ref([])
const knowledgeTypes = ref([])
const retrievalProfiles = ref([])
const knowledgeBases = ref([])
const indexes = ref([])
const selectedCollectionId = ref('')
const detail = ref(null)
const selectedVersion = ref(null)
const collectionForm = reactive({ name: '', description: '', knowledge_type_id: '' })
const versionForm = reactive({ retrieval_profile_id: '', knowledge_base_ids: [] })

const selectedCollection = computed(() => collections.value.find(item => item.id === selectedCollectionId.value))
const compatibleRetrievalProfiles = computed(() => retrievalProfiles.value.filter(profile => profile.active && profile.validation_status === 'validated' && profile.knowledge_type_id === selectedCollection.value?.knowledge_type_id))
const selectedRetrieval = computed(() => retrievalProfiles.value.find(item => item.id === versionForm.retrieval_profile_id))
const compatibleBases = computed(() => {
  const profileId = selectedRetrieval.value?.index_profile_id
  if (!profileId) return []
  const available = new Set(indexes.value.filter(index => index.status === 'available' && index.index_profile_id === profileId).map(index => index.knowledge_base_id))
  return knowledgeBases.value.filter(base => base.knowledge_type_id === selectedCollection.value?.knowledge_type_id && available.has(base.id))
})
const selectedCompatibility = computed(() => {
  const profile = selectedRetrieval.value
  if (!profile) return null
  return {
    index: profile.index_profile_name,
    fields: profile.config?.return_fields || [],
    topK: profile.config?.top_k || 5
  }
})

function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 4200) }
function toggleBase(id) { versionForm.knowledge_base_ids = versionForm.knowledge_base_ids.includes(id) ? versionForm.knowledge_base_ids.filter(item => item !== id) : [...versionForm.knowledge_base_ids, id] }
async function load() {
  try {
    [collections.value, knowledgeTypes.value, retrievalProfiles.value, knowledgeBases.value, indexes.value] = await Promise.all([api.knowledgeCollections(), api.knowledgeTypes(), api.retrievalProfiles(), api.knowledgeBases(), api.knowledgeIndexes()])
    if (!collectionForm.knowledge_type_id) collectionForm.knowledge_type_id = knowledgeTypes.value.find(item => item.active)?.id || ''
    if (!selectedCollectionId.value && collections.value.length) selectedCollectionId.value = collections.value[0].id
    if (selectedCollectionId.value) await selectCollection(selectedCollectionId.value, true)
  } catch (error) { flash(error.message, true) }
}
async function selectCollection(id, silent = false) {
  selectedCollectionId.value = id
  if (!silent) selectedVersion.value = null
  try {
    detail.value = await api.knowledgeCollection(id)
    if (!selectedVersion.value && detail.value.versions.length) await inspectVersion(detail.value.versions[0].id)
  } catch (error) { flash(error.message, true) }
}
async function inspectVersion(id) {
  try { selectedVersion.value = await api.collectionVersion(id) } catch (error) { flash(error.message, true) }
}
async function createCollection() {
  busy.value = 'collection'
  try {
    const created = await api.createKnowledgeCollection({ ...collectionForm })
    Object.assign(collectionForm, { name: '', description: '' })
    selectedCollectionId.value = created.id
    await load()
    flash('知识集合已创建，请继续生成第一个版本')
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function createVersion() {
  if (!versionForm.knowledge_base_ids.length) return flash('请至少选择一个已完成索引的知识库', true)
  busy.value = 'version'
  try {
    const created = await api.createCollectionVersion(selectedCollectionId.value, { ...versionForm })
    versionForm.knowledge_base_ids = []
    await load()
    await inspectVersion(created.id)
    flash(`集合 V${created.version} 草稿已生成，成员索引已锁定`)
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}
async function publishVersion(version) {
  busy.value = `publish-${version.id}`
  try {
    const published = await api.publishCollectionVersion(version.id, { make_current: true })
    await load(); await inspectVersion(published.id)
    flash(`集合 V${published.version} 已发布为当前版本`)
  } catch (error) { flash(error.message, true) } finally { busy.value = '' }
}

watch(selectedCollectionId, id => {
  const collection = collections.value.find(item => item.id === id)
  versionForm.retrieval_profile_id = retrievalProfiles.value.find(profile => profile.active && profile.validation_status === 'validated' && profile.knowledge_type_id === collection?.knowledge_type_id)?.id || ''
  versionForm.knowledge_base_ids = []
})
watch(() => versionForm.retrieval_profile_id, () => { versionForm.knowledge_base_ids = versionForm.knowledge_base_ids.filter(id => compatibleBases.value.some(base => base.id === id)) })
onMounted(load)
</script>

<template>
  <section class="page delivery-page">
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>
    <div class="delivery-flow" aria-label="交付流程"><span>知识资产</span><i>→</i><strong>知识集合版本</strong><i>→</i><span>应用接入标识</span><i>→</i><span>AI 应用</span></div>

    <div class="collection-layout">
      <aside class="panel collection-catalog">
        <div class="panel-heading"><div><span class="eyebrow">Knowledge collections</span><h2>知识集合</h2></div><span class="resource-count">{{ collections.length }}</span></div>
        <button v-for="item in collections" :key="item.id" type="button" class="collection-row" :class="{ active: item.id === selectedCollectionId }" @click="selectCollection(item.id)">
          <span class="collection-symbol">集</span><span><b>{{ item.name }}</b><small>{{ item.knowledge_type_name }} · {{ item.version_count }} 个版本</small></span><span class="status" :class="item.current_version ? 'available' : 'configured'"><i></i>{{ item.current_version ? `当前 V${item.current_version}` : '待发布' }}</span>
        </button>
        <div v-if="!collections.length" class="compact-empty">还没有知识集合。先创建一个稳定容器，再逐版添加知识资产。</div>
      </aside>

      <main class="collection-main">
        <article id="create-collection" class="panel collection-create">
          <div class="panel-heading"><div><span class="eyebrow">Stable container</span><h2>新建知识集合</h2></div><span class="step-label">只定义用途与知识类型</span></div>
          <form class="config-form collection-form" @submit.prevent="createCollection">
            <label><span>集合名称</span><input v-model="collectionForm.name" required placeholder="例如 慢病随访知识集合"></label>
            <label><span>知识类型</span><select v-model="collectionForm.knowledge_type_id" required><option v-for="type in knowledgeTypes.filter(item => item.active)" :key="type.id" :value="type.id">{{ type.name }}</option></select></label>
            <label class="wide"><span>使用说明</span><input v-model="collectionForm.description" placeholder="描述供哪些应用使用"></label>
            <div class="wide form-action"><small>集合本身保持稳定，成员、检索方案和索引快照都记录在不可变版本中。</small><button class="primary-button" :disabled="!!busy">创建集合</button></div>
          </form>
        </article>

        <template v-if="selectedCollection">
          <article class="panel version-composer">
            <div class="panel-heading"><div><span class="eyebrow">Version composer</span><h2>{{ selectedCollection.name }} · 生成新版本</h2></div><span class="status configured"><i></i>{{ selectedCollection.knowledge_type_name }}</span></div>
            <form @submit.prevent="createVersion">
              <section class="composer-contract"><label><span>已发布检索方案</span><select v-model="versionForm.retrieval_profile_id" required><option v-for="profile in compatibleRetrievalProfiles" :key="profile.id" :value="profile.id">{{ profile.name }} · V{{ profile.version }}</option></select></label><div v-if="selectedCompatibility" class="contract-summary"><span>索引契约</span><b>{{ selectedCompatibility.index }}</b><small>Top {{ selectedCompatibility.topK }} · 返回 {{ selectedCompatibility.fields.length }} 个字段</small></div></section>
              <section class="member-selector"><header><div><b>选择兼容知识库</b><small>只展示使用同一索引方案且状态可用的资产；发布后固定到具体索引版本。</small></div><span>{{ versionForm.knowledge_base_ids.length }} / {{ compatibleBases.length }}</span></header><div class="member-grid"><label v-for="base in compatibleBases" :key="base.id" :class="{ selected: versionForm.knowledge_base_ids.includes(base.id) }"><input type="checkbox" :checked="versionForm.knowledge_base_ids.includes(base.id)" @change="toggleBase(base.id)"><span><b>{{ base.name }}</b><small>{{ base.record_count }} 条记录 · {{ base.knowledge_type_name }}</small></span></label><div v-if="!compatibleBases.length" class="compact-empty">所选检索方案还没有兼容的可用索引，请先完成索引任务。</div></div></section>
              <footer class="composer-footer"><span>创建草稿不会影响当前线上版本。</span><button class="primary-button" :disabled="!!busy || !compatibleBases.length">生成集合版本</button></footer>
            </form>
          </article>

          <article class="panel release-history">
            <div class="panel-heading"><div><span class="eyebrow">Immutable releases</span><h2>版本与成员快照</h2></div><span class="resource-count">{{ detail?.versions?.length || 0 }}</span></div>
            <div class="release-layout"><div class="release-list"><button v-for="version in detail?.versions" :key="version.id" type="button" :class="{ active: selectedVersion?.id === version.id }" @click="inspectVersion(version.id)"><span class="version-number">V{{ version.version }}</span><span><b>{{ version.retrieval_profile_name }}</b><small>{{ version.member_count }} 个知识库 · {{ version.index_profile_name }}</small></span><span class="status" :class="version.status === 'published' ? 'available' : 'configured'"><i></i>{{ version.is_current ? '当前发布版' : version.status === 'published' ? '已发布' : '草稿' }}</span></button><div v-if="!detail?.versions?.length" class="compact-empty">尚未生成版本。</div></div>
              <section v-if="selectedVersion" class="release-detail"><header><div><span class="eyebrow">Pinned snapshot</span><h3>{{ selectedVersion.collection_name }} · V{{ selectedVersion.version }}</h3></div><button v-if="selectedVersion.status === 'draft'" class="primary-button compact" :disabled="!!busy" @click="publishVersion(selectedVersion)">校验并发布</button></header><div class="compatibility-strip"><span><small>Embedding</small><b>{{ selectedVersion.validation.compatibility?.embedding_model || '—' }}</b></span><span><small>维度</small><b>{{ selectedVersion.validation.compatibility?.dimension || '—' }}</b></span><span><small>向量库</small><b>{{ selectedVersion.validation.compatibility?.vector_store_kind || '—' }}</b></span><span><small>距离</small><b>{{ selectedVersion.validation.compatibility?.metric_type || '—' }}</b></span></div><div class="snapshot-members"><article v-for="member in selectedVersion.members" :key="member.id"><span class="snapshot-order">{{ member.ordinal }}</span><div><b>{{ member.knowledge_base_name }}</b><small>知识索引 V{{ member.knowledge_index_version }} · {{ member.record_count }} 条</small><code>{{ member.collection_name }}</code></div><span class="status available"><i></i>已锁定</span></article></div></section>
            </div>
          </article>
        </template>
      </main>
    </div>
  </section>
</template>
