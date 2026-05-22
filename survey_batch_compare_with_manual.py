"""批量运行 survey_judge_single.py 并与人工结果比对，导出 Excel。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from survey_judge_single import resolve_input_files, run_single_survey


MANUAL_YES = "是"
MANUAL_NO = "否"


def normalize_manual(value: Any) -> str:
    text = str(value).strip()
    if text in {"是", "yes", "YES", "Y", "y", "1", "True", "true"}:
        return MANUAL_YES
    return MANUAL_NO


def normalize_script_transfer(should_transfer: Any) -> str:
    text = str(should_transfer).strip()
    if text in {"是", "转人工"}:
        return MANUAL_YES
    return MANUAL_NO


def path_to_sample_dir(raw_path: str) -> Path:
    p = Path(str(raw_path).strip())
    if p.suffix == ".survey":
        return p
    return p


def _find_one(sample_dir: Path, pattern: str) -> str | None:
    items = sorted(sample_dir.glob(f"**/{pattern}"))
    if not items:
        return None
    return str(items[0])


def _find_all(sample_dir: Path, pattern: str) -> list[str]:
    return [str(p) for p in sorted(sample_dir.glob(f"**/{pattern}"))]


def resolve_input_files_compatible(sample_dir: str) -> dict[str, Any]:
    """兼容定位输入文件：优先使用原逻辑，失败时回退支持 all.ntspe.xls。"""
    try:
        return resolve_input_files(sample_dir)
    except Exception:
        pass

    sample_path = Path(sample_dir).expanduser().resolve()
    if not sample_path.exists() or not sample_path.is_dir():
        raise FileNotFoundError(f"样本目录不存在或不是目录: {sample_path}")

    spe_path = _find_one(sample_path, "*.SpeFreq.cut")
    num_path = _find_one(sample_path, "*.NumFreq.cut")
    ntcls_path = _find_one(sample_path, "all.ntcls.xls") or _find_one(sample_path, "*.ntcls.xls")
    ntspe_paths = _find_all(sample_path, "*.species.xls")
    if not ntspe_paths:
        ntspe_paths = _find_all(sample_path, "*.species.test.xls")
    if not ntspe_paths:
        ntspe_paths = _find_all(sample_path, "all.ntspe.xls")
    result_path = _find_one(sample_path, "*.Result.xls")

    missing = []
    if not spe_path:
        missing.append("*.SpeFreq.cut")
    if not num_path:
        missing.append("*.NumFreq.cut")
    if not ntcls_path:
        missing.append("all.ntcls.xls（备选：*.ntcls.xls）")
    if not ntspe_paths:
        missing.append("至少一个 *.species.xls（备选：*.species.test.xls, all.ntspe.xls）")
    if not result_path:
        missing.append("*.Result.xls")
    if missing:
        raise FileNotFoundError(
            f"在目录 {sample_path} 内未找到以下文件: {', '.join(missing)}。"
            "请确认输入文件都在该目录（或其子目录）中。"
        )

    return {
        "spe_path": spe_path,
        "num_path": num_path,
        "ntcls_path": ntcls_path,
        "ntspe_paths": ntspe_paths,
        "result_path": result_path,
    }


def run_one(sample_path: str, verbose: bool = False) -> dict[str, Any]:
    sample_dir = path_to_sample_dir(sample_path)
    paths = resolve_input_files_compatible(str(sample_dir))
    merged = run_single_survey(
        spe_path=paths["spe_path"],
        num_path=paths["num_path"],
        ntcls_path=paths["ntcls_path"],
        ntspe_paths=paths["ntspe_paths"],
        result_path=paths.get("result_path"),
        verbose=verbose,
    )

    survey = merged.get("survey_result", {})
    nt = merged.get("nt_result", {})
    gc = merged.get("gc_result", {})

    return {
        "script_final_level": survey.get("final_level", ""),
        "script_should_transfer_raw": survey.get("should_transfer", ""),
        "script_transfer_normalized": normalize_script_transfer(survey.get("should_transfer", "")),
        "script_remark": survey.get("remark", ""),
        "target_species": merged.get("target_species", ""),
        "kmer_pattern": merged.get("pattern", ""),
        "kmer_is_normal": bool(merged.get("is_normal", False)),
        "nt_level": nt.get("nt_level", ""),
        "pollution_ratio_percent": nt.get("pollution_ratio_percent", ""),
        "pollution_threshold_percent": nt.get("pollution_threshold_percent", ""),
        "gc_status": gc.get("status", ""),
        "gc_reason": gc.get("reason", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="批量测试并与人工结果比较")
    parser.add_argument(
        "--input",
        default="data/batch_test/survey_data_check.txt",
        help="输入txt/tsv路径（需包含两列：路径、是否流转-结果）",
    )
    parser.add_argument(
        "--output",
        default="data/batch_test/survey_data_check_result.xlsx",
        help="输出 Excel 路径",
    )
    parser.add_argument("--max", type=int, default=None, help="仅处理前N条（调试用）")
    parser.add_argument("--verbose", action="store_true", help="打印单样本详细日志")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, sep="\t")
    required_cols = ["路径", "是否流转-结果"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"输入文件缺少列: {col}")

    if args.max is not None:
        df = df.head(args.max).copy()
    else:
        df = df.copy()

    rows: list[dict[str, Any]] = []
    total = len(df)

    for idx, row in df.iterrows():
        sample_path = str(row["路径"]).strip()
        manual_raw = row["是否流转-结果"]
        manual_norm = normalize_manual(manual_raw)

        print(f"[{len(rows)+1}/{total}] 处理: {sample_path}")

        record: dict[str, Any] = {
            "路径": sample_path,
            "人工结果": manual_raw,
            "人工结果标准化": manual_norm,
            "一致": "否",
            "错误": "",
        }

        try:
            script_res = run_one(sample_path, verbose=args.verbose)
            record.update(
                {
                    "脚本综合判定": script_res["script_final_level"],
                    "脚本是否流转(原始)": script_res["script_should_transfer_raw"],
                    "脚本是否流转(标准化)": script_res["script_transfer_normalized"],
                    "脚本备注": script_res["script_remark"],
                    "目标物种": script_res["target_species"],
                    "kmer峰型": script_res["kmer_pattern"],
                    "kmer正常": "是" if script_res["kmer_is_normal"] else "否",
                    "NT等级": script_res["nt_level"],
                    "NT污染合计(%)": script_res["pollution_ratio_percent"],
                    "NT阈值(%)": script_res["pollution_threshold_percent"],
                    "GC状态": script_res["gc_status"],
                    "GC原因": script_res["gc_reason"],
                }
            )
            record["一致"] = (
                MANUAL_YES
                if script_res["script_transfer_normalized"] == manual_norm
                else MANUAL_NO
            )
        except Exception as exc:
            record.update(
                {
                    "脚本综合判定": "fail",
                    "脚本是否流转(原始)": "fail",
                    "脚本是否流转(标准化)": MANUAL_NO,
                    "脚本备注": "",
                    "目标物种": "",
                    "kmer峰型": "",
                    "kmer正常": "",
                    "NT等级": "",
                    "NT污染合计(%)": "",
                    "NT阈值(%)": "",
                    "GC状态": "",
                    "GC原因": "",
                    "错误": str(exc),
                    "一致": MANUAL_NO,
                }
            )

        rows.append(record)

    out_df = pd.DataFrame(rows)

    total_count = len(out_df)
    matched_count = int((out_df["一致"] == MANUAL_YES).sum())
    mismatch_count = total_count - matched_count
    err_count = int((out_df["错误"].astype(str).str.len() > 0).sum())

    summary_df = pd.DataFrame(
        [
            {"指标": "总样本数", "值": total_count},
            {"指标": "一致数", "值": matched_count},
            {"指标": "不一致数", "值": mismatch_count},
            {"指标": "一致率", "值": f"{(matched_count / total_count * 100):.2f}%" if total_count else "0.00%"},
            {"指标": "报错数", "值": err_count},
        ]
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        out_df.to_excel(writer, sheet_name="明细", index=False)
        summary_df.to_excel(writer, sheet_name="汇总", index=False)

    print("=" * 60)
    print(f"总样本数: {total_count}")
    print(f"一致数: {matched_count}")
    print(f"不一致数: {mismatch_count}")
    print(f"一致率: {(matched_count / total_count * 100):.2f}%" if total_count else "一致率: 0.00%")
    print(f"报错数: {err_count}")
    print(f"输出文件: {output_path}")


if __name__ == "__main__":
    main()
