from __future__ import annotations

from sqlalchemy import Select, select
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
    obj.raw_json = to_json_text(payload.raw_payload)
    return obj


def _upsert_nt(db: Session, case_id: int, payload: schemas.NtResultIn) -> models.NtResult:
    obj = db.execute(select(models.NtResult).where(models.NtResult.case_id == case_id)).scalar_one_or_none()
    if obj is None:
        obj = models.NtResult(case_id=case_id)
        db.add(obj)

    obj.nt_score = payload.nt_score
    obj.nt_level = payload.nt_level
    obj.ntcls_score = payload.ntcls_score
    obj.ntspe_score = payload.ntspe_score
    obj.ntcls_detail = payload.ntcls_detail
    obj.ntspe_detail = payload.ntspe_detail
    obj.ntcls_top1_pass = payload.ntcls_top1_pass
    obj.ntcls_contamination_pass = payload.ntcls_contamination_pass
    obj.ntspe_contamination_pass = payload.ntspe_contamination_pass
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


def create_case(db: Session, payload: schemas.CaseCreate) -> models.SurveyCase:
    obj = models.SurveyCase(
        sample_code=payload.sample_code,
        target_species=payload.target_species,
        source_path=payload.source_path,
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
    if payload.survey_result:
        survey = _upsert_survey(db, obj.id, payload.survey_result)
        obj.final_level = survey.final_level
        obj.should_transfer = survey.should_transfer
        obj.remark = survey.remark
        obj.status = "judged"

    db.commit()
    db.refresh(obj)
    return obj


def import_case_from_survey_json(
    db: Session,
    sample_code: str | None,
    source_path: str | None,
    payload: dict,
) -> models.SurveyCase:
    target_species = payload.get("target_species")
    if not target_species:
        raise ValueError("payload.target_species 不能为空")

    case_payload = schemas.CaseCreate(
        sample_code=sample_code,
        target_species=target_species,
        source_path=source_path,
        status="created",
        kmer_result=schemas.KmerResultIn(
            spe_peaks=schemas.PeaksData(**payload.get("spe_peaks", {})),
            num_peaks=schemas.PeaksData(**payload.get("num_peaks", {})),
            pattern=payload.get("pattern"),
            is_normal=payload.get("is_normal"),
            detail=payload.get("detail"),
            warnings=payload.get("warnings", []),
            analysis_ploidy=(
                schemas.AnalysisPloidy(**payload.get("analysis_ploidy", {}))
                if payload.get("analysis_ploidy")
                else None
            ),
            raw_payload=payload,
        ),
        nt_result=schemas.NtResultIn(**payload.get("nt_result", {})) if payload.get("nt_result") else None,
        survey_result=(
            schemas.SurveyResultIn(**payload.get("survey_result", {}))
            if payload.get("survey_result")
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


def list_cases(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    target_species: str | None = None,
    final_level: str | None = None,
    should_transfer: str | None = None,
    status: str | None = None,
) -> list[models.SurveyCase]:
    stmt: Select[tuple[models.SurveyCase]] = (
        select(models.SurveyCase)
        .options(joinedload(models.SurveyCase.kmer_result), joinedload(models.SurveyCase.nt_result))
        .order_by(models.SurveyCase.updated_at.desc(), models.SurveyCase.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if target_species:
        stmt = stmt.where(models.SurveyCase.target_species.contains(target_species))
    if final_level:
        stmt = stmt.where(models.SurveyCase.final_level == final_level)
    if should_transfer:
        stmt = stmt.where(models.SurveyCase.should_transfer == should_transfer)
    if status:
        stmt = stmt.where(models.SurveyCase.status == status)
    return list(db.execute(stmt).scalars().unique().all())


def get_case_detail(db: Session, case_id: int) -> models.SurveyCase | None:
    stmt = (
        select(models.SurveyCase)
        .where(models.SurveyCase.id == case_id)
        .options(
            joinedload(models.SurveyCase.kmer_result),
            joinedload(models.SurveyCase.nt_result),
            joinedload(models.SurveyCase.survey_result),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def to_case_summary_out(obj: models.SurveyCase) -> schemas.CaseSummaryOut:
    return schemas.CaseSummaryOut(
        id=obj.id,
        sample_code=obj.sample_code,
        target_species=obj.target_species,
        status=obj.status,
        kmer_pattern=obj.kmer_result.pattern if obj.kmer_result else None,
        kmer_is_normal=obj.kmer_result.is_normal if obj.kmer_result else None,
        nt_score=obj.nt_result.nt_score if obj.nt_result else None,
        nt_level=obj.nt_result.nt_level if obj.nt_result else None,
        final_level=obj.final_level,
        should_transfer=obj.should_transfer,
        updated_at=obj.updated_at,
    )


def to_case_detail_out(obj: models.SurveyCase) -> schemas.CaseDetailOut:
    kmer_out = None
    nt_out = None
    survey_out = None

    if obj.kmer_result:
        kmer_out = schemas.KmerResultOut(
            pattern=obj.kmer_result.pattern,
            is_normal=obj.kmer_result.is_normal,
            detail=obj.kmer_result.detail,
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
            created_at=obj.kmer_result.created_at,
            updated_at=obj.kmer_result.updated_at,
        )

    if obj.nt_result:
        nt_out = schemas.NtResultOut(
            nt_score=obj.nt_result.nt_score,
            nt_level=obj.nt_result.nt_level,
            ntcls_score=obj.nt_result.ntcls_score,
            ntspe_score=obj.nt_result.ntspe_score,
            ntcls_detail=obj.nt_result.ntcls_detail,
            ntspe_detail=obj.nt_result.ntspe_detail,
            ntcls_top1_pass=obj.nt_result.ntcls_top1_pass,
            ntcls_contamination_pass=obj.nt_result.ntcls_contamination_pass,
            ntspe_contamination_pass=obj.nt_result.ntspe_contamination_pass,
            created_at=obj.nt_result.created_at,
            updated_at=obj.nt_result.updated_at,
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

    return schemas.CaseDetailOut(
        id=obj.id,
        sample_code=obj.sample_code,
        target_species=obj.target_species,
        source_path=obj.source_path,
        status=obj.status,
        final_level=obj.final_level,
        should_transfer=obj.should_transfer,
        remark=obj.remark,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        kmer_result=kmer_out,
        nt_result=nt_out,
        survey_result=survey_out,
    )
