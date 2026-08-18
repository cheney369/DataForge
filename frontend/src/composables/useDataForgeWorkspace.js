import { computed, inject, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { lifecycleStages } from '../app/moduleRegistry'

const workspaceKey = Symbol('dataforge-workspace')

function createWorkspace() {
  const route = useRoute()
  const router = useRouter()
  const loading = ref(true)
  const busy = ref(false)
  const toast = ref(null)
  const lastUpdated = ref('')
  const dashboard = ref({ counts: {}, knowledge_counts: {} })
  const sources = ref([])
  const knowledgeTypes = ref([])
  const standardPipelines = ref([])
  const knowledgeJobs = ref([])
  const knowledgeBases = ref([])
  const dataflowPipelines = ref([])
  const dataflowTasks = ref([])
  const studioStatus = ref({})
  const dataflowHealth = ref({ status: 'blocked', runtime: [], pipelines: [], summary: {} })
  const selectedSourceId = ref('')
  const sourceQuery = ref('')
  const sourceKind = ref('')
  const sourcePreview = ref(null)
  const sourcePreviewLoading = ref(false)
  const uploadFile = ref(null)
  const uploadName = ref('')
  const uploadVersionSourceId = ref('')
  const wizardStep = ref(1)
  const selectedVersionIds = ref([])
  const selectedJobId = ref('')
  const jobDetail = ref(null)
  const jobDetailLoading = ref(false)
  const jobQuery = ref('')
  const jobStatus = ref('')
  const jobForm = reactive({ name: '', knowledge_type_id: '' })
  const selectedBaseId = ref('')
  const baseDetail = ref(null)
  const recordQuery = ref('')
  const recordPage = ref(1)
  const lineage = ref(null)
  const typeForm = reactive({ base_id: '', name: '', description: '', fields: [{ name: 'content', type: 'string', required: true }] })
  const publishForm = reactive({ name: '', description: '', dataflow_pipeline_id: '', sample_task_id: '', knowledge_type_id: '', version: 1, make_default: true })

  const workspace = computed(() => route.meta.workspace || 'business')
  const activePage = computed(() => route.meta.page || 'overview')
  const showUpload = computed(() => route.name === 'sources-upload')
  const showTypeForm = computed(() => route.name === 'types-new')
  const jobMode = computed(() => route.name === 'jobs-create' ? 'create' : 'list')
  const activeStage = computed(() => lifecycleStages.find(stage => stage.pages.some(page => page.id === activePage.value)) || lifecycleStages[0])
  const activeNav = computed(() => activeStage.value.pages)
  const showContextNav = computed(() => activeStage.value.id !== 'overview' && activePage.value !== 'studio')
  const pageTitle = computed(() => route.meta.title || '')
  const pageDescription = computed(() => route.meta.description || '')
  const actionLabel = computed(() => route.meta.action || '')
  const canGoBack = computed(() => Boolean(route.meta.panel))
  const returnLabel = computed(() => route.meta.returnLabel || '')
  const readyKnowledgeTypes = computed(() => knowledgeTypes.value.filter(type => type.active && standardPipelines.value.some(pipe => pipe.knowledge_type_id === type.id && pipe.active && pipe.validation_status === 'validated')))
  const latestVersions = computed(() => sources.value.filter(source => source.latest_version).map(source => ({ ...source.latest_version, source_name: source.name, source_kind: source.kind })))
  const selectedSource = computed(() => sources.value.find(item => item.id === selectedSourceId.value))
  const sourceKindOptions = computed(() => {
    const formats = new Map()
    sources.value.forEach(source => {
      const filename = source.latest_version?.original_filename || ''
      const key = filename.includes('.') ? filename.split('.').pop().toLowerCase() : source.kind
      formats.set(key, kindText(source.kind, filename))
    })
    return [...formats].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
  })
  const filteredSources = computed(() => {
    const query = sourceQuery.value.trim().toLocaleLowerCase('zh-CN')
    return sources.value.filter(source => {
      const filenames = source.versions.map(version => version.original_filename)
      const latestFilename = source.latest_version?.original_filename || ''
      const format = latestFilename.includes('.') ? latestFilename.split('.').pop().toLowerCase() : source.kind
      const matchesQuery = !query || source.name.toLocaleLowerCase('zh-CN').includes(query) || filenames.some(filename => filename.toLocaleLowerCase('zh-CN').includes(query))
      return matchesQuery && (!sourceKind.value || format === sourceKind.value)
    })
  })
  const filteredJobs = computed(() => {
    const query = jobQuery.value.trim().toLocaleLowerCase('zh-CN')
    return knowledgeJobs.value.filter(job => {
      const matchesQuery = !query || [job.name, job.knowledge_type_name, job.standard_pipeline_name].some(value => value?.toLocaleLowerCase('zh-CN').includes(query))
      return matchesQuery && (!jobStatus.value || job.status === jobStatus.value)
    })
  })
  const selectedJob = computed(() => {
    const summary = knowledgeJobs.value.find(item => item.id === selectedJobId.value)
    return jobDetail.value?.id === selectedJobId.value ? { ...summary, ...jobDetail.value } : summary
  })
  const selectedType = computed(() => knowledgeTypes.value.find(item => item.id === jobForm.knowledge_type_id && item.active))
  const selectedStandardPipeline = computed(() => standardPipelines.value.find(pipe => pipe.knowledge_type_id === jobForm.knowledge_type_id && pipe.active && pipe.validation_status === 'validated' && pipe.is_default) || standardPipelines.value.find(pipe => pipe.knowledge_type_id === jobForm.knowledge_type_id && pipe.active && pipe.validation_status === 'validated'))
  const selectedPipeline = computed(() => dataflowPipelines.value.find(item => item.id === publishForm.dataflow_pipeline_id))
  const compatibleTasks = computed(() => dataflowTasks.value.filter(task => task.pipeline_id === publishForm.dataflow_pipeline_id && task.status === 'completed'))
  const runningJobs = computed(() => knowledgeJobs.value.filter(job => ['pending', 'running'].includes(job.status)))
  const totalRecords = computed(() => knowledgeBases.value.reduce((total, base) => total + (base.record_count || 0), 0))

  function notify(message, error = false) { toast.value = { message, error }; window.setTimeout(() => { toast.value = null }, 3200) }
  function formatTime(value) { if (!value) return '—'; return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
  function formatSize(bytes) { if (!bytes && bytes !== 0) return '—'; if (bytes < 1024) return `${bytes} B`; if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / 1048576).toFixed(1)} MB` }
  function statusText(status) { return ({ pending: '等待处理', running: '处理中', completed: '已完成', failed: '处理失败', cancelled: '已取消', validated: '已发布', configured: '待验证', inactive: '已停用', available: '可使用' })[status] || status || '—' }
  function kindText(kind, filename = '') { const extension = filename.split('.').pop()?.toLowerCase(); return ({ pdf: 'PDF', csv: 'CSV', xlsx: 'Excel', md: 'Markdown', doc: 'Word', docx: 'Word', txt: '文本', json: 'JSON', jsonl: 'JSONL' })[extension] || ({ file: '文件', document: '文档' })[kind] || kind || '文件' }
  function recordSummary(record) { const data = record?.data || {}; return data.question || data.content || data.subject || data.messages?.[0]?.content || JSON.stringify(data) }
  function recordContent(value) { if (value == null) return '—'; if (typeof value === 'string') return value; return JSON.stringify(value, null, 2) }
  function fieldTypeText(type) { return ({ string: '文本', integer: '整数', array: '列表', object: '对象' })[type] || type }

  async function refreshAll(silent = false) {
    if (!silent) loading.value = true
    try {
      const [dash, sourceList, types, standards, jobs, bases, studio, health, pipelines, tasks] = await Promise.all([api.dashboard(), api.sources(), api.knowledgeTypes(), api.standardPipelines(), api.knowledgeJobs(), api.knowledgeBases(), api.studioStatus(), api.dataflowHealth(), api.dataflowPipelines(), api.dataflowTasks()])
      dashboard.value = dash; sources.value = sourceList; knowledgeTypes.value = types; standardPipelines.value = standards; knowledgeJobs.value = jobs; knowledgeBases.value = bases; studioStatus.value = studio; dataflowHealth.value = health; dataflowPipelines.value = pipelines; dataflowTasks.value = tasks
      if (!selectedSourceId.value && sourceList.length) selectedSourceId.value = sourceList[0].id
      if (!selectedJobId.value && jobs.length) selectedJobId.value = jobs[0].id
      if (!selectedBaseId.value && bases.length) selectedBaseId.value = bases[0].id
      if (selectedJobId.value) await selectJob(selectedJobId.value, true)
      lastUpdated.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date())
    } catch (error) { notify(error.message, true) } finally { loading.value = false }
  }

  const pageRoutes = { overview: 'overview', sources: 'sources', jobs: 'jobs', knowledge: 'knowledge', indexes: 'indexes', collections: 'collections', types: 'types', standard: 'standard', studio: 'studio', resources: 'resources', 'index-profiles': 'index-profiles', 'retrieval-profiles': 'retrieval-profiles', 'application-access': 'application-access', 'ai-applications': 'ai-applications' }
  function navigate(page) { if (route.name !== pageRoutes[page]) router.push({ name: pageRoutes[page] }) }
  function navigateStage(stageId) { const stage = lifecycleStages.find(item => item.id === stageId); if (stage) navigate(stage.defaultPage) }
  function switchWorkspace(next) { router.push({ name: next === 'business' ? 'overview' : 'types' }) }
  function goBack(fallback = {}) { if (route.meta.panel) router.back(); else router.push({ name: fallback.activePage || (workspace.value === 'business' ? 'overview' : 'types') }) }
  function openUpload() { router.push({ name: 'sources-upload' }) }
  function openTypeForm() { Object.assign(typeForm, { base_id: '', name: '', description: '', fields: [{ name: 'content', type: 'string', required: true }] }); router.push({ name: 'types-new' }) }
  function openTypeVersion(type) { Object.assign(typeForm, { base_id: type.id, name: type.name, description: type.description || '', fields: Object.entries(type.schema.properties || {}).map(([name, fieldType]) => ({ name, type: fieldType, required: (type.schema.required || []).includes(name) })) }); router.push({ name: 'types-new' }) }
  function closeCurrentPanel() { router.back() }
  function handlePrimaryAction() { if (['overview', 'jobs'].includes(activePage.value)) return openTaskWizard(); if (activePage.value === 'sources') return openUpload(); if (activePage.value === 'types') return openTypeForm(); if (activePage.value === 'standard') navigate('studio'); if (activePage.value === 'indexes') document.querySelector('#create-index')?.scrollIntoView({ behavior: 'smooth' }); if (activePage.value === 'collections') document.querySelector('#create-collection')?.scrollIntoView({ behavior: 'smooth' }) }
  function openTaskWizard(versionId = '') { selectedVersionIds.value = versionId ? [versionId] : []; jobForm.name = ''; jobForm.knowledge_type_id = readyKnowledgeTypes.value[0]?.id || ''; wizardStep.value = versionId ? 2 : 1; router.push({ name: 'jobs-create' }) }
  function closeTaskWizard() { router.back() }
  function openJob(jobId) { selectedJobId.value = jobId; router.push({ name: 'jobs' }) }
  function openKnowledgeBase(baseId) { selectedBaseId.value = baseId; router.push({ name: 'knowledge' }) }
  function toggleVersion(id) { selectedVersionIds.value = selectedVersionIds.value.includes(id) ? selectedVersionIds.value.filter(item => item !== id) : [...selectedVersionIds.value, id] }
  function nextWizardStep() { if (wizardStep.value === 1 && !selectedVersionIds.value.length) return notify('请至少选择一份文档', true); if (wizardStep.value === 2 && !jobForm.knowledge_type_id) return notify('请选择要生成的内容', true); wizardStep.value += 1 }
  function previousWizardStep() { if (wizardStep.value > 1) wizardStep.value -= 1 }

  async function startKnowledgeJob() { if (!jobForm.name.trim()) return notify('请填写知识库名称', true); busy.value = true; try { const job = await api.startKnowledgeJob({ name: jobForm.name.trim(), knowledge_type_id: jobForm.knowledge_type_id, source_version_ids: selectedVersionIds.value }); selectedJobId.value = job.id; await router.push({ name: 'jobs' }); notify('任务已创建，系统正在后台处理'); await refreshAll(true) } catch (error) { notify(error.message, true) } finally { busy.value = false } }
  async function selectJob(id, silent = false) { selectedJobId.value = id; if (!silent) jobDetailLoading.value = true; try { jobDetail.value = await api.knowledgeJob(id) } catch (error) { if (!silent) notify(error.message, true) } finally { jobDetailLoading.value = false } }
  async function cancelKnowledgeJob() { if (!selectedJob.value || !['pending', 'running'].includes(selectedJob.value.status)) return; if (!window.confirm('确认取消这个处理任务？已完成的源文件结果不会发布为知识资产。')) return; busy.value = true; try { await api.cancelKnowledgeJob(selectedJob.value.id); await refreshAll(true); notify('任务已取消') } catch (error) { notify(error.message, true) } finally { busy.value = false } }
  async function retryKnowledgeJob() { if (!selectedJob.value || !['failed', 'cancelled'].includes(selectedJob.value.status)) return; busy.value = true; try { const retry = await api.retryKnowledgeJob(selectedJob.value.id); selectedJobId.value = retry.id; jobDetail.value = null; await refreshAll(true); notify(`已创建第 ${retry.attempt_no} 次尝试`) } catch (error) { notify(error.message, true) } finally { busy.value = false } }
  async function uploadSource() { if (!uploadFile.value) return notify('请先选择文件', true); busy.value = true; const form = new FormData(); form.append('file', uploadFile.value); if (uploadName.value.trim()) form.append('name', uploadName.value.trim()); if (uploadVersionSourceId.value) form.append('source_id', uploadVersionSourceId.value); try { const result = await api.uploadSource(form); uploadFile.value = null; uploadName.value = ''; uploadVersionSourceId.value = ''; await router.push({ name: 'sources' }); await refreshAll(true); selectedSourceId.value = result.source.id; notify(result.created ? '文档上传成功' : '相同内容已经存在，未重复保存') } catch (error) { notify(error.message, true) } finally { busy.value = false } }
  async function previewSourceVersion(versionId) { sourcePreviewLoading.value = true; try { sourcePreview.value = await api.sourcePreview(versionId) } catch (error) { notify(error.message, true) } finally { sourcePreviewLoading.value = false } }
  function closeSourcePreview() { sourcePreview.value = null }
  async function selectBase(id, page = 1) { selectedBaseId.value = id; recordPage.value = page; lineage.value = null; try { baseDetail.value = await api.knowledgeBase(id, { page, pageSize: 30, query: recordQuery.value }) } catch (error) { notify(error.message, true) } }
  async function showLineage(recordId) { try { lineage.value = await api.knowledgeRecordLineage(recordId) } catch (error) { notify(error.message, true) } }
  async function createKnowledgeType() { const validFields = typeForm.fields.filter(field => field.name.trim()); if (!typeForm.name.trim() || !validFields.length) return notify('请填写类型名称和至少一个字段', true); busy.value = true; try { const properties = Object.fromEntries(validFields.map(field => [field.name.trim(), field.type])); const required = validFields.filter(field => field.required).map(field => field.name.trim()); if (!required.length) return notify('至少需要一个必填字段', true); const payload = { name: typeForm.name.trim(), description: typeForm.description.trim(), schema: { type: 'object', required, properties } }; const baseId = typeForm.base_id; const created = baseId ? await api.createKnowledgeTypeVersion(baseId, payload) : await api.createKnowledgeType(payload); Object.assign(typeForm, { base_id: '', name: '', description: '', fields: [{ name: 'content', type: 'string', required: true }] }); await router.push({ name: 'types' }); await refreshAll(true); notify(baseId ? `知识类型 V${created.version} 已创建` : '知识类型已创建，可继续为它发布标准流程') } catch (error) { notify(error.message, true) } finally { busy.value = false } }
  async function publishStandardPipeline() { if (!publishForm.dataflow_pipeline_id || !publishForm.sample_task_id || !publishForm.knowledge_type_id || !publishForm.name.trim()) return notify('请完整选择流程、成功样本、知识类型并填写名称', true); busy.value = true; try { const result = await api.publishStandardPipeline({ ...publishForm, name: publishForm.name.trim() }); notify(`发布成功，已验证 ${result.checked_records} 条样本数据`); Object.assign(publishForm, { name: '', description: '', dataflow_pipeline_id: '', sample_task_id: '', knowledge_type_id: '', version: 1, make_default: true }); await refreshAll(true) } catch (error) { notify(error.message, true) } finally { busy.value = false } }
  async function setDefaultPipeline(id) { try { await api.setDefaultPipeline(id); await refreshAll(true); notify('默认流程已更新，业务任务将自动使用它') } catch (error) { notify(error.message, true) } }
  async function deactivateStandardPipeline(id) { if (!window.confirm('确认停用这个标准流程版本？历史任务不受影响，但新任务将不能再使用它。')) return; busy.value = true; try { await api.deactivateStandardPipeline(id); await refreshAll(true); notify('标准流程已停用，历史版本仍保留') } catch (error) { notify(error.message, true) } finally { busy.value = false } }

  watch(selectedBaseId, id => { if (id) selectBase(id) })
  watch(selectedSourceId, () => { sourcePreview.value = null })
  watch(filteredSources, matches => { if (matches.length && !matches.some(source => source.id === selectedSourceId.value)) selectedSourceId.value = matches[0].id })
  watch(() => publishForm.dataflow_pipeline_id, () => { publishForm.sample_task_id = '' })
  let poller
  onMounted(async () => { await refreshAll(); if (selectedBaseId.value) await selectBase(selectedBaseId.value); poller = window.setInterval(() => { if (runningJobs.value.length) refreshAll(true) }, 3000) })
  onBeforeUnmount(() => window.clearInterval(poller))

  return { route, workspace, activePage, activeStage, lifecycleStages, showContextNav, loading, busy, toast, lastUpdated, dashboard, sources, knowledgeTypes, standardPipelines, knowledgeJobs, knowledgeBases, dataflowPipelines, dataflowTasks, studioStatus, dataflowHealth, selectedSourceId, sourceQuery, sourceKind, sourcePreview, sourcePreviewLoading, uploadFile, uploadName, uploadVersionSourceId, wizardStep, selectedVersionIds, selectedJobId, jobDetailLoading, jobQuery, jobStatus, jobForm, selectedBaseId, baseDetail, recordQuery, recordPage, lineage, typeForm, publishForm, activeNav, pageTitle, pageDescription, actionLabel, canGoBack, returnLabel, showUpload, showTypeForm, jobMode, readyKnowledgeTypes, latestVersions, selectedSource, sourceKindOptions, filteredSources, filteredJobs, selectedJob, selectedType, selectedStandardPipeline, selectedPipeline, compatibleTasks, runningJobs, totalRecords, formatTime, formatSize, statusText, kindText, recordSummary, recordContent, fieldTypeText, refreshAll, navigate, navigateStage, switchWorkspace, goBack, openUpload, openTypeForm, openTypeVersion, closeCurrentPanel, handlePrimaryAction, openTaskWizard, closeTaskWizard, openJob, openKnowledgeBase, toggleVersion, nextWizardStep, previousWizardStep, startKnowledgeJob, cancelKnowledgeJob, retryKnowledgeJob, selectJob, uploadSource, previewSourceVersion, closeSourcePreview, selectBase, showLineage, createKnowledgeType, publishStandardPipeline, setDefaultPipeline, deactivateStandardPipeline }
}

export function provideDataForgeWorkspace() { const workspace = createWorkspace(); provide(workspaceKey, workspace); return workspace }
export function useDataForgeWorkspace() { const workspace = inject(workspaceKey); if (!workspace) throw new Error('DataForge workspace is not available'); return workspace }
