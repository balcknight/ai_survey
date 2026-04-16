from __future__ import annotations

from pathlib import Path

from kmer_judge import main_dual
from nt_judge import judge_nt_contamination
from survey_judge_single import run_single_survey
from survey_judge_single import build_final_survey, load_target_species

from .. import schemas


def _find_first(sample_path: Path, pattern: str) -> Path | None:
    candidates = sorted(sample_path.glob(f"**/{pattern}"))
    if not candidates:
        return None
    return candidates[0]


def check_required_files(sample_dir: str) -> schemas.FileCheckOut:
    sample_path = Path(sample_dir).expanduser().resolve()
    if not sample_path.exists() or not sample_path.is_dir():
        return schemas.FileCheckOut(
            missing=["sample_dir"],
            kmer_complete=False,
            nt_complete=False,
            complete=False,
        )

    spe_file = _find_first(sample_path, "*.SpeFreq.cut")
    num_file = _find_first(sample_path, "*.NumFreq.cut")
    ntcls_file = _find_first(sample_path, "all.ntcls.xls")
    ntspe_file = _find_first(sample_path, "all.ntspe.xls")

    missing: list[str] = []
    if spe_file is None:
        missing.append("*.SpeFreq.cut")
    if num_file is None:
        missing.append("*.NumFreq.cut")
    if ntcls_file is None:
        missing.append("all.ntcls.xls")
    if ntspe_file is None:
        missing.append("all.ntspe.xls")

    return schemas.FileCheckOut(
        spe_path=str(spe_file) if spe_file else None,
        num_path=str(num_file) if num_file else None,
        ntcls_path=str(ntcls_file) if ntcls_file else None,
        ntspe_path=str(ntspe_file) if ntspe_file else None,
        missing=missing,
        kmer_complete=(spe_file is not None and num_file is not None),
        nt_complete=(ntcls_file is not None and ntspe_file is not None),
        complete=(len(missing) == 0),
    )


def infer_target_species(file_check: schemas.FileCheckOut) -> str | None:
    if not file_check.ntcls_path:
        return None
    try:
        return load_target_species(file_check.ntcls_path)
    except Exception:
        return None


def run_kmer_by_paths(file_check: schemas.FileCheckOut, verbose: bool = True) -> dict:
    if not file_check.kmer_complete:
        raise ValueError("缺少 kmer 必需文件（*.SpeFreq.cut / *.NumFreq.cut）")
    species_name = infer_target_species(file_check)
    return main_dual(
        spe_filepath=file_check.spe_path or "",
        num_filepath=file_check.num_path or "",
        species_name=species_name,
        verbose=verbose,
    )


def run_nt_by_paths(file_check: schemas.FileCheckOut) -> tuple[str, dict]:
    if not file_check.nt_complete:
        raise ValueError("缺少 NT 必需文件（all.ntcls.xls / all.ntspe.xls）")
    target_species = load_target_species(file_check.ntcls_path or "")
    nt_result = judge_nt_contamination(
        file_check.ntcls_path or "",
        file_check.ntspe_path or "",
        target_species,
    )
    return target_species, nt_result


def run_survey_from_parts(kmer_result: dict, nt_result: dict) -> dict:
    return build_final_survey(kmer_result, nt_result)


def run_survey_by_paths(file_check: schemas.FileCheckOut, verbose: bool = True) -> dict:
    if not file_check.complete:
        raise ValueError("输入文件不完整，不能执行判定")
    return run_single_survey(
        spe_path=file_check.spe_path or "",
        num_path=file_check.num_path or "",
        ntcls_path=file_check.ntcls_path or "",
        ntspe_path=file_check.ntspe_path or "",
        verbose=verbose,
    )
