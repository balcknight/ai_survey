from __future__ import annotations

import hashlib
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
KMER_PLOT_ROOT = (PROJECT_ROOT / "data" / "kmer_plots").resolve()


def _infer_sample_stem(filepath: Path) -> str:
    stem = filepath.stem
    stem = stem.replace(".17merFreq.NumFreq", "")
    stem = stem.replace(".17merFreq.SpeFreq", "")
    return stem


def _safe_name(text: str, fallback: str = "sample") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("._-")
    return cleaned or fallback


def _is_managed_plot_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(KMER_PLOT_ROOT)
        return True
    except Exception:
        return False


def _build_output_dir(sample_dir: str) -> Path:
    sample_path = Path(sample_dir).expanduser().resolve()
    digest = hashlib.sha1(str(sample_path).encode("utf-8")).hexdigest()[:16]
    sample_name = _safe_name(sample_path.name, fallback="sample")
    return KMER_PLOT_ROOT / f"{sample_name}_{digest}"


def _plot_single_curve(
    input_path: Path,
    output_path: Path,
    title: str,
    color: str,
    truncate_low_depth_spike: bool,
) -> None:
    # 延迟导入，避免非绘图场景强依赖 matplotlib/pandas。
    import matplotlib.pyplot as plt
    import pandas as pd

    df = pd.read_csv(input_path, sep=r"\s+", header=None, names=["Depth", "Frequency"])
    df["Depth"] = pd.to_numeric(df["Depth"], errors="coerce")
    df["Frequency"] = pd.to_numeric(df["Frequency"], errors="coerce")
    df = df.dropna(subset=["Depth", "Frequency"])
    df = df[df["Depth"] <= 300]
    if df.empty:
        raise ValueError(f"输入文件无可用数据: {input_path}")

    plt.figure(figsize=(8, 5))
    plt.plot(df["Depth"], df["Frequency"], color=color, label=input_path.name)
    plt.title(title)
    plt.xlabel("Depth")
    plt.ylabel("Frequency")

    if truncate_low_depth_spike:
        main_region = df[df["Depth"] >= 10]["Frequency"]
        if not main_region.empty:
            y_top = float(main_region.max()) * 1.15
            if y_top > 0:
                plt.ylim(0, y_top)
            if float(df["Frequency"].max()) > y_top:
                plt.text(
                    0.02,
                    0.96,
                    "Low-depth spike truncated",
                    transform=plt.gca().transAxes,
                    va="top",
                    ha="left",
                    fontsize=9,
                    color="gray",
                )

    plt.legend()
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()


def generate_kmer_plots(
    spe_path: str | None,
    num_path: str | None,
    sample_dir: str | None = None,
) -> dict[str, str | list[str] | None]:
    warnings: list[str] = []
    spe_plot_path: str | None = None
    num_plot_path: str | None = None

    if not spe_path or not num_path:
        return {
            "spe_plot_path": None,
            "num_plot_path": None,
            "warnings": ["缺少 SpeFreq 或 NumFreq 路径，无法绘图"],
        }
    if not sample_dir:
        return {
            "spe_plot_path": None,
            "num_plot_path": None,
            "warnings": ["缺少 sample_dir，无法确定固定峰图输出目录"],
        }

    spe_file = Path(spe_path).expanduser().resolve()
    num_file = Path(num_path).expanduser().resolve()
    out_dir = _build_output_dir(sample_dir)
    sample_stem = _infer_sample_stem(spe_file)

    spe_out = out_dir / f"{sample_stem}.17mer.SpeFreq.png"
    num_out = out_dir / f"{sample_stem}.17mer.NumFreq.png"

    try:
        _plot_single_curve(
            input_path=spe_file,
            output_path=spe_out,
            title=f"17-mer SpeFreq ({sample_stem})",
            color="#db4c3f",
            truncate_low_depth_spike=True,
        )
        spe_plot_path = str(spe_out)
    except Exception as exc:
        warnings.append(f"SpeFreq 峰图绘制失败: {exc}")

    try:
        _plot_single_curve(
            input_path=num_file,
            output_path=num_out,
            title=f"17-mer NumFreq ({sample_stem})",
            color="#2b73b6",
            truncate_low_depth_spike=False,
        )
        num_plot_path = str(num_out)
    except Exception as exc:
        warnings.append(f"NumFreq 峰图绘制失败: {exc}")

    return {
        "spe_plot_path": spe_plot_path,
        "num_plot_path": num_plot_path,
        "warnings": warnings,
    }


def cleanup_kmer_plots(paths: list[str | None]) -> dict[str, int | list[str]]:
    deleted_files = 0
    ignored_paths: list[str] = []

    for raw in paths:
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if not _is_managed_plot_path(path):
            ignored_paths.append(str(path))
            continue
        if path.exists() and path.is_file():
            path.unlink()
            deleted_files += 1

    # 尝试回收空目录（仅处理固定峰图根目录内）。
    for parent in sorted({Path(p).expanduser().resolve().parent for p in paths if p}, key=lambda x: len(str(x)), reverse=True):
        if not _is_managed_plot_path(parent):
            continue
        try:
            parent.rmdir()
        except OSError:
            pass

    return {
        "deleted_files": deleted_files,
        "ignored_paths": ignored_paths,
    }
