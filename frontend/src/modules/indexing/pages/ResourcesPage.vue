<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../../api'

const loading = ref(true)
const busy = ref('')
const message = ref(null)
const embeddings = ref([])
const rerankers = ref([])
const llms = ref([])
const vectors = ref([])
const graphs = ref([])
const embeddingForm = reactive({ name: 'BCE 本地 Embedding', provider: 'openai-compatible', base_url: 'http://127.0.0.1:8002/v1', model: 'bce-embedding-base', dimension: 768, batch_size: 32, concurrency: 1, timeout_seconds: 30, max_retries: 2, api_key_env: '' })
const llmForm = reactive({ name: 'Qwen3 本地 LLM', provider: 'openai-compatible', base_url: 'http://127.0.0.1:8001/v1', model: 'Qwen3-32B', timeout_seconds: 60, max_retries: 1, api_key_env: '' })
const rerankerForm = reactive({ name: 'BGE 本地 Reranker', provider: 'openai-compatible', base_url: 'http://127.0.0.1:8197/v1', model: 'bge-reranker-large', timeout_seconds: 30, max_retries: 1, api_key_env: '' })
const vectorForm = reactive({ name: 'Milvus Standalone', kind: 'milvus', uri: 'http://127.0.0.1:19530', database_name: 'default', collection_prefix: 'dataforge', token_env: '' })
const graphForm = reactive({ name: '', kind: 'neo4j', uri: 'bolt://127.0.0.1:7687', graph_space: 'neo4j', username_env: 'NEO4J_USERNAME', password_env: 'NEO4J_PASSWORD' })

function flash(text, error = false) { message.value = { text, error }; window.setTimeout(() => { message.value = null }, 3500) }
async function load() { loading.value = true; try { [llms.value, embeddings.value, rerankers.value, vectors.value, graphs.value] = await Promise.all([api.llmServices(), api.embeddingServices(), api.rerankerServices(), api.vectorStores(), api.graphStores()]) } catch (error) { flash(error.message, true) } finally { loading.value = false } }
async function save(kind) { busy.value = `save-${kind}`; try { if (kind === 'llm') await api.saveLLMService(llmForm); if (kind === 'embedding') await api.saveEmbeddingService(embeddingForm); if (kind === 'reranker') await api.saveRerankerService(rerankerForm); if (kind === 'vector') await api.saveVectorStore(vectorForm); if (kind === 'graph') await api.saveGraphStore(graphForm); await load(); flash('配置已保存，请继续执行连接测试') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
async function test(kind, id) { busy.value = `test-${id}`; try { let result; if (kind === 'llm') result = await api.testLLMService(id); if (kind === 'embedding') result = await api.testEmbeddingService(id); if (kind === 'reranker') result = await api.testRerankerService(id); if (kind === 'vector') result = await api.testVectorStore(id); if (kind === 'graph') result = await api.testGraphStore(id); await load(); flash(result.status === 'ready' ? '连接测试通过' : result.last_test?.error || '连接测试失败', result.status !== 'ready') } catch (error) { flash(error.message, true) } finally { busy.value = '' } }
function statusLabel(item) { return item.status === 'ready' ? '连接正常' : item.status === 'failed' ? '连接失败' : '待测试' }
onMounted(load)
</script>

<template>
  <section class="page developer-page indexing-page">
    <div class="developer-notice"><b>运行资源不写进业务代码</b><span>密钥只引用服务端环境变量；索引方案发布时保存脱敏配置快照，保证重建可复现。</span></div>
    <div v-if="message" class="inline-message" :class="{ error: message.error }" role="status">{{ message.text }}</div>
    <div class="resource-grid">
      <article class="panel resource-card">
        <div class="panel-heading"><div><span class="eyebrow">LLM · Application runtime</span><h2>大语言模型服务</h2></div><span class="resource-count">{{ llms.length }}</span></div>
        <form class="config-form" @submit.prevent="save('llm')">
          <label><span>配置名称</span><input v-model="llmForm.name" required></label>
          <label><span>模型名称</span><input v-model="llmForm.model" required></label>
          <label class="wide"><span>OpenAI 兼容地址</span><input v-model="llmForm.base_url" type="url" required></label>
          <label><span>超时（秒）</span><input v-model.number="llmForm.timeout_seconds" type="number" min="1"></label>
          <label><span>最大重试</span><input v-model.number="llmForm.max_retries" type="number" min="0"></label>
          <label class="wide"><span>API Key 环境变量（可选）</span><input v-model="llmForm.api_key_env" placeholder="例如 LLM_API_KEY"><small>供 Text2QA 与 AI 应用选择</small></label>
          <button class="primary-button wide" :disabled="!!busy" type="submit">保存 LLM 配置</button>
        </form>
        <div class="resource-list"><div v-for="item in llms" :key="item.id"><span class="resource-symbol llm">L</span><span><b>{{ item.name }}</b><small>{{ item.model }} · OpenAI Compatible</small></span><span class="status" :class="item.status"><i></i>{{ statusLabel(item) }}</span><button class="text-button" :disabled="!!busy" @click="test('llm', item.id)">测试</button></div></div>
      </article>

      <article class="panel resource-card">
        <div class="panel-heading"><div><span class="eyebrow">Reranker · Optional</span><h2>重排模型服务</h2></div><span class="resource-count">{{ rerankers.length }}</span></div>
        <form class="config-form" @submit.prevent="save('reranker')">
          <label><span>配置名称</span><input v-model="rerankerForm.name" required></label>
          <label><span>模型名称</span><input v-model="rerankerForm.model" required></label>
          <label class="wide"><span>Rerank 兼容地址</span><input v-model="rerankerForm.base_url" type="url" required><small>系统会自动调用该地址下的 /rerank</small></label>
          <label><span>超时（秒）</span><input v-model.number="rerankerForm.timeout_seconds" type="number" min="1"></label>
          <label><span>最大重试</span><input v-model.number="rerankerForm.max_retries" type="number" min="0"></label>
          <label class="wide"><span>API Key 环境变量（可选）</span><input v-model="rerankerForm.api_key_env" placeholder="例如 RERANKER_API_KEY"></label>
          <button class="primary-button wide" :disabled="!!busy" type="submit">保存 Reranker 配置</button>
        </form>
        <div class="resource-list"><div v-for="item in rerankers" :key="item.id"><span class="resource-symbol reranker">R</span><span><b>{{ item.name }}</b><small>{{ item.model }} · {{ item.base_url }}</small></span><span class="status" :class="item.status"><i></i>{{ statusLabel(item) }}</span><button class="text-button" :disabled="!!busy" @click="test('reranker', item.id)">测试</button></div></div>
      </article>

      <article class="panel resource-card">
        <div class="panel-heading"><div><span class="eyebrow">Embedding</span><h2>向量模型服务</h2></div><span class="resource-count">{{ embeddings.length }}</span></div>
        <form class="config-form" @submit.prevent="save('embedding')">
          <label><span>配置名称</span><input v-model="embeddingForm.name" required></label>
          <label class="wide"><span>OpenAI 兼容地址</span><input v-model="embeddingForm.base_url" type="url" required></label>
          <label><span>模型名称</span><input v-model="embeddingForm.model" required></label>
          <label><span>向量维度</span><input v-model.number="embeddingForm.dimension" type="number" min="0"></label>
          <label><span>批大小</span><input v-model.number="embeddingForm.batch_size" type="number" min="1"></label>
          <label><span>并发</span><input v-model.number="embeddingForm.concurrency" type="number" min="1"></label>
          <label class="wide"><span>API Key 环境变量（可选）</span><input v-model="embeddingForm.api_key_env" placeholder="例如 EMBEDDING_API_KEY"><small>只保存变量名，不保存密钥值</small></label>
          <button class="primary-button wide" :disabled="!!busy" type="submit">保存模型配置</button>
        </form>
        <div class="resource-list"><div v-for="item in embeddings" :key="item.id"><span class="resource-symbol">E</span><span><b>{{ item.name }}</b><small>{{ item.model }} · {{ item.dimension || '待检测' }} 维</small></span><span class="status" :class="item.status"><i></i>{{ statusLabel(item) }}</span><button class="text-button" :disabled="!!busy" @click="test('embedding', item.id)">测试</button></div></div>
      </article>

      <article class="panel resource-card">
        <div class="panel-heading"><div><span class="eyebrow">Vector store</span><h2>Milvus 向量库</h2></div><span class="resource-count">{{ vectors.length }}</span></div>
        <form class="config-form" @submit.prevent="save('vector')">
          <label><span>配置名称</span><input v-model="vectorForm.name" required></label>
          <label><span>存储类型</span><select v-model="vectorForm.kind"><option value="milvus">Milvus</option></select></label>
          <label class="wide"><span>连接地址</span><input v-model="vectorForm.uri" required></label>
          <label><span>Database</span><input v-model="vectorForm.database_name"></label>
          <label><span>Collection 前缀</span><input v-model="vectorForm.collection_prefix"></label>
          <label class="wide"><span>Token 环境变量（可选）</span><input v-model="vectorForm.token_env" placeholder="例如 MILVUS_TOKEN"></label>
          <button class="primary-button wide" :disabled="!!busy" type="submit">保存向量库配置</button>
        </form>
        <div class="resource-list"><div v-for="item in vectors" :key="item.id"><span class="resource-symbol vector">V</span><span><b>{{ item.name }}</b><small>{{ item.uri }} · {{ item.database_name }}</small></span><span class="status" :class="item.status"><i></i>{{ statusLabel(item) }}</span><button class="text-button" :disabled="!!busy" @click="test('vector', item.id)">测试</button></div></div>
      </article>

      <article class="panel resource-card graph-card">
        <div class="panel-heading"><div><span class="eyebrow">Graph store · Optional</span><h2>图数据库</h2></div><span class="resource-count">{{ graphs.length }}</span></div>
        <form class="config-form graph-form" @submit.prevent="save('graph')">
          <label><span>配置名称</span><input v-model="graphForm.name" placeholder="需要三元组图索引时配置"></label>
          <label><span>类型</span><select v-model="graphForm.kind"><option value="neo4j">Neo4j</option></select></label>
          <label><span>连接地址</span><input v-model="graphForm.uri"></label>
          <label><span>数据库</span><input v-model="graphForm.graph_space"></label>
          <label><span>用户名环境变量</span><input v-model="graphForm.username_env"></label>
          <label><span>密码环境变量</span><input v-model="graphForm.password_env"></label>
          <button class="ghost-button wide" :disabled="!!busy || !graphForm.name" type="submit">保存图数据库配置</button>
        </form>
        <div class="resource-list"><div v-for="item in graphs" :key="item.id"><span class="resource-symbol graph">G</span><span><b>{{ item.name }}</b><small>{{ item.uri }} · {{ item.graph_space }}</small></span><span class="status" :class="item.status"><i></i>{{ statusLabel(item) }}</span><button class="text-button" :disabled="!!busy" @click="test('graph', item.id)">测试</button></div><div v-if="!graphs.length" class="compact-empty">文本和 FAQ 索引不依赖图数据库，可以后续配置。</div></div>
      </article>
    </div>
    <div v-if="loading" class="page-loader"><span></span><p>正在读取资源配置…</p></div>
  </section>
</template>
