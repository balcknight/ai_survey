import http from './http'
import type {
  CaseDetail,
  CaseListResponse,
  CaseStats,
  CaseSummary,
  JudgeReport,
  ManualReview,
  RunResponse,
} from '../types/case'

export interface ListQuery {
  limit: number
  offset: number
  target_species?: string
  final_level?: string
  should_transfer?: string
  status?: string
  stage_code?: string
  bioinfo_email?: string
  review_status?: 'reviewed' | 'unreviewed'
  review_final_decision?: 'transfer' | 'no_transfer' | 'confirm' | 'rerun' | 'manual_transfer'
}

export async function getCases(params: ListQuery): Promise<CaseListResponse> {
  const response = await http.get('/api/cases', { params })
  const data = response.data as unknown

  // 兼容两种后端返回：
  // 1) 直接返回数组：CaseSummary[]
  // 2) 分页对象：{ items, total, limit, offset }
  if (Array.isArray(data)) {
    return {
      items: data as CaseSummary[],
      total: data.length,
      limit: params.limit,
      offset: params.offset,
    }
  }

  const payload = (data ?? {}) as Partial<CaseListResponse>
  const items = Array.isArray(payload.items) ? payload.items : []
  const headerTotal = Number(response.headers?.['x-total-count'])
  const total = Number.isFinite(payload.total)
    ? Number(payload.total)
    : Number.isFinite(headerTotal)
      ? headerTotal
      : params.offset + items.length

  return {
    items,
    total,
    limit: Number.isFinite(payload.limit) ? Number(payload.limit) : params.limit,
    offset: Number.isFinite(payload.offset) ? Number(payload.offset) : params.offset,
  }
}

export async function getCaseDetail(caseId: number): Promise<CaseDetail> {
  const { data } = await http.get(`/api/cases/${caseId}`)
  return data
}

export async function getCaseStats(): Promise<CaseStats> {
  const { data } = await http.get('/api/cases/stats')
  return data
}

export async function getJudgeReport(caseId: number): Promise<JudgeReport> {
  const { data } = await http.get(`/api/cases/${caseId}/judge-report`)
  return data
}

export function getCaseReportHtmlUrl(caseId: number): string {
  const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://10.11.0.6:8001').replace(/\/$/, '')
  return `${base}/api/cases/${caseId}/report-html`
}

export function getCaseArchiveUrl(caseId: number): string {
  const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://10.11.0.6:8001').replace(/\/$/, '')
  return `${base}/api/cases/${caseId}/archive`
}

export async function getManualReviews(caseId: number): Promise<ManualReview[]> {
  const { data } = await http.get(`/api/cases/${caseId}/manual-review`)
  return Array.isArray(data) ? data : []
}

export async function createManualReview(
  caseId: number,
  payload: Omit<ManualReview, 'id' | 'case_id' | 'created_at' | 'updated_at'>,
): Promise<ManualReview> {
  const { data } = await http.post(`/api/cases/${caseId}/manual-review`, payload)
  return data
}

export async function deleteCase(caseId: number): Promise<void> {
  await http.delete(`/api/cases/${caseId}`)
}

export async function rerunSurvey(sampleDir: string, sampleCode?: string): Promise<RunResponse> {
  const { data } = await http.post('/api/cases/rerun-survey', {
    sample_dir: sampleDir,
    sample_code: sampleCode ?? null,
    verbose: false,
    confirm: true,
  })
  return data
}
