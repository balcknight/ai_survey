<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { useCasesStore } from '../../stores/cases'

const store = useCasesStore()

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

async function onRerun() {
  await ElMessageBox.confirm('将覆盖该路径已有记录，是否继续？', '确认重跑', {
    type: 'warning',
    confirmButtonText: '继续覆盖',
    cancelButtonText: '取消',
  })
  await store.rerunSelectedCase()
}

async function onDelete() {
  await ElMessageBox.confirm('删除后可重新发起同路径判定，是否继续？', '确认删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await store.removeSelectedCase()
}
</script>

<template>
  <el-card shadow="never" class="case-board">
    <template #header>
      <div class="case-board__header">
        <span>详情看板</span>
        <div class="case-board__actions">
          <el-button :disabled="!store.hasSelection" :loading="store.runningType === 'survey'" @click="onRerun">
            重跑 survey
          </el-button>
          <el-button type="danger" plain :disabled="!store.hasSelection" @click="onDelete">删除</el-button>
        </div>
      </div>
    </template>

    <el-empty v-if="!store.selectedCase && !store.loadingDetail" description="请先从左侧选择一个样本" />

    <template v-else>
      <el-skeleton v-if="store.loadingDetail" :rows="8" animated />

      <div v-else class="board-sections">
        <el-card shadow="never">
          <template #header>摘要</template>
          <div class="kv-grid">
            <div><b>ID:</b> {{ fmt(store.selectedCase?.id) }}</div>
            <div><b>sample_code:</b> {{ fmt(store.selectedCase?.sample_code) }}</div>
            <div><b>target_species:</b> {{ fmt(store.selectedCase?.target_species) }}</div>
            <div><b>status:</b> {{ fmt(store.selectedCase?.status) }}</div>
            <div><b>final_level:</b> {{ fmt(store.selectedCase?.final_level) }}</div>
            <div><b>should_transfer:</b> {{ fmt(store.selectedCase?.should_transfer) }}</div>
            <div><b>source_path:</b> {{ fmt(store.selectedCase?.source_path) }}</div>
            <div><b>updated_at:</b> {{ fmt(store.selectedCase?.updated_at) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>Kmer 结果</template>
          <div class="kv-grid">
            <div><b>pattern:</b> {{ fmt(store.selectedCase?.kmer_result?.pattern) }}</div>
            <div><b>is_normal:</b> {{ fmt(store.selectedCase?.kmer_result?.is_normal) }}</div>
            <div class="span-2"><b>detail:</b> {{ fmt(store.selectedCase?.kmer_result?.detail) }}</div>
            <div class="span-2"><b>warnings:</b> {{ fmt(store.selectedCase?.kmer_result?.warnings) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>NT 结果</template>
          <div class="kv-grid">
            <div><b>nt_score:</b> {{ fmt(store.selectedCase?.nt_result?.nt_score) }}</div>
            <div><b>nt_level:</b> {{ fmt(store.selectedCase?.nt_result?.nt_level) }}</div>
            <div><b>ntcls_score:</b> {{ fmt(store.selectedCase?.nt_result?.ntcls_score) }}</div>
            <div><b>ntspe_score:</b> {{ fmt(store.selectedCase?.nt_result?.ntspe_score) }}</div>
            <div><b>ntcls_top1_pass:</b> {{ fmt(store.selectedCase?.nt_result?.ntcls_top1_pass) }}</div>
            <div><b>ntcls_contamination_pass:</b> {{ fmt(store.selectedCase?.nt_result?.ntcls_contamination_pass) }}</div>
            <div><b>ntspe_contamination_pass:</b> {{ fmt(store.selectedCase?.nt_result?.ntspe_contamination_pass) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>Survey + Result Metrics</template>
          <div class="kv-grid">
            <div><b>survey.final_level:</b> {{ fmt(store.selectedCase?.survey_result?.final_level) }}</div>
            <div><b>survey.should_transfer:</b> {{ fmt(store.selectedCase?.survey_result?.should_transfer) }}</div>
            <div class="span-2"><b>survey.remark:</b> {{ fmt(store.selectedCase?.survey_result?.remark) }}</div>
            <div><b>ploidy_pattern:</b> {{ fmt(store.selectedCase?.result_metrics?.ploidy_pattern) }}</div>
            <div><b>ploidy_multiplier:</b> {{ fmt(store.selectedCase?.result_metrics?.ploidy_multiplier) }}</div>
            <div class="span-2"><b>metrics.remark:</b> {{ fmt(store.selectedCase?.result_metrics?.remark) }}</div>
          </div>
        </el-card>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.case-board {
  height: 100%;
}

.case-board__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.case-board__actions {
  display: flex;
  gap: 8px;
}

.board-sections {
  display: grid;
  gap: 12px;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 8px 16px;
  font-size: 13px;
}

.span-2 {
  grid-column: span 2;
}

@media (max-width: 1100px) {
  .kv-grid {
    grid-template-columns: 1fr;
  }

  .span-2 {
    grid-column: span 1;
  }
}
</style>
