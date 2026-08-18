<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import { provideDataForgeWorkspace } from '../composables/useDataForgeWorkspace'

const w = provideDataForgeWorkspace()
const storedNavMode = window.localStorage.getItem('dataforge-nav-mode')
const navPreference = ref(storedNavMode || 'auto')
const mobileNavOpen = ref(false)
const expandedStageId = ref(null)
const quickMenu = ref(null)

const isNavCollapsed = computed(() => navPreference.value === 'compact' || (navPreference.value === 'auto' && w.activePage.value === 'studio'))
const navigationStages = computed(() => w.lifecycleStages.filter(stage => stage.id !== 'overview'))

function toggleNavigation() {
  navPreference.value = isNavCollapsed.value ? 'expanded' : 'compact'
  window.localStorage.setItem('dataforge-nav-mode', navPreference.value)
}

function navigate(page) {
  mobileNavOpen.value = false
  w.navigate(page)
}

function handleStageClick(stage) {
  if (isNavCollapsed.value) {
    navigate(stage.defaultPage)
    return
  }
  if (w.activeStage.value.id === stage.id) {
    expandedStageId.value = expandedStageId.value === stage.id ? null : stage.id
    return
  }
  expandedStageId.value = stage.id
  navigate(stage.defaultPage)
}

function runQuickAction(action) {
  quickMenu.value?.removeAttribute('open')
  action()
}

function handleGlobalKey(event) {
  if (event.key === 'Escape') {
    mobileNavOpen.value = false
    quickMenu.value?.removeAttribute('open')
  }
}

watch(() => w.route.fullPath, () => {
  mobileNavOpen.value = false
  quickMenu.value?.removeAttribute('open')
})
watch(() => w.activeStage.value.id, stageId => {
  expandedStageId.value = stageId === 'overview' ? null : stageId
}, { immediate: true })
onMounted(() => window.addEventListener('keydown', handleGlobalKey))
onBeforeUnmount(() => window.removeEventListener('keydown', handleGlobalKey))
</script>

<template>
  <div class="app-shell" :class="{ 'overview-shell': w.activePage.value === 'overview', 'studio-shell': w.activePage.value === 'studio', 'nav-compact': isNavCollapsed, 'mobile-nav-open': mobileNavOpen }">
    <header class="app-header">
      <button class="mobile-nav-toggle" type="button" aria-label="打开主导航" @click="mobileNavOpen = true"><AppIcon name="menu" /></button>
      <button class="brand brand-button" type="button" aria-label="返回 DataForge 总览" @click="navigate('overview')">
        <span class="brand-mark">DF</span>
        <span><strong>DataForge</strong><small>Knowledge Operations</small></span>
      </button>

      <div class="header-tools">
        <details ref="quickMenu" class="quick-menu">
          <summary><AppIcon name="plus" size="16" /> 快捷创建</summary>
          <div>
            <button type="button" @click="runQuickAction(w.openUpload)"><AppIcon name="sources" /><span><b>上传文档</b><small>添加新的数据来源</small></span></button>
            <button type="button" @click="runQuickAction(w.openTaskWizard)"><AppIcon name="jobs" /><span><b>生产任务</b><small>从文档生成知识</small></span></button>
            <button type="button" @click="runQuickAction(w.openTypeForm)"><AppIcon name="types" /><span><b>知识类型</b><small>定义结构与字段</small></span></button>
          </div>
        </details>
        <div class="app-health" :class="{ online: w.dashboard.value.health?.status === 'ok' }" :title="w.dashboard.value.health?.status === 'ok' ? '服务运行正常' : '服务存在异常'">
          <span class="health-dot" :class="{ online: w.dashboard.value.health?.status === 'ok' }"></span>
          <span><b>{{ w.dashboard.value.health?.status === 'ok' ? '服务正常' : '服务异常' }}</b><small>本地环境</small></span>
        </div>
      </div>
    </header>

    <div class="workspace-frame">
      <button class="navigation-scrim" type="button" aria-label="关闭主导航" @click="mobileNavOpen = false"></button>
      <aside class="app-sidebar" aria-label="主导航">
        <div class="sidebar-scroll">
          <button class="sidebar-home nav-link" type="button" :class="{ active: w.activePage.value === 'overview' }" :title="isNavCollapsed ? '总览' : undefined" @click="navigate('overview')">
            <span class="nav-icon"><AppIcon name="overview" /></span><span class="nav-copy"><b>总览</b><small>运行概览与下一步</small></span>
          </button>

          <div v-for="stage in navigationStages" :key="stage.id" class="nav-stage" :class="{ active: w.activeStage.value.id === stage.id, expanded: expandedStageId === stage.id }">
            <button class="stage-button" type="button" :aria-expanded="isNavCollapsed ? undefined : expandedStageId === stage.id" :title="isNavCollapsed ? `${stage.label} · ${stage.note}` : undefined" @click="handleStageClick(stage)">
              <span class="nav-icon"><AppIcon :name="stage.id" /></span>
              <span class="nav-copy"><b>{{ stage.label }}</b><small>{{ stage.note }}</small></span>
              <span class="stage-chevron">›</span>
            </button>
            <nav v-if="!isNavCollapsed && expandedStageId === stage.id" :aria-label="`${stage.label}功能`">
              <button v-for="item in stage.pages" :key="item.id" type="button" class="nav-link child-link" :class="{ active: w.activePage.value === item.id }" @click="navigate(item.id)">
                <span class="child-rail"></span><span class="nav-copy"><b>{{ item.label }}</b><small>{{ item.note }}</small></span>
              </button>
            </nav>
          </div>
        </div>

        <div class="sidebar-footer">
          <div class="sidebar-service"><span class="health-dot" :class="{ online: w.dashboard.value.health?.status === 'ok' }"></span><span class="nav-copy"><b>{{ w.dashboard.value.health?.status === 'ok' ? '系统运行正常' : '需要检查服务' }}</b><small>{{ w.lastUpdated.value ? `同步于 ${w.lastUpdated.value}` : '正在连接服务' }}</small></span></div>
          <button class="nav-collapse" type="button" :aria-label="isNavCollapsed ? '展开主导航' : '收起主导航'" :title="isNavCollapsed ? '展开主导航' : '收起主导航'" @click="toggleNavigation"><AppIcon name="panel" /></button>
        </div>
      </aside>

      <main class="main-content">
        <header class="topbar" :class="{ 'overview-topbar': w.activePage.value === 'overview' }">
          <div class="topbar-title">
            <button v-if="w.canGoBack.value" class="top-back" type="button" @click="w.goBack()">← 返回{{ w.returnLabel.value }}</button>
            <div v-if="w.activePage.value !== 'overview'" class="breadcrumb"><span>{{ w.activeStage.value.label }}</span><i>/</i>{{ w.pageTitle.value }}</div>
            <h1>{{ w.pageTitle.value }}</h1><p>{{ w.pageDescription.value }}</p>
          </div>
          <div class="topbar-action"><small v-if="w.lastUpdated.value">同步于 {{ w.lastUpdated.value }}</small><button v-if="w.actionLabel.value" class="primary-button" type="button" @click="w.handlePrimaryAction">{{ w.actionLabel.value }}</button></div>
        </header>
        <div v-if="w.loading.value" class="page-loader"><span></span><p>正在载入工作空间…</p></div>
        <RouterView v-else />
      </main>
    </div>
    <Transition name="toast"><div v-if="w.toast.value" class="toast" :class="{ error: w.toast.value.error }" role="status" aria-live="polite">{{ w.toast.value.message }}</div></Transition>
  </div>
</template>
