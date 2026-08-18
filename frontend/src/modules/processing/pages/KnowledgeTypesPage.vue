<script setup>
import { useDataForgeWorkspace } from '../../../composables/useDataForgeWorkspace'

const {
  showTypeForm, typeForm, busy, knowledgeTypes, readyKnowledgeTypes, standardPipelines,
  closeCurrentPanel, createKnowledgeType, openTypeVersion, fieldTypeText
} = useDataForgeWorkspace()
</script>

<template>
  <section class="page developer-page">
    <div class="developer-notice"><b>结构先于流程</b><span>知识类型定义固定输出契约；Schema 变化必须创建新版本，再重新验证兼容流程。</span></div>

    <article v-if="showTypeForm" class="panel editor-panel">
      <div class="panel-heading"><div><span class="eyebrow">Schema governance</span><h2>{{ typeForm.base_id ? '创建知识类型新版本' : '新建知识类型' }}</h2></div><button class="text-button" type="button" @click="closeCurrentPanel">取消</button></div>
      <p v-if="typeForm.base_id" class="version-notice">保存后原版本停止用于新任务，已发布流程和历史知识资产仍保留原 Schema 引用。</p>
      <div class="type-form">
        <label><span>类型名称</span><input v-model="typeForm.name"></label>
        <label><span>业务说明</span><input v-model="typeForm.description"></label>
        <div class="field-editor">
          <div class="field-heading"><b>输出字段</b><button class="text-button" type="button" @click="typeForm.fields.push({ name: '', type: 'string', required: true })">添加字段</button></div>
          <div v-for="(field, index) in typeForm.fields" :key="index" class="field-row"><input v-model="field.name" placeholder="字段名"><select v-model="field.type"><option value="string">文本</option><option value="integer">整数</option><option value="array">列表</option><option value="object">对象</option></select><label class="check-label"><input v-model="field.required" type="checkbox">必填</label><button class="remove-button" type="button" :disabled="typeForm.fields.length === 1" @click="typeForm.fields.splice(index, 1)">移除</button></div>
        </div>
      </div>
      <div class="editor-actions"><button class="primary-button" type="button" :disabled="busy" @click="createKnowledgeType">{{ busy ? '正在保存…' : typeForm.base_id ? '创建新版本' : '保存类型' }}</button></div>
    </article>

    <div class="type-catalog">
      <article v-for="type in knowledgeTypes" :key="type.id" class="panel type-catalog-card" :class="{ 'inactive-type': !type.active }">
        <div class="panel-heading"><div><span class="eyebrow">Knowledge contract · V{{ type.version || 1 }}</span><h2>{{ type.name }}</h2></div><span class="status" :class="!type.active ? 'inactive' : readyKnowledgeTypes.some(item => item.id === type.id) ? 'validated' : 'configured'"><i></i>{{ !type.active ? '历史版本' : readyKnowledgeTypes.some(item => item.id === type.id) ? '业务可用' : '待发布流程' }}</span></div>
        <p>{{ type.description || '暂无业务说明' }}</p>
        <div class="schema-fields"><span v-for="(fieldType, fieldName) in type.schema.properties" :key="fieldName"><b>{{ fieldName }}</b><small>{{ fieldTypeText(fieldType) }}{{ type.schema.required.includes(fieldName) ? ' · 必填' : '' }}</small></span></div>
        <footer><span>{{ standardPipelines.filter(pipeline => pipeline.knowledge_type_id === type.id && pipeline.active && pipeline.validation_status === 'validated').length }} 个有效流程</span><button v-if="type.active" class="text-button" type="button" @click="openTypeVersion(type)">创建新版本</button><span v-else>由 V{{ type.version + 1 }} 或更高版本接替</span></footer>
      </article>
    </div>
  </section>
</template>
