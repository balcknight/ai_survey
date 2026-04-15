from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=schemas.CaseDetailOut)
def create_case(payload: schemas.CaseCreate, db: Session = Depends(get_db)):
    obj = crud.create_case(db, payload)
    obj = crud.get_case_detail(db, obj.id)
    if obj is None:
        raise HTTPException(status_code=500, detail="创建后读取失败")
    return crud.to_case_detail_out(obj)


@router.post("/import-survey-json", response_model=schemas.CaseDetailOut)
def import_case(payload: schemas.SurveyJsonImportIn, db: Session = Depends(get_db)):
    try:
        obj = crud.import_case_from_survey_json(
            db=db,
            sample_code=payload.sample_code,
            source_path=payload.source_path,
            payload=payload.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    obj = crud.get_case_detail(db, obj.id)
    if obj is None:
        raise HTTPException(status_code=500, detail="导入后读取失败")
    return crud.to_case_detail_out(obj)


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

