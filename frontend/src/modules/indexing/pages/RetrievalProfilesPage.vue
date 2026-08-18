<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../../api'

const busy = ref('')
const message = ref(null)
const indexProfiles = ref([])
const retrievalProfiles = ref([])
const knowledgeBases = ref([])
const indexes = ref([])
const rerankers = ref([])
const result = ref(null)
const form = reactive({ name: '', description: '', index_profile_id: '', top_k: 5, score_threshold: 0, reranker_enabled: false, reranker_service_id: '', rerank_candidate_count: 20, return_fields: [], context_template: '{{ indexed_text }}', context_separator: '\n\n---\n\n' })
const test = reactive({ retrieval_profile_id: '', knowledge_base_id: '', query: '', filters: '{}' })
const publishedIndexes = computed(() => indexProfiles.value.filter(item => item.active && item.validation_status === 'validated'))
const selectedIndexProfile = computed(() => indexProfiles.value.find(item => item.id === form.index_profile_id))
const availableFields = computed(() => [...new Set([...(selectedIndexProfile.value?.config?.stored_fields || []), 'indexed_text', 'score', 'source_locator', 'source_version_id', 'knowledge_record_id', 'knowledge_base_id'])])
const publishedRetrieval = computed(() => retrievalProfiles.value.filter(item => item.active && item.validation_status === 'validated'))
const readyRerankers = computed(() => rerankers.value.filter(item => item.active))
const selectedRetrieval = computed(() => retrievalProfiles.value.find(item => item.id === test.retrieval_profile_id))
const compatibleBases = computed(() => {
  const profileId = selectedRetrieval.value?.index_profile_id
  const availableBaseIds = new Set(indexes.value.filter(item => item.index_profile_id === profileId && item.status === 'available').map(item => item.knowledge_base_id))
  return knowledgeBases.value.filter(item => availableBaseIds.has(item.id))
})

function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 4200) }
function toggle(field) { const i = form.return_fields.indexOf(field); i >= 0 ? form.return_fields.splice(i, 1) : form.return_fields.push(field) }
function loadVersion(profile) { const config = profile.config || {}; Object.assign(form, { name: profile.name, description: profile.description || '', index_profile_id: profile.index_profile_id, top_k: config.top_k || 5, score_threshold: config.score_threshold || 0, reranker_enabled: !!config.reranker_enabled, reranker_service_id: config.reranker_service_id || readyRerankers.value[0]?.id || '', rerank_candidate_count: config.rerank_candidate_count || 20, return_fields: [...(config.return_fields || [])], context_template: config.context_template || '{{ indexed_text }}', context_separator: config.context_separator || '\n\n---\n\n' }); document.querySelector('#retrieval-builder')?.scrollIntoView({ behavior: 'smooth' }) }
async function load() {
  try {
    [indexProfiles.value, retrievalProfiles.value, knowledgeBases.value, indexes.value, rerankers.value] = await Promise.all([api.indexProfiles(), api.retrievalProfiles(), api.knowledgeBases(), api.knowledgeIndexes(), api.rerankerServices()])
    if (!form.index_profile_id) form.index_profile_id = publishedIndexes.value[0]?.id || ''
    if (!form.reranker_service_id) form.reranker_service_id = readyRerankers.value[0]?.id || ''
    if (!test.retrieval_profile_id) test.retrieval_profile_id = publishedRetrieval.value[0]?.id || ''
  } catch (error) { flash(error.message, true) }
}
async function createProfile() { busy.value = 'create'; try { const created = await api.createRetrievalProfile({ name: form.name, description: form.description, index_profile_id: form.index_profile_id, config: { top_k: form.top_k, score_threshold: form.score_threshold, reranker_enabled: form.reranker_enabled, reranker_service_id: form.reranker_enabled ? form.reranker_service_id : null, rerank_candidate_count: form.rerank_candidate_count, return_fields: form.return_fields, context_template: form.context_template, context_separator: form.context_separator } }); await load(); flash(`检索方案 V${created.version} 草稿已保存`) } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function publish(profile) { busy.value = `publish-${profile.id}`; try { await api.publishRetrievalProfile(profile.id, { make_default: true }); await load(); test.retrieval_profile_id = profile.id; flash('字段兼容性验证通过，检索方案已发布') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function query() { busy.value = 'query'; result.value = null; try { result.value = await api.retrieve({ retrieval_profile_id: test.retrieval_profile_id, knowledge_base_id: test.knowledge_base_id, query: test.query, filters: JSON.parse(test.filters || '{}') }) } catch (error) { flash(error instanceof SyntaxError ? '过滤条件必须是合法 JSON' : error.message, true) } finally { busy.value = '' } }
watch(() => form.index_profile_id, () => { form.return_fields = availableFields.value.filter(field => ['indexed_text', 'source_locator'].includes(field)) })
watch(() => test.retrieval_profile_id, () => { test.knowledge_base_id = compatibleBases.value[0]?.id || '' })
onMounted(load)
</script>

<template>
  <section class="page developer-page indexing-page">
    <div class="developer-notice"><b>检索方案是应用与索引之间的配置契约</b><span>同一索引可以按应用配置不同 Top K、返回字段和上下文模板，应用只调用统一检索接口。</span></div>
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>
    <div class="profile-layout retrieval-layout">
      <article id="retrieval-builder" class="panel profile-builder"><div class="panel-heading"><div><span class="eyebrow">Retrieval profile builder</span><h2>配置召回与上下文</h2></div><span class="status configured"><i></i>应用级</span></div>
        <form class="profile-form" @submit.prevent="createProfile">
          <fieldset><legend>01 · 依赖索引</legend><div class="config-form"><label><span>方案名称</span><input v-model="form.name" required placeholder="例如 客服问答检索"></label><label><span>已发布索引方案</span><select v-model="form.index_profile_id" required><option v-for="item in publishedIndexes" :key="item.id" :value="item.id">{{ item.name }} · V{{ item.version }}</option></select></label><label class="wide"><span>说明</span><input v-model="form.description" placeholder="供哪个应用或场景使用"></label></div><div v-if="!publishedIndexes.length" class="blocking-note">请先在“索引方案”中验证并发布至少一套方案。</div></fieldset>
          <fieldset><legend>02 · 召回与重排</legend><div class="retrieval-parameters"><label><span>Top K 上限</span><input v-model.number="form.top_k" type="number" min="1" max="100"></label><label><span>最低相似度</span><input v-model.number="form.score_threshold" type="number" min="-1" max="1" step="0.01"></label><div><span>基础召回</span><b>向量召回 · COSINE</b><small>查询时允许缩小 Top K，不能突破方案上限。</small></div></div><div class="reranker-switch"><label><input v-model="form.reranker_enabled" type="checkbox"><span><b>启用 Reranker</b><small>先召回更多候选，再按问题相关性重新排序。</small></span></label><div v-if="form.reranker_enabled" class="reranker-settings"><label><span>重排模型</span><select v-model="form.reranker_service_id" required><option v-for="item in readyRerankers" :key="item.id" :value="item.id">{{ item.name }} · {{ item.model }}</option></select></label><label><span>候选数量</span><input v-model.number="form.rerank_candidate_count" type="number" :min="form.top_k" max="200"><small>最终仍只返回 Top K。</small></label></div><div v-if="form.reranker_enabled && !readyRerankers.length" class="blocking-note">请先在“模型与存储”中配置 Reranker 服务。</div></div></fieldset>
          <fieldset><legend>03 · API 返回字段</legend><p class="fieldset-note">这里只能选择索引方案已经保存的字段，发布时会自动校验兼容性。</p><div class="check-grid return-fields"><label v-for="field in availableFields" :key="field"><input type="checkbox" :checked="form.return_fields.includes(field)" @change="toggle(field)"><span>{{ field }}</span></label></div></fieldset>
          <fieldset><legend>04 · 上下文拼接</legend><label class="template-field"><span>单条结果模板</span><textarea v-model="form.context_template" rows="6" required></textarea><small>可引用已保存字段，也可以引用 indexed_text、score 和 source_locator。</small></label><div class="field-inserter"><span>插入字段</span><button v-for="field in availableFields" :key="field" type="button" @click="form.context_template += `{{ ${field} }}`">+ {{ field }}</button></div><label class="template-field separator"><span>多条结果分隔符</span><textarea v-model="form.context_separator" rows="2"></textarea></label></fieldset>
          <div class="publish-strip"><span class="config-assurance">发布后版本不可覆盖；修改会生成新版本。</span><button class="primary-button" :disabled="!!busy || !publishedIndexes.length || (form.reranker_enabled && !readyRerankers.length)" type="submit">保存检索方案草稿</button></div>
        </form>
      </article>
      <aside class="panel version-catalog"><div class="panel-heading"><div><span class="eyebrow">Application contracts</span><h2>检索方案版本</h2></div><span class="resource-count">{{ retrievalProfiles.length }}</span></div><div class="profile-list"><article v-for="profile in retrievalProfiles" :key="profile.id"><header><span><b>{{ profile.name }}</b><small>{{ profile.index_profile_name }} · V{{ profile.version }}</small></span><span class="status" :class="profile.validation_status"><i></i>{{ profile.validation_status === 'validated' ? (profile.is_default ? '默认发布版' : '已发布') : '草稿' }}</span></header><p>Top {{ profile.config.top_k || 5 }} · {{ profile.config.reranker_enabled ? `Rerank ${profile.config.rerank_candidate_count || 20} → ${profile.config.top_k || 5}` : '仅向量排序' }}</p><div class="profile-tags"><span v-if="profile.config.reranker_enabled">Reranker</span><span v-for="field in profile.config.return_fields" :key="field">{{ field }}</span></div><footer><button class="text-button" @click="loadVersion(profile)">新建版本</button><button v-if="profile.validation_status === 'configured'" class="primary-button compact" :disabled="!!busy" @click="publish(profile)">校验并发布</button><button v-else class="text-button" @click="test.retrieval_profile_id=profile.id; document.querySelector('#retrieval-test')?.scrollIntoView({behavior:'smooth'})">联调</button></footer></article><div v-if="!retrievalProfiles.length" class="compact-empty">尚未创建检索方案。</div></div></aside>
    </div>

    <article id="retrieval-test" class="panel retrieval-test"><div class="panel-heading"><div><span class="eyebrow">Live retrieval console</span><h2>统一检索接口联调</h2></div><span class="status available"><i></i>POST /api/retrieval/query</span></div><form @submit.prevent="query"><label><span>检索方案</span><select v-model="test.retrieval_profile_id" required><option v-for="item in publishedRetrieval" :key="item.id" :value="item.id">{{ item.name }} · V{{ item.version }}</option></select></label><label><span>兼容知识索引</span><select v-model="test.knowledge_base_id" required><option v-for="item in compatibleBases" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label class="query-field"><span>用户问题</span><input v-model="test.query" required placeholder="输入实际检索问题"></label><label class="filter-field"><span>过滤条件 JSON</span><input v-model="test.filters" spellcheck="false"></label><button class="primary-button" :disabled="!!busy || !compatibleBases.length">执行检索</button></form><div v-if="!compatibleBases.length && test.retrieval_profile_id" class="blocking-note">该检索方案还没有兼容的可用索引，请先创建索引任务。</div><div v-if="result" class="retrieval-result"><section><header><b>召回 {{ result.results.length }} 条</b><span>{{ result.reranker?.enabled ? `${result.reranker.model} · ${result.reranker.latency_ms} ms` : `Index V${result.knowledge_index.version}` }}</span></header><article v-for="(item, index) in result.results" :key="item.index_record_id"><span class="rank">{{ index + 1 }}</span><div><b>{{ item.rerank_score == null ? '相似度' : '重排分' }} {{ item.score.toFixed(4) }}</b><pre>{{ JSON.stringify(item.fields, null, 2) }}</pre><small v-if="item.rerank_score != null">向量分 {{ item.vector_score.toFixed(4) }}</small><small>{{ item.source.source_name }} · {{ item.source.original_filename }}</small></div></article></section><section class="context-output"><header><b>最终应用上下文</b><span>按方案模板生成</span></header><pre>{{ result.context }}</pre></section></div></article>
  </section>
</template>
