<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCasesStore } from '../stores/cases'
import type { CaseSummary } from '../types/case'
import { getCaseArchiveUrl, getCaseReportHtmlUrl } from '../api/cases'
import CaseBoard from '../components/workbench/CaseBoard.vue'

type ReviewChoice = 'correct' | 'incorrect' | 'uncertain'
type FinalDecision = 'transfer' | 'no_transfer'

const store = useCasesStore()

const reviewForm = reactive({
  kmer: 'correct' as ReviewChoice,
  nt: 'correct' as ReviewChoice,
  gc: 'correct' as ReviewChoice,
  finalDecision: 'no_transfer' as FinalDecision,
  note: '',
})
const submitConfirmVisible = ref(false)
const listRefreshing = ref(false)
const lastRefreshedAt = ref<Date | null>(null)
let filterTimer: ReturnType<typeof setTimeout> | null = null
const aiDetailDialogVisible = ref(false)
const aiDetailTitle = ref('')
const aiDetailContent = ref('')

const reviewChoiceOptions = [
  { label: '正确', value: 'correct' },
  { label: '不正确', value: 'incorrect' },
  { label: '不确定', value: 'uncertain' },
]

const selectedCaseTitle = computed(() => {
  if (!store.selectedCase) return '-'
  return store.selectedCase.sample_code || `Case #${store.selectedCase.id}`
})

const leftPaneMode = ref<'list' | 'report' | 'ai'>('list')
const leftPaneWidth = ref(44)
const resizing = ref(false)

const reportHtmlUrl = computed(() => {
  if (!store.selectedCaseId) return ''
  return getCaseReportHtmlUrl(store.selectedCaseId)
})

const layoutStyle = computed(() => ({
  gridTemplateColumns: `${leftPaneWidth.value}% 8px minmax(420px, 1fr)`,
}))

const archiveUrl = computed(() => {
  if (!store.selectedCaseId) return ''
  return getCaseArchiveUrl(store.selectedCaseId)
})

const bioinfoNamesText = computed(() => {
  const emails = store.selectedCase?.bioinfo_emails ?? []
  if (!emails.length) return '-'
  const names = emails
    .map((item) => item.email?.split('@')[0] || '')
    .map((item) => item.trim())
    .filter(Boolean)
  return names.length ? names.join(', ') : '-'
})

function yesNoText(value: boolean | null | undefined): string {
  if (value === true) return '是'
  if (value === false) return '否'
  return '-'
}

function openAiDetail(title: string, content: string | string[] | null | undefined) {
  aiDetailTitle.value = title
  if (Array.isArray(content)) {
    aiDetailContent.value = content.length ? content.join('\n') : '-'
  } else {
    aiDetailContent.value = (content || '-').toString()
  }
  aiDetailDialogVisible.value = true
}

function onRowClick(row: CaseSummary) {
  store.selectCase(row.id)
  leftPaneMode.value = 'ai'
}

async function onSubmitPrototype() {
  if (!store.selectedCase) {
    ElMessage.warning('请先选择样本再提交审核')
    return
  }
  submitConfirmVisible.value = true
}

async function confirmSubmit() {
  if (!store.selectedCase) return
  await store.submitManualReview(store.selectedCase.id, {
    kmer_review: reviewForm.kmer,
    nt_review: reviewForm.nt,
    gc_review: store.selectedCase.gc_result?.executed ? reviewForm.gc : 'uncertain',
    final_decision: reviewForm.finalDecision,
    note: reviewForm.note.trim() || null,
  })
  submitConfirmVisible.value = false
  ElMessage.success('人工审核已提交并持久化')
}

function decisionText(value: string | null | undefined): string {
  if (!value) return ''
  if (value === 'transfer' || value === 'rerun' || value === 'manual_transfer') return '流转'
  if (value === 'no_transfer' || value === 'confirm') return '不流转'
  return value
}

function buildJudgeNoteTemplate() {
  const report = store.selectedJudgeReport
  const ntAbnormal = yesNoText(report?.nt_abnormal)
  const kmerPoisson = yesNoText(report?.kmer_poisson)
  const ploidy = report?.ploidy_text || '-'
  const suggestion = report?.transfer_suggestion || '-'
  const summary = report?.summary_text || '-'
  return [
    `1.数据质控NT比对是否异常：${ntAbnormal}`,
    `2.Kmer峰型是否符合泊松分布：${kmerPoisson}`,
    `3.物种倍性：${ploidy}`,
    `4.流转建议：${suggestion}`,
    `survey结论：${summary}`,
  ].join('\n')
}

function startResize(event: MouseEvent) {
  event.preventDefault()
  resizing.value = true
  const onMove = (e: MouseEvent) => {
    const percent = (e.clientX / window.innerWidth) * 100
    leftPaneWidth.value = Math.max(28, Math.min(65, Number(percent.toFixed(1))))
  }
  const onUp = () => {
    resizing.value = false
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

const notePreviewHtml = computed(() => {
  const text = reviewForm.note.trim()
  if (!text) return '<p class="confirm-note-empty">（当前备注为空）</p>'
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `<p>${line}</p>`)
    .join('')
})

const listStatusText = computed(() => {
  if (listRefreshing.value || store.loadingList) return '正在更新列表...'
  if (!lastRefreshedAt.value) return '等待首次加载'
  const hh = `${lastRefreshedAt.value.getHours()}`.padStart(2, '0')
  const mm = `${lastRefreshedAt.value.getMinutes()}`.padStart(2, '0')
  const ss = `${lastRefreshedAt.value.getSeconds()}`.padStart(2, '0')
  return `已更新 ${hh}:${mm}:${ss}`
})

async function refreshListWithStatus() {
  listRefreshing.value = true
  try {
    store.filters.offset = 0
    await store.fetchList()
    lastRefreshedAt.value = new Date()
  } finally {
    listRefreshing.value = false
  }
}

onMounted(async () => {
  store.filters.review_status = 'unreviewed'
  if (!store.list.length) {
    await refreshListWithStatus()
  }
  if (!store.selectedCaseId && store.list.length) {
    await store.selectCase(store.list[0].id)
  }
})

watch(
  () => [store.selectedCaseId, store.selectedCase?.should_transfer, store.selectedJudgeReport?.summary_text] as const,
  ([caseId, shouldTransfer, summary]) => {
    if (!caseId || !summary) return
    reviewForm.kmer = 'correct'
    reviewForm.nt = 'correct'
    reviewForm.gc = 'correct'
    reviewForm.finalDecision = shouldTransfer === '是' || shouldTransfer === '转人工' ? 'transfer' : 'no_transfer'
    reviewForm.note = buildJudgeNoteTemplate()
  },
  { immediate: true },
)

watch(
  () => [store.filters.stage_code, store.filters.bioinfo_email, store.filters.review_status] as const,
  () => {
    if (filterTimer) clearTimeout(filterTimer)
    filterTimer = setTimeout(async () => {
      await refreshListWithStatus()
    }, 250)
  },
)
</script>

<template>
  <div class="manual-review-page">
    <header class="manual-review-page__header">
      <h1>人工审核模块</h1>
      <p>审核 survey 自动判定结果，逐项确认 kmer / nt / gc，并记录备注与最终决策。</p>
    </header>

    <section class="manual-review-page__layout" :style="layoutStyle">
      <el-card shadow="never" class="manual-review-page__list">
        <template #header>
          <div class="panel-title panel-title--with-actions">
            <span>
              {{
                leftPaneMode === 'list'
                  ? '待审核样本'
                  : leftPaneMode === 'report'
                    ? '报告'
                    : 'AI 自动判定'
              }}
            </span>
            <div class="panel-title-actions">
              <el-button size="small" :type="leftPaneMode === 'list' ? 'primary' : 'default'" @click="leftPaneMode = 'list'">
                样本
              </el-button>
              <el-button
                size="small"
                :type="leftPaneMode === 'report' ? 'primary' : 'default'"
                :disabled="!store.selectedCaseId"
                @click="leftPaneMode = 'report'"
              >
                报告
              </el-button>
              <el-button
                size="small"
                :type="leftPaneMode === 'ai' ? 'primary' : 'default'"
                :disabled="!store.selectedCaseId"
                @click="leftPaneMode = 'ai'"
              >
                AI 自动判定
              </el-button>
            </div>
          </div>
        </template>
        <template v-if="leftPaneMode === 'list'">
          <div class="filters">
          <el-input v-model="store.filters.stage_code" clearable placeholder="stage_code" />
          <el-input v-model="store.filters.bioinfo_email" clearable placeholder="bioinfo_email" />
          <el-select v-model="store.filters.review_status" placeholder="审核状态">
            <el-option label="未审核（默认）" value="unreviewed" />
            <el-option label="已审核" value="reviewed" />
          </el-select>
        </div>
        <div class="filters-status">
          <span class="filters-status__dot" :class="{ 'filters-status__dot--active': listRefreshing || store.loadingList }" />
          <span>{{ listStatusText }}</span>
        </div>
          <el-table
          v-loading="store.loadingList"
          :data="store.list"
          height="calc(100vh - 250px)"
          row-key="id"
          highlight-current-row
          :current-row-key="store.selectedCaseId ?? undefined"
          @row-click="onRowClick"
        >
          <el-table-column prop="stage_code" label="分期编号" width="120" />
          <el-table-column prop="sample_code" label="样本编号" min-width="150" show-overflow-tooltip />
          <el-table-column label="审核生信" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              {{ (row.bioinfo_emails?.[0]?.email || '').split('@')[0] || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="final_level" label="自动等级" width="110" />
          <el-table-column label="审核状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.reviewed ? 'success' : 'info'">{{ row.reviewed ? '已审核' : '未审核' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最终决策" width="130">
            <template #default="{ row }">
              {{ row.reviewed ? decisionText(row.review_final_decision) : '' }}
            </template>
          </el-table-column>
          </el-table>
        </template>
        <template v-else-if="leftPaneMode === 'report'">
          <div class="report-board">
            <div class="report-board__title">
              <span>报告看板（{{ selectedCaseTitle }}）</span>
              <a v-if="archiveUrl" :href="archiveUrl" target="_blank" rel="noopener">
                <el-button size="small">下载原始压缩包</el-button>
              </a>
            </div>
            <iframe
              v-if="reportHtmlUrl"
              :src="reportHtmlUrl"
              class="report-board__frame"
              title="survey-report-html"
            />
            <el-empty v-else description="暂无可展示报告" />
          </div>
        </template>
        <template v-else>
          <div class="ai-board-wrapper">
            <CaseBoard />
          </div>
        </template>
      </el-card>

      <div class="splitter" :class="{ 'splitter--active': resizing }" @mousedown="startResize" />

      <el-card shadow="never" class="manual-review-page__form">
        <template #header>
          <div class="panel-title">审核单 - {{ selectedCaseTitle }}</div>
        </template>

        <el-skeleton v-if="store.loadingDetail" :rows="10" animated />
        <el-empty v-else-if="!store.selectedCase" description="请选择左侧样本后开始审核" />
        <template v-else>
          <div class="auto-result">
            <div><b>自动 final_level:</b> {{ store.selectedCase.final_level || '-' }}</div>
            <div><b>自动 should_transfer:</b> {{ store.selectedCase.should_transfer || '-' }}</div>
            <div><b>审核生信（邮箱前缀）:</b> {{ bioinfoNamesText }}</div>
            <div><b>survey.remark:</b> {{ store.selectedCase.survey_result?.remark || '-' }}</div>
          </div>

          <div class="ai-judge-panel">
            <div class="ai-judge-panel__title">AI 判定结果（供人工校对）</div>
            <div class="ai-judge-grid">
              <div class="ai-judge-item">
                <div class="ai-judge-item__title">kmer</div>
                <div class="ai-judge-fields">
                  <div><b>kmer.pattern:</b> {{ store.selectedCase.kmer_result?.pattern || '-' }}</div>
                  <div><b>kmer.is_normal:</b> {{ yesNoText(store.selectedCase.kmer_result?.is_normal) }}</div>
                </div>
                <div class="ai-judge-links">
                  <el-button text type="primary" @click="openAiDetail('kmer.detail', store.selectedCase.kmer_result?.detail)">
                    查看 detail
                  </el-button>
                  <el-button
                    text
                    type="primary"
                    @click="openAiDetail('kmer.warnings', store.selectedCase.kmer_result?.warnings || [])"
                  >
                    查看 warnings
                  </el-button>
                </div>
                <div class="card-review-row">
                  <span class="review-ai-hint">人工确认</span>
                  <el-radio-group v-model="reviewForm.kmer" size="small">
                    <el-radio-button v-for="item in reviewChoiceOptions" :key="`k-${item.value}`" :value="item.value">
                      {{ item.label }}
                    </el-radio-button>
                  </el-radio-group>
                </div>
              </div>
              <div class="ai-judge-item">
                <div class="ai-judge-item__title">nt</div>
                <div class="ai-judge-fields">
                  <div><b>nt.nt_level:</b> {{ store.selectedCase.nt_result?.nt_level || '-' }}</div>
                  <div><b>nt.is_heavy_contamination:</b> {{ yesNoText(store.selectedCase.nt_result?.is_heavy_contamination) }}</div>
                </div>
                <div class="ai-judge-links">
                  <el-button
                    text
                    type="primary"
                    @click="openAiDetail('nt.ntspe_detail', store.selectedCase.nt_result?.ntspe_detail)"
                  >
                    查看 ntspe_detail
                  </el-button>
                </div>
                <div class="card-review-row">
                  <span class="review-ai-hint">人工确认</span>
                  <el-radio-group v-model="reviewForm.nt" size="small">
                    <el-radio-button v-for="item in reviewChoiceOptions" :key="`n-${item.value}`" :value="item.value">
                      {{ item.label }}
                    </el-radio-button>
                  </el-radio-group>
                </div>
              </div>
              <div class="ai-judge-item">
                <div class="ai-judge-item__title">gc</div>
                <div class="ai-judge-fields">
                  <div><b>gc.executed:</b> {{ yesNoText(store.selectedCase.gc_result?.executed) }}</div>
                  <div><b>gc.heavy_contamination:</b> {{ yesNoText(store.selectedCase.gc_result?.heavy_contamination) }}</div>
                </div>
                <div class="ai-judge-links" />
                <div v-if="store.selectedCase.gc_result?.executed" class="card-review-row">
                  <span class="review-ai-hint">人工确认</span>
                  <el-radio-group v-model="reviewForm.gc" size="small">
                    <el-radio-button v-for="item in reviewChoiceOptions" :key="`g-${item.value}`" :value="item.value">
                      {{ item.label }}
                    </el-radio-button>
                  </el-radio-group>
                </div>
                <div v-else class="card-review-row card-review-row--muted">
                  <span class="review-ai-hint">人工确认</span>
                  <span class="review-skip-text">GC 未执行，无需确认</span>
                </div>
              </div>
            </div>
          </div>

          <el-form label-position="top" class="review-form">
            <div class="review-decision-bar">
              <el-form-item label="审核最终决策" class="review-decision-item">
                <div class="decision-buttons">
                  <el-button
                    class="decision-button"
                    :type="reviewForm.finalDecision === 'transfer' ? 'primary' : 'default'"
                    @click="reviewForm.finalDecision = 'transfer'"
                  >
                    流转
                  </el-button>
                  <el-button
                    class="decision-button"
                    :type="reviewForm.finalDecision === 'no_transfer' ? 'danger' : 'default'"
                    @click="reviewForm.finalDecision = 'no_transfer'"
                  >
                    不流转
                  </el-button>
                </div>
              </el-form-item>
              <div class="review-submit-slot">
                <el-button class="submit-button" type="primary" @click="onSubmitPrototype">提交审核</el-button>
              </div>
            </div>

            <el-form-item label="审核备注">
              <el-input
                class="review-note-input"
                v-model="reviewForm.note"
                type="textarea"
                :rows="7"
                maxlength="1000"
                show-word-limit
                placeholder="请记录人工判断依据、疑点、后续建议"
              />
            </el-form-item>
          </el-form>
        </template>
      </el-card>
    </section>

    <el-dialog v-model="aiDetailDialogVisible" :title="aiDetailTitle" width="700px">
      <pre class="ai-detail-pre">{{ aiDetailContent }}</pre>
    </el-dialog>
    <el-dialog
      v-model="submitConfirmVisible"
      title="提交前确认"
      width="680px"
      class="submit-confirm-dialog"
    >
      <div class="submit-confirm">
        <div class="submit-confirm__alert">
          <strong>提醒：</strong>审核备注会作为 survey 完成邮件正文发送，请确认后提交。
        </div>

        <div class="submit-confirm__meta">
          <div><span>样本：</span>{{ selectedCaseTitle }}</div>
          <div><span>最终决策：</span>{{ reviewForm.finalDecision === 'transfer' ? '流转' : '不流转' }}</div>
        </div>

        <div class="submit-confirm__note">
          <div class="submit-confirm__note-title">邮件正文预览（审核备注）</div>
          <div class="submit-confirm__note-body" v-html="notePreviewHtml" />
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="submitConfirmVisible = false">返回修改</el-button>
          <el-button type="primary" @click="confirmSubmit">确认提交</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.manual-review-page {
  display: grid;
  gap: 12px;
  min-height: 100vh;
  padding: 16px;
  background: #f4f6f8;
}

.manual-review-page__header {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
  padding: 12px 16px;
}

.manual-review-page__header h1 {
  margin: 0;
  font-size: 22px;
  color: #0b2545;
}

.manual-review-page__header p {
  margin: 8px 0 0;
  color: #5b6b79;
}

.manual-review-page__layout {
  display: grid;
  grid-template-columns: 44% 8px minmax(420px, 1fr);
  gap: 12px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
}

.panel-title--with-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title-actions {
  display: flex;
  gap: 8px;
}

.filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.filters-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  min-height: 24px;
  color: #637083;
  font-size: 12px;
}

.filters-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c7d2;
}

.filters-status__dot--active {
  background: #409eff;
  box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.16);
}

.auto-result {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid #e5e9f2;
  border-radius: 8px;
  background: #fafcff;
}

.ai-judge-panel {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #e5e9f2;
  border-radius: 8px;
  background: #fff;
}

.ai-judge-panel__title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}

.ai-judge-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 10px;
  align-items: stretch;
}

.ai-judge-item {
  border: 1px solid #eef1f6;
  border-radius: 6px;
  padding: 0;
  background: #fafcff;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 190px;
}

.ai-judge-item__title {
  padding: 8px 10px;
  border-bottom: 1px solid #e8edf5;
  background: #f2f6fc;
  font-size: 13px;
  font-weight: 700;
  color: #1f2d3d;
  text-transform: lowercase;
  letter-spacing: 0.2px;
}

.ai-judge-fields {
  display: grid;
  gap: 6px;
  padding: 0 10px;
}

.ai-judge-links {
  min-height: 64px;
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-start;
  align-content: flex-start;
  gap: 6px 10px;
  padding: 0 10px;
}

.ai-judge-links :deep(.el-button) {
  margin-left: 0;
  min-height: 28px;
  line-height: 28px;
}

.review-form {
  margin-top: 12px;
}

.review-ai-hint {
  color: #2b6cb0;
  font-size: 12px;
}

.decision-buttons {
  display: flex;
  gap: 10px;
}

.decision-button {
  min-width: 88px;
  min-height: 36px;
}

.card-review-row {
  margin-top: auto;
  padding-top: 8px;
  padding-left: 10px;
  padding-right: 10px;
  padding-bottom: 10px;
  border-top: 1px dashed #e4eaf3;
  display: grid;
  gap: 6px;
}

.card-review-row--muted {
  gap: 4px;
}

.review-skip-text {
  font-size: 12px;
  color: #8a94a6;
}

.review-decision-bar {
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  background: #f8fbff;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.review-decision-item {
  margin-bottom: 0;
}

.review-decision-item :deep(.el-form-item__label) {
  margin-bottom: 6px;
}

.review-submit-slot {
  display: flex;
  align-items: center;
}

.submit-button {
  min-width: 110px;
  min-height: 38px;
}

.review-note-input {
  width: 100%;
}

.report-board {
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 8px;
}

.report-board__title {
  font-size: 16px;
  font-weight: 600;
  color: #0b2545;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.report-board__frame {
  width: 100%;
  height: calc(100vh - 200px);
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #fff;
}

.ai-board-wrapper {
  height: calc(100vh - 200px);
  overflow: auto;
}

.splitter {
  background: #dcdfe6;
  border-radius: 8px;
  cursor: col-resize;
}

.splitter--active {
  background: #409eff;
}

.ai-detail-pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 420px;
  overflow: auto;
}

.submit-confirm {
  display: grid;
  gap: 12px;
}

.submit-confirm__alert {
  padding: 10px 12px;
  border: 1px solid #ffe0b2;
  background: #fff8ee;
  border-radius: 8px;
  color: #8a4b00;
}

.submit-confirm__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 8px;
  padding: 8px 10px;
  background: #f7f9fc;
  border: 1px solid #e8edf5;
  border-radius: 8px;
}

.submit-confirm__meta span {
  color: #6b778c;
}

.submit-confirm__note {
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.submit-confirm__note-title {
  padding: 8px 10px;
  font-weight: 600;
  background: #f2f6fc;
  border-bottom: 1px solid #e8edf5;
}

.submit-confirm__note-body {
  max-height: 320px;
  overflow: auto;
  padding: 10px;
  line-height: 1.75;
  color: #1f2d3d;
  word-break: break-word;
}

.submit-confirm__note-body p {
  margin: 0 0 6px;
}

.confirm-note-empty {
  color: #909399;
}

@media (max-width: 1200px) {
  .manual-review-page__layout {
    grid-template-columns: 1fr;
  }
  .splitter {
    display: none;
  }
  .ai-judge-grid {
    grid-template-columns: 1fr;
  }
  .auto-result {
    grid-template-columns: 1fr;
  }
  .ai-board-wrapper {
    height: auto;
    max-height: none;
  }
  .review-decision-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .review-submit-slot {
    justify-content: flex-end;
  }
  .submit-confirm__meta {
    grid-template-columns: 1fr;
  }
}
</style>
