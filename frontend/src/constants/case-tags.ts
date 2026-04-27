import type { CaseStatus } from '../types/case'

export const FINAL_LEVEL_TAG_TYPE: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  正常: 'success',
  轻度污染: 'warning',
  重度污染: 'danger',
  待人工复核: 'warning',
  fail: 'info',
}

export const STATUS_TAG_TYPE: Record<CaseStatus, 'primary' | 'info' | 'warning' | 'danger'> = {
  judged: 'primary',
  created: 'info',
  kmer_done: 'info',
  nt_done: 'info',
  failed: 'danger',
}

export function getFinalLevelTagType(finalLevel: string | null): 'success' | 'warning' | 'danger' | 'info' {
  if (!finalLevel) return 'info'
  return FINAL_LEVEL_TAG_TYPE[finalLevel] ?? 'info'
}

export function getStatusTagType(status: CaseStatus): 'primary' | 'info' | 'warning' | 'danger' {
  return STATUS_TAG_TYPE[status] ?? 'warning'
}
