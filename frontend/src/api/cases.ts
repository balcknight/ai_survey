import http from './http'
import type { CaseDetail, CaseListResponse, CaseSummary, FileCheckResponse, RunRequest, RunResponse } from '../types/case'

export interface ListQuery {
  limit: number
  offset: number
  target_species?: string
  final_level?: string
  should_transfer?: string
  status?: string
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

export async function deleteCase(caseId: number): Promise<void> {
  await http.delete(`/api/cases/${caseId}`)
}

export async function checkByPath(sampleDir: string): Promise<FileCheckResponse> {
  const { data } = await http.post('/api/cases/check-by-path', { sample_dir: sampleDir })
  return data
}

export async function runKmer(payload: RunRequest): Promise<RunResponse> {
  const { data } = await http.post('/api/cases/run-kmer', payload)
  return data
}

export async function runNt(payload: RunRequest): Promise<RunResponse> {
  const { data } = await http.post('/api/cases/run-nt', payload)
  return data
}

export async function runSurvey(payload: RunRequest): Promise<RunResponse> {
  const { data } = await http.post('/api/cases/run-survey', payload)
  return data
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
