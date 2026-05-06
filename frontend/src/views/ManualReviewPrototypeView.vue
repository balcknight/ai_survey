<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useCasesStore } from '../stores/cases'
import type { CaseSummary } from '../types/case'
import { getCaseArchiveUrl, getCaseReportHtmlUrl } from '../api/cases'

type ReviewChoice = 'correct' | 'incorrect' | 'uncertain'
type FinalDecision = 'confirm' | 'rerun' | 'manual_transfer'

const store = useCasesStore()

const reviewForm = reactive({
  reviewer_name: '',
  kmer: 'correct' as ReviewChoice,
  nt: 'correct' as ReviewChoice,
  gc: 'correct' as ReviewChoice,
  finalDecision: 'confirm' as FinalDecision,
  note: '',
})

const reviewChoiceOptions = [
  { label: '正确', value: 'correct' },
  { label: '不正确', value: 'incorrect' },
  { label: '不确定', value: 'uncertain' },
]

const finalDecisionOptions = [
  { label: '确认自动判定', value: 'confirm' },
  { label: '建议重跑', value: 'rerun' },
  { label: '转人工复核池', value: 'manual_transfer' },
]

const selectedCaseTitle = computed(() => {
  if (!store.selectedCase) return '-'
  return store.selectedCase.sample_code || `Case #${store.selectedCase.id}`
})

const reportDrawerVisible = computed({
  get: () => store.boardDrawerVisible,
  set: (value: boolean) => {
    if (!value) {
      store.closeBoardDrawer()
    }
  },
})

const reportHtmlUrl = computed(() => {
  if (!store.selectedCaseId) return ''
  return getCaseReportHtmlUrl(store.selectedCaseId)
})

const archiveUrl = computed(() => {
  if (!store.selectedCaseId) return ''
  return getCaseArchiveUrl(store.selectedCaseId)
})

const latestManualReview = computed(() => store.selectedManualReviews[0] ?? null)

const bioinfoNamesText = computed(() => {
  const emails = store.selectedCase?.bioinfo_emails ?? []
  if (!emails.length) return '-'
  const names = emails
    .map((item) => item.email?.split('@')[0] || '')
    .map((item) => item.trim())
    .filter(Boolean)
  return names.length ? names.join(', ') : '-'
})

function onRowClick(row: CaseSummary) {
  store.selectCase(row.id)
}

async function onSubmitPrototype() {
  if (!store.selectedCase) {
    ElMessage.warning('请先选择样本再提交审核')
    return
  }
  if (!reviewForm.reviewer_name.trim()) {
    ElMessage.warning('请填写审核人')
    return
  }
  await store.submitManualReview(store.selectedCase.id, {
    reviewer_name: reviewForm.reviewer_name.trim(),
    kmer_review: reviewForm.kmer,
    nt_review: reviewForm.nt,
    gc_review: reviewForm.gc,
    final_decision: reviewForm.finalDecision,
    note: reviewForm.note.trim() || null,
  })
  ElMessage.success('人工审核已提交并持久化')
}

async function onSearch() {
  store.filters.offset = 0
  await store.fetchList()
}

async function onReset() {
  store.resetFilters()
  await store.fetchList()
}

onMounted(async () => {
  store.filters.review_status = 'unreviewed'
  if (!store.list.length) {
    await store.fetchList()
  }
  if (!store.selectedCaseId && store.list.length) {
    await store.selectCase(store.list[0].id)
  }
})
</script>

<template>
  <div class="manual-review-page">
    <header class="manual-review-page__header">
      <h1>人工审核模块原型</h1>
      <p>审核 survey 自动判定结果，逐项确认 kmer / nt / gc，并记录备注与最终决策。</p>
    </header>

    <section class="manual-review-page__layout">
      <el-card shadow="never" class="manual-review-page__list">
        <template #header>
          <div class="panel-title">待审核样本</div>
        </template>
        <div class="filters">
          <el-input v-model="store.filters.stage_code" clearable placeholder="stage_code" />
          <el-input v-model="store.filters.bioinfo_email" clearable placeholder="bioinfo_email" />
          <el-select v-model="store.filters.review_status" placeholder="审核状态">
            <el-option label="未审核（默认）" value="unreviewed" />
            <el-option label="已审核" value="reviewed" />
          </el-select>
        </div>
        <div class="filters filters-actions">
          <el-button type="primary" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
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
          <el-table-column prop="id" label="ID" width="68" />
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
          <el-table-column prop="should_transfer" label="转人工" width="90" />
        </el-table>
      </el-card>

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
            <div><b>最近审核人:</b> {{ latestManualReview?.reviewer_name || '-' }}</div>
          </div>

          <el-form label-position="top" class="review-form">
            <el-form-item label="审核人">
              <el-input v-model="reviewForm.reviewer_name" placeholder="例如: wangwu" />
            </el-form-item>
            <el-form-item label="kmer 结果是否正确">
              <el-radio-group v-model="reviewForm.kmer">
                <el-radio-button v-for="item in reviewChoiceOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="nt 结果是否正确">
              <el-radio-group v-model="reviewForm.nt">
                <el-radio-button v-for="item in reviewChoiceOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="gc 结果是否正确">
              <el-radio-group v-model="reviewForm.gc">
                <el-radio-button v-for="item in reviewChoiceOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="审核最终决策">
              <el-radio-group v-model="reviewForm.finalDecision">
                <el-radio v-for="item in finalDecisionOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="审核备注">
              <el-input
                v-model="reviewForm.note"
                type="textarea"
                :rows="5"
                maxlength="1000"
                show-word-limit
                placeholder="请记录人工判断依据、疑点、后续建议"
              />
            </el-form-item>
          </el-form>

          <div class="review-actions">
            <el-button type="primary" @click="onSubmitPrototype">提交审核</el-button>
          </div>
        </template>
      </el-card>
    </section>

    <el-drawer
      v-model="reportDrawerVisible"
      direction="ltr"
      size="50%"
      :with-header="false"
      class="manual-review-page__report-drawer"
    >
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
    </el-drawer>
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
  grid-template-columns: 0.9fr 1.1fr;
  gap: 12px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
}

.filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.filters-actions {
  grid-template-columns: 100px 100px;
}

.auto-result {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid #e5e9f2;
  border-radius: 8px;
  background: #fafcff;
}

.review-form {
  margin-top: 12px;
}

.review-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
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
  height: calc(100vh - 70px);
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #fff;
}

@media (max-width: 1200px) {
  .manual-review-page__layout {
    grid-template-columns: 1fr;
  }
}
</style>
