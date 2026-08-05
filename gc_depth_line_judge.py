#!/usr/bin/env python3
"""
GC-Depth 线性分割判定脚本

输入: .pos 文件（第3列GC，第4列Depth）
输出:
1) JSON 结果（线参数、计数、比值、判定）
2) PNG 可视化（密度图 + 候选直线）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd


@dataclass
class FitResult:
    exists: bool
    slope: float | None
    intercept: float | None
    separation: float | None
    balance: float | None
    score: float | None
    low_depth_points: int


@dataclass
class RidgeResult:
    exists: bool
    gc_min: float | None
    gc_max: float | None
    peak_gc: float | None
    peak_depth: float | None
    points_used: int


def _find_in_sample_dir(sample_path: Path, pattern: str) -> Path | None:
    """仅在 sample_dir 内查找匹配文件（含子目录），不向上层目录扩展。"""
    candidates = sorted(sample_path.glob(f"**/{pattern}"))
    if not candidates:
        return None
    return candidates[0]


def resolve_gc_input_file(sample_dir: str) -> dict[str, str]:
    """输入样本目录，仅在该目录内自动定位 .pos 文件。"""
    sample_path = Path(sample_dir).expanduser().resolve()
    if not sample_path.exists() or not sample_path.is_dir():
        raise FileNotFoundError(f"样本目录不存在或不是目录: {sample_path}")

    pos_file = _find_in_sample_dir(sample_path, "*.pos")
    if pos_file is None:
        raise FileNotFoundError(
            f"在目录 {sample_path} 内未找到 *.pos 文件。"
            "请确认输入文件在该目录（或其子目录）中。"
        )

    return {
        "sample_dir": str(sample_path),
        "pos_path": str(pos_file),
    }


def gaussian_smooth_1d(arr: np.ndarray, sigma: float) -> np.ndarray:
    """纯 numpy 的 1D 高斯平滑，避免额外依赖 scipy。"""
    if sigma <= 0:
        return arr.copy()
    radius = max(1, int(round(3 * sigma)))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x ** 2) / (2 * sigma * sigma))
    kernel = kernel / kernel.sum()
    return np.convolve(arr, kernel, mode="same")


def load_gc_depth(
    pos_path: Path,
    gc_col: int = 2,
    depth_col: int = 3,
    gc_min: float = 20.0,
    gc_max: float = 95.0,
    depth_min: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """读取 .pos 第3/4列（默认0-based索引 2/3），并做基础清洗。"""
    df = pd.read_csv(pos_path, sep="\t", header=None, usecols=[gc_col, depth_col], names=["gc", "depth"])
    gc = pd.to_numeric(df["gc"], errors="coerce").to_numpy(float)
    depth = pd.to_numeric(df["depth"], errors="coerce").to_numpy(float)

    keep = np.isfinite(gc) & np.isfinite(depth)
    keep &= (gc >= gc_min) & (gc <= gc_max)
    keep &= depth >= depth_min

    return gc[keep], depth[keep]


def quantize_points(x: np.ndarray, y: np.ndarray, gc_grid: float, depth_grid: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """将点云量化为网格并合并重复点，返回 (xq, yq, weight)。"""
    xq = np.round(x / gc_grid) * gc_grid
    yq = np.round(y / depth_grid) * depth_grid

    arr = np.column_stack([xq, yq])
    uniq, counts = np.unique(arr, axis=0, return_counts=True)
    return uniq[:, 0], uniq[:, 1], counts.astype(float)


def estimate_main_ridge(
    gc: np.ndarray,
    depth: np.ndarray,
    low_depth_max: float = 10.0,
    gc_grid: float = 0.5,
    min_bin_points: int = 80,
    mode_depth_grid: float = 1.0,
    ridge_sigma: float = 2.0,
) -> tuple[RidgeResult, dict[str, np.ndarray]]:
    """按 GC 分箱估计主云团主脊线。"""
    gc_centers = np.arange(20.0, 95.0 + gc_grid, gc_grid)
    left_edges = gc_centers - gc_grid / 2
    right_edges = gc_centers + gc_grid / 2

    ridge_depths = np.full(gc_centers.shape, np.nan, dtype=float)
    counts = np.zeros(gc_centers.shape, dtype=int)
    low_counts = np.zeros(gc_centers.shape, dtype=int)

    for idx, (lo, hi) in enumerate(zip(left_edges, right_edges)):
        if idx == len(gc_centers) - 1:
            mask = (gc >= lo) & (gc <= hi)
        else:
            mask = (gc >= lo) & (gc < hi)
        if not np.any(mask):
            continue

        depth_bin = depth[mask]
        counts[idx] = int(depth_bin.size)
        low_counts[idx] = int((depth_bin <= low_depth_max).sum())
        if counts[idx] < min_bin_points:
            continue

        ridge_source = depth_bin[depth_bin > low_depth_max]
        if ridge_source.size < max(20, min_bin_points // 4):
            ridge_source = depth_bin
        if ridge_source.size == 0:
            continue

        upper = max(float(np.percentile(ridge_source, 99.5)), low_depth_max + mode_depth_grid)
        edges = np.arange(0.0, upper + mode_depth_grid, mode_depth_grid)
        if edges.size < 3:
            continue
        hist, depth_edges = np.histogram(ridge_source, bins=edges)
        hist_smoothed = gaussian_smooth_1d(hist.astype(float), sigma=1.2)
        mode_idx = int(np.argmax(hist_smoothed))
        ridge_depths[idx] = 0.5 * (depth_edges[mode_idx] + depth_edges[mode_idx + 1])

    valid = np.isfinite(ridge_depths)
    if valid.sum() < 5:
        return (
            RidgeResult(False, None, None, None, None, int(valid.sum())),
            {
                "gc_centers": gc_centers,
                "ridge_depths": ridge_depths,
                "counts": counts,
                "low_counts": low_counts,
                "low_ratios": np.divide(low_counts, np.maximum(counts, 1), dtype=float),
            },
        )

    ridge_interp = np.interp(gc_centers, gc_centers[valid], ridge_depths[valid])
    ridge_smooth = gaussian_smooth_1d(ridge_interp, sigma=ridge_sigma)
    ridge_depths[valid] = ridge_smooth[valid]
    ridge_depths[~valid] = ridge_interp[~valid]

    peak_idx = int(np.nanargmax(ridge_depths))
    ridge = RidgeResult(
        exists=True,
        gc_min=float(gc_centers[np.where(np.isfinite(ridge_depths))[0][0]]),
        gc_max=float(gc_centers[np.where(np.isfinite(ridge_depths))[0][-1]]),
        peak_gc=float(gc_centers[peak_idx]),
        peak_depth=float(ridge_depths[peak_idx]),
        points_used=int(valid.sum()),
    )
    return (
        ridge,
        {
            "gc_centers": gc_centers,
            "ridge_depths": ridge_depths,
            "counts": counts,
            "low_counts": low_counts,
            "low_ratios": np.divide(low_counts, np.maximum(counts, 1), dtype=float),
        },
    )


def find_contamination_region(
    gc: np.ndarray,
    depth: np.ndarray,
    ridge: RidgeResult,
    ridge_profile: dict[str, np.ndarray],
    low_depth_max: float = 10.0,
    side_eps: float = 0.4,
    gc_grid: float = 0.5,
) -> FitResult:
    """根据主脊线峰值右侧的低深度富集区，拟合污染区上边界直线。"""
    low_mask = depth <= low_depth_max
    low_depth_points = int(low_mask.sum())
    if (not ridge.exists) or low_depth_points < 100:
        return FitResult(False, None, None, None, None, None, low_depth_points)

    gc_centers = ridge_profile["gc_centers"]
    counts = ridge_profile["counts"]
    low_counts = ridge_profile["low_counts"]
    low_ratios = ridge_profile["low_ratios"]

    peak_gc = ridge.peak_gc if ridge.peak_gc is not None else 40.0
    right_mask = gc_centers >= (peak_gc + 3.0)
    baseline_mask = (gc_centers >= max(20.0, peak_gc - 12.0)) & (gc_centers <= peak_gc)
    baseline = float(np.median(low_ratios[baseline_mask])) if np.any(baseline_mask) else 0.0
    threshold = max(0.015, baseline * 2.5)

    candidate_mask = right_mask & (counts >= 40) & (low_counts >= 20) & (low_ratios >= threshold)
    candidate_idx = np.where(candidate_mask)[0]
    if candidate_idx.size == 0:
        strongest_mask = right_mask & (counts >= 40) & (low_counts >= 20)
        strongest_idx = np.where(strongest_mask)[0]
        if strongest_idx.size == 0:
            return FitResult(False, None, None, None, None, None, low_depth_points)
        best_idx = strongest_idx[int(np.argmax(low_ratios[strongest_idx]))]
        if low_ratios[best_idx] < max(threshold, 0.02):
            return FitResult(False, None, None, None, None, None, low_depth_points)
        candidate_idx = np.array([best_idx], dtype=int)

    best_run: np.ndarray | None = None
    runs: list[np.ndarray] = []
    start = candidate_idx[0]
    prev = candidate_idx[0]
    for idx in candidate_idx[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        runs.append(np.arange(start, prev + 1))
        start = idx
        prev = idx
    runs.append(np.arange(start, prev + 1))
    if runs:
        best_run = max(runs, key=lambda arr: (arr.size, float(low_counts[arr].sum()), float(low_ratios[arr].mean())))
    if best_run is None or best_run.size == 0:
        return FitResult(False, None, None, None, None, None, low_depth_points)

    run_low = float(gc_centers[best_run[0]])
    run_high = float(gc_centers[best_run[-1]])
    ridge_profile["contam_gc_start"] = run_low
    ridge_profile["contam_gc_end"] = run_high
    expanded = (gc >= run_low - gc_grid / 2) & (gc <= run_high + gc_grid / 2) & low_mask
    if expanded.sum() < 50:
        return FitResult(False, None, None, None, None, None, low_depth_points)

    ridge_depth_at_points = np.interp(gc[expanded], gc_centers, ridge_profile["ridge_depths"])
    residual_below_ridge = ridge_depth_at_points - depth[expanded]
    strong_mask = residual_below_ridge >= max(np.percentile(residual_below_ridge, 25), low_depth_max * 0.25)
    if strong_mask.sum() < 20:
        strong_mask = np.ones(residual_below_ridge.shape, dtype=bool)

    x_sel = gc[expanded][strong_mask]
    y_sel = depth[expanded][strong_mask]

    bin_centers: list[float] = []
    upper_depths: list[float] = []
    weights: list[float] = []
    for idx in best_run:
        lo = gc_centers[idx] - gc_grid / 2
        hi = gc_centers[idx] + gc_grid / 2
        if idx == best_run[-1]:
            mask = (x_sel >= lo) & (x_sel <= hi)
        else:
            mask = (x_sel >= lo) & (x_sel < hi)
        if mask.sum() < 8:
            continue
        y_bin = y_sel[mask]
        upper_q = float(np.quantile(y_bin, 0.97))
        upper_q = min(upper_q + 0.2, low_depth_max)
        bin_centers.append(float(gc_centers[idx]))
        upper_depths.append(upper_q)
        weights.append(float(mask.sum()))

    if len(bin_centers) < 2:
        return FitResult(False, None, None, None, None, None, low_depth_points)

    coef = np.polyfit(np.asarray(bin_centers), np.asarray(upper_depths), deg=1, w=np.asarray(weights))
    slope = float(np.clip(coef[0], -0.6, 0.1))
    intercept = float(coef[1])

    predicted = slope * np.asarray(bin_centers) + intercept
    mae = float(np.average(np.abs(np.asarray(upper_depths) - predicted), weights=np.asarray(weights)))
    separation = float(min(1.0, np.average(np.asarray(weights)) / max(low_depth_points, 1) * len(bin_centers)))
    balance = float(min(1.0, low_counts[best_run].sum() / max(low_depth_points, 1)))
    score = float(max(0.0, 1.0 - mae / max(low_depth_max, 1e-6)) * separation)
    return FitResult(True, slope, intercept, separation, balance, score, low_depth_points)


def compute_global_stats(
    gc: np.ndarray,
    depth: np.ndarray,
    slope: float,
    intercept: float,
    gc_start: float,
    line_eps: float,
    low_depth_max: float,
) -> dict:
    """按右下污染区统计点数与占比。"""
    line_depth = slope * gc + intercept
    boundary = np.minimum(line_depth, low_depth_max)
    boundary = np.maximum(boundary, 0.0)
    residual = depth - boundary
    region_mask = gc >= gc_start
    contamination_mask = region_mask & (depth <= low_depth_max) & (residual <= 0)

    below = int(contamination_mask.sum())
    total = int(gc.size)
    on = int(total - below)
    ratio = float(below / max(total, 1))
    below_over_on = float(below / max(on, 1))

    on_band = int((region_mask & (np.abs(residual) <= line_eps) & (depth <= low_depth_max)).sum())
    below_band = int((region_mask & (residual < -line_eps) & (depth <= low_depth_max)).sum())
    above_band = int((region_mask & (residual > line_eps) & (depth <= low_depth_max)).sum())
    return {
        "line_below_count": below,
        "line_on_count": on,
        "below_over_on_ratio": below_over_on,
        "contam_over_total_ratio": ratio,
        "contam_gc_start": float(gc_start),
        "low_depth_region_count": int(((gc >= gc_start) & (depth <= low_depth_max)).sum()),
        "diagnostic_on_band_count": on_band,
        "diagnostic_below_band_count": below_band,
        "diagnostic_above_band_count": above_band,
    }


def plot_gc_depth(
    gc: np.ndarray,
    depth: np.ndarray,
    out_png: Path,
    ridge: RidgeResult,
    ridge_profile: dict[str, np.ndarray],
    fit: FitResult,
    low_depth_max: float,
    line_eps: float,
    plot_depth_max: float | None,
    title: str,
) -> None:
    """输出密度图 + 直线可视化。"""
    out_png.parent.mkdir(parents=True, exist_ok=True)

    y_max = float(np.percentile(depth, 99.5)) if plot_depth_max is None else float(plot_depth_max)
    y_max = max(y_max, low_depth_max + 5)

    cmap = LinearSegmentedColormap.from_list(
        "gray_to_red",
        ["#d9d9d9", "#bdbdbd", "#fb9a99", "#e31a1c", "#99000d"],
        N=256,
    )

    fig, ax = plt.subplots(figsize=(10, 7), dpi=150)
    hb = ax.hexbin(
        gc,
        depth,
        gridsize=220,
        extent=(20, 95, 0, y_max),
        bins="log",
        mincnt=1,
        cmap=cmap,
    )
    cbar = fig.colorbar(hb, ax=ax)
    cbar.set_label("log10(point count)")

    ax.axhline(low_depth_max, color="#3182bd", linestyle="--", linewidth=1.2, label=f"depth <= {low_depth_max:g}")

    if ridge.exists:
        ridge_gc = ridge_profile["gc_centers"]
        ridge_depths = ridge_profile["ridge_depths"]
        valid = np.isfinite(ridge_depths)
        if np.any(valid):
            ax.plot(
                ridge_gc[valid],
                ridge_depths[valid],
                color="#ff8c00",
                linewidth=2.0,
                alpha=0.95,
                label="main ridge",
            )

    if fit.exists and (fit.slope is not None) and (fit.intercept is not None):
        gc_start = ridge_profile.get("contam_gc_start", 20.0)
        xs = np.linspace(gc_start, 95, 240)
        ys = np.minimum(fit.slope * xs + fit.intercept, low_depth_max)
        ys = np.maximum(ys, 0.0)
        ax.plot(xs, ys, color="#006d2c", linewidth=2.2, label=f"contam top: y={fit.slope:.4f}x+{fit.intercept:.3f}")
        ax.plot(xs, np.minimum(ys + line_eps, low_depth_max), color="#238b45", linewidth=1.0, alpha=0.6)
        ax.plot(xs, np.maximum(ys - line_eps, 0.0), color="#238b45", linewidth=1.0, alpha=0.6, label=f"boundary band (+/-{line_eps:g})")
        ax.axvline(gc_start, color="#31a354", linestyle=":", linewidth=1.2, alpha=0.9, label=f"contam GC start {gc_start:.1f}")

    ax.set_xlim(20, 95)
    ax.set_ylim(0, y_max)
    ax.set_xlabel("GC (%)")
    ax.set_ylabel("Sequencing depth")
    ax.set_title(title)
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GC-Depth 低深度线性分割与重度污染判定")
    parser.add_argument("--pos", required=True, help="输入 .pos 文件路径")
    parser.add_argument("--out-json", default=None, help="输出 JSON 路径（默认: outputs/gc_line/<样本名>.gc_line.json）")
    parser.add_argument("--out-png", default=None, help="输出 PNG 路径（默认: outputs/gc_line/<样本名>.gc_line.png）")

    parser.add_argument("--low-depth-max", type=float, default=12.0, help="搜索分割线时使用的低深度上限")
    parser.add_argument("--line-eps", type=float, default=0.4, help="定义“在线上”的容忍带宽")
    parser.add_argument("--heavy-threshold", type=float, default=0.07, help="重度污染阈值: below/on > threshold")

    parser.add_argument("--slope-min", type=float, default=-0.5)
    parser.add_argument("--slope-max", type=float, default=0.5)
    parser.add_argument("--slope-steps", type=int, default=401)

    parser.add_argument("--residual-bins", type=int, default=240)
    parser.add_argument("--smooth-sigma", type=float, default=2.0)
    parser.add_argument("--peak-min-gap-bins", type=int, default=20)
    parser.add_argument("--min-separation", type=float, default=0.35)
    parser.add_argument("--min-balance", type=float, default=0.10)
    parser.add_argument("--gc-grid", type=float, default=0.5, help="低深度点云量化的 GC 步长")
    parser.add_argument("--depth-grid", type=float, default=0.2, help="低深度点云量化的 depth 步长")

    parser.add_argument("--plot-depth-max", type=float, default=None, help="绘图 y 轴上限；默认自动取 depth 99.5 分位")
    return parser.parse_args()


def run_gc_depth_line(
    pos_path: str | Path,
    out_json: str | Path | None = None,
    out_png: str | Path | None = None,
    low_depth_max: float = 12.0,
    line_eps: float = 0.4,
    heavy_threshold: float = 0.07,
    slope_min: float = -0.5,
    slope_max: float = 0.5,
    slope_steps: int = 401,
    residual_bins: int = 240,
    smooth_sigma: float = 2.0,
    peak_min_gap_bins: int = 20,
    min_separation: float = 0.35,
    min_balance: float = 0.10,
    gc_grid: float = 0.5,
    depth_grid: float = 0.2,
    plot_depth_max: float | None = None,
) -> dict:
    pos_path = Path(pos_path).expanduser().resolve()
    if not pos_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {pos_path}")

    default_out_dir = (Path.cwd() / "outputs" / "gc_line").resolve()
    out_json_path = (
        Path(out_json).expanduser().resolve()
        if out_json
        else default_out_dir / f"{pos_path.stem}.gc_line.json"
    )
    out_png_path = (
        Path(out_png).expanduser().resolve()
        if out_png
        else default_out_dir / f"{pos_path.stem}.gc_line.png"
    )

    gc, depth = load_gc_depth(pos_path)
    if gc.size == 0:
        raise ValueError("输入数据为空或清洗后无有效点")

    ridge, ridge_profile = estimate_main_ridge(
        gc=gc,
        depth=depth,
        low_depth_max=low_depth_max,
        gc_grid=gc_grid,
        ridge_sigma=smooth_sigma,
    )

    fit = find_contamination_region(
        gc=gc,
        depth=depth,
        ridge=ridge,
        ridge_profile=ridge_profile,
        low_depth_max=low_depth_max,
        side_eps=line_eps,
        gc_grid=gc_grid,
    )

    stats = None
    heavy = False
    if fit.exists and (fit.slope is not None) and (fit.intercept is not None):
        gc_start = float(ridge_profile.get("contam_gc_start", ridge.peak_gc or 20.0))
        stats = compute_global_stats(
            gc,
            depth,
            fit.slope,
            fit.intercept,
            gc_start=gc_start,
            line_eps=line_eps,
            low_depth_max=low_depth_max,
        )
        heavy = bool(stats["contam_over_total_ratio"] > heavy_threshold)

    result = {
        "input": {
            "pos_path": str(pos_path),
            "total_points_after_clean": int(gc.size),
        },
        "params": {
            "low_depth_max": low_depth_max,
            "line_eps": line_eps,
            "heavy_threshold": heavy_threshold,
            "slope_min": slope_min,
            "slope_max": slope_max,
            "slope_steps": slope_steps,
            "residual_bins": residual_bins,
            "smooth_sigma": smooth_sigma,
            "peak_min_gap_bins": peak_min_gap_bins,
            "min_separation": min_separation,
            "min_balance": min_balance,
            "gc_grid": gc_grid,
            "depth_grid": depth_grid,
        },
        "ridge": asdict(ridge),
        "fit": asdict(fit),
        "global_stats": stats,
        "decision": {
            "heavy_contamination": heavy,
            "reason": (
                "未找到满足右下污染区条件的边界线"
                if not fit.exists
                else (
                    f"contam/total={stats['contam_over_total_ratio']:.4f} > {heavy_threshold}"
                    if heavy
                    else f"contam/total={stats['contam_over_total_ratio']:.4f} <= {heavy_threshold}"
                )
            ),
        },
        "artifacts": {
            "json": str(out_json_path),
            "png": str(out_png_path),
        },
    }

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    plot_title = f"GC-Depth Split Detection | {'Heavy' if heavy else 'Not Heavy'}"
    plot_gc_depth(
        gc=gc,
        depth=depth,
        out_png=out_png_path,
        ridge=ridge,
        ridge_profile=ridge_profile,
        fit=fit,
        low_depth_max=low_depth_max,
        line_eps=line_eps,
        plot_depth_max=plot_depth_max,
        title=plot_title,
    )

    return result


def main_cli() -> None:
    args = parse_args()
    result = run_gc_depth_line(
        pos_path=args.pos,
        out_json=args.out_json,
        out_png=args.out_png,
        low_depth_max=args.low_depth_max,
        line_eps=args.line_eps,
        heavy_threshold=args.heavy_threshold,
        slope_min=args.slope_min,
        slope_max=args.slope_max,
        slope_steps=args.slope_steps,
        residual_bins=args.residual_bins,
        smooth_sigma=args.smooth_sigma,
        peak_min_gap_bins=args.peak_min_gap_bins,
        min_separation=args.min_separation,
        min_balance=args.min_balance,
        gc_grid=args.gc_grid,
        depth_grid=args.depth_grid,
        plot_depth_max=args.plot_depth_max,
    )
    _print_summary(result)


def _print_summary(result: dict) -> None:
    print(f"[OK] JSON: {result['artifacts']['json']}")
    print(f"[OK] PNG : {result['artifacts']['png']}")
    fit = result.get("fit", {})
    stats = result.get("global_stats")
    if fit.get("exists"):
        print(f"[FIT] y = {fit['slope']:.6f} * GC + {fit['intercept']:.6f}")
    else:
        print("[FIT] 未检出可用污染边界线")
    if stats:
        print(
            f"[STAT] contam={stats['line_below_count']} total={stats['line_below_count'] + stats['line_on_count']} "
            f"contam/total={stats['contam_over_total_ratio']:.6f} below/on={stats['below_over_on_ratio']:.6f}"
        )
        print(f"[DECISION] heavy_contamination={result['decision']['heavy_contamination']}")


def main() -> None:
    # 只需要修改样本目录（适配 VSCode 直接运行）
    sample_dir = "data/to_zhurui_surey_jinxianlan/FDSW260016098-2r_DaYuanYe叶-1"
    paths = resolve_gc_input_file(sample_dir)
    print("自动定位输入文件:")
    print(f"  .pos: {paths['pos_path']}")
    result = run_gc_depth_line(pos_path=paths["pos_path"])
    _print_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 兼容两种运行方式：
    # 1) 直接运行（无参数）=> VSCode 单样本调试模式
    # 2) 带参数运行（如 --pos）=> CLI 模式
    if len(sys.argv) > 1:
        main_cli()
    else:
        main()
