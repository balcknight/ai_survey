from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..services.survey_runner import (
    check_required_files,
    infer_target_species,
    run_kmer_by_paths,
    run_nt_by_paths,
    run_survey_by_paths,
    run_survey_from_parts,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _normalize_sample_dir(sample_dir: str) -> str:
    return str(Path(sample_dir).expanduser().resolve())


def _guard_duplicate_source_path(db: Session, source_path: str, case_id: int | None = None):
    existing = crud.get_case_by_source_path(db, source_path)
    if existing is None:
        return
    if case_id is not None and existing.id == case_id:
        return
    raise HTTPException(
        status_code=409,
        detail=f"该路径已存在记录(case_id={existing.id})，请先删除后再执行判定",
    )


def _to_kmer_input(kmer_result: dict) -> schemas.KmerResultIn:
    return schemas.KmerResultIn(
        spe_peaks=schemas.PeaksData(**kmer_result.get("spe_peaks", {})),
        num_peaks=schemas.PeaksData(**kmer_result.get("num_peaks", {})),
        pattern=kmer_result.get("pattern"),
        is_normal=kmer_result.get("is_normal"),
        detail=kmer_result.get("detail"),
        warnings=kmer_result.get("warnings", []),
        analysis_ploidy=(
            schemas.AnalysisPloidy(**kmer_result.get("analysis_ploidy", {}))
            if kmer_result.get("analysis_ploidy")
            else None
        ),
        raw_payload=kmer_result,
    )


def _to_nt_input(nt_result: dict) -> schemas.NtResultIn:
    return schemas.NtResultIn(
        nt_score=nt_result.get("nt_score"),
        nt_level=nt_result.get("nt_level"),
        ntcls_score=nt_result.get("ntcls_score"),
        ntspe_score=nt_result.get("ntspe_score"),
        ntcls_detail=nt_result.get("ntcls_detail"),
        ntspe_detail=nt_result.get("ntspe_detail"),
        ntcls_top1_pass=nt_result.get("ntcls_top1_pass"),
        ntcls_contamination_pass=nt_result.get("ntcls_contamination_pass"),
        ntspe_contamination_pass=nt_result.get("ntspe_contamination_pass"),
        raw_payload=nt_result,
    )


def _to_survey_input(survey_result: dict) -> schemas.SurveyResultIn:
    return schemas.SurveyResultIn(
        final_level=survey_result.get("final_level"),
        should_transfer=survey_result.get("should_transfer"),
        remark=survey_result.get("remark"),
        rule_version="survey_rule_v1",
        raw_payload=survey_result,
    )


@router.get("", response_model=list[schemas.CaseSummaryOut])
def list_cases(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    target_species: str | None = None,
    final_level: str | None = None,
    should_transfer: str | None = None,
    status: str | None = None,
):
    items = crud.list_cases(
        db=db,
        limit=limit,
        offset=offset,
        target_species=target_species,
        final_level=final_level,
        should_transfer=should_transfer,
        status=status,
    )
    return [crud.to_case_summary_out(i) for i in items]


@router.get("/{case_id}", response_model=schemas.CaseDetailOut)
def get_case_detail(case_id: int, db: Session = Depends(get_db)):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    return crud.to_case_detail_out(obj)


@router.post("/run-by-path", response_model=schemas.RunByPathOut)
def run_by_path(payload: schemas.RunByPathIn, db: Session = Depends(get_db)):
    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    _guard_duplicate_source_path(db, normalized_dir, case_id=None)
    file_check = check_required_files(normalized_dir)
    if not file_check.complete:
        return schemas.RunByPathOut(
            sample_dir=normalized_dir,
            file_check=file_check,
            executed=False,
            message=f"输入文件不完整，缺失: {', '.join(file_check.missing)}",
        )

    try:
        merged = run_survey_by_paths(file_check=file_check, verbose=payload.verbose)
        obj = crud.import_case_from_survey_json(
            db=db,
            sample_code=payload.sample_code,
            source_path=normalized_dir,
            payload=merged,
        )
        detail_obj = crud.get_case_detail(db, obj.id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"执行survey判定失败: {exc}") from exc

    if detail_obj is None:
        raise HTTPException(status_code=500, detail="执行后读取样本失败")

    return schemas.RunByPathOut(
        sample_dir=normalized_dir,
        file_check=file_check,
        executed=True,
        message="文件齐全，已完成survey判定并入库",
        case_id=detail_obj.id,
        case_detail=crud.to_case_detail_out(detail_obj),
    )


@router.post("/check-by-path", response_model=schemas.CheckByPathOut)
def check_by_path(payload: schemas.CheckByPathIn):
    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    file_check = check_required_files(normalized_dir)
    if file_check.complete:
        message = "文件齐全，可执行完整 survey 判定"
    else:
        message = f"文件不完整，缺失: {', '.join(file_check.missing)}"
    return schemas.CheckByPathOut(
        sample_dir=normalized_dir,
        file_check=file_check,
        message=message,
    )


@router.post("/run-kmer", response_model=schemas.RunStepByPathOut)
def run_kmer(payload: schemas.RunStepByPathIn, db: Session = Depends(get_db)):
    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    _guard_duplicate_source_path(db, normalized_dir, case_id=payload.case_id)
    file_check = check_required_files(normalized_dir)
    if not file_check.kmer_complete:
        return schemas.RunStepByPathOut(
            sample_dir=normalized_dir,
            executed=False,
            message=f"kmer输入文件不完整，缺失: {', '.join(file_check.missing)}",
            file_check=file_check,
        )

    try:
        kmer_result = run_kmer_by_paths(file_check=file_check, verbose=payload.verbose)
        target_species = infer_target_species(file_check) or "未提供"
        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=payload.sample_code,
            source_path=normalized_dir,
            case_id=payload.case_id,
        )
        crud.save_kmer_result(db, obj.id, _to_kmer_input(kmer_result))
        detail_obj = crud.get_case_detail(db, obj.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"执行kmer判定失败: {exc}") from exc

    if detail_obj is None:
        raise HTTPException(status_code=500, detail="执行后读取样本失败")
    return schemas.RunStepByPathOut(
        sample_dir=normalized_dir,
        executed=True,
        message="kmer判定完成并已入库",
        file_check=file_check,
        case_id=detail_obj.id,
        case_detail=crud.to_case_detail_out(detail_obj),
    )


@router.post("/run-nt", response_model=schemas.RunStepByPathOut)
def run_nt(payload: schemas.RunStepByPathIn, db: Session = Depends(get_db)):
    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    _guard_duplicate_source_path(db, normalized_dir, case_id=payload.case_id)
    file_check = check_required_files(normalized_dir)
    if not file_check.nt_complete:
        return schemas.RunStepByPathOut(
            sample_dir=normalized_dir,
            executed=False,
            message=f"NT输入文件不完整，缺失: {', '.join(file_check.missing)}",
            file_check=file_check,
        )

    try:
        target_species, nt_result = run_nt_by_paths(file_check=file_check)
        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=payload.sample_code,
            source_path=normalized_dir,
            case_id=payload.case_id,
        )
        crud.save_nt_result(db, obj.id, _to_nt_input(nt_result))
        detail_obj = crud.get_case_detail(db, obj.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"执行NT判定失败: {exc}") from exc

    if detail_obj is None:
        raise HTTPException(status_code=500, detail="执行后读取样本失败")
    return schemas.RunStepByPathOut(
        sample_dir=normalized_dir,
        executed=True,
        message="NT判定完成并已入库",
        file_check=file_check,
        case_id=detail_obj.id,
        case_detail=crud.to_case_detail_out(detail_obj),
    )


@router.post("/run-survey", response_model=schemas.RunStepByPathOut)
def run_survey(payload: schemas.RunStepByPathIn, db: Session = Depends(get_db)):
    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    _guard_duplicate_source_path(db, normalized_dir, case_id=payload.case_id)
    file_check = check_required_files(normalized_dir)
    if not file_check.complete:
        return schemas.RunStepByPathOut(
            sample_dir=normalized_dir,
            executed=False,
            message=f"survey输入文件不完整，缺失: {', '.join(file_check.missing)}",
            file_check=file_check,
        )

    try:
        kmer_result = run_kmer_by_paths(file_check=file_check, verbose=payload.verbose)
        target_species, nt_result = run_nt_by_paths(file_check=file_check)
        survey_result = run_survey_from_parts(kmer_result, nt_result)

        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=payload.sample_code,
            source_path=normalized_dir,
            case_id=payload.case_id,
        )
        crud.save_kmer_result(db, obj.id, _to_kmer_input(kmer_result))
        crud.save_nt_result(db, obj.id, _to_nt_input(nt_result))
        crud.save_survey_result(db, obj.id, _to_survey_input(survey_result))
        detail_obj = crud.get_case_detail(db, obj.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"执行survey判定失败: {exc}") from exc

    if detail_obj is None:
        raise HTTPException(status_code=500, detail="执行后读取样本失败")
    return schemas.RunStepByPathOut(
        sample_dir=normalized_dir,
        executed=True,
        message="survey判定完成并已入库",
        file_check=file_check,
        case_id=detail_obj.id,
        case_detail=crud.to_case_detail_out(detail_obj),
    )


@router.post("/rerun-survey", response_model=schemas.RunStepByPathOut)
def rerun_survey(payload: schemas.RerunSurveyIn, db: Session = Depends(get_db)):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="请显式确认：confirm=true 后才能覆盖重跑")

    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    existing = crud.get_case_by_source_path(db, normalized_dir)
    if existing is None:
        raise HTTPException(status_code=404, detail="该路径暂无历史记录，无法重跑；请先执行 run-survey")

    file_check = check_required_files(normalized_dir)
    if not file_check.complete:
        return schemas.RunStepByPathOut(
            sample_dir=normalized_dir,
            executed=False,
            message=f"survey输入文件不完整，缺失: {', '.join(file_check.missing)}",
            file_check=file_check,
            case_id=existing.id,
            case_detail=crud.to_case_detail_out(existing),
        )

    try:
        kmer_result = run_kmer_by_paths(file_check=file_check, verbose=payload.verbose)
        target_species, nt_result = run_nt_by_paths(file_check=file_check)
        survey_result = run_survey_from_parts(kmer_result, nt_result)

        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=payload.sample_code,
            source_path=normalized_dir,
            case_id=existing.id,
        )
        crud.save_kmer_result(db, obj.id, _to_kmer_input(kmer_result))
        crud.save_nt_result(db, obj.id, _to_nt_input(nt_result))
        crud.save_survey_result(db, obj.id, _to_survey_input(survey_result))
        detail_obj = crud.get_case_detail(db, obj.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"执行重跑失败: {exc}") from exc

    if detail_obj is None:
        raise HTTPException(status_code=500, detail="重跑后读取样本失败")
    return schemas.RunStepByPathOut(
        sample_dir=normalized_dir,
        executed=True,
        message="survey重跑完成，已覆盖原记录",
        file_check=file_check,
        case_id=detail_obj.id,
        case_detail=crud.to_case_detail_out(detail_obj),
    )


@router.delete("/{case_id}", response_model=schemas.DeleteCaseOut)
def delete_case(case_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_case(db, case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="样本不存在")
    return schemas.DeleteCaseOut(
        deleted=True,
        case_id=case_id,
        message="样本记录已删除",
    )
