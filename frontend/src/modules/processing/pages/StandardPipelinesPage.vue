<script setup>
import { useDataForgeWorkspace } from '../../../composables/useDataForgeWorkspace'

const {
  publishForm, dataflowPipelines, compatibleTasks, selectedPipeline, knowledgeTypes,
  standardPipelines, busy, navigate, publishStandardPipeline, setDefaultPipeline,
  deactivateStandardPipeline, formatTime, statusText
} = useDataForgeWorkspace()
</script>

<template>
  <section class="page developer-page">
    <div class="developer-notice"><b>发布门禁</b><span>DataFlow 成功样本 → 运行环境预检 → 固定结构验证 → 不可变标准流程版本 → 业务默认流程。</span></div>
    <div class="standard-layout">
      <article class="panel publish-panel">
        <div class="panel-heading"><div><span class="eyebrow">Capability publishing</span><h2>从样本结果发布</h2></div></div>
        <div class="publish-form">
          <label><span>1. DataFlow 流程</span><select v-model="publishForm.dataflow_pipeline_id"><option value="">请选择</option><option v-for="pipe in dataflowPipelines" :key="pipe.id" :value="pipe.id" :disabled="pipe.is_draft">{{ pipe.name }}</option></select></label>
          <label><span>2. 成功样本</span><select v-model="publishForm.sample_task_id"><option value="">请选择</option><option v-for="task in compatibleTasks" :key="task.task_id" :value="task.task_id">{{ task.name || task.task_id.slice(0, 8) }} · {{ formatTime(task.completed_at || task.started_at) }}</option></select></label>
          <button v-if="selectedPipeline && !compatibleTasks.length" class="ghost-button" type="button" @click="navigate('studio')">去运行样本</button>
          <label><span>3. 输出知识类型</span><select v-model="publishForm.knowledge_type_id"><option value="">请选择</option><option v-for="type in knowledgeTypes.filter(item => item.active)" :key="type.id" :value="type.id">{{ type.name }} · V{{ type.version || 1 }}</option></select></label>
          <label><span>4. 标准流程名称</span><input v-model="publishForm.name"></label>
          <label><span>版本</span><input v-model.number="publishForm.version" type="number" min="1"></label>
          <label><span>说明</span><textarea v-model="publishForm.description" rows="3"></textarea></label>
          <button class="primary-button" type="button" :disabled="busy" @click="publishStandardPipeline">{{ busy ? '正在验证…' : '验证并发布' }}</button>
        </div>
      </article>

      <article class="panel catalog-panel">
        <div class="panel-heading"><div><span class="eyebrow">Published catalog</span><h2>{{ standardPipelines.length }} 个流程版本</h2></div></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>标准流程</th><th>输出类型</th><th>版本</th><th>状态</th><th>治理操作</th></tr></thead>
            <tbody>
              <tr v-for="pipe in standardPipelines" :key="pipe.id" :class="{ 'inactive-row': !pipe.active }">
                <td><b>{{ pipe.name }}</b><small>{{ pipe.description }}</small></td>
                <td>{{ pipe.knowledge_type_name }}</td>
                <td>V{{ pipe.version }}</td>
                <td><span class="status" :class="pipe.active ? pipe.validation_status : 'inactive'"><i></i>{{ statusText(pipe.active ? pipe.validation_status : 'inactive') }}</span></td>
                <td><div class="pipeline-actions"><span v-if="pipe.is_default" class="default-label">默认</span><button v-else-if="pipe.active && pipe.validation_status === 'validated'" class="text-button" type="button" @click="setDefaultPipeline(pipe.id)">设为默认</button><button v-if="pipe.active" class="text-button danger-text" type="button" :disabled="busy" @click="deactivateStandardPipeline(pipe.id)">停用</button><span v-else>保留历史引用</span></div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </div>
  </section>
</template>
