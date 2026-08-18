import { createRouter, createWebHashHistory } from 'vue-router'
import { pageMeta } from './moduleRegistry'
import AppShell from '../layouts/AppShell.vue'

const page = (path, name, component, extra = {}) => ({
  path,
  name,
  component,
  meta: { page: extra.page || name, ...pageMeta[extra.page || name], ...extra }
})

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [{ path: '/', component: AppShell, children: [
    { path: '', redirect: '/business/overview' },
    page('/business/overview', 'overview', () => import('../modules/dashboard/pages/OverviewPage.vue')),
    page('/business/sources', 'sources', () => import('../modules/documents/pages/DocumentsPage.vue')),
    page('/business/sources/upload', 'sources-upload', () => import('../modules/documents/pages/DocumentsPage.vue'), { page: 'sources', panel: true, returnLabel: '文档管理' }),
    page('/business/jobs', 'jobs', () => import('../modules/processing/pages/JobsPage.vue')),
    page('/business/jobs/create', 'jobs-create', () => import('../modules/processing/pages/JobsPage.vue'), { page: 'jobs', panel: true, returnLabel: '处理任务', action: '' }),
    page('/business/knowledge', 'knowledge', () => import('../modules/assets/pages/AssetsPage.vue')),
    page('/business/indexes', 'indexes', () => import('../modules/indexing/pages/IndexJobsPage.vue')),
    page('/business/collections', 'collections', () => import('../modules/delivery/pages/CollectionsPage.vue')),
    page('/developer/types', 'types', () => import('../modules/processing/pages/KnowledgeTypesPage.vue')),
    page('/developer/types/new', 'types-new', () => import('../modules/processing/pages/KnowledgeTypesPage.vue'), { page: 'types', panel: true, returnLabel: '知识类型' }),
    page('/developer/standard', 'standard', () => import('../modules/processing/pages/StandardPipelinesPage.vue')),
    page('/developer/studio', 'studio', () => import('../modules/processing/pages/StudioPage.vue')),
    page('/developer/resources', 'resources', () => import('../modules/indexing/pages/ResourcesPage.vue')),
    page('/developer/index-profiles', 'index-profiles', () => import('../modules/indexing/pages/IndexProfilesPage.vue')),
    page('/developer/retrieval-profiles', 'retrieval-profiles', () => import('../modules/indexing/pages/RetrievalProfilesPage.vue')),
    page('/developer/application-access', 'application-access', () => import('../modules/applications/pages/ApplicationsPage.vue')),
    { path: '/developer/ai-applications', redirect: '/developer/application-access' },
    { path: '/:pathMatch(.*)*', redirect: '/business/overview' }
  ]}],
  scrollBehavior: () => ({ top: 0 })
})
