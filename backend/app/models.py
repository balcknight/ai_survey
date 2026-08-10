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
    bioinfo_emails_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_emails_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_emails_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    manual_reviews: Mapped[list[ManualReview]] = relationship(
        "ManualReview",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="desc(ManualReview.created_at)",
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


class ManualReview(Base):
    __tablename__ = "manual_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("survey_cases.id"), index=True)
    # 审核人 user id（可空：历史记录为 NULL）。
    # 注意：老库通过 ALTER TABLE 补列，SQLite ALTER 不支持附带 FK 约束，
    # 因此老库中该列为普通可空 INTEGER，业务层不依赖 DB 级 FK。
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # 兼容历史库结构：旧库 reviewer_name 可能是 NOT NULL。
    # 新语义：提交审核时写入审核人 display_name 快照（保证改名/停用后历史可读）。
    reviewer_name: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    kmer_review: Mapped[str] = mapped_column(String(16), nullable=False)
    nt_review: Mapped[str] = mapped_column(String(16), nullable=False)
    gc_review: Mapped[str] = mapped_column(String(16), nullable=False)
    final_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Kmer AI 判定被勾选为「不正确」时人工填写的原因。
    # 仅用于记录以便后续校对/改进算法，不作为邮件正文发送（区别于 note）。
    kmer_incorrect_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    case: Mapped[SurveyCase] = relationship("SurveyCase", back_populates="manual_reviews")
    reviewer: Mapped[User | None] = relationship("User")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    sessions: Mapped[list[UserSession]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    # 只存 sha256(token)，库泄露不直接暴露可用会话。
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="sessions")
