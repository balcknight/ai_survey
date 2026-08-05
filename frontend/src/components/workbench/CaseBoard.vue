<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useCasesStore } from '../../stores/cases'
import { formatCellValue, formatLongText } from '../../utils/format'

const store = useCasesStore()

const showSurveyRemark = ref(false)
const showMetricsRemark = ref(false)
const plotPreviewVisible = ref(false)
const plotPreviewTitle = ref('')
const plotPreviewUrl = ref('')

watch(
  () => store.selectedCaseId,
  () => {
    showSurveyRemark.value = false
    showMetricsRemark.value = false
    plotPreviewVisible.value = false
    plotPreviewTitle.value = ''
    plotPreviewUrl.value = ''
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

const gcDecision = computed(() => {
  const gcRaw = store.selectedCase?.gc_result?.gc_raw as Record<string, unknown> | null | undefined
  return (gcRaw?.decision ?? null) as Record<string, unknown> | null
})

const gcGlobalStats = computed(() => {
  const gcRaw = store.selectedCase?.gc_result?.gc_raw as Record<string, unknown> | null | undefined
  return (gcRaw?.global_stats ?? null) as Record<string, unknown> | null
})

const gcArtifacts = computed(() => {
  const gcRaw = store.selectedCase?.gc_result?.gc_raw as Record<string, unknown> | null | undefined
  return (gcRaw?.artifacts ?? null) as Record<string, unknown> | null
})

const gcPlotUrl = computed(() => {
  const caseId = store.selectedCase?.id
  const gc = store.selectedCase?.gc_result
  const artifacts = gcArtifacts.value
  const pngPath = typeof artifacts?.png === 'string' ? artifacts.png : ''
  const updatedAt = gc?.updated_at ?? store.selectedCase?.updated_at
  if (!caseId || !pngPath) return ''
  const qs = new URLSearchParams({
    t: String(updatedAt ?? ''),
  })
  return `${apiBase}/api/cases/${caseId}/gc-plot?${qs.toString()}`
})

const gcPlotEmptyText = computed(() => {
  const gc = store.selectedCase?.gc_result
  if (!gc) return '暂无 GC 数据'
  if (gc.status === 'fail') return 'GC 判定失败，未产出可展示图像'
  return '暂无 GC 图'
})

const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://10.11.0.6:8001'

const spePlotUrl = computed(() => {
  const caseId = store.selectedCase?.id
  const plotPath = store.selectedCase?.kmer_result?.spe_plot_path
  const updatedAt = store.selectedCase?.kmer_result?.updated_at ?? store.selectedCase?.updated_at
  if (!caseId || !plotPath) return ''
  const qs = new URLSearchParams({
    spectrum: 'spe',
    t: String(updatedAt ?? ''),
  })
  return `${apiBase}/api/cases/${caseId}/kmer-plot?${qs.toString()}`
})

const numPlotUrl = computed(() => {
  const caseId = store.selectedCase?.id
  const plotPath = store.selectedCase?.kmer_result?.num_plot_path
  const updatedAt = store.selectedCase?.kmer_result?.updated_at ?? store.selectedCase?.updated_at
  if (!caseId || !plotPath) return ''
  const qs = new URLSearchParams({
    spectrum: 'num',
    t: String(updatedAt ?? ''),
  })
  return `${apiBase}/api/cases/${caseId}/kmer-plot?${qs.toString()}`
})

function openPlotPreview(kind: 'Spe' | 'Num' | 'GC', url: string) {
  if (!url) return
  plotPreviewTitle.value = kind === 'GC' ? 'GC 图' : `${kind} 峰图`
  plotPreviewUrl.value = url
  plotPreviewVisible.value = true
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
            <div><b>spe_plot_path:</b> {{ formatCellValue(store.selectedCase?.kmer_result?.spe_plot_path) }}</div>
            <div><b>num_plot_path:</b> {{ formatCellValue(store.selectedCase?.kmer_result?.num_plot_path) }}</div>
            <div class="span-2"><b>detail:</b> {{ formatLongText(store.selectedCase?.kmer_result?.detail) }}</div>
            <div class="span-2"><b>warnings:</b> {{ formatLongText(store.selectedCase?.kmer_result?.warnings) }}</div>
          </div>
          <div class="kmer-plot-grid">
            <el-card shadow="never">
              <template #header>Spe 峰图</template>
              <el-empty v-if="!spePlotUrl" description="暂无 Spe 峰图" :image-size="80" />
              <img
                v-else
                :src="spePlotUrl"
                alt="spe-peak-plot"
                class="kmer-plot-image"
                @click="openPlotPreview('Spe', spePlotUrl)"
              />
            </el-card>
            <el-card shadow="never">
              <template #header>Num 峰图</template>
              <el-empty v-if="!numPlotUrl" description="暂无 Num 峰图" :image-size="80" />
              <img
                v-else
                :src="numPlotUrl"
                alt="num-peak-plot"
                class="kmer-plot-image"
                @click="openPlotPreview('Num', numPlotUrl)"
              />
            </el-card>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>NT 结果</template>
          <div class="kv-grid">
            <div><b>nt_level:</b> {{ formatCellValue(store.selectedCase?.nt_result?.nt_level) }}</div>
            <div><b>is_heavy_contamination:</b> {{ formatCellValue(store.selectedCase?.nt_result?.is_heavy_contamination) }}</div>
            <div><b>dominant_category:</b> {{ formatCellValue(store.selectedCase?.nt_result?.dominant_category) }}</div>
            <div><b>pollution_ratio_percent:</b> {{ formatCellValue(store.selectedCase?.nt_result?.pollution_ratio_percent) }}</div>
            <div><b>pollution_threshold_percent:</b> {{ formatCellValue(store.selectedCase?.nt_result?.pollution_threshold_percent) }}</div>
            <div class="span-2"><b>ntcls_detail:</b> {{ formatLongText(store.selectedCase?.nt_result?.ntcls_detail) }}</div>
            <div class="span-2"><b>ntspe_detail:</b> {{ formatLongText(store.selectedCase?.nt_result?.ntspe_detail) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>GC 复核</template>
          <div class="kv-grid">
            <div><b>executed:</b> {{ formatCellValue(store.selectedCase?.gc_result?.executed) }}</div>
            <div><b>status:</b> {{ formatCellValue(store.selectedCase?.gc_result?.status) }}</div>
            <div><b>heavy_contamination:</b> {{ formatCellValue(store.selectedCase?.gc_result?.heavy_contamination) }}</div>
            <div><b>pos_path:</b> {{ formatCellValue(store.selectedCase?.gc_result?.pos_path) }}</div>
            <div class="span-2"><b>reason:</b> {{ formatLongText(store.selectedCase?.gc_result?.reason) }}</div>
            <div class="span-2"><b>gc_raw.decision:</b> {{ formatLongText(gcDecision) }}</div>
            <div class="span-2"><b>gc_raw.global_stats:</b> {{ formatLongText(gcGlobalStats) }}</div>
            <div class="span-2"><b>gc_raw.artifacts:</b> {{ formatLongText(gcArtifacts) }}</div>
          </div>
          <div class="gc-plot-grid">
            <el-card shadow="never">
              <template #header>GC 图</template>
              <el-empty v-if="!gcPlotUrl" :description="gcPlotEmptyText" :image-size="80" />
              <img
                v-else
                :src="gcPlotUrl"
                alt="gc-plot"
                class="kmer-plot-image"
                @click="openPlotPreview('GC', gcPlotUrl)"
              />
            </el-card>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>判定报告</template>
          <div class="kv-grid">
            <div><b>NT比对是否异常:</b> {{ formatCellValue(store.selectedJudgeReport?.nt_abnormal) }}</div>
            <div><b>Kmer峰型是否泊松:</b> {{ formatCellValue(store.selectedJudgeReport?.kmer_poisson) }}</div>
            <div><b>物种倍性:</b> {{ formatCellValue(store.selectedJudgeReport?.ploidy_text) }}</div>
            <div><b>流转建议:</b> {{ formatCellValue(store.selectedJudgeReport?.transfer_suggestion) }}</div>
            <div class="span-2">
              <b>survey结论:</b>
              <div class="remark-content">{{ formatLongText(store.selectedJudgeReport?.summary_text) }}</div>
            </div>
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

  <el-dialog
    v-model="plotPreviewVisible"
    :title="plotPreviewTitle"
    width="86%"
    top="4vh"
    append-to-body
    destroy-on-close
  >
    <img v-if="plotPreviewUrl" :src="plotPreviewUrl" alt="kmer-plot-preview" class="kmer-plot-preview-image" />
  </el-dialog>
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
  align-items: start;
}

.kv-grid > div {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
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

.kmer-plot-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 12px;
}

.gc-plot-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: minmax(280px, 1fr);
  gap: 12px;
}

.kmer-plot-image {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 6px;
  border: 1px solid #e3e8ef;
  cursor: zoom-in;
}

.kmer-plot-preview-image {
  width: 100%;
  height: auto;
  display: block;
}

@media (max-width: 1100px) {
  .kv-grid {
    grid-template-columns: 1fr;
  }

  .span-2 {
    grid-column: span 1;
  }

  .kmer-plot-grid {
    grid-template-columns: 1fr;
  }

  .gc-plot-grid {
    grid-template-columns: 1fr;
  }
}
</style>
