import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import {
  checkByPath,
  createManualReview,
  deleteCase,
  getCaseDetail,
  getCases,
  getJudgeReport,
  getManualReviews,
  rerunSurvey,
  runKmer,
  runNt,
  runSurvey,
} from '../api/cases'
import type { CaseDetail, CaseSummary, FileCheckResponse, JudgeReport, ManualReview, RunResponse } from '../types/case'

export type RunType = 'kmer' | 'nt' | 'survey'

export const useCasesStore = defineStore('cases', () => {
  const list = ref<CaseSummary[]>([])
  const total = ref(0)
  const loadingList = ref(false)

  const selectedCaseId = ref<number | null>(null)
  const selectedCase = ref<CaseDetail | null>(null)
  const selectedJudgeReport = ref<JudgeReport | null>(null)
  const selectedManualReviews = ref<ManualReview[]>([])
  const loadingDetail = ref(false)
  const boardDrawerVisible = ref(false)

  const runningType = ref<RunType | null>(null)
  const checkingFiles = ref(false)

  const filters = ref({
    target_species: '',
    final_level: '',
    should_transfer: '',
    status: '',
    stage_code: '',
    bioinfo_email: '',
    review_status: '' as '' | 'reviewed' | 'unreviewed',
    review_final_decision: '' as '' | 'transfer' | 'no_transfer',
    limit: 20,
    offset: 0,
  })

  const fileCheckResult = ref<FileCheckResponse | null>(null)

  const hasSelection = computed(() => selectedCaseId.value !== null)

  async function fetchList() {
    loadingList.value = true
    try {
      const data = await getCases({
        limit: filters.value.limit,
        offset: filters.value.offset,
        target_species: filters.value.target_species || undefined,
        final_level: filters.value.final_level || undefined,
        should_transfer: filters.value.should_transfer || undefined,
        status: filters.value.status || undefined,
        stage_code: filters.value.stage_code || undefined,
        bioinfo_email: filters.value.bioinfo_email || undefined,
        review_status: filters.value.review_status || undefined,
        review_final_decision: filters.value.review_final_decision || undefined,
      })
      list.value = Array.isArray(data.items) ? data.items : []
      total.value = Number.isFinite(data.total) ? data.total : list.value.length
    } finally {
      loadingList.value = false
    }
  }

  async function selectCase(caseId: number) {
    selectedCaseId.value = caseId
    boardDrawerVisible.value = true
    loadingDetail.value = true
    try {
      selectedCase.value = await getCaseDetail(caseId)
      try {
        selectedJudgeReport.value = await getJudgeReport(caseId)
      } catch {
        selectedJudgeReport.value = null
      }
      try {
        selectedManualReviews.value = await getManualReviews(caseId)
      } catch {
        selectedManualReviews.value = []
      }
    } finally {
      loadingDetail.value = false
    }
  }

  async function submitManualReview(
    caseId: number,
    payload: Omit<ManualReview, 'id' | 'case_id' | 'created_at' | 'updated_at'>,
  ) {
    await createManualReview(caseId, payload)
    selectedManualReviews.value = await getManualReviews(caseId)
    await fetchList()
  }

  async function checkFiles(sampleDir: string) {
    checkingFiles.value = true
    try {
      fileCheckResult.value = await checkByPath(sampleDir)
      ElMessage.success('文件检查完成')
    } finally {
      checkingFiles.value = false
    }
  }

  async function runByPath(runType: RunType, sampleDir: string, sampleCode?: string): Promise<RunResponse> {
    runningType.value = runType
    try {
      const payload = {
        sample_dir: sampleDir,
        sample_code: sampleCode || null,
        verbose: false,
      }

      let result: RunResponse
      if (runType === 'kmer') {
        result = await runKmer(payload)
      } else if (runType === 'nt') {
        result = await runNt(payload)
      } else {
        result = await runSurvey(payload)
      }

      if (result.executed) {
        ElMessage.success(result.message)
        await fetchList()
        if (result.case_id) {
          await selectCase(result.case_id)
        }
      } else {
        ElMessage.warning(result.message)
      }

      return result
    } finally {
      runningType.value = null
    }
  }

  async function rerunSelectedCase() {
    if (!selectedCase.value?.source_path) {
      ElMessage.warning('当前样本缺少 source_path，无法重跑')
      return
    }

    runningType.value = 'survey'
    try {
      const result = await rerunSurvey(selectedCase.value.source_path, selectedCase.value.sample_code ?? undefined)
      ElMessage.success(result.message)
      await fetchList()
      if (selectedCaseId.value) {
        await selectCase(selectedCaseId.value)
      }
    } finally {
      runningType.value = null
    }
  }

  async function removeSelectedCase() {
    if (!selectedCaseId.value) return

    const caseId = selectedCaseId.value
    await deleteCase(caseId)
    ElMessage.success('删除成功')

    if (selectedCaseId.value === caseId) {
      selectedCaseId.value = null
      selectedCase.value = null
      selectedJudgeReport.value = null
      selectedManualReviews.value = []
      boardDrawerVisible.value = false
    }
    await fetchList()
  }

  function closeBoardDrawer() {
    boardDrawerVisible.value = false
  }

  function resetFilters() {
    filters.value = {
      target_species: '',
      final_level: '',
      should_transfer: '',
      status: '',
      stage_code: '',
      bioinfo_email: '',
      review_status: '',
      review_final_decision: '',
      limit: 20,
      offset: 0,
    }
  }

  return {
    list,
    total,
    loadingList,
    selectedCaseId,
    selectedCase,
    selectedJudgeReport,
    selectedManualReviews,
    loadingDetail,
    boardDrawerVisible,
    runningType,
    checkingFiles,
    filters,
    fileCheckResult,
    hasSelection,
    fetchList,
    selectCase,
    submitManualReview,
    checkFiles,
    runByPath,
    rerunSelectedCase,
    removeSelectedCase,
    closeBoardDrawer,
    resetFilters,
  }
})
