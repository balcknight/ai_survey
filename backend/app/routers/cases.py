from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..services.kmer_plot import KMER_PLOT_ROOT, cleanup_kmer_plots, generate_kmer_plots
from ..services.survey_runner import (
    check_required_files,
    infer_target_species,
    run_kmer_by_paths,
    run_nt_by_paths,
    run_survey_by_paths,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _normalize_sample_dir(sample_dir: str) -> str:
    return str(Path(sample_dir).expanduser().resolve())


def _resolve_sample_code(sample_code: str | None, normalized_dir: str) -> str | None:
    if sample_code is not None:
        cleaned = sample_code.strip()
        if cleaned:
            return cleaned

    # 未传 sample_code 时，默认使用样本目录名作为样本编号。
    inferred = Path(normalized_dir).name.strip()
    return inferred or None


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
        spe_plot_path=kmer_result.get("spe_plot_path"),
        num_plot_path=kmer_result.get("num_plot_path"),
        raw_payload=kmer_result,
    )


def _attach_kmer_plots(kmer_result: dict, file_check: schemas.FileCheckOut, sample_dir: str) -> dict:
    plot_result = generate_kmer_plots(
        spe_path=file_check.spe_path,
        num_path=file_check.num_path,
        sample_dir=sample_dir,
    )
    merged = dict(kmer_result)
    merged["spe_plot_path"] = plot_result.get("spe_plot_path")
    merged["num_plot_path"] = plot_result.get("num_plot_path")
    existing_warnings = list(merged.get("warnings") or [])
    merged["warnings"] = existing_warnings + list(plot_result.get("warnings", []))
    return merged


def _to_nt_input(nt_result: dict) -> schemas.NtResultIn:
    return schemas.NtResultIn(
        nt_level=nt_result.get("nt_level"),
        is_heavy_contamination=nt_result.get("is_heavy_contamination"),
        nt_rule_version=nt_result.get("nt_rule_version"),
        target_species=nt_result.get("target_species"),
        target_category=nt_result.get("target_category"),
        source_nt_count=nt_result.get("source_nt_count"),
        valid_nt_count=nt_result.get("valid_nt_count"),
        dominant_category=nt_result.get("dominant_category"),
        dominant_ratio_percent=nt_result.get("dominant_ratio_percent"),
        metazoa_ratio_percent=nt_result.get("metazoa_ratio_percent"),
        plantae_ratio_percent=nt_result.get("plantae_ratio_percent"),
        bacteria_ratio_percent=nt_result.get("bacteria_ratio_percent"),
        fungi_ratio_percent=nt_result.get("fungi_ratio_percent"),
        viruses_ratio_percent=nt_result.get("viruses_ratio_percent"),
        reasonable_contamination_ratio_percent=nt_result.get("reasonable_contamination_ratio_percent"),
        pollution_ratio_percent=nt_result.get("pollution_ratio_percent"),
        pollution_threshold_percent=nt_result.get("pollution_threshold_percent"),
        ntcls_detail=nt_result.get("ntcls_detail"),
        ntspe_detail=nt_result.get("ntspe_detail"),
        class_filtered_path=nt_result.get("class_filtered_path"),
        class_filtered_paths=nt_result.get("class_filtered_paths") or [],
        small_judged_paths=nt_result.get("small_judged_paths") or [],
        nt_results=nt_result.get("nt_results") or [],
        raw_payload=nt_result,
    )


def _to_gc_input(gc_result: dict) -> schemas.GcResultIn:
    return schemas.GcResultIn(
        executed=bool(gc_result.get("executed", False)),
        status=gc_result.get("status"),
        reason=gc_result.get("reason"),
        pos_path=gc_result.get("pos_path"),
        heavy_contamination=gc_result.get("heavy_contamination"),
        gc_raw=gc_result.get("gc_raw"),
        raw_payload=gc_result,
    )


def _to_survey_input(survey_result: dict) -> schemas.SurveyResultIn:
    return schemas.SurveyResultIn(
        final_level=survey_result.get("final_level"),
        should_transfer=survey_result.get("should_transfer"),
        remark=survey_result.get("remark"),
        rule_version=survey_result.get("rule_version") or "survey_rule_v2_gc",
        raw_payload=survey_result,
    )


def _to_result_metrics_input(result_metrics: dict) -> schemas.ResultMetricsIn:
    return schemas.ResultMetricsIn(
        result_path=result_metrics.get("result_path"),
        ploidy_pattern=result_metrics.get("ploidy_pattern"),
        ploidy_multiplier=result_metrics.get("ploidy_multiplier"),
        raw=result_metrics.get("raw"),
        adjusted=result_metrics.get("adjusted"),
        remark=result_metrics.get("remark"),
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


@router.get("/{case_id}/kmer-plot")
def get_kmer_plot(
    case_id: int,
    spectrum: str = Query(..., pattern="^(spe|num)$"),
    db: Session = Depends(get_db),
):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    if obj.kmer_result is None:
        raise HTTPException(status_code=404, detail="该样本暂无kmer结果")

    plot_path = obj.kmer_result.spe_plot_path if spectrum == "spe" else obj.kmer_result.num_plot_path
    if not plot_path:
        raise HTTPException(status_code=404, detail=f"该样本暂无{spectrum}峰图")

    path = Path(plot_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="峰图文件不存在")
    try:
        path.relative_to(KMER_PLOT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="峰图路径不在受管目录，拒绝访问") from exc

    return FileResponse(str(path), media_type="image/png", filename=path.name)


@router.post("/run-by-path", response_model=schemas.RunByPathOut)
def run_by_path(payload: schemas.RunByPathIn, db: Session = Depends(get_db)):
    normalized_dir = _normalize_sample_dir(payload.sample_dir)
    resolved_sample_code = _resolve_sample_code(payload.sample_code, normalized_dir)
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
        merged = _attach_kmer_plots(merged, file_check, normalized_dir)
        obj = crud.import_case_from_survey_json(
            db=db,
            sample_code=resolved_sample_code,
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
    resolved_sample_code = _resolve_sample_code(payload.sample_code, normalized_dir)
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
        kmer_result = _attach_kmer_plots(kmer_result, file_check, normalized_dir)
        target_species = infer_target_species(file_check) or "未提供"
        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=resolved_sample_code,
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
    resolved_sample_code = _resolve_sample_code(payload.sample_code, normalized_dir)
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
            sample_code=resolved_sample_code,
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
    resolved_sample_code = _resolve_sample_code(payload.sample_code, normalized_dir)
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
        merged = run_survey_by_paths(file_check=file_check, verbose=payload.verbose)
        kmer_result = _attach_kmer_plots(merged, file_check, normalized_dir)
        nt_result = merged.get("nt_result", {})
        gc_result = merged.get("gc_result", {})
        survey_result = merged.get("survey_result", {})
        result_metrics = merged.get("result_metrics", {})
        target_species = merged.get("target_species") or infer_target_species(file_check) or "未提供"

        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=resolved_sample_code,
            source_path=normalized_dir,
            case_id=payload.case_id,
        )
        crud.save_kmer_result(db, obj.id, _to_kmer_input(kmer_result))
        crud.save_nt_result(db, obj.id, _to_nt_input(nt_result))
        crud.save_gc_result(db, obj.id, _to_gc_input(gc_result))
        crud.save_survey_result(db, obj.id, _to_survey_input(survey_result))
        if result_metrics:
            crud.save_result_metrics(db, obj.id, _to_result_metrics_input(result_metrics))
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
    resolved_sample_code = _resolve_sample_code(payload.sample_code, normalized_dir)
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
        merged = run_survey_by_paths(file_check=file_check, verbose=payload.verbose)
        kmer_result = _attach_kmer_plots(merged, file_check, normalized_dir)
        nt_result = merged.get("nt_result", {})
        gc_result = merged.get("gc_result", {})
        survey_result = merged.get("survey_result", {})
        result_metrics = merged.get("result_metrics", {})
        target_species = merged.get("target_species") or infer_target_species(file_check) or "未提供"

        obj = crud.ensure_case(
            db=db,
            target_species=target_species,
            sample_code=resolved_sample_code,
            source_path=normalized_dir,
            case_id=existing.id,
        )
        crud.save_kmer_result(db, obj.id, _to_kmer_input(kmer_result))
        crud.save_nt_result(db, obj.id, _to_nt_input(nt_result))
        crud.save_gc_result(db, obj.id, _to_gc_input(gc_result))
        crud.save_survey_result(db, obj.id, _to_survey_input(survey_result))
        if result_metrics:
            crud.save_result_metrics(db, obj.id, _to_result_metrics_input(result_metrics))
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
    existing = crud.get_case_detail(db, case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="样本不存在")

    cleanup_result = cleanup_kmer_plots(
        [
            existing.kmer_result.spe_plot_path if existing.kmer_result else None,
            existing.kmer_result.num_plot_path if existing.kmer_result else None,
        ]
    )
    crud.delete_case(db, case_id)

    deleted_files = int(cleanup_result.get("deleted_files", 0))
    ignored_paths = list(cleanup_result.get("ignored_paths", []))
    message = f"样本记录已删除，已同步清理峰图 {deleted_files} 个文件"
    if ignored_paths:
        message += f"（忽略 {len(ignored_paths)} 个非受管路径）"
    return schemas.DeleteCaseOut(
        deleted=True,
        case_id=case_id,
        message=message,
    )
