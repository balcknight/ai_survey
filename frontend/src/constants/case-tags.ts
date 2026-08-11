import type { CaseStatus } from '../types/case'

export const FINAL_LEVEL_TAG_TYPE: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  正常: 'success',
  重度污染: 'danger',
  待人工复核: 'warning',
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

/** 样本状态中文映射（created|kmer_done|nt_done|judged|failed） */
export const CASE_STATUS_TEXT: Record<CaseStatus, string> = {
  created: '已创建',
  kmer_done: 'Kmer完成',
  nt_done: 'NT完成',
  judged: '已判定',
  failed: '失败',
}

/** GC 判定状态中文映射（ok|fail|skipped，未知值原样展示） */
export const GC_STATUS_TEXT: Record<string, string> = {
  ok: '正常',
  fail: '失败',
  skipped: '未执行',
}

/** NT 判定等级中文映射（正常/重度污染 原样展示；fail 表示 NT 判定本身未跑成） */
export const NT_LEVEL_TEXT: Record<string, string> = {
  fail: '判定失败',
}

export function getCaseStatusText(status: CaseStatus | null | undefined): string {
  if (!status) return '-'
  return CASE_STATUS_TEXT[status] ?? status
}

export function getGcStatusText(status: string | null | undefined): string {
  if (!status) return '-'
  return GC_STATUS_TEXT[status] ?? status
}

export function getNtLevelText(level: string | null | undefined): string {
  if (!level) return '-'
  return NT_LEVEL_TEXT[level] ?? level
}
