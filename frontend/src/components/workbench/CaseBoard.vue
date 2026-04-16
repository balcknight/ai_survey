<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useCasesStore } from '../../stores/cases'
import { formatCellValue, formatLongText } from '../../utils/format'

const store = useCasesStore()

const showSurveyRemark = ref(false)
const showMetricsRemark = ref(false)

watch(
  () => store.selectedCaseId,
  () => {
    showSurveyRemark.value = false
    showMetricsRemark.value = false
  },
)

const resultMetricCompareRows = computed(() => {
  const raw = (store.selectedCase?.result_metrics?.raw ?? {}) as Record<string, unknown>
  const adjusted = (store.selectedCase?.result_metrics?.adjusted ?? {}) as Record<string, unknown>
  const keys = Array.from(new Set([...Object.keys(raw), ...Object.keys(adjusted)]))
  return keys.map((key) => ({
    key,
    raw: raw[key],
    adjusted: adjusted[key],
  }))
})

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

    <el-empty v-if="!store.selectedCase && !store.loadingDetail" description="请先从列表中选择一个样本" />

    <template v-else>
      <el-skeleton v-if="store.loadingDetail" :rows="8" animated />

      <div v-else class="board-sections">
        <el-card shadow="never">
          <template #header>摘要</template>
          <div class="kv-grid">
            <div><b>ID:</b> {{ formatCellValue(store.selectedCase?.id) }}</div>
            <div><b>sample_code:</b> {{ formatCellValue(store.selectedCase?.sample_code) }}</div>
            <div><b>target_species:</b> {{ formatCellValue(store.selectedCase?.target_species) }}</div>
            <div><b>status:</b> {{ formatCellValue(store.selectedCase?.status) }}</div>
            <div><b>final_level:</b> {{ formatCellValue(store.selectedCase?.final_level) }}</div>
            <div><b>should_transfer:</b> {{ formatCellValue(store.selectedCase?.should_transfer) }}</div>
            <div><b>source_path:</b> {{ formatCellValue(store.selectedCase?.source_path) }}</div>
            <div><b>updated_at:</b> {{ formatCellValue(store.selectedCase?.updated_at) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>Kmer 结果</template>
          <div class="kv-grid">
            <div><b>pattern:</b> {{ formatCellValue(store.selectedCase?.kmer_result?.pattern) }}</div>
            <div><b>is_normal:</b> {{ formatCellValue(store.selectedCase?.kmer_result?.is_normal) }}</div>
            <div class="span-2"><b>detail:</b> {{ formatLongText(store.selectedCase?.kmer_result?.detail) }}</div>
            <div class="span-2"><b>warnings:</b> {{ formatLongText(store.selectedCase?.kmer_result?.warnings) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>NT 结果</template>
          <div class="kv-grid">
            <div><b>nt_score:</b> {{ formatCellValue(store.selectedCase?.nt_result?.nt_score) }}</div>
            <div><b>nt_level:</b> {{ formatCellValue(store.selectedCase?.nt_result?.nt_level) }}</div>
            <div><b>ntcls_score:</b> {{ formatCellValue(store.selectedCase?.nt_result?.ntcls_score) }}</div>
            <div><b>ntspe_score:</b> {{ formatCellValue(store.selectedCase?.nt_result?.ntspe_score) }}</div>
            <div><b>ntcls_top1_pass:</b> {{ formatCellValue(store.selectedCase?.nt_result?.ntcls_top1_pass) }}</div>
            <div><b>ntcls_contamination_pass:</b> {{ formatCellValue(store.selectedCase?.nt_result?.ntcls_contamination_pass) }}</div>
            <div><b>ntspe_contamination_pass:</b> {{ formatCellValue(store.selectedCase?.nt_result?.ntspe_contamination_pass) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>Survey + Result Metrics</template>
          <div class="kv-grid">
            <div><b>survey.final_level:</b> {{ formatCellValue(store.selectedCase?.survey_result?.final_level) }}</div>
            <div><b>survey.should_transfer:</b> {{ formatCellValue(store.selectedCase?.survey_result?.should_transfer) }}</div>
            <div class="span-2">
              <b>survey.remark:</b>
              <div class="remark-content" :class="{ 'remark-content--collapsed': !showSurveyRemark }">
                {{ formatLongText(store.selectedCase?.survey_result?.remark) }}
              </div>
              <el-button text type="primary" @click="showSurveyRemark = !showSurveyRemark">
                {{ showSurveyRemark ? '收起' : '展开' }}
              </el-button>
            </div>
            <div><b>ploidy_pattern:</b> {{ formatCellValue(store.selectedCase?.result_metrics?.ploidy_pattern) }}</div>
            <div><b>ploidy_multiplier:</b> {{ formatCellValue(store.selectedCase?.result_metrics?.ploidy_multiplier) }}</div>
            <div class="span-2">
              <b>metrics.remark:</b>
              <div class="remark-content" :class="{ 'remark-content--collapsed': !showMetricsRemark }">
                {{ formatLongText(store.selectedCase?.result_metrics?.remark) }}
              </div>
              <el-button text type="primary" @click="showMetricsRemark = !showMetricsRemark">
                {{ showMetricsRemark ? '收起' : '展开' }}
              </el-button>
            </div>
          </div>

          <div class="result-metrics-table">
            <h4>Result Metrics 对比（raw / adjusted）</h4>
            <el-empty v-if="resultMetricCompareRows.length === 0" description="无 raw/adjusted 数据" :image-size="80" />
            <el-table v-else :data="resultMetricCompareRows" size="small" border>
              <el-table-column prop="key" label="字段" min-width="220" />
              <el-table-column label="raw" min-width="180">
                <template #default="{ row }">{{ formatCellValue(row.raw) }}</template>
              </el-table-column>
              <el-table-column label="adjusted" min-width="180">
                <template #default="{ row }">{{ formatCellValue(row.adjusted) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.case-board {
  height: 100%;
  border: 0;
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

.remark-content {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #4a5a6a;
  margin-top: 4px;
}

.remark-content--collapsed {
  max-height: 72px;
  overflow: hidden;
}

.result-metrics-table {
  margin-top: 14px;
}

.result-metrics-table h4 {
  margin: 0 0 8px;
  font-size: 14px;
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
