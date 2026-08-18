<script setup>
import { api } from '../../../api'
import { useDataForgeWorkspace } from '../../../composables/useDataForgeWorkspace'

const {
  showUpload, sources, filteredSources, sourceKindOptions, selectedSourceId, selectedSource,
  sourceQuery, sourceKind, sourcePreview, sourcePreviewLoading, uploadFile, uploadName,
  uploadVersionSourceId, busy, openUpload, closeCurrentPanel, uploadSource,
  previewSourceVersion, closeSourcePreview, openTaskWizard, kindText, formatTime, formatSize
} = useDataForgeWorkspace()
</script>

<template>
  <section class="page">
    <article v-if="showUpload" class="panel editor-panel">
      <div class="panel-heading">
        <div><span class="eyebrow">来源接入</span><h2>上传文档</h2></div>
        <button class="text-button" type="button" @click="closeCurrentPanel">取消</button>
      </div>
      <div class="upload-grid">
        <label class="file-picker">
          <input type="file" accept=".pdf,.csv,.xlsx,.md,.docx,.txt,.json,.jsonl" @change="uploadFile = $event.target.files[0]">
          <b>{{ uploadFile?.name || '选择文件' }}</b>
          <small>PDF / CSV / Excel / Markdown / DOCX / TXT / JSON</small>
        </label>
        <label><span>文档名称</span><input v-model="uploadName" placeholder="默认使用文件名"></label>
        <label><span>版本归属</span><select v-model="uploadVersionSourceId"><option value="">创建新文档</option><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option></select></label>
      </div>
      <div class="editor-actions"><button class="primary-button" type="button" :disabled="busy" @click="uploadSource">{{ busy ? '正在上传…' : '确认上传' }}</button></div>
    </article>

    <div v-else class="section-command">
      <div><span class="eyebrow">Documents</span><b>来源与不可变版本</b></div>
      <button class="ghost-button" type="button" @click="openUpload">添加来源</button>
    </div>

    <div class="content-split">
      <article class="panel list-panel">
        <div class="panel-heading"><div><span class="eyebrow">来源目录</span><h2>{{ filteredSources.length }} 份文档</h2></div></div>
        <div class="source-toolbar" role="search">
          <label><span>搜索来源</span><input v-model="sourceQuery" type="search" placeholder="名称或文件名"></label>
          <label><span>文件格式</span><select v-model="sourceKind"><option value="">全部格式</option><option v-for="option in sourceKindOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        </div>
        <div v-if="filteredSources.length" class="entity-list">
          <button v-for="source in filteredSources" :key="source.id" class="entity-row" type="button" :class="{ selected: selectedSourceId === source.id }" :aria-pressed="selectedSourceId === source.id" @click="selectedSourceId = source.id">
            <span class="file-badge">{{ kindText(source.kind, source.latest_version?.original_filename) }}</span>
            <span><b>{{ source.name }}</b><small>{{ source.version_count }} 个版本 · {{ formatTime(source.latest_version?.created_at) }}</small></span>
          </button>
        </div>
        <div v-else class="empty-state"><p>{{ sources.length ? '没有符合条件的来源' : '还没有文档来源' }}</p><button v-if="sources.length" class="text-button" type="button" @click="sourceQuery = ''; sourceKind = ''">清除筛选</button></div>
      </article>

      <article class="panel detail-panel">
        <template v-if="selectedSource">
          <div class="panel-heading"><div><span class="eyebrow">来源详情</span><h2>{{ selectedSource.name }}</h2></div></div>
          <div class="detail-summary">
            <div><span>版本</span><b>{{ selectedSource.version_count }}</b></div>
            <div><span>最近更新</span><b>{{ formatTime(selectedSource.latest_version?.created_at) }}</b></div>
            <div><span>格式</span><b>{{ kindText(selectedSource.kind, selectedSource.latest_version?.original_filename) }}</b></div>
          </div>
          <h3 class="section-title">版本记录</h3>
          <div class="version-list">
            <div v-for="version in selectedSource.versions" :key="version.id">
              <span class="version-tag">V{{ version.version_no }}</span>
              <span><b>{{ version.original_filename }}</b><small>{{ formatSize(version.size_bytes) }} · {{ formatTime(version.created_at) }}</small></span>
              <span class="version-actions">
                <button class="text-button" type="button" :disabled="sourcePreviewLoading" @click="previewSourceVersion(version.id)">{{ sourcePreviewLoading ? '读取中…' : '预览' }}</button>
                <a class="text-button" :href="api.sourceDownloadUrl(version.id)" download>下载原文件</a>
                <button class="ghost-button" type="button" @click="openTaskWizard(version.id)">创建任务</button>
              </span>
            </div>
          </div>

          <section v-if="sourcePreview" class="source-preview" aria-live="polite">
            <header>
              <div><span class="eyebrow">版本预览</span><h3>{{ sourcePreview.source_version.original_filename }}</h3></div>
              <button class="text-button" type="button" aria-label="关闭版本预览" @click="closeSourcePreview">关闭</button>
            </header>
            <div class="preview-meta"><span>{{ sourcePreview.preview_record_count }} 条预览记录</span><span>{{ sourcePreview.character_count.toLocaleString() }} 个字符</span><span v-if="sourcePreview.truncated">已截取部分内容</span></div>
            <div class="preview-records">
              <article v-for="record in sourcePreview.records" :key="record.index">
                <small>记录 {{ record.index + 1 }}</small>
                <pre>{{ record.content }}</pre>
              </article>
            </div>
          </section>
        </template>
        <div v-else class="empty-state">选择文档查看版本</div>
      </article>
    </div>
  </section>
</template>
