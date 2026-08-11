export type CaseStatus = 'created' | 'kmer_done' | 'nt_done' | 'judged' | 'failed'

export interface CaseSummary {
  id: number
  sample_code: string | null
  target_species: string
  stage_code?: string | null
  bioinfo_emails?: Array<{ name: string; email: string }>
  reviewed?: boolean
  review_final_decision?: 'transfer' | 'no_transfer' | 'confirm' | 'rerun' | 'manual_transfer' | null
  status: CaseStatus
  kmer_pattern: string | null
  kmer_is_normal: boolean | null
  nt_level: string | null
  nt_is_heavy_contamination: boolean | null
  gc_status: string | null
  gc_heavy_contamination: boolean | null
  final_level: string | null
  should_transfer: '是' | '否' | '转人工' | null
  updated_at: string
}

export interface CaseListResponse {
  items: CaseSummary[]
  total: number
  limit: number
  offset: number
}

export interface CaseStats {
  total: number
  by_final_level: Record<string, number>
  reviewed: number
  unreviewed: number
}

export interface PeaksData {
  depths: number[]
  freqs: number[]
}

/** GC 边界线参数（png_steps[].line） */
export interface GcLineParams {
  gc_start?: number | null
  d_left?: number | null
  d_right?: number | null
  slope?: number | null
  intercept?: number | null
}

/** GC 判定演进步骤快照（gc_raw.artifacts.png_steps[]） */
export interface GcPngStep {
  index: number
  stage: 'algo' | 'llm_round' | 'final'
  label: string
  note?: string | null
  png: string
  round?: number | null
  line?: GcLineParams | null
  contam_over_total_ratio?: number | null
}

/** GC LLM 单轮复核摘要（gc_raw.llm_adjustment.rounds_detail[]） */
export interface GcLlmRoundSummary {
  round: number
  action?: string | null
  has_contamination?: boolean | null
  reason?: string | null
  proposed?: Record<string, unknown> | null
  clamped?: Record<string, unknown> | null
  stats_after?: Record<string, unknown> | null
  retried_parse?: boolean | null
  parse_error?: string | null
  error?: string | null
  elapsed_sec?: number | null
  png_step_index?: number | null
}

export interface CaseDetail
  extends Omit<
    CaseSummary,
    'kmer_pattern' | 'kmer_is_normal' | 'nt_level' | 'nt_is_heavy_contamination' | 'gc_status' | 'gc_heavy_contamination'
  > {
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
    spe_plot_path: string | null
    num_plot_path: string | null
    created_at?: string | null
    updated_at?: string | null
  } | null
  nt_result: {
    nt_level: string | null
    is_heavy_contamination: boolean | null
    nt_rule_version: string | null
    target_species: string | null
    target_category: string | null
    source_nt_count: number | null
    valid_nt_count: number | null
    dominant_category: string | null
    dominant_ratio_percent: number | null
    metazoa_ratio_percent: number | null
    plantae_ratio_percent: number | null
    bacteria_ratio_percent: number | null
    fungi_ratio_percent: number | null
    viruses_ratio_percent: number | null
    reasonable_contamination_ratio_percent: number | null
    pollution_ratio_percent: number | null
    pollution_threshold_percent: number | null
    ntcls_detail: string | null
    ntspe_detail: string | null
    class_filtered_path: string | null
    class_filtered_paths: string[]
    small_judged_paths: string[]
    nt_results: Record<string, unknown>[]
  } | null
  gc_result: {
    executed: boolean
    status: string | null
    reason: string | null
    pos_path: string | null
    heavy_contamination: boolean | null
    /** 本次 GC 是否参与最终裁决（老数据为 null，前端按 executed 回退） */
    participated?: boolean | null
    gc_raw: Record<string, unknown> | null
    created_at?: string | null
    updated_at?: string | null
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

export interface RunResponse {
  sample_dir: string
  executed: boolean
  message: string
  case_id?: number
  case_detail?: CaseDetail
  judge_report?: JudgeReport
  file_check?: {
    missing?: string[]
    complete?: boolean
    kmer_complete?: boolean
    nt_complete?: boolean
    ntcls_source?: string | null
    ntspe_source?: string | null
    ntspe_paths?: string[]
  }
}

export interface JudgeReport {
  nt_abnormal: boolean | null
  kmer_poisson: boolean | null
  ploidy_text: string | null
  transfer_suggestion: string | null
  summary_text: string
}

export interface ManualReview {
  id: number
  case_id: number
  reviewer_id?: number | null
  reviewer_name?: string | null
  kmer_review: 'correct' | 'incorrect' | 'uncertain'
  nt_review: 'correct' | 'incorrect' | 'uncertain'
  gc_review: 'correct' | 'incorrect' | 'uncertain'
  final_decision: 'transfer' | 'no_transfer' | 'confirm' | 'rerun' | 'manual_transfer'
  note: string | null
  // Kmer 判定不正确原因（仅记录用于算法校对，不作为邮件正文）
  kmer_incorrect_reason?: string | null
  created_at: string
  updated_at: string
}
