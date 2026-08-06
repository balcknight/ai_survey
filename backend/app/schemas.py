from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceItem(BaseModel):
    title: str
    url: str
    snippet: str


class AnalysisPloidy(BaseModel):
    pattern: str | None = None
    confidence: str | None = None
    reason: str | None = None
    sources: list[SourceItem] = Field(default_factory=list)
    enabled: bool = False


class PeaksData(BaseModel):
    depths: list[int] = Field(default_factory=list)
    freqs: list[float] = Field(default_factory=list)


class KmerResultIn(BaseModel):
    spe_peaks: PeaksData | None = None
    num_peaks: PeaksData | None = None
    pattern: str | None = None
    is_normal: bool | None = None
    detail: str | None = None
    spe_main_peak_depth: float | None = None
    num_main_peak_depth: float | None = None
    warnings: list[str] = Field(default_factory=list)
    analysis_ploidy: AnalysisPloidy | None = None
    spe_plot_path: str | None = None
    num_plot_path: str | None = None
    raw_payload: dict[str, Any] | None = None


class NtResultIn(BaseModel):
    nt_level: str | None = None
    is_heavy_contamination: bool | None = None
    nt_rule_version: str | None = None
    target_species: str | None = None
    target_category: str | None = None
    source_nt_count: int | None = None
    valid_nt_count: int | None = None
    dominant_category: str | None = None
    dominant_ratio_percent: float | None = None
    metazoa_ratio_percent: float | None = None
    plantae_ratio_percent: float | None = None
    bacteria_ratio_percent: float | None = None
    fungi_ratio_percent: float | None = None
    viruses_ratio_percent: float | None = None
    reasonable_contamination_ratio_percent: float | None = None
    pollution_ratio_percent: float | None = None
    pollution_threshold_percent: float | None = None
    ntcls_detail: str | None = None
    ntspe_detail: str | None = None
    class_filtered_path: str | None = None
    class_filtered_paths: list[str] = Field(default_factory=list)
    small_judged_paths: list[str] = Field(default_factory=list)
    nt_results: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] | None = None


class GcResultIn(BaseModel):
    executed: bool = False
    status: str | None = None
    reason: str | None = None
    pos_path: str | None = None
    heavy_contamination: bool | None = None
    gc_raw: dict[str, Any] | None = None
    raw_payload: dict[str, Any] | None = None


class SurveyResultIn(BaseModel):
    final_level: str | None = None
    should_transfer: str | None = None
    remark: str | None = None
    rule_version: str = "survey_rule_v2_gc"
    raw_payload: dict[str, Any] | None = None


class ResultMetricsIn(BaseModel):
    result_path: str | None = None
    ploidy_pattern: str | None = None
    ploidy_multiplier: int | None = None
    raw: dict[str, Any] | None = None
    adjusted: dict[str, Any] | None = None
    remark: str | None = None


class CaseCreate(BaseModel):
    sample_code: str | None = None
    target_species: str
    source_path: str | None = None
    stage_code: str | None = None
    bioinfo_emails: list["ContactInfo"] = Field(default_factory=list)
    operation_emails: list["ContactInfo"] = Field(default_factory=list)
    group_emails: list[str] = Field(default_factory=list)
    archive_path: str | None = None
    status: str = "created"
    remark: str | None = None
    kmer_result: KmerResultIn | None = None
    nt_result: NtResultIn | None = None
    gc_result: GcResultIn | None = None
    survey_result: SurveyResultIn | None = None
    result_metrics: ResultMetricsIn | None = None


class KmerResultOut(BaseModel):
    pattern: str | None = None
    is_normal: bool | None = None
    detail: str | None = None
    spe_main_peak_depth: float | None = None
    num_main_peak_depth: float | None = None
    spe_peaks: PeaksData | None = None
    num_peaks: PeaksData | None = None
    warnings: list[str] = Field(default_factory=list)
    analysis_ploidy: dict[str, Any] | None = None
    spe_plot_path: str | None = None
    num_plot_path: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NtResultOut(BaseModel):
    nt_level: str | None = None
    is_heavy_contamination: bool | None = None
    nt_rule_version: str | None = None
    target_species: str | None = None
    target_category: str | None = None
    source_nt_count: int | None = None
    valid_nt_count: int | None = None
    dominant_category: str | None = None
    dominant_ratio_percent: float | None = None
    metazoa_ratio_percent: float | None = None
    plantae_ratio_percent: float | None = None
    bacteria_ratio_percent: float | None = None
    fungi_ratio_percent: float | None = None
    viruses_ratio_percent: float | None = None
    reasonable_contamination_ratio_percent: float | None = None
    pollution_ratio_percent: float | None = None
    pollution_threshold_percent: float | None = None
    ntcls_detail: str | None = None
    ntspe_detail: str | None = None
    class_filtered_path: str | None = None
    class_filtered_paths: list[str] = Field(default_factory=list)
    small_judged_paths: list[str] = Field(default_factory=list)
    nt_results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GcResultOut(BaseModel):
    executed: bool = False
    status: str | None = None
    reason: str | None = None
    pos_path: str | None = None
    heavy_contamination: bool | None = None
    gc_raw: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SurveyResultOut(BaseModel):
    final_level: str | None = None
    should_transfer: str | None = None
    remark: str | None = None
    rule_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResultMetricsOut(BaseModel):
    result_path: str | None = None
    ploidy_pattern: str | None = None
    ploidy_multiplier: int | None = None
    raw: dict[str, Any] | None = None
    adjusted: dict[str, Any] | None = None
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CaseSummaryOut(BaseModel):
    id: int
    sample_code: str | None = None
    target_species: str
    stage_code: str | None = None
    bioinfo_emails: list["ContactInfo"] = Field(default_factory=list)
    status: str
    kmer_pattern: str | None = None
    kmer_is_normal: bool | None = None
    nt_level: str | None = None
    nt_is_heavy_contamination: bool | None = None
    gc_status: str | None = None
    gc_heavy_contamination: bool | None = None
    final_level: str | None = None
    should_transfer: str | None = None
    reviewed: bool = False
    review_final_decision: str | None = None
    updated_at: datetime


class CaseListOut(BaseModel):
    items: list[CaseSummaryOut]
    total: int
    limit: int
    offset: int


class CaseStatsOut(BaseModel):
    total: int
    by_final_level: dict[str, int] = Field(default_factory=dict)
    reviewed: int
    unreviewed: int


class CaseDetailOut(BaseModel):
    id: int
    sample_code: str | None = None
    target_species: str
    source_path: str | None = None
    stage_code: str | None = None
    bioinfo_emails: list["ContactInfo"] = Field(default_factory=list)
    operation_emails: list["ContactInfo"] = Field(default_factory=list)
    group_emails: list[str] = Field(default_factory=list)
    archive_path: str | None = None
    status: str
    final_level: str | None = None
    should_transfer: str | None = None
    remark: str | None = None
    created_at: datetime
    updated_at: datetime
    kmer_result: KmerResultOut | None = None
    nt_result: NtResultOut | None = None
    gc_result: GcResultOut | None = None
    survey_result: SurveyResultOut | None = None
    result_metrics: ResultMetricsOut | None = None


class FileCheckOut(BaseModel):
    spe_path: str | None = None
    num_path: str | None = None
    ntcls_path: str | None = None
    ntcls_source: str | None = None
    ntspe_path: str | None = None
    ntspe_paths: list[str] = Field(default_factory=list)
    ntspe_source: str | None = None
    result_path: str | None = None
    missing: list[str] = Field(default_factory=list)
    kmer_complete: bool = False
    nt_complete: bool = False
    complete: bool = False


class RunByPathIn(BaseModel):
    sample_dir: str
    sample_code: str | None = None
    verbose: bool = True


class JudgeReportOut(BaseModel):
    nt_abnormal: bool | None = None
    kmer_poisson: bool | None = None
    ploidy_text: str | None = None
    transfer_suggestion: str | None = None
    summary_text: str


class RunByPathOut(BaseModel):
    sample_dir: str
    file_check: FileCheckOut
    executed: bool = False
    message: str
    case_id: int | None = None
    case_detail: CaseDetailOut | None = None
    judge_report: JudgeReportOut | None = None


class ContactInfo(BaseModel):
    name: str
    email: str


class ExternalRunByArchiveOut(BaseModel):
    sample_dir: str
    archive_path: str
    stage_code: str
    sample_name: str
    bioinfo_emails: list[ContactInfo] = Field(default_factory=list)
    operation_emails: list[ContactInfo] = Field(default_factory=list)
    group_emails: list[str] = Field(default_factory=list)
    file_check: FileCheckOut
    executed: bool = False
    message: str
    case_id: int | None = None
    case_detail: CaseDetailOut | None = None
    judge_report: JudgeReportOut | None = None


class CheckByPathIn(BaseModel):
    sample_dir: str


class CheckByPathOut(BaseModel):
    sample_dir: str
    file_check: FileCheckOut
    message: str


class RunStepByPathIn(BaseModel):
    sample_dir: str
    sample_code: str | None = None
    case_id: int | None = None
    verbose: bool = True


class RunStepByPathOut(BaseModel):
    sample_dir: str
    executed: bool
    message: str
    file_check: FileCheckOut
    case_id: int | None = None
    case_detail: CaseDetailOut | None = None


class DeleteCaseOut(BaseModel):
    deleted: bool
    case_id: int
    message: str


class RerunSurveyIn(BaseModel):
    sample_dir: str
    sample_code: str | None = None
    verbose: bool = True
    confirm: bool = False


class ManualReviewIn(BaseModel):
    kmer_review: str = Field(pattern="^(correct|incorrect|uncertain)$")
    nt_review: str = Field(pattern="^(correct|incorrect|uncertain)$")
    gc_review: str = Field(pattern="^(correct|incorrect|uncertain)$")
    final_decision: str = Field(pattern="^(transfer|no_transfer|confirm|rerun|manual_transfer)$")
    note: str | None = None


class ManualReviewOut(BaseModel):
    id: int
    case_id: int
    kmer_review: str
    nt_review: str
    gc_review: str
    final_decision: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
