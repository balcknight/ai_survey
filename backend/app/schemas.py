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
    freqs: list[int] = Field(default_factory=list)


class KmerResultIn(BaseModel):
    spe_peaks: PeaksData | None = None
    num_peaks: PeaksData | None = None
    pattern: str | None = None
    is_normal: bool | None = None
    detail: str | None = None
    warnings: list[str] = Field(default_factory=list)
    analysis_ploidy: AnalysisPloidy | None = None
    raw_payload: dict[str, Any] | None = None


class NtResultIn(BaseModel):
    nt_score: int | None = None
    nt_level: str | None = None
    ntcls_score: int | None = None
    ntspe_score: int | None = None
    ntcls_detail: str | None = None
    ntspe_detail: str | None = None
    ntcls_top1_pass: bool | None = None
    ntcls_contamination_pass: bool | None = None
    ntspe_contamination_pass: bool | None = None
    raw_payload: dict[str, Any] | None = None


class SurveyResultIn(BaseModel):
    final_level: str | None = None
    should_transfer: str | None = None
    remark: str | None = None
    rule_version: str = "survey_rule_v1"
    raw_payload: dict[str, Any] | None = None


class CaseCreate(BaseModel):
    sample_code: str | None = None
    target_species: str
    source_path: str | None = None
    status: str = "created"
    remark: str | None = None
    kmer_result: KmerResultIn | None = None
    nt_result: NtResultIn | None = None
    survey_result: SurveyResultIn | None = None


class SurveyJsonImportIn(BaseModel):
    sample_code: str | None = None
    source_path: str | None = None
    payload: dict[str, Any]


class KmerResultOut(BaseModel):
    pattern: str | None = None
    is_normal: bool | None = None
    detail: str | None = None
    spe_peaks: PeaksData | None = None
    num_peaks: PeaksData | None = None
    warnings: list[str] = Field(default_factory=list)
    analysis_ploidy: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NtResultOut(BaseModel):
    nt_score: int | None = None
    nt_level: str | None = None
    ntcls_score: int | None = None
    ntspe_score: int | None = None
    ntcls_detail: str | None = None
    ntspe_detail: str | None = None
    ntcls_top1_pass: bool | None = None
    ntcls_contamination_pass: bool | None = None
    ntspe_contamination_pass: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SurveyResultOut(BaseModel):
    final_level: str | None = None
    should_transfer: str | None = None
    remark: str | None = None
    rule_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CaseSummaryOut(BaseModel):
    id: int
    sample_code: str | None = None
    target_species: str
    status: str
    kmer_pattern: str | None = None
    kmer_is_normal: bool | None = None
    nt_score: int | None = None
    nt_level: str | None = None
    final_level: str | None = None
    should_transfer: str | None = None
    updated_at: datetime


class CaseDetailOut(BaseModel):
    id: int
    sample_code: str | None = None
    target_species: str
    source_path: str | None = None
    status: str
    final_level: str | None = None
    should_transfer: str | None = None
    remark: str | None = None
    created_at: datetime
    updated_at: datetime
    kmer_result: KmerResultOut | None = None
    nt_result: NtResultOut | None = None
    survey_result: SurveyResultOut | None = None

