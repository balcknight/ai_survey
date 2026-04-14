from typing import Any

from kmer_judge import main_dual
from ploidy_agent.agent import run_ploidy_correction


def correct_from_main_dual_result(
    species_name: str,
    main_dual_result: dict[str, Any],
    script_text: str | None = None,
) -> dict[str, Any]:
    """输入物种名 + main_dual 的返回字典，输出结构化纠错结果(dict)。"""
    structured = run_ploidy_correction(
        species_name=species_name,
        kmer_result=main_dual_result,
        script_text=script_text,
    )
    if hasattr(structured, "model_dump"):
        return structured.model_dump()
    return structured


def correct_from_kmer_files(
    species_name: str,
    spe_filepath: str,
    num_filepath: str,
    script_text: str | None = None,
    kmer_verbose: bool = False,
    **kmer_kwargs,
) -> dict[str, Any]:
    """输入物种名 + Spe/Num k-mer 文件路径，内部先跑 main_dual，再跑纠错 Agent。"""
    kmer_result = main_dual(
        spe_filepath=spe_filepath,
        num_filepath=num_filepath,
        verbose=kmer_verbose,
        **kmer_kwargs,
    )
    return correct_from_main_dual_result(
        species_name=species_name,
        main_dual_result=kmer_result,
        script_text=script_text,
    )

