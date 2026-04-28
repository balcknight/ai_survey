from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class SurveyCase(Base):
    __tablename__ = "survey_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sample_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    target_species: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cc_emails_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False, index=True)
    final_level: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    should_transfer: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    kmer_result: Mapped[KmerResult | None] = relationship(
        "KmerResult", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    nt_result: Mapped[NtResult | None] = relationship(
        "NtResult", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    gc_result: Mapped[GcResult | None] = relationship(
        "GcResult", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    survey_result: Mapped[SurveyResult | None] = relationship(
        "SurveyResult", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )
    result_metrics: Mapped[ResultMetrics | None] = relationship(
        "ResultMetrics", back_populates="case", uselist=False, cascade="all, delete-orphan"
    )


class KmerResult(Base):
    __tablename__ = "kmer_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("survey_cases.id"), unique=True, index=True)
    spe_depths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    spe_freqs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    num_depths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    num_freqs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_normal: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_ploidy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    spe_plot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    num_plot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    case: Mapped[SurveyCase] = relationship("SurveyCase", back_populates="kmer_result")


class NtResult(Base):
    __tablename__ = "nt_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("survey_cases.id"), unique=True, index=True)
    nt_level: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_heavy_contamination: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    nt_rule_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_species: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_nt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_nt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dominant_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dominant_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    metazoa_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    plantae_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    bacteria_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    fungi_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    viruses_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasonable_contamination_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    pollution_ratio_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    pollution_threshold_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    ntcls_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ntspe_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_filtered_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_filtered_paths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    small_judged_paths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    nt_results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    case: Mapped[SurveyCase] = relationship("SurveyCase", back_populates="nt_result")


class GcResult(Base):
    __tablename__ = "gc_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("survey_cases.id"), unique=True, index=True)
    executed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pos_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    heavy_contamination: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    gc_raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    case: Mapped[SurveyCase] = relationship("SurveyCase", back_populates="gc_result")


class SurveyResult(Base):
    __tablename__ = "survey_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("survey_cases.id"), unique=True, index=True)
    final_level: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    should_transfer: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_version: Mapped[str] = mapped_column(String(64), default="survey_rule_v2_gc", nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    case: Mapped[SurveyCase] = relationship("SurveyCase", back_populates="survey_result")


class ResultMetrics(Base):
    __tablename__ = "result_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("survey_cases.id"), unique=True, index=True)
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ploidy_pattern: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ploidy_multiplier: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjusted_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    case: Mapped[SurveyCase] = relationship("SurveyCase", back_populates="result_metrics")
