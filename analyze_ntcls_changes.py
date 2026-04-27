from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

CATS = ["Metazoa", "Plantae", "Bacteria", "Fungi", "Viruses"]
PAIR_RE = re.compile(r"^\s*([^()]+)\(([-+]?\d*\.?\d+)\)\s*$")


@dataclass
class ParseResult:
    sample_name: str
    library_name: str
    ratios: dict[str, float]

def parse_cat_cell(cell: object) -> tuple[str, float] | None:
    if cell is None:
        return None
    text = str(cell).strip()
    if not text:
        return None
    m = PAIR_RE.match(text)
    if not m:
        return None
    cat = m.group(1).strip()
    try:
        val = float(m.group(2))
    except Exception:
        return None
    return cat, val

def parse_ntcls_new(path: Path) -> ParseResult:
    df = pd.read_csv(path, sep="\t", header=None)
    if df.empty:
        raise ValueError("ntcls.new 为空")
    row = df.iloc[0].tolist()
    sample_name = str(row[0]).strip() if len(row) > 0 else ""
    library_name = str(row[1]).strip() if len(row) > 1 else ""
    ratios = {c: 0.0 for c in CATS}
    for cell in row[2:]:
        parsed = parse_cat_cell(cell)
        if not parsed:
            continue
        cat, val = parsed
        if cat in ratios:
            ratios[cat] += val
    return ParseResult(sample_name=sample_name, library_name=library_name, ratios=ratios)


def parse_class_filtered(path: Path) -> ParseResult:
    df = pd.read_csv(path, sep="\t")
    if df.empty:
        raise ValueError("class.filtered 为空")
    row = df.iloc[0]
    sample_name = str(row.get("Sample name", "")).strip()
    library_name = str(row.get("Library name", "")).strip()
    ratios = {c: 0.0 for c in CATS}
    for col in ["First", "Second", "Third", "Fourth", "Fifth"]:
        parsed = parse_cat_cell(row.get(col, ""))
        if not parsed:
            continue
        cat, val = parsed
        if cat in ratios:
            ratios[cat] += val
    return ParseResult(sample_name=sample_name, library_name=library_name, ratios=ratios)


def count_judged_rows(judged_path: Path) -> int:
    df = pd.read_csv(judged_path, sep="\t")
    if "是否合理" not in df.columns:
        return 0
    col = df["是否合理"].fillna("").astype(str).str.strip()
    return int((col != "").sum())


def pick_ntcls_new(sample_dir: Path, lib_prefix: str) -> Path | None:
    exact = sample_dir / f"{lib_prefix}.ntcls.xls.new"
    if exact.exists():
        return exact
    cands = sorted(sample_dir.glob("*.ntcls.xls.new"))
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    for p in cands:
        if p.name.startswith(lib_prefix):
            return p
    return cands[0]


def iter_targets(root: Path) -> Iterable[tuple[Path, Path, Path, str]]:
    pattern = "*_NT.species.xls.class.filtered.tsv"
    for class_path in sorted(root.glob(f"**/{pattern}")):
        sample_dir = class_path.parent
        stem = class_path.name
        lib_prefix = stem.replace("_NT.species.xls.class.filtered.tsv", "")
        judged_path = sample_dir / f"{lib_prefix}_NT.species.xls.judged.tsv"
        ntcls_new = pick_ntcls_new(sample_dir, lib_prefix)
        if ntcls_new is None:
            yield class_path, judged_path, Path(""), lib_prefix
        else:
            yield class_path, judged_path, ntcls_new, lib_prefix


def main() -> None:
    root = Path("data/survey_nt_correct_20260421").resolve()
    out_xlsx = root / "ntcls_change_stats.xlsx"

    rows = []
    changed_rows = []
    skipped_rows = []
    missing_rows = []

    for class_path, judged_path, ntcls_new, lib_prefix in iter_targets(root):
        sample_dir = class_path.parent

        if not judged_path.exists():
            missing_rows.append({
                "sample_dir": str(sample_dir),
                "library_prefix": lib_prefix,
                "reason": "缺少 judged 文件",
                "class_filtered": str(class_path),
            })
            continue
        if not ntcls_new.exists():
            missing_rows.append({
                "sample_dir": str(sample_dir),
                "library_prefix": lib_prefix,
                "reason": "缺少 ntcls.xls.new",
                "class_filtered": str(class_path),
            })
            continue

        judged_count = count_judged_rows(judged_path)
        if judged_count > 10:
            skipped_rows.append({
                "sample_dir": str(sample_dir),
                "library_prefix": lib_prefix,
                "judged_rows": judged_count,
                "judged_path": str(judged_path),
            })
            continue

        try:
            old = parse_ntcls_new(ntcls_new)
            new = parse_class_filtered(class_path)
        except Exception as e:
            missing_rows.append({
                "sample_dir": str(sample_dir),
                "library_prefix": lib_prefix,
                "reason": f"解析失败: {e}",
                "class_filtered": str(class_path),
            })
            continue

        record = {
            "sample_dir": str(sample_dir),
            "library_prefix": lib_prefix,
            "sample_name_old": old.sample_name,
            "library_name_old": old.library_name,
            "sample_name_new": new.sample_name,
            "library_name_new": new.library_name,
            "judged_rows": judged_count,
            "ntcls_new_path": str(ntcls_new),
            "class_filtered_path": str(class_path),
            "changed": False,
            "changed_category_count": 0,
            "sum_abs_delta": 0.0,
        }

        changed_count = 0
        sum_abs_delta = 0.0
        for cat in CATS:
            old_v = float(old.ratios.get(cat, 0.0))
            new_v = float(new.ratios.get(cat, 0.0))
            delta = new_v - old_v
            abs_delta = abs(delta)
            record[f"old_{cat}"] = old_v
            record[f"new_{cat}"] = new_v
            record[f"delta_{cat}"] = delta
            if abs_delta > 1e-12:
                changed_count += 1
                sum_abs_delta += abs_delta
                changed_rows.append(
                    {
                        "sample_dir": str(sample_dir),
                        "library_prefix": lib_prefix,
                        "category": cat,
                        "old_ratio": old_v,
                        "new_ratio": new_v,
                        "delta": delta,
                        "abs_delta": abs_delta,
                        "judged_rows": judged_count,
                    }
                )

        record["changed"] = changed_count > 0
        record["changed_category_count"] = changed_count
        record["sum_abs_delta"] = sum_abs_delta
        rows.append(record)

    df_all = pd.DataFrame(rows)
    df_changed = pd.DataFrame(changed_rows)
    df_skipped = pd.DataFrame(skipped_rows)
    df_missing = pd.DataFrame(missing_rows)

    if not df_changed.empty:
        df_cat_stats = (
            df_changed.groupby("category", as_index=False)
            .agg(
                changed_samples=("sample_dir", "count"),
                delta_sum=("delta", "sum"),
                abs_delta_sum=("abs_delta", "sum"),
                delta_mean=("delta", "mean"),
                abs_delta_mean=("abs_delta", "mean"),
                delta_max=("delta", "max"),
                delta_min=("delta", "min"),
            )
            .sort_values("abs_delta_sum", ascending=False)
        )
    else:
        df_cat_stats = pd.DataFrame(columns=[
            "category", "changed_samples", "delta_sum", "abs_delta_sum",
            "delta_mean", "abs_delta_mean", "delta_max", "delta_min"
        ])

    total = len(df_all)
    changed_samples = int(df_all["changed"].sum()) if not df_all.empty else 0
    summary = pd.DataFrame([
        {"metric": "total_compared_samples", "value": total},
        {"metric": "changed_samples", "value": changed_samples},
        {"metric": "unchanged_samples", "value": total - changed_samples},
        {"metric": "skipped_samples_judged_rows_gt_10", "value": len(df_skipped)},
        {"metric": "missing_or_parse_failed", "value": len(df_missing)},
    ])

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        df_all.to_excel(writer, sheet_name="sample_compare", index=False)
        df_changed.to_excel(writer, sheet_name="changed_categories", index=False)
        df_cat_stats.to_excel(writer, sheet_name="category_stats", index=False)
        df_skipped.to_excel(writer, sheet_name="skipped_gt10", index=False)
        df_missing.to_excel(writer, sheet_name="missing_or_failed", index=False)

    print(f"输出完成: {out_xlsx}")
    print(f"对比样本数: {total}")
    print(f"发生变化样本数: {changed_samples}")
    print(f"跳过(判定行>10)样本数: {len(df_skipped)}")
    print(f"缺失/解析失败样本数: {len(df_missing)}")


if __name__ == "__main__":
    main()
