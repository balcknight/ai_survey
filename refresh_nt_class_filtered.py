from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import pandas as pd


CATEGORY_ORDER = ["Metazoa", "Plantae", "Bacteria", "Fungi", "Viruses"]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(str(value).strip())
    except Exception:
        return 0.0


def _format_ratio(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _read_judged(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    lower_map = {c.lower(): c for c in df.columns}

    class_col = "#class" if "#class" in df.columns else lower_map.get("class")
    total_rate_col = "total rate" if "total rate" in df.columns else lower_map.get("total rate")

    if class_col is None or total_rate_col is None:
        raise ValueError(f"缺少必需列(#class/class 或 total rate): {path}")

    out = df.copy()
    out["class"] = out[class_col].astype(str).map(_normalize_text)
    out["total_rate"] = out[total_rate_col].map(_safe_float)
    if "是否合理" in out.columns:
        out["是否合理"] = out["是否合理"].astype(str).map(_normalize_text)
    else:
        out["是否合理"] = ""
    return out


def _pick_sample_library(class_path: Path) -> tuple[str, str]:
    sample_name = ""
    library_name = ""

    if class_path.exists():
        try:
            df_cls = pd.read_csv(class_path, sep="\t")
            if not df_cls.empty:
                first = df_cls.iloc[0]
                sample_name = _normalize_text(first.get("Sample name", ""))
                library_name = _normalize_text(first.get("Library name", ""))
        except Exception:
            pass

    return sample_name, library_name


def _build_class_line(df: pd.DataFrame, sample_name: str, library_name: str) -> pd.DataFrame:
    # 取反逻辑：
    # - 是否合理=是 -> 排除
    # - 是否合理=否 -> 纳入
    # - 空值(未参与LLM判定) -> 纳入
    keep_mask = df["是否合理"] != "是"
    kept_df = df[keep_mask].copy()

    class_sum = kept_df.groupby("class", as_index=False)["total_rate"].sum()
    class_sum_map = {
        _normalize_text(row["class"]): _safe_float(row["total_rate"])
        for _, row in class_sum.iterrows()
    }

    values = [f"{cat}({_format_ratio(class_sum_map.get(cat, 0.0))})" for cat in CATEGORY_ORDER]
    return pd.DataFrame(
        [
            {
                "Sample name": sample_name,
                "Library name": library_name,
                "First": values[0],
                "Second": values[1],
                "Third": values[2],
                "Fourth": values[3],
                "Fifth": values[4],
            }
        ]
    )


def refresh_one(judged_path: Path, dry_run: bool = False) -> tuple[Path, str]:
    class_path = judged_path.with_name(judged_path.name.replace(".judged.tsv", ".class.filtered.tsv"))
    if class_path == judged_path:
        raise ValueError(f"文件名不符合 *.judged.tsv 约定: {judged_path}")

    df = _read_judged(judged_path)
    sample_name, library_name = _pick_sample_library(class_path)
    class_line = _build_class_line(df, sample_name=sample_name, library_name=library_name)

    if not dry_run:
        class_line.to_csv(class_path, sep="\t", index=False)

    metazoa = class_line.iloc[0]["First"]
    return class_path, str(metazoa)


def main() -> None:
    parser = argparse.ArgumentParser(description="按新规则重算 NT 大类汇总文件")
    parser.add_argument(
        "--root",
        default="data/survey_nt_correct_20260421",
        help="扫描根目录（递归查找 *.judged.tsv）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"目录不存在: {root}")

    judged_files = sorted(root.glob("**/*_NT.species.xls.judged.tsv"))
    print(f"扫描目录: {root}")
    print(f"发现 judged 文件: {len(judged_files)}")

    ok = 0
    fail = 0
    for idx, judged_path in enumerate(judged_files, 1):
        try:
            class_path, metazoa_str = refresh_one(judged_path, dry_run=args.dry_run)
            action = "预览" if args.dry_run else "已刷新"
            print(f"[{idx}/{len(judged_files)}] {action}: {class_path} | {metazoa_str}")
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[{idx}/{len(judged_files)}] 失败: {judged_path} | {e}")

    print(f"完成: 成功={ok}, 失败={fail}, 总数={len(judged_files)}")


if __name__ == "__main__":
    main()
