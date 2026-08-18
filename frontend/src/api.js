async function request(path, options = {}) {
  const response = await fetch(path, options)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      detail = payload.message || payload.detail || detail
    } catch (_) {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return response.json()
}

export const api = {
  health: () => request('/api/health'),
  dashboard: () => request('/api/dashboard'),
  sources: ({ query = '', kind = '' } = {}) => {
    const params = new URLSearchParams()
    if (query) params.set('query', query)
    if (kind) params.set('kind', kind)
    return request(`/api/sources${params.size ? `?${params}` : ''}`)
  },
  sourceVersions: (sourceId) => request(`/api/sources/${sourceId}/versions`),
  sourcePreview: (versionId) => request(`/api/source-versions/${versionId}/preview`),
  sourceDownloadUrl: (versionId) => `/api/source-versions/${versionId}/download`,
  uploadSource: (formData) => request('/api/sources', { method: 'POST', body: formData }),
  studioStatus: () => request('/api/dataflow-studio/status'),
  dataflowHealth: () => request('/api/dataflow-health'),
  dataflowPipelines: () => request('/api/dataflow-pipelines'),
  validateDataflowPipeline: (pipelineId) => request(`/api/dataflow-pipelines/${pipelineId}/validate`, { method: 'POST' }),
  dataflowTasks: (pipelineId = '') => request(`/api/dataflow-tasks${pipelineId ? `?pipeline_id=${encodeURIComponent(pipelineId)}` : ''}`),
  sendToDataFlow: (versionId) => request(`/api/source-versions/${versionId}/send-to-dataflow`, { method: 'POST' }),
  pipelines: () => request('/api/pipelines'),
  knowledgeTypes: () => request('/api/knowledge-types'),
  createKnowledgeType: (payload) => request('/api/knowledge-types', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  createKnowledgeTypeVersion: (typeId, payload) => request(`/api/knowledge-types/${typeId}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  standardPipelines: (typeId = '') => request(`/api/standard-pipelines${typeId ? `?knowledge_type_id=${encodeURIComponent(typeId)}` : ''}`),
  publishStandardPipeline: (payload) => request('/api/standard-pipelines/publish', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  setDefaultPipeline: (pipelineId) => request(`/api/standard-pipelines/${pipelineId}/default`, { method: 'POST' }),
  deactivateStandardPipeline: (pipelineId) => request(`/api/standard-pipelines/${pipelineId}/deactivate`, { method: 'POST' }),
  knowledgeJobs: () => request('/api/knowledge-jobs'),
  knowledgeJob: (jobId) => request(`/api/knowledge-jobs/${jobId}`),
  cancelKnowledgeJob: (jobId) => request(`/api/knowledge-jobs/${jobId}/cancel`, { method: 'POST' }),
  retryKnowledgeJob: (jobId) => request(`/api/knowledge-jobs/${jobId}/retry`, { method: 'POST' }),
  startKnowledgeJob: (payload) => request('/api/knowledge-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  knowledgeBases: () => request('/api/knowledge-bases'),
  knowledgeBase: (baseId, { page = 1, pageSize = 50, query = '' } = {}) => request(`/api/knowledge-bases/${baseId}?page=${page}&page_size=${pageSize}&query=${encodeURIComponent(query)}`),
  knowledgeRecordLineage: (recordId) => request(`/api/knowledge-records/${recordId}/lineage`),
  runs: () => request('/api/runs'),
  run: (runId) => request(`/api/runs/${runId}`),
  startRun: (payload) => request('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  assets: () => request('/api/assets'),
  assetVersions: (assetId) => request(`/api/assets/${assetId}/versions`),
  assetPreview: (versionId) => request(`/api/asset-versions/${versionId}/preview?limit=8`),
  lineage: (versionId) => request(`/api/asset-versions/${versionId}/lineage`),
  downloadUrl: (versionId) => `/api/asset-versions/${versionId}/download`,
  llmServices: () => request('/api/llm-services'),
  saveLLMService: (payload) => request('/api/llm-services', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  testLLMService: (id) => request(`/api/llm-services/${id}/test`, { method: 'POST' }),
  embeddingServices: () => request('/api/embedding-services'),
  saveEmbeddingService: (payload) => request('/api/embedding-services', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  testEmbeddingService: (id) => request(`/api/embedding-services/${id}/test`, { method: 'POST' }),
  rerankerServices: () => request('/api/reranker-services'),
  saveRerankerService: (payload) => request('/api/reranker-services', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  testRerankerService: (id) => request(`/api/reranker-services/${id}/test`, { method: 'POST' }),
  vectorStores: () => request('/api/vector-stores'),
  saveVectorStore: (payload) => request('/api/vector-stores', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  testVectorStore: (id) => request(`/api/vector-stores/${id}/test`, { method: 'POST' }),
  graphStores: () => request('/api/graph-stores'),
  saveGraphStore: (payload) => request('/api/graph-stores', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  testGraphStore: (id) => request(`/api/graph-stores/${id}/test`, { method: 'POST' }),
  indexProfiles: () => request('/api/index-profiles'),
  createIndexProfile: (payload) => request('/api/index-profiles', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  previewIndexProfile: (id, baseId = '') => request(`/api/index-profiles/${id}/preview${baseId ? `?base_id=${encodeURIComponent(baseId)}` : ''}`),
  publishIndexProfile: (id, payload = {}) => request(`/api/index-profiles/${id}/publish`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  deactivateIndexProfile: (id) => request(`/api/index-profiles/${id}/deactivate`, { method: 'POST' }),
  knowledgeIndexes: (baseId = '') => request(`/api/knowledge-indexes${baseId ? `?knowledge_base_id=${encodeURIComponent(baseId)}` : ''}`),
  createKnowledgeIndex: (payload) => request('/api/knowledge-indexes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  indexJobs: () => request('/api/index-jobs'),
  indexJob: (id) => request(`/api/index-jobs/${id}`),
  cancelIndexJob: (id) => request(`/api/index-jobs/${id}/cancel`, { method: 'POST' }),
  retryIndexJob: (id) => request(`/api/index-jobs/${id}/retry`, { method: 'POST' }),
  retrievalProfiles: () => request('/api/retrieval-profiles'),
  createRetrievalProfile: (payload) => request('/api/retrieval-profiles', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  publishRetrievalProfile: (id, payload = {}) => request(`/api/retrieval-profiles/${id}/publish`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  retrieve: (payload) => request('/api/retrieval/query', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  knowledgeCollections: () => request('/api/knowledge-collections'),
  createKnowledgeCollection: (payload) => request('/api/knowledge-collections', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  knowledgeCollection: (id) => request(`/api/knowledge-collections/${id}`),
  collectionVersions: (collectionId = '') => request(`/api/collection-versions${collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : ''}`),
  createCollectionVersion: (collectionId, payload) => request(`/api/knowledge-collections/${collectionId}/versions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  collectionVersion: (id) => request(`/api/collection-versions/${id}`),
  publishCollectionVersion: (id, payload = {}) => request(`/api/collection-versions/${id}/publish`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  queryCollectionVersion: (id, payload) => request(`/api/collection-versions/${id}/query`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  applicationBindings: () => request('/api/application-bindings'),
  createApplicationBinding: (payload) => request('/api/application-bindings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  applicationBindingEvents: (id) => request(`/api/application-bindings/${id}/events`),
  repointApplicationBinding: (id, payload) => request(`/api/application-bindings/${id}/repoint`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  queryApplicationBinding: (key, payload) => request(`/api/application-access/${encodeURIComponent(key)}/query`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  aiApplications: () => request('/api/ai-applications'),
  createAIApplication: (payload) => request('/api/ai-applications', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  aiApplication: (id) => request(`/api/ai-applications/${id}`),
  aiApplicationVersions: (applicationId = '') => request(`/api/ai-application-versions${applicationId ? `?application_id=${encodeURIComponent(applicationId)}` : ''}`),
  createAIApplicationVersion: (id, payload) => request(`/api/ai-applications/${id}/versions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  publishAIApplicationVersion: (id) => request(`/api/ai-application-versions/${id}/publish`, { method: 'POST' }),
  previewAIApplicationVersion: (id, payload) => request(`/api/ai-application-versions/${id}/preview`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  publishedApplicationConfig: (key, version = '') => request(`/v1/application-configs/${encodeURIComponent(key)}${version ? `/versions/${version}` : ''}`),
  createAIApplicationCredential: (id, payload) => request(`/api/ai-applications/${id}/credentials`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  }),
  revokeAIApplicationCredential: (id) => request(`/api/ai-application-credentials/${id}/revoke`, { method: 'POST' }),
  aiApplicationRuns: (applicationId = '', limit = 50) => request(`/api/ai-application-runs?limit=${limit}${applicationId ? `&application_id=${encodeURIComponent(applicationId)}` : ''}`),
  chatAIApplication: (key, payload) => request(`/api/ai-applications/${encodeURIComponent(key)}/chat`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  })
}
