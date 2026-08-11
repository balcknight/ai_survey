<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useCasesStore } from '../../stores/cases'
import { formatCellValue, formatDatetime, formatLongText } from '../../utils/format'
import { getCaseStatusText, getGcStatusText, getNtLevelText } from '../../constants/case-tags'
import { getToken } from '../../utils/auth-token'
import type { GcLlmRoundSummary, GcPngStep } from '../../types/case'

const store = useCasesStore()

const showSurveyRemark = ref(false)
const showMetricsRemark = ref(false)
const plotPreviewVisible = ref(false)
const plotPreviewTitle = ref('')
const plotPreviewUrl = ref('')
const gcStepIndex = ref<number | null>(null)

watch(
  () => store.selectedCaseId,
  () => {
    showSurveyRemark.value = false
    showMetricsRemark.value = false
    plotPreviewVisible.value = false
    plotPreviewTitle.value = ''
    plotPreviewUrl.value = ''
    gcStepIndex.value = null
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
  // <img> 无法携带 Authorization 头，改用 ?token= 查询参数鉴权。
  const token = getToken()
  if (token) qs.set('token', token)
  return `${apiBase}/api/cases/${caseId}/gc-plot?${qs.toString()}`
})

const gcPlotEmptyText = computed(() => {
  const gc = store.selectedCase?.gc_result
  if (!gc) return '暂无 GC 数据'
  if (gc.status === 'fail') return 'GC 判定失败，未产出可展示图像'
  return '暂无 GC 图'
})

// ---- GC 判定演进展示（步骤快照 + LLM 思考过程） ----
const gcPngSteps = computed<GcPngStep[]>(() => {
  const steps = gcArtifacts.value?.png_steps
  return Array.isArray(steps) ? (steps as GcPngStep[]) : []
})

const gcHasSteps = computed(() => gcPngSteps.value.length > 0)

// 默认展示最终帧；gcStepIndex 为 null 时同样指向最后一步
const gcActiveStep = computed<GcPngStep | null>(() => {
  if (!gcHasSteps.value) return null
  return (
    gcPngSteps.value.find((s) => s.index === gcStepIndex.value) ??
    gcPngSteps.value[gcPngSteps.value.length - 1]
  )
})

const gcActiveImageUrl = computed(() => {
  const caseId = store.selectedCase?.id
  const gc = store.selectedCase?.gc_result
  const updatedAt = gc?.updated_at ?? store.selectedCase?.updated_at
  if (!caseId) return ''
  const pngPath = typeof gcArtifacts.value?.png === 'string' ? gcArtifacts.value.png : ''
  const qs = new URLSearchParams({ t: String(updatedAt ?? '') })
  if (gcHasSteps.value && gcActiveStep.value) {
    // 演进快照按 step 取图（后端会校验路径在受管目录内）
    qs.set('step', String(gcActiveStep.value.index))
  } else if (!pngPath) {
    return '' // 老数据无图可取
  }
  // <img> 无法携带 Authorization 头，改用 ?token= 查询参数鉴权。
  const token = getToken()
  if (token) qs.set('token', token)
  return `${apiBase}/api/cases/${caseId}/gc-plot?${qs.toString()}`
})

const gcActiveRoundDetail = computed<GcLlmRoundSummary | null>(() => {
  const step = gcActiveStep.value
  if (!step || step.stage !== 'llm_round' || step.round == null) return null
  const gcRaw = store.selectedCase?.gc_result?.gc_raw as Record<string, unknown> | null | undefined
  const llm = (gcRaw?.llm_adjustment ?? {}) as Record<string, unknown>
  const rounds = (llm.rounds_detail ?? []) as GcLlmRoundSummary[]
  return rounds.find((r) => r.round === step.round) ?? null
})

function gcStageText(stage?: string | null): string {
  if (stage === 'algo') return '算法第一遍'
  if (stage === 'llm_round') return 'LLM调整'
  if (stage === 'final') return '最终'
  return stage || '-'
}

function gcStageTagType(stage?: string | null): 'info' | 'warning' | 'success' {
  if (stage === 'llm_round') return 'warning'
  if (stage === 'final') return 'success'
  return 'info'
}

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
  const token = getToken()
  if (token) qs.set('token', token)
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
  const token = getToken()
  if (token) qs.set('token', token)
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
            <div><b>样本ID:</b> {{ formatCellValue(store.selectedCase?.id) }}</div>
            <div><b>样本编号:</b> {{ formatCellValue(store.selectedCase?.sample_code) }}</div>
            <div><b>分期号:</b> {{ formatCellValue(store.selectedCase?.stage_code) }}</div>
            <div><b>目标物种:</b> {{ formatCellValue(store.selectedCase?.target_species) }}</div>
            <div><b>判定状态:</b> {{ getCaseStatusText(store.selectedCase?.status) }}</div>
            <div><b>最终等级:</b> {{ formatCellValue(store.selectedCase?.final_level) }}</div>
            <div><b>是否流转:</b> {{ formatCellValue(store.selectedCase?.should_transfer) }}</div>
            <div><b>更新时间:</b> {{ formatDatetime(store.selectedCase?.updated_at) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>Kmer 结果</template>
          <div class="kv-grid">
            <div><b>Kmer倍型:</b> {{ formatCellValue(store.selectedCase?.kmer_result?.pattern) }}</div>
            <div><b>是否正常:</b> {{ formatCellValue(store.selectedCase?.kmer_result?.is_normal) }}</div>
            <div class="span-2"><b>判定详情:</b> {{ formatLongText(store.selectedCase?.kmer_result?.detail) }}</div>
            <div class="span-2"><b>警告信息:</b> {{ formatLongText(store.selectedCase?.kmer_result?.warnings) }}</div>
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
            <div><b>NT判定等级:</b> {{ getNtLevelText(store.selectedCase?.nt_result?.nt_level) }}</div>
            <div><b>是否重度污染:</b> {{ formatCellValue(store.selectedCase?.nt_result?.is_heavy_contamination) }}</div>
            <div><b>主要类别:</b> {{ formatCellValue(store.selectedCase?.nt_result?.dominant_category) }}</div>
            <div><b>污染占比(%):</b> {{ formatCellValue(store.selectedCase?.nt_result?.pollution_ratio_percent) }}</div>
            <div><b>污染判定阈值(%):</b> {{ formatCellValue(store.selectedCase?.nt_result?.pollution_threshold_percent) }}</div>
            <div class="span-2"><b>NT类别详情:</b> {{ formatLongText(store.selectedCase?.nt_result?.ntcls_detail) }}</div>
            <div class="span-2"><b>NT物种详情:</b> {{ formatLongText(store.selectedCase?.nt_result?.ntspe_detail) }}</div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>GC 复核</template>
          <div class="kv-grid">
            <div><b>是否执行:</b> {{ formatCellValue(store.selectedCase?.gc_result?.executed) }}</div>
            <div><b>GC状态:</b> {{ getGcStatusText(store.selectedCase?.gc_result?.status) }}</div>
            <div><b>是否重度污染:</b> {{ formatCellValue(store.selectedCase?.gc_result?.heavy_contamination) }}</div>
            <div><b>参与最终裁决:</b> {{ formatCellValue(store.selectedCase?.gc_result?.participated) }}</div>
            <div class="span-2"><b>原因说明:</b> {{ formatLongText(store.selectedCase?.gc_result?.reason) }}</div>
            <div class="span-2"><b>GC判定依据:</b> {{ formatLongText(gcDecision) }}</div>
            <div class="span-2"><b>全局统计:</b> {{ formatLongText(gcGlobalStats) }}</div>
          </div>
          <!-- 新数据：GC 判定演进（步骤快照 + LLM 思考） -->
          <div v-if="gcHasSteps" class="gc-evolution">
            <div class="gc-evolution__steps">
              <div
                v-for="s in gcPngSteps"
                :key="s.index"
                class="gc-step-item"
                :class="{ 'gc-step-item--active': gcActiveStep?.index === s.index }"
                @click="gcStepIndex = s.index"
              >
                <el-tag size="small" :type="gcStageTagType(s.stage)">{{ gcStageText(s.stage) }}</el-tag>
                <div class="gc-step-item__label">{{ s.label }}</div>
                <div v-if="s.contam_over_total_ratio != null" class="gc-step-item__ratio">
                  污染占比={{ Number(s.contam_over_total_ratio).toFixed(4) }}
                </div>
              </div>
            </div>
            <div class="gc-evolution__main">
              <img
                :src="gcActiveImageUrl"
                alt="gc-plot-step"
                class="kmer-plot-image"
                @click="openPlotPreview('GC', gcActiveImageUrl)"
              />
              <el-card shadow="never" class="gc-step-info">
                <template #header>当前步骤：{{ gcActiveStep?.label }}</template>
                <div class="kv-grid">
                  <div><b>阶段:</b> {{ gcStageText(gcActiveStep?.stage) }}</div>
                  <div><b>污染占比:</b> {{ formatCellValue(gcActiveStep?.contam_over_total_ratio) }}</div>
                  <div><b>污染带起点(gc_start):</b> {{ formatCellValue(gcActiveStep?.line?.gc_start) }}</div>
                  <div>
                    <b>边界线深度(d_left/d_right):</b>
                    {{ formatCellValue(gcActiveStep?.line?.d_left) }} / {{ formatCellValue(gcActiveStep?.line?.d_right) }}
                  </div>
                  <div><b>边界线斜率(slope):</b> {{ formatCellValue(gcActiveStep?.line?.slope) }}</div>
                  <div><b>边界线截距(intercept):</b> {{ formatCellValue(gcActiveStep?.line?.intercept) }}</div>
                  <div class="span-2">
                    <b>LLM调整原因:</b>
                    {{ formatLongText(gcActiveRoundDetail?.reason ?? gcActiveStep?.note ?? null) }}
                  </div>
                </div>
              </el-card>
            </div>
          </div>
          <!-- 老数据回退：单图展示 -->
          <div v-else class="gc-plot-grid">
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
          <template #header>Survey 判定与结果指标</template>
          <div class="kv-grid">
            <div><b>最终等级:</b> {{ formatCellValue(store.selectedCase?.survey_result?.final_level) }}</div>
            <div><b>是否流转:</b> {{ formatCellValue(store.selectedCase?.survey_result?.should_transfer) }}</div>
            <div class="span-2">
              <b>Survey备注:</b>
              <div class="remark-content" :class="{ 'remark-content--collapsed': !showSurveyRemark }">
                {{ formatLongText(store.selectedCase?.survey_result?.remark) }}
              </div>
              <el-button text type="primary" @click="showSurveyRemark = !showSurveyRemark">
                {{ showSurveyRemark ? '收起' : '展开' }}
              </el-button>
            </div>
            <div><b>倍型:</b> {{ formatCellValue(store.selectedCase?.result_metrics?.ploidy_pattern) }}</div>
            <div><b>倍型系数:</b> {{ formatCellValue(store.selectedCase?.result_metrics?.ploidy_multiplier) }}</div>
            <div class="span-2">
              <b>结果备注:</b>
              <div class="remark-content" :class="{ 'remark-content--collapsed': !showMetricsRemark }">
                {{ formatLongText(store.selectedCase?.result_metrics?.remark) }}
              </div>
              <el-button text type="primary" @click="showMetricsRemark = !showMetricsRemark">
                {{ showMetricsRemark ? '收起' : '展开' }}
              </el-button>
            </div>
          </div>

          <div class="result-metrics-table">
            <h4>结果指标对比（原始值 / 倍型修正值）</h4>
            <el-empty v-if="resultMetricCompareRows.length === 0" description="无原始/修正数据" :image-size="80" />
            <el-table v-else :data="resultMetricCompareRows" size="small" border>
              <el-table-column prop="key" label="指标" min-width="220" />
              <el-table-column label="原始值" min-width="180">
                <template #default="{ row }">{{ formatCellValue(row.raw) }}</template>
              </el-table-column>
              <el-table-column label="修正值" min-width="180">
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

.gc-evolution {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.gc-evolution__steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gc-step-item {
  border: 1px solid #e3e8ef;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.gc-step-item:hover {
  border-color: #b3c1d1;
}

.gc-step-item--active {
  border-color: #409eff;
  background: #ecf5ff;
}

.gc-step-item__label {
  margin-top: 6px;
  font-size: 13px;
  font-weight: 600;
}

.gc-step-item__ratio {
  margin-top: 2px;
  font-size: 12px;
  color: #6a7a8a;
}

.gc-evolution__main {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gc-step-info {
  border: 0;
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

  .gc-evolution {
    grid-template-columns: 1fr;
  }
}
</style>
