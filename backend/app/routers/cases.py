from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..db import get_db
from ..deps import get_current_user
from ..json_utils import from_json_text
from ..services.gc_plot import GC_PLOT_ROOT, cleanup_gc_outputs, collect_gc_cleanup_paths
from ..services.kmer_plot import KMER_PLOT_ROOT, cleanup_kmer_plots, generate_kmer_plots
from ..services.mailer import send_survey_done_email
from ..services.survey_runner import (
    check_required_files,
    infer_target_species,
    run_kmer_by_paths,
    run_nt_by_paths,
    run_survey_by_paths,
)

# 前端使用的接口：全部需要登录。
router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(get_current_user)])
# 外部机器对机器接口（run-*/check-by-path）：保持开放，避免破坏外部集成。
public_router = APIRouter(prefix="/api/cases", tags=["cases-public"])
# 资源端点（峰图/GC 图/HTML 报告/压缩包）通过 ?token= 传递凭证，
# 禁止缓存并避免 token 随 Referer 泄露。
RESOURCE_RESPONSE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
EXTERNAL_UPLOAD_ROOT = Path("data/external_uploads").resolve()
logger = logging.getLogger("uvicorn.error")


def _normalize_sample_dir(sample_dir: str) -> str:
    return str(Path(sample_dir).expanduser().resolve())


def _safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = extract_dir / member.filename
            resolved = member_path.resolve()
            if extract_dir != resolved and extract_dir not in resolved.parents:
                raise ValueError(f"压缩包包含非法路径: {member.filename}")
        zf.extractall(extract_dir)


def _resolve_extracted_sample_dir(extract_dir: Path) -> Path:
    entries = [p for p in extract_dir.iterdir() if p.name != "__MACOSX"]
    dirs = [p for p in entries if p.is_dir()]
    if len(dirs) == 1 and not any(p.is_file() for p in entries):
        return dirs[0]
    return extract_dir


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
        spe_main_peak_depth=kmer_result.get("spe_main_peak_depth"),
        num_main_peak_depth=kmer_result.get("num_main_peak_depth"),
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
        participated=gc_result.get("participated"),
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


def _format_num(value: object, digits: int = 2, fallback: str = "--") -> str:
    try:
        val = float(value)  # type: ignore[arg-type]
        text = f"{val:.{digits}f}".rstrip("0").rstrip(".")
        return text if text else "0"
    except Exception:
        return fallback


def _ploidy_human(pattern: str | None) -> str:
    mapping = {
        "二倍体": "推测二倍体",
        "三倍体": "推测三倍体",
        "四倍体": "推测四倍体",
        "六倍体": "推测六倍体",
    }
    return mapping.get(pattern or "", f"待人工确认（{pattern or '未知'}）")


def _build_judge_report_payload(case_detail: schemas.CaseDetailOut | None) -> schemas.JudgeReportOut | None:
    if case_detail is None:
        return None

    nt_abnormal = case_detail.nt_result.is_heavy_contamination if case_detail.nt_result else None
    kmer_poisson = case_detail.kmer_result.is_normal if case_detail.kmer_result else None

    pattern = case_detail.result_metrics.ploidy_pattern if case_detail.result_metrics else None
    multiplier = case_detail.result_metrics.ploidy_multiplier if case_detail.result_metrics else None
    adjusted = case_detail.result_metrics.adjusted if case_detail.result_metrics else None
    raw = case_detail.result_metrics.raw if case_detail.result_metrics else None

    revised_mono = _format_num((adjusted or {}).get("revised_genome_size_m"))
    heter = _format_num((adjusted or {}).get("heterozygous_rate_percent"))
    repeat = _format_num((adjusted or {}).get("repeat_rate_percent"))
    kmer_k = str((raw or {}).get("kmer") or "--")

    ploidy_text = _ploidy_human(pattern)
    transfer_suggestion = "建议流转" if case_detail.should_transfer == "是" else "重新送样"
    if case_detail.should_transfer == "转人工":
        transfer_suggestion = "转人工复核"

    summary = (
        f"采用kmer {kmer_k}进行Survey分析，预估得到: 矫正后基因组大小为{revised_mono}Mbp，"
        f"杂合率为{heter}%，重复序列比例为{repeat}%。"
    )
    if multiplier and multiplier > 1:
        full_size = "--"
        try:
            full_size = _format_num(float(revised_mono) * float(multiplier))
        except Exception:
            pass
        summary += (
            f" 多倍体情况下，单套基因组大小为{revised_mono}Mbp，杂合率为{heter}%，"
            f"重复序列比例为{repeat}%。全套基因组大小约为{full_size}Mbp。"
        )

    return schemas.JudgeReportOut(
        nt_abnormal=nt_abnormal,
        kmer_poisson=kmer_poisson,
        ploidy_text=ploidy_text,
        transfer_suggestion=transfer_suggestion,
        summary_text=summary,
    )


def _ensure_gc_plot_artifacts(merged: dict, file_check: schemas.FileCheckOut, sample_dir: str) -> dict:
    updated = dict(merged)
    gc_result = dict(updated.get("gc_result") or {})
    gc_raw = gc_result.get("gc_raw")

    has_png = False
    if isinstance(gc_raw, dict):
        artifacts = gc_raw.get("artifacts")
        has_png = isinstance(artifacts, dict) and bool(str(artifacts.get("png") or "").strip())
    if has_png:
        updated["gc_result"] = gc_result
        return updated

    try:
        from gc_depth_line_judge import resolve_gc_input_file, run_gc_depth_line
        from ..services.gc_plot import build_gc_output_paths

        gc_paths = resolve_gc_input_file(sample_dir)
        pos_path = gc_paths["pos_path"]
        output_paths = build_gc_output_paths(sample_dir=sample_dir, pos_path=pos_path)
        gc_raw_plot = run_gc_depth_line(
            pos_path=pos_path,
            out_json=output_paths["out_json"],
            out_png=output_paths["out_png"],
        )
        if not isinstance(gc_raw_plot, dict):
            raise ValueError("GC绘图返回格式异常")
        if not gc_result:
            gc_result = {"executed": False, "status": "skipped", "reason": "仅补充GC图展示，未参与裁决", "participated": False}
        gc_result["pos_path"] = gc_result.get("pos_path") or pos_path
        gc_result["gc_raw"] = gc_raw_plot
    except Exception as exc:
        # 只记录告警，不改变原有GC判定逻辑和状态。
        warnings = list(updated.get("warnings") or [])
        warnings.append(f"GC图生成失败: {exc}")
        updated["warnings"] = warnings

    updated["gc_result"] = gc_result
    return updated


def _enqueue_survey_done_email(
    background_tasks: BackgroundTasks,
    *,
    case_detail: schemas.CaseDetailOut,
    sample_dir: str,
    judge_report: schemas.JudgeReportOut | None,
    body_text: str | None = None,
) -> None:
    logger.info("已加入邮件提醒后台任务: case_id=%s, sample_dir=%s", case_detail.id, sample_dir)

    def _send() -> None:
        try:
            send_survey_done_email(
                case_id=case_detail.id,
                sample_code=case_detail.sample_code,
                sample_dir=sample_dir,
                transfer_suggestion=judge_report.transfer_suggestion if judge_report else None,
                summary_text=judge_report.summary_text if judge_report else None,
                body_text=body_text,
            )
        except Exception as exc:
            logger.exception("邮件提醒发送失败: case_id=%s, error=%s", case_detail.id, exc)

    background_tasks.add_task(_send)


def _parse_contact_list_json(field_value: str, field_name: str) -> list[schemas.ContactInfo]:
    try:
        raw = json.loads(field_value)
        if not isinstance(raw, list):
            raise ValueError("not list")
        return [schemas.ContactInfo(**item) for item in raw]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} 必须是合法 JSON 数组，格式: "
            "[{\"name\":\"...\",\"email\":\"...\"}]",
        ) from exc


def _parse_group_emails(group_emails_text: str | None) -> list[str]:
    if group_emails_text is None or not group_emails_text.strip():
        return []
    text = group_emails_text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(i).strip() for i in parsed if str(i).strip()]
    except Exception:
        pass
    return [i.strip() for i in text.split(",") if i.strip()]


@router.get("", response_model=schemas.CaseListOut)
def list_cases(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    target_species: str | None = None,
    final_level: str | None = None,
    should_transfer: str | None = None,
    status: str | None = None,
    stage_code: str | None = None,
    bioinfo_email: str | None = None,
    review_status: str | None = Query(None, pattern="^(reviewed|unreviewed)$"),
    review_final_decision: str | None = Query(None, pattern="^(transfer|no_transfer|confirm|rerun|manual_transfer)$"),
):
    items = crud.list_cases(
        db=db,
        limit=limit,
        offset=offset,
        target_species=target_species,
        final_level=final_level,
        should_transfer=should_transfer,
        status=status,
        stage_code=stage_code,
        bioinfo_email=bioinfo_email,
        review_status=review_status,
        review_final_decision=review_final_decision,
    )
    total = crud.count_cases(
        db=db,
        target_species=target_species,
        final_level=final_level,
        should_transfer=should_transfer,
        status=status,
        stage_code=stage_code,
        bioinfo_email=bioinfo_email,
        review_status=review_status,
        review_final_decision=review_final_decision,
    )
    return schemas.CaseListOut(
        items=[crud.to_case_summary_out(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=schemas.CaseStatsOut)
def get_case_stats(db: Session = Depends(get_db)):
    return crud.get_case_stats(db)


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

    return FileResponse(str(path), media_type="image/png", filename=path.name, headers=RESOURCE_RESPONSE_HEADERS)


@router.get("/{case_id}/gc-plot")
def get_gc_plot(
    case_id: int,
    step: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    if obj.gc_result is None:
        raise HTTPException(status_code=404, detail="该样本暂无GC结果")

    gc_raw = from_json_text(obj.gc_result.gc_raw_json, None)
    artifacts = gc_raw.get("artifacts") if isinstance(gc_raw, dict) else None
    if step is None:
        plot_path = artifacts.get("png") if isinstance(artifacts, dict) else None
        if not isinstance(plot_path, str) or not plot_path.strip():
            raise HTTPException(status_code=404, detail="该样本暂无GC图")
    else:
        png_steps = artifacts.get("png_steps") if isinstance(artifacts, dict) else None
        matched = next(
            (s for s in (png_steps or []) if isinstance(s, dict) and s.get("index") == step),
            None,
        )
        plot_path = matched.get("png") if isinstance(matched, dict) else None
        if not isinstance(plot_path, str) or not plot_path.strip():
            raise HTTPException(
                status_code=404,
                detail="该样本GC图无此步骤（step 越界或历史数据无步骤快照）",
            )

    path = Path(plot_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="GC图文件不存在")
    try:
        path.relative_to(GC_PLOT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="GC图路径不在受管目录，拒绝访问") from exc

    return FileResponse(str(path), media_type="image/png", filename=path.name, headers=RESOURCE_RESPONSE_HEADERS)


@router.get("/{case_id}/judge-report", response_model=schemas.JudgeReportOut)
def get_judge_report(case_id: int, db: Session = Depends(get_db)):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    detail = crud.to_case_detail_out(obj)
    report = _build_judge_report_payload(detail)
    if report is None:
        raise HTTPException(status_code=404, detail="该样本暂无判定报告")
    return report


@router.get("/{case_id}/report-html")
def get_case_report_html(case_id: int, db: Session = Depends(get_db)):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    if not obj.source_path:
        raise HTTPException(status_code=404, detail="样本缺少 source_path，无法定位报告")

    sample_dir = Path(obj.source_path).expanduser().resolve()
    if not sample_dir.exists() or not sample_dir.is_dir():
        raise HTTPException(status_code=404, detail="样本目录不存在")

    # 仅在 sample_dir（含子目录）内查找 html 报告，优先命中包含 report/survey 关键词的文件。
    html_candidates = [p.resolve() for p in sample_dir.rglob("*.html") if p.is_file()]
    if not html_candidates:
        raise HTTPException(status_code=404, detail="未找到 html 报告文件")

    keyword_hits = [
        p
        for p in html_candidates
        if ("report" in p.name.lower()) or ("survey" in p.name.lower()) or ("report" in str(p.parent).lower())
    ]
    target = sorted(keyword_hits or html_candidates)[0]
    try:
        target.relative_to(sample_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="报告文件路径非法，拒绝访问") from exc

    html_text = target.read_text(encoding="utf-8", errors="ignore")
    return HTMLResponse(
        content=html_text,
        media_type="text/html; charset=utf-8",
        headers=RESOURCE_RESPONSE_HEADERS,
    )


@router.get("/{case_id}/archive")
def download_case_archive(case_id: int, db: Session = Depends(get_db)):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    if not obj.archive_path:
        raise HTTPException(status_code=404, detail="该样本无原始压缩包")

    archive_path = Path(obj.archive_path).expanduser().resolve()
    if not archive_path.exists() or not archive_path.is_file():
        raise HTTPException(status_code=404, detail="压缩包文件不存在")

    return FileResponse(
        str(archive_path),
        media_type="application/zip",
        filename=archive_path.name,
        headers=RESOURCE_RESPONSE_HEADERS,
    )


@router.get("/{case_id}/manual-review", response_model=list[schemas.ManualReviewOut])
def get_manual_reviews(case_id: int, db: Session = Depends(get_db)):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    rows = crud.list_manual_reviews(db, case_id)
    return [
        schemas.ManualReviewOut(
            id=row.id,
            case_id=row.case_id,
            reviewer_id=row.reviewer_id,
            reviewer_name=row.reviewer_name,
            kmer_review=row.kmer_review,
            nt_review=row.nt_review,
            gc_review=row.gc_review,
            final_decision=row.final_decision,
            note=row.note,
            kmer_incorrect_reason=row.kmer_incorrect_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/{case_id}/manual-review", response_model=schemas.ManualReviewOut)
def create_manual_review(
    case_id: int,
    payload: schemas.ManualReviewIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    obj = crud.get_case_detail(db, case_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    # kmer AI 判定被勾选为「不正确」时，强制要求填写原因（独立记录，不作为邮件正文）。
    if payload.kmer_review == "incorrect" and not (payload.kmer_incorrect_reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Kmer AI判定结果被勾选为不正确，必须填写不正确原因后才能提交",
        )
    row = crud.create_manual_review(db, case_id, payload, reviewer=current_user)
    detail = crud.to_case_detail_out(obj)
    _enqueue_survey_done_email(
        background_tasks,
        case_detail=detail,
        sample_dir=detail.source_path or "未提供",
        judge_report=_build_judge_report_payload(detail),
        body_text=payload.note,
    )
    return schemas.ManualReviewOut(
        id=row.id,
        case_id=row.case_id,
        reviewer_id=row.reviewer_id,
        reviewer_name=row.reviewer_name,
        kmer_review=row.kmer_review,
        nt_review=row.nt_review,
        gc_review=row.gc_review,
        final_decision=row.final_decision,
        note=row.note,
        kmer_incorrect_reason=row.kmer_incorrect_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@public_router.post("/run-by-path", response_model=schemas.RunByPathOut)
def run_by_path(
    payload: schemas.RunByPathIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
        merged = _ensure_gc_plot_artifacts(merged, file_check, normalized_dir)
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

    detail = crud.to_case_detail_out(detail_obj)
    report = _build_judge_report_payload(detail)
    _enqueue_survey_done_email(
        background_tasks,
        case_detail=detail,
        sample_dir=normalized_dir,
        judge_report=report,
    )

    return schemas.RunByPathOut(
        sample_dir=normalized_dir,
        file_check=file_check,
        executed=True,
        message="文件齐全，已完成survey判定并入库",
        case_id=detail_obj.id,
        case_detail=detail,
        judge_report=report,
    )


@public_router.post("/run-by-archive", response_model=schemas.ExternalRunByArchiveOut)
async def run_by_archive(
    background_tasks: BackgroundTasks,
    archive: UploadFile = File(...),
    stage_code: str = Form(...),
    sample_name: str = Form(...),
    bioinfo_emails: str = Form(...),
    operation_emails: str = Form(...),
    group_emails: str | None = Form(None),
    verbose: bool = Form(True),
    db: Session = Depends(get_db),
):
    filename = (archive.filename or "").strip()
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 压缩包")

    bioinfo_contact_list = _parse_contact_list_json(bioinfo_emails, "bioinfo_emails")
    operation_contact_list = _parse_contact_list_json(operation_emails, "operation_emails")
    group_email_list = _parse_group_emails(group_emails)

    date_seg = datetime.now().strftime("%Y%m%d")
    task_id = uuid.uuid4().hex[:12]
    safe_sample = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in sample_name.strip()) or "sample"
    root_dir = (EXTERNAL_UPLOAD_ROOT / date_seg / f"{safe_sample}_{task_id}").resolve()
    extract_dir = (root_dir / "extracted").resolve()
    archive_path = (root_dir / "upload.zip").resolve()

    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with archive_path.open("wb") as f:
            while True:
                chunk = await archive.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        await archive.close()
        _safe_extract_zip(archive_path, extract_dir)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(root_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="压缩包格式错误，无法解压") from exc
    except Exception as exc:
        shutil.rmtree(root_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"保存或解压压缩包失败: {exc}") from exc

    sample_dir = _resolve_extracted_sample_dir(extract_dir).resolve()
    normalized_dir = str(sample_dir)
    _guard_duplicate_source_path(db, normalized_dir, case_id=None)
    file_check = check_required_files(normalized_dir)
    if not file_check.complete:
        return schemas.ExternalRunByArchiveOut(
            sample_dir=normalized_dir,
            archive_path=str(archive_path),
            stage_code=stage_code,
            sample_name=sample_name,
            bioinfo_emails=bioinfo_contact_list,
            operation_emails=operation_contact_list,
            group_emails=group_email_list,
            file_check=file_check,
            executed=False,
            message=f"输入文件不完整，缺失: {', '.join(file_check.missing)}",
        )

    try:
        merged = run_survey_by_paths(file_check=file_check, verbose=verbose)
        merged = _attach_kmer_plots(merged, file_check, normalized_dir)
        merged = _ensure_gc_plot_artifacts(merged, file_check, normalized_dir)
        obj = crud.import_case_from_survey_json(
            db=db,
            sample_code=sample_name.strip() or None,
            source_path=normalized_dir,
            payload=merged,
            stage_code=stage_code,
            bioinfo_emails=[item.model_dump() for item in bioinfo_contact_list],
            operation_emails=[item.model_dump() for item in operation_contact_list],
            group_emails=group_email_list,
            archive_path=str(archive_path),
        )
        detail_obj = crud.get_case_detail(db, obj.id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"执行survey判定失败: {exc}") from exc

    if detail_obj is None:
        raise HTTPException(status_code=500, detail="执行后读取样本失败")

    detail = crud.to_case_detail_out(detail_obj)
    report = _build_judge_report_payload(detail)
    _enqueue_survey_done_email(
        background_tasks,
        case_detail=detail,
        sample_dir=normalized_dir,
        judge_report=report,
    )

    return schemas.ExternalRunByArchiveOut(
        sample_dir=normalized_dir,
        archive_path=str(archive_path),
        stage_code=stage_code,
        sample_name=sample_name,
        bioinfo_emails=bioinfo_contact_list,
        operation_emails=operation_contact_list,
        group_emails=group_email_list,
        file_check=file_check,
        executed=True,
        message="压缩包文件齐全，已完成survey判定并入库",
        case_id=detail_obj.id,
        case_detail=detail,
        judge_report=report,
    )


@public_router.post("/check-by-path", response_model=schemas.CheckByPathOut)
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


@public_router.post("/run-kmer", response_model=schemas.RunStepByPathOut)
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


@public_router.post("/run-nt", response_model=schemas.RunStepByPathOut)
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


@public_router.post("/run-survey", response_model=schemas.RunStepByPathOut)
def run_survey(
    payload: schemas.RunStepByPathIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
    detail = crud.to_case_detail_out(detail_obj)
    _enqueue_survey_done_email(
        background_tasks,
        case_detail=detail,
        sample_dir=normalized_dir,
        judge_report=_build_judge_report_payload(detail),
    )
    return schemas.RunStepByPathOut(
        sample_dir=normalized_dir,
        executed=True,
        message="survey判定完成并已入库",
        file_check=file_check,
        case_id=detail_obj.id,
        case_detail=detail,
    )


@router.post("/rerun-survey", response_model=schemas.RunStepByPathOut)
def rerun_survey(
    payload: schemas.RerunSurveyIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
    detail = crud.to_case_detail_out(detail_obj)
    _enqueue_survey_done_email(
        background_tasks,
        case_detail=detail,
        sample_dir=normalized_dir,
        judge_report=_build_judge_report_payload(detail),
    )
    return schemas.RunStepByPathOut(
        sample_dir=normalized_dir,
        executed=True,
        message="survey重跑完成，已覆盖原记录",
        file_check=file_check,
        case_id=detail_obj.id,
        case_detail=detail,
    )


@router.delete("/{case_id}", response_model=schemas.DeleteCaseOut)
def delete_case(case_id: int, db: Session = Depends(get_db)):
    existing = crud.get_case_detail(db, case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="样本不存在")

    gc_raw = from_json_text(existing.gc_result.gc_raw_json, None) if existing.gc_result else None
    gc_cleanup_result = cleanup_gc_outputs(collect_gc_cleanup_paths(gc_raw))
    kmer_cleanup_result = cleanup_kmer_plots(
        [
            existing.kmer_result.spe_plot_path if existing.kmer_result else None,
            existing.kmer_result.num_plot_path if existing.kmer_result else None,
        ]
    )
    crud.delete_case(db, case_id)

    deleted_files = int(kmer_cleanup_result.get("deleted_files", 0)) + int(gc_cleanup_result.get("deleted_files", 0))
    ignored_paths = list(kmer_cleanup_result.get("ignored_paths", [])) + list(gc_cleanup_result.get("ignored_paths", []))
    message = f"样本记录已删除，已同步清理峰图/GC图 {deleted_files} 个文件"
    if ignored_paths:
        message += f"（忽略 {len(ignored_paths)} 个非受管路径）"
    return schemas.DeleteCaseOut(
        deleted=True,
        case_id=case_id,
        message=message,
    )
