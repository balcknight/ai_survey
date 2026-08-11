from __future__ import annotations

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .json_utils import from_json_text, to_json_text


def _upsert_kmer(db: Session, case_id: int, payload: schemas.KmerResultIn) -> models.KmerResult:
    obj = db.execute(select(models.KmerResult).where(models.KmerResult.case_id == case_id)).scalar_one_or_none()
    if obj is None:
        obj = models.KmerResult(case_id=case_id)
        db.add(obj)

    obj.pattern = payload.pattern
    obj.is_normal = payload.is_normal
    obj.detail = payload.detail
    obj.spe_depths_json = to_json_text(payload.spe_peaks.depths if payload.spe_peaks else None)
    obj.spe_freqs_json = to_json_text(payload.spe_peaks.freqs if payload.spe_peaks else None)
    obj.num_depths_json = to_json_text(payload.num_peaks.depths if payload.num_peaks else None)
    obj.num_freqs_json = to_json_text(payload.num_peaks.freqs if payload.num_peaks else None)
    obj.warnings_json = to_json_text(payload.warnings)
    obj.analysis_ploidy_json = to_json_text(
        payload.analysis_ploidy.model_dump() if payload.analysis_ploidy else None
    )
    obj.spe_plot_path = payload.spe_plot_path
    obj.num_plot_path = payload.num_plot_path
    obj.raw_json = to_json_text(payload.raw_payload)
    return obj


def _upsert_nt(db: Session, case_id: int, payload: schemas.NtResultIn) -> models.NtResult:
    obj = db.execute(select(models.NtResult).where(models.NtResult.case_id == case_id)).scalar_one_or_none()
    if obj is None:
        obj = models.NtResult(case_id=case_id)
        db.add(obj)

    obj.nt_level = payload.nt_level
    obj.is_heavy_contamination = payload.is_heavy_contamination
    obj.nt_rule_version = payload.nt_rule_version
    obj.target_species = payload.target_species
    obj.target_category = payload.target_category
    obj.source_nt_count = payload.source_nt_count
    obj.valid_nt_count = payload.valid_nt_count
    obj.dominant_category = payload.dominant_category
    obj.dominant_ratio_percent = payload.dominant_ratio_percent
    obj.metazoa_ratio_percent = payload.metazoa_ratio_percent
    obj.plantae_ratio_percent = payload.plantae_ratio_percent
    obj.bacteria_ratio_percent = payload.bacteria_ratio_percent
    obj.fungi_ratio_percent = payload.fungi_ratio_percent
    obj.viruses_ratio_percent = payload.viruses_ratio_percent
    obj.reasonable_contamination_ratio_percent = payload.reasonable_contamination_ratio_percent
    obj.pollution_ratio_percent = payload.pollution_ratio_percent
    obj.pollution_threshold_percent = payload.pollution_threshold_percent
    obj.ntcls_detail = payload.ntcls_detail
    obj.ntspe_detail = payload.ntspe_detail
    obj.class_filtered_path = payload.class_filtered_path
    obj.class_filtered_paths_json = to_json_text(payload.class_filtered_paths)
    obj.small_judged_paths_json = to_json_text(payload.small_judged_paths)
    obj.nt_results_json = to_json_text(payload.nt_results)
    obj.raw_json = to_json_text(payload.raw_payload)
    return obj


def _upsert_gc(db: Session, case_id: int, payload: schemas.GcResultIn) -> models.GcResult:
    obj = db.execute(select(models.GcResult).where(models.GcResult.case_id == case_id)).scalar_one_or_none()
    if obj is None:
        obj = models.GcResult(case_id=case_id)
        db.add(obj)

    obj.executed = payload.executed
    obj.status = payload.status
    obj.reason = payload.reason
    obj.pos_path = payload.pos_path
    obj.heavy_contamination = payload.heavy_contamination
    obj.participated = payload.participated
    obj.gc_raw_json = to_json_text(payload.gc_raw)
    obj.raw_json = to_json_text(payload.raw_payload)
    return obj


def _upsert_survey(db: Session, case_id: int, payload: schemas.SurveyResultIn) -> models.SurveyResult:
    obj = db.execute(select(models.SurveyResult).where(models.SurveyResult.case_id == case_id)).scalar_one_or_none()
    if obj is None:
        obj = models.SurveyResult(case_id=case_id)
        db.add(obj)

    obj.final_level = payload.final_level
    obj.should_transfer = payload.should_transfer
    obj.remark = payload.remark
    obj.rule_version = payload.rule_version
    obj.raw_json = to_json_text(payload.raw_payload)
    return obj


def _upsert_result_metrics(
    db: Session,
    case_id: int,
    payload: schemas.ResultMetricsIn,
) -> models.ResultMetrics:
    obj = db.execute(
        select(models.ResultMetrics).where(models.ResultMetrics.case_id == case_id)
    ).scalar_one_or_none()
    if obj is None:
        obj = models.ResultMetrics(case_id=case_id)
        db.add(obj)

    obj.result_path = payload.result_path
    obj.ploidy_pattern = payload.ploidy_pattern
    obj.ploidy_multiplier = payload.ploidy_multiplier
    obj.raw_json = to_json_text(payload.raw)
    obj.adjusted_json = to_json_text(payload.adjusted)
    obj.remark = payload.remark
    return obj


def create_case(db: Session, payload: schemas.CaseCreate) -> models.SurveyCase:
    obj = models.SurveyCase(
        sample_code=payload.sample_code,
        target_species=payload.target_species,
        source_path=payload.source_path,
        stage_code=payload.stage_code,
        bioinfo_emails_json=to_json_text([item.model_dump() for item in payload.bioinfo_emails]),
        operation_emails_json=to_json_text([item.model_dump() for item in payload.operation_emails]),
        group_emails_json=to_json_text(payload.group_emails),
        archive_path=payload.archive_path,
        status=payload.status,
        remark=payload.remark,
    )
    db.add(obj)
    db.flush()

    if payload.kmer_result:
        _upsert_kmer(db, obj.id, payload.kmer_result)
        obj.status = "kmer_done"
    if payload.nt_result:
        _upsert_nt(db, obj.id, payload.nt_result)
        obj.status = "nt_done" if obj.status == "created" else obj.status
    if payload.gc_result:
        _upsert_gc(db, obj.id, payload.gc_result)
    if payload.survey_result:
        survey = _upsert_survey(db, obj.id, payload.survey_result)
        obj.final_level = survey.final_level
        obj.should_transfer = survey.should_transfer
        obj.remark = survey.remark
        obj.status = "judged"
    if payload.result_metrics:
        _upsert_result_metrics(db, obj.id, payload.result_metrics)

    db.commit()
    db.refresh(obj)
    return obj


def import_case_from_survey_json(
    db: Session,
    sample_code: str | None,
    source_path: str | None,
    payload: dict,
    stage_code: str | None = None,
    bioinfo_emails: list[dict] | None = None,
    operation_emails: list[dict] | None = None,
    group_emails: list[str] | None = None,
    archive_path: str | None = None,
) -> models.SurveyCase:
    target_species = payload.get("target_species")
    if not target_species:
        raise ValueError("payload.target_species 不能为空")

    case_payload = schemas.CaseCreate(
        sample_code=sample_code,
        target_species=target_species,
        source_path=source_path,
        stage_code=stage_code,
        bioinfo_emails=[schemas.ContactInfo(**item) for item in list(bioinfo_emails or [])],
        operation_emails=[schemas.ContactInfo(**item) for item in list(operation_emails or [])],
        group_emails=list(group_emails or []),
        archive_path=archive_path,
        status="created",
        kmer_result=schemas.KmerResultIn(
            spe_peaks=schemas.PeaksData(**payload.get("spe_peaks", {})),
            num_peaks=schemas.PeaksData(**payload.get("num_peaks", {})),
            pattern=payload.get("pattern"),
            is_normal=payload.get("is_normal"),
            detail=payload.get("detail"),
            spe_main_peak_depth=payload.get("spe_main_peak_depth"),
            num_main_peak_depth=payload.get("num_main_peak_depth"),
            warnings=payload.get("warnings", []),
            analysis_ploidy=(
                schemas.AnalysisPloidy(**payload.get("analysis_ploidy", {}))
                if payload.get("analysis_ploidy")
                else None
            ),
            spe_plot_path=payload.get("spe_plot_path"),
            num_plot_path=payload.get("num_plot_path"),
            raw_payload=payload,
        ),
        nt_result=schemas.NtResultIn(**payload.get("nt_result", {})) if payload.get("nt_result") else None,
        gc_result=schemas.GcResultIn(**payload.get("gc_result", {})) if payload.get("gc_result") else None,
        survey_result=(
            schemas.SurveyResultIn(**payload.get("survey_result", {}))
            if payload.get("survey_result")
            else None
        ),
        result_metrics=(
            schemas.ResultMetricsIn(**payload.get("result_metrics", {}))
            if payload.get("result_metrics")
            else None
        ),
    )
    return create_case(db, case_payload)


def ensure_case(
    db: Session,
    target_species: str,
    sample_code: str | None = None,
    source_path: str | None = None,
    case_id: int | None = None,
) -> models.SurveyCase:
    if case_id is not None:
        obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
        if obj is None:
            raise ValueError(f"case_id={case_id} 不存在")
        if sample_code and not obj.sample_code:
            obj.sample_code = sample_code
        if source_path and not obj.source_path:
            obj.source_path = source_path
        if target_species and obj.target_species != target_species:
            obj.target_species = target_species
        db.commit()
        db.refresh(obj)
        return obj

    obj = models.SurveyCase(
        sample_code=sample_code,
        target_species=target_species,
        source_path=source_path,
        status="created",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def save_kmer_result(db: Session, case_id: int, payload: schemas.KmerResultIn) -> models.SurveyCase:
    obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
    if obj is None:
        raise ValueError(f"case_id={case_id} 不存在")
    _upsert_kmer(db, case_id, payload)
    if obj.status == "created":
        obj.status = "kmer_done"
    db.commit()
    db.refresh(obj)
    return obj


def save_nt_result(db: Session, case_id: int, payload: schemas.NtResultIn) -> models.SurveyCase:
    obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
    if obj is None:
        raise ValueError(f"case_id={case_id} 不存在")
    _upsert_nt(db, case_id, payload)
    if obj.status in ("created", "kmer_done"):
        obj.status = "nt_done"
    db.commit()
    db.refresh(obj)
    return obj


def save_gc_result(db: Session, case_id: int, payload: schemas.GcResultIn) -> models.SurveyCase:
    obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
    if obj is None:
        raise ValueError(f"case_id={case_id} 不存在")
    _upsert_gc(db, case_id, payload)
    db.commit()
    db.refresh(obj)
    return obj


def save_survey_result(db: Session, case_id: int, payload: schemas.SurveyResultIn) -> models.SurveyCase:
    obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
    if obj is None:
        raise ValueError(f"case_id={case_id} 不存在")
    survey = _upsert_survey(db, case_id, payload)
    obj.final_level = survey.final_level
    obj.should_transfer = survey.should_transfer
    obj.remark = survey.remark
    obj.status = "judged"
    db.commit()
    db.refresh(obj)
    return obj


def save_result_metrics(db: Session, case_id: int, payload: schemas.ResultMetricsIn) -> models.SurveyCase:
    obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
    if obj is None:
        raise ValueError(f"case_id={case_id} 不存在")
    _upsert_result_metrics(db, case_id, payload)
    db.commit()
    db.refresh(obj)
    return obj


def get_case_by_source_path(db: Session, source_path: str) -> models.SurveyCase | None:
    stmt = select(models.SurveyCase).where(models.SurveyCase.source_path == source_path)
    return db.execute(stmt).scalar_one_or_none()


def delete_case(db: Session, case_id: int) -> bool:
    obj = db.execute(select(models.SurveyCase).where(models.SurveyCase.id == case_id)).scalar_one_or_none()
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    return True


def _apply_case_filters(
    stmt,
    *,
    target_species: str | None = None,
    final_level: str | None = None,
    should_transfer: str | None = None,
    status: str | None = None,
    stage_code: str | None = None,
    bioinfo_email: str | None = None,
    review_status: str | None = None,
    review_final_decision: str | None = None,
):
    if target_species:
        stmt = stmt.where(models.SurveyCase.target_species.contains(target_species))
    if final_level:
        stmt = stmt.where(models.SurveyCase.final_level == final_level)
    if should_transfer:
        stmt = stmt.where(models.SurveyCase.should_transfer == should_transfer)
    if status:
        stmt = stmt.where(models.SurveyCase.status == status)
    if stage_code:
        stmt = stmt.where(models.SurveyCase.stage_code.contains(stage_code))
    if bioinfo_email:
        stmt = stmt.where(models.SurveyCase.bioinfo_emails_json.contains(bioinfo_email))
    if review_status == "reviewed":
        stmt = stmt.where(models.SurveyCase.manual_reviews.any())
    elif review_status == "unreviewed":
        stmt = stmt.where(~models.SurveyCase.manual_reviews.any())
    if review_final_decision:
        latest_review_id = (
            select(func.max(models.ManualReview.id))
            .where(models.ManualReview.case_id == models.SurveyCase.id)
            .correlate(models.SurveyCase)
            .scalar_subquery()
        )
        stmt = stmt.where(
            exists()
            .where(models.ManualReview.id == latest_review_id)
            .where(models.ManualReview.final_decision == review_final_decision)
        )
    return stmt


def list_cases(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    target_species: str | None = None,
    final_level: str | None = None,
    should_transfer: str | None = None,
    status: str | None = None,
    stage_code: str | None = None,
    bioinfo_email: str | None = None,
    review_status: str | None = None,
    review_final_decision: str | None = None,
) -> list[models.SurveyCase]:
    stmt: Select[tuple[models.SurveyCase]] = (
        select(models.SurveyCase)
        .options(
            joinedload(models.SurveyCase.kmer_result),
            joinedload(models.SurveyCase.nt_result),
            joinedload(models.SurveyCase.gc_result),
            joinedload(models.SurveyCase.manual_reviews),
        )
        .order_by(models.SurveyCase.updated_at.desc(), models.SurveyCase.id.desc())
        .limit(limit)
        .offset(offset)
    )
    stmt = _apply_case_filters(
        stmt,
        target_species=target_species,
        final_level=final_level,
        should_transfer=should_transfer,
        status=status,
        stage_code=stage_code,
        bioinfo_email=bioinfo_email,
        review_status=review_status,
        review_final_decision=review_final_decision,
    )
    return list(db.execute(stmt).scalars().unique().all())


def count_cases(
    db: Session,
    target_species: str | None = None,
    final_level: str | None = None,
    should_transfer: str | None = None,
    status: str | None = None,
    stage_code: str | None = None,
    bioinfo_email: str | None = None,
    review_status: str | None = None,
    review_final_decision: str | None = None,
) -> int:
    stmt = select(func.count(models.SurveyCase.id))
    stmt = _apply_case_filters(
        stmt,
        target_species=target_species,
        final_level=final_level,
        should_transfer=should_transfer,
        status=status,
        stage_code=stage_code,
        bioinfo_email=bioinfo_email,
        review_status=review_status,
        review_final_decision=review_final_decision,
    )
    return db.execute(stmt).scalar_one()


def get_case_stats(db: Session) -> dict:
    total = db.execute(select(func.count(models.SurveyCase.id))).scalar_one()

    level_rows = db.execute(
        select(models.SurveyCase.final_level, func.count(models.SurveyCase.id)).group_by(
            models.SurveyCase.final_level
        )
    ).all()
    by_final_level: dict[str, int] = {}
    for level, count in level_rows:
        by_final_level[level if level else "未判定"] = count

    reviewed = db.execute(
        select(func.count(models.SurveyCase.id)).where(models.SurveyCase.manual_reviews.any())
    ).scalar_one()

    return {
        "total": total,
        "by_final_level": by_final_level,
        "reviewed": reviewed,
        "unreviewed": total - reviewed,
    }


def get_case_detail(db: Session, case_id: int) -> models.SurveyCase | None:
    stmt = (
        select(models.SurveyCase)
        .where(models.SurveyCase.id == case_id)
        .options(
            joinedload(models.SurveyCase.kmer_result),
            joinedload(models.SurveyCase.nt_result),
            joinedload(models.SurveyCase.gc_result),
            joinedload(models.SurveyCase.survey_result),
            joinedload(models.SurveyCase.result_metrics),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def to_case_summary_out(obj: models.SurveyCase) -> schemas.CaseSummaryOut:
    bioinfo_emails_raw = from_json_text(obj.bioinfo_emails_json, None)
    if isinstance(bioinfo_emails_raw, list):
        bioinfo_emails = [schemas.ContactInfo(**item) for item in bioinfo_emails_raw if isinstance(item, dict)]
    elif obj.contact_name and obj.contact_email:
        bioinfo_emails = [schemas.ContactInfo(name=obj.contact_name, email=obj.contact_email)]
    else:
        bioinfo_emails = []

    latest_review = obj.manual_reviews[0] if obj.manual_reviews else None

    return schemas.CaseSummaryOut(
        id=obj.id,
        sample_code=obj.sample_code,
        target_species=obj.target_species,
        stage_code=obj.stage_code,
        bioinfo_emails=bioinfo_emails,
        status=obj.status,
        kmer_pattern=obj.kmer_result.pattern if obj.kmer_result else None,
        kmer_is_normal=obj.kmer_result.is_normal if obj.kmer_result else None,
        nt_level=obj.nt_result.nt_level if obj.nt_result else None,
        nt_is_heavy_contamination=obj.nt_result.is_heavy_contamination if obj.nt_result else None,
        gc_status=obj.gc_result.status if obj.gc_result else None,
        gc_heavy_contamination=obj.gc_result.heavy_contamination if obj.gc_result else None,
        final_level=obj.final_level,
        should_transfer=obj.should_transfer,
        reviewed=latest_review is not None,
        review_final_decision=latest_review.final_decision if latest_review else None,
        updated_at=obj.updated_at,
    )


def create_manual_review(
    db: Session,
    case_id: int,
    payload: schemas.ManualReviewIn,
    *,
    reviewer: models.User | None = None,
) -> models.ManualReview:
    # 兼容历史枚举：confirm/rerun/manual_transfer；新前端统一为 transfer/no_transfer。
    decision = payload.final_decision
    if decision in ("confirm", "no_transfer"):
        normalized_decision = "no_transfer"
    elif decision in ("rerun", "manual_transfer", "transfer"):
        normalized_decision = "transfer"
    else:
        normalized_decision = decision

    # 审核人只能由后端从登录态注入，不接受客户端入参，防止伪造他人身份。
    reviewer_id = reviewer.id if reviewer is not None else None
    if reviewer is not None:
        reviewer_name = reviewer.display_name.strip() or reviewer.username
    else:
        reviewer_name = "system"

    # Kmer 判定不正确原因仅在 kmer_review=incorrect 时记录，其余情况置空，保证数据干净。
    if payload.kmer_review == "incorrect":
        kmer_incorrect_reason = (payload.kmer_incorrect_reason or "").strip() or None
    else:
        kmer_incorrect_reason = None

    obj = models.ManualReview(
        case_id=case_id,
        reviewer_id=reviewer_id,
        reviewer_name=reviewer_name,
        kmer_review=payload.kmer_review,
        nt_review=payload.nt_review,
        gc_review=payload.gc_review,
        final_decision=normalized_decision,
        note=(payload.note or "").strip() or None,
        kmer_incorrect_reason=kmer_incorrect_reason,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_manual_reviews(db: Session, case_id: int) -> list[models.ManualReview]:
    stmt = (
        select(models.ManualReview)
        .where(models.ManualReview.case_id == case_id)
        .order_by(models.ManualReview.created_at.desc(), models.ManualReview.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def to_case_detail_out(obj: models.SurveyCase) -> schemas.CaseDetailOut:
    kmer_out = None
    nt_out = None
    gc_out = None
    survey_out = None
    result_metrics_out = None

    if obj.kmer_result:
        kmer_raw = from_json_text(obj.kmer_result.raw_json, {}) or {}
        kmer_out = schemas.KmerResultOut(
            pattern=obj.kmer_result.pattern,
            is_normal=obj.kmer_result.is_normal,
            detail=obj.kmer_result.detail,
            spe_main_peak_depth=kmer_raw.get("spe_main_peak_depth"),
            num_main_peak_depth=kmer_raw.get("num_main_peak_depth"),
            spe_peaks=schemas.PeaksData(
                depths=from_json_text(obj.kmer_result.spe_depths_json, []),
                freqs=from_json_text(obj.kmer_result.spe_freqs_json, []),
            ),
            num_peaks=schemas.PeaksData(
                depths=from_json_text(obj.kmer_result.num_depths_json, []),
                freqs=from_json_text(obj.kmer_result.num_freqs_json, []),
            ),
            warnings=from_json_text(obj.kmer_result.warnings_json, []),
            analysis_ploidy=from_json_text(obj.kmer_result.analysis_ploidy_json, None),
            spe_plot_path=obj.kmer_result.spe_plot_path,
            num_plot_path=obj.kmer_result.num_plot_path,
            created_at=obj.kmer_result.created_at,
            updated_at=obj.kmer_result.updated_at,
        )

    if obj.nt_result:
        nt_out = schemas.NtResultOut(
            nt_level=obj.nt_result.nt_level,
            is_heavy_contamination=obj.nt_result.is_heavy_contamination,
            nt_rule_version=obj.nt_result.nt_rule_version,
            target_species=obj.nt_result.target_species,
            target_category=obj.nt_result.target_category,
            source_nt_count=obj.nt_result.source_nt_count,
            valid_nt_count=obj.nt_result.valid_nt_count,
            dominant_category=obj.nt_result.dominant_category,
            dominant_ratio_percent=obj.nt_result.dominant_ratio_percent,
            metazoa_ratio_percent=obj.nt_result.metazoa_ratio_percent,
            plantae_ratio_percent=obj.nt_result.plantae_ratio_percent,
            bacteria_ratio_percent=obj.nt_result.bacteria_ratio_percent,
            fungi_ratio_percent=obj.nt_result.fungi_ratio_percent,
            viruses_ratio_percent=obj.nt_result.viruses_ratio_percent,
            reasonable_contamination_ratio_percent=obj.nt_result.reasonable_contamination_ratio_percent,
            pollution_ratio_percent=obj.nt_result.pollution_ratio_percent,
            pollution_threshold_percent=obj.nt_result.pollution_threshold_percent,
            ntcls_detail=obj.nt_result.ntcls_detail,
            ntspe_detail=obj.nt_result.ntspe_detail,
            class_filtered_path=obj.nt_result.class_filtered_path,
            class_filtered_paths=from_json_text(obj.nt_result.class_filtered_paths_json, []),
            small_judged_paths=from_json_text(obj.nt_result.small_judged_paths_json, []),
            nt_results=from_json_text(obj.nt_result.nt_results_json, []),
            created_at=obj.nt_result.created_at,
            updated_at=obj.nt_result.updated_at,
        )

    if obj.gc_result:
        gc_out = schemas.GcResultOut(
            executed=obj.gc_result.executed,
            status=obj.gc_result.status,
            reason=obj.gc_result.reason,
            pos_path=obj.gc_result.pos_path,
            heavy_contamination=obj.gc_result.heavy_contamination,
            participated=obj.gc_result.participated,
            gc_raw=from_json_text(obj.gc_result.gc_raw_json, None),
            created_at=obj.gc_result.created_at,
            updated_at=obj.gc_result.updated_at,
        )

    if obj.survey_result:
        survey_out = schemas.SurveyResultOut(
            final_level=obj.survey_result.final_level,
            should_transfer=obj.survey_result.should_transfer,
            remark=obj.survey_result.remark,
            rule_version=obj.survey_result.rule_version,
            created_at=obj.survey_result.created_at,
            updated_at=obj.survey_result.updated_at,
        )
    if obj.result_metrics:
        result_metrics_out = schemas.ResultMetricsOut(
            result_path=obj.result_metrics.result_path,
            ploidy_pattern=obj.result_metrics.ploidy_pattern,
            ploidy_multiplier=obj.result_metrics.ploidy_multiplier,
            raw=from_json_text(obj.result_metrics.raw_json, None),
            adjusted=from_json_text(obj.result_metrics.adjusted_json, None),
            remark=obj.result_metrics.remark,
            created_at=obj.result_metrics.created_at,
            updated_at=obj.result_metrics.updated_at,
        )

    bioinfo_emails_raw = from_json_text(obj.bioinfo_emails_json, None)
    if isinstance(bioinfo_emails_raw, list):
        bioinfo_emails = [schemas.ContactInfo(**item) for item in bioinfo_emails_raw if isinstance(item, dict)]
    elif obj.contact_name and obj.contact_email:
        # 兼容历史单联系人字段
        bioinfo_emails = [schemas.ContactInfo(name=obj.contact_name, email=obj.contact_email)]
    else:
        bioinfo_emails = []

    operation_emails_raw = from_json_text(obj.operation_emails_json, [])
    operation_emails = [schemas.ContactInfo(**item) for item in operation_emails_raw if isinstance(item, dict)]

    group_emails = from_json_text(obj.group_emails_json, None)
    if not isinstance(group_emails, list):
        # 兼容历史抄送字段
        group_emails = from_json_text(obj.cc_emails_json, [])

    return schemas.CaseDetailOut(
        id=obj.id,
        sample_code=obj.sample_code,
        target_species=obj.target_species,
        source_path=obj.source_path,
        stage_code=obj.stage_code,
        bioinfo_emails=bioinfo_emails,
        operation_emails=operation_emails,
        group_emails=[str(item).strip() for item in group_emails if str(item).strip()],
        archive_path=obj.archive_path,
        status=obj.status,
        final_level=obj.final_level,
        should_transfer=obj.should_transfer,
        remark=obj.remark,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        kmer_result=kmer_out,
        nt_result=nt_out,
        gc_result=gc_out,
        survey_result=survey_out,
        result_metrics=result_metrics_out,
    )
