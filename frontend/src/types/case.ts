export type CaseStatus = 'created' | 'kmer_done' | 'nt_done' | 'judged' | 'failed'

export interface CaseSummary {
  id: number
  sample_code: string | null
  target_species: string
  status: CaseStatus
  kmer_pattern: string | null
  kmer_is_normal: boolean | null
  nt_score: number | null
  nt_level: string | null
  final_level: string | null
  should_transfer: '是' | '否' | null
  updated_at: string
}

export interface CaseListResponse {
  items: CaseSummary[]
  total: number
  limit: number
  offset: number
}

export interface PeaksData {
  depths: number[]
  freqs: number[]
}

export interface CaseDetail extends Omit<CaseSummary, 'kmer_pattern' | 'kmer_is_normal' | 'nt_score' | 'nt_level'> {
  source_path: string | null
  remark: string | null
  created_at: string
  kmer_result: {
    pattern: string | null
    is_normal: boolean | null
    detail: string | null
    spe_peaks: PeaksData | null
    num_peaks: PeaksData | null
    warnings: string[]
    analysis_ploidy: Record<string, unknown> | null
  } | null
  nt_result: {
    nt_score: number | null
    nt_level: string | null
    ntcls_score: number | null
    ntspe_score: number | null
    ntcls_detail: string | null
    ntspe_detail: string | null
    ntcls_top1_pass: boolean | null
    ntcls_contamination_pass: boolean | null
    ntspe_contamination_pass: boolean | null
  } | null
  survey_result: {
    final_level: string | null
    should_transfer: string | null
    remark: string | null
    rule_version: string | null
  } | null
  result_metrics: {
    result_path: string | null
    ploidy_pattern: string | null
    ploidy_multiplier: number | null
    raw: Record<string, unknown> | null
    adjusted: Record<string, unknown> | null
    remark: string | null
  } | null
}

export interface RunRequest {
  sample_dir: string
  sample_code?: string | null
  case_id?: number | null
  verbose?: boolean
}

export interface RunResponse {
  sample_dir: string
  executed: boolean
  message: string
  case_id?: number
  case_detail?: CaseDetail
  file_check?: {
    missing?: string[]
    complete?: boolean
    kmer_complete?: boolean
    nt_complete?: boolean
  }
}

export interface FileCheckResponse {
  sample_dir: string
  message: string
  file_check: {
    spe_path: string | null
    num_path: string | null
    ntcls_path: string | null
    ntspe_path: string | null
    result_path: string | null
    missing: string[]
    kmer_complete: boolean
    nt_complete: boolean
    complete: boolean
  }
}
