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


def find_split_line(
    gc: np.ndarray,
    depth: np.ndarray,
    low_depth_max: float = 10.0,
    slope_min: float = -0.5,
    slope_max: float = 0.5,
    slope_steps: int = 401,
    residual_bins: int = 240,
    smooth_sigma: float = 2.0,
    peak_min_gap_bins: int = 20,
    min_separation: float = 0.35,
    min_balance: float = 0.10,
    side_eps: float = 0.4,
    gc_grid: float = 0.5,
    depth_grid: float = 0.2,
) -> FitResult:
    """
    在 depth<=low_depth_max 区域搜索“可大致分开两团密度”的直线。

    核心思想：
    1. 扫描斜率 m
    2. 对每个 m，观察残差 r = depth - m*gc 的密度是否呈双峰
    3. 若双峰明显，则谷值对应截距 b
    4. 用峰谷分离度 + 两侧平衡度筛选最佳线
    """
    low_mask = depth <= low_depth_max
    if low_mask.sum() < 100:
        return FitResult(False, None, None, None, None, None, int(low_mask.sum()))

    x_low = gc[low_mask]
    y_low = depth[low_mask]
    xw, yw, w = quantize_points(x_low, y_low, gc_grid=gc_grid, depth_grid=depth_grid)

    candidates: list[tuple[float, float, float, float, float]] = []  # score, m, b, sep, balance

    for m in np.linspace(slope_min, slope_max, slope_steps):
        r = yw - m * xw
        lo, hi = np.percentile(r, [1, 99])
        if hi - lo < 1e-6:
            continue

        edges = np.linspace(lo, hi, residual_bins + 1)
        hist, _ = np.histogram(r, bins=edges, weights=w)
        hs = gaussian_smooth_1d(hist.astype(float), sigma=smooth_sigma)

        peaks = np.where((hs[1:-1] > hs[:-2]) & (hs[1:-1] > hs[2:]))[0] + 1
        if peaks.size < 2:
            continue

        # 选出最强的若干峰，再找一个间距足够大的峰对。
        top_peaks = sorted(peaks.tolist(), key=lambda i: hs[i], reverse=True)[:10]
        chosen_pair: tuple[int, int] | None = None
        for i in range(len(top_peaks)):
            for j in range(i + 1, len(top_peaks)):
                p1, p2 = sorted([top_peaks[i], top_peaks[j]])
                if (p2 - p1) >= peak_min_gap_bins:
                    chosen_pair = (p1, p2)
                    break
            if chosen_pair is not None:
                break

        if chosen_pair is None:
            continue

        p1, p2 = chosen_pair
        valley = p1 + int(np.argmin(hs[p1 : p2 + 1]))
        v = hs[valley]

        sep = (hs[p1] + hs[p2] - 2 * v) / (hs[p1] + hs[p2] + 1e-12)
        if sep < min_separation:
            continue

        b = 0.5 * (edges[valley] + edges[valley + 1])
        side = yw - (m * xw + b)
        below = w[side < -side_eps].sum()
        above = w[side > side_eps].sum()
        if (below + above) <= 0:
            continue

        balance = min(below, above) / (below + above)
        if balance < min_balance:
            continue

        score = float(sep * balance)
        candidates.append((score, float(m), float(b), float(sep), float(balance)))

    if not candidates:
        return FitResult(False, None, None, None, None, None, int(low_mask.sum()))

    # 自动搜索：直接选择分离分数最优的候选线。
    score, m, b, sep, balance = max(candidates, key=lambda c: c[0])
    return FitResult(True, m, b, sep, balance, score, int(low_mask.sum()))


def compute_global_stats(
    gc: np.ndarray,
    depth: np.ndarray,
    slope: float,
    intercept: float,
    line_eps: float,
) -> dict:
    """在全局点云上统计直线两侧数量与比值。"""
    residual = depth - (slope * gc + intercept)
    # 业务口径：below 为整条线以下所有点；on 为斜线及其以上所有点（与 below 对称）。
    below = int((residual < 0).sum())
    on = int((residual >= 0).sum())
    ratio = float(below / max(on, 1))

    # 保留窄带统计用于诊断（不参与最终判定）。
    on_band = int((np.abs(residual) <= line_eps).sum())
    below_band = int((residual < -line_eps).sum())
    above_band = int((residual > line_eps).sum())
    return {
        "line_below_count": below,
        "line_on_count": on,
        "below_over_on_ratio": ratio,
        "diagnostic_on_band_count": on_band,
        "diagnostic_below_band_count": below_band,
        "diagnostic_above_band_count": above_band,
    }


def plot_gc_depth(
    gc: np.ndarray,
    depth: np.ndarray,
    out_png: Path,
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

    if fit.exists and (fit.slope is not None) and (fit.intercept is not None):
        xs = np.linspace(20, 95, 300)
        ys = fit.slope * xs + fit.intercept
        ax.plot(xs, ys, color="#006d2c", linewidth=2.2, label=f"split line: y={fit.slope:.4f}x+{fit.intercept:.3f}")
        ax.plot(xs, ys + line_eps, color="#238b45", linewidth=1.0, alpha=0.6)
        ax.plot(xs, ys - line_eps, color="#238b45", linewidth=1.0, alpha=0.6, label=f"on-line band (+/-{line_eps:g})")

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
    parser.add_argument("--heavy-threshold", type=float, default=0.25, help="重度污染阈值: below/on > threshold")

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


def main() -> None:
    args = parse_args()
    pos_path = Path(args.pos).expanduser().resolve()
    if not pos_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {pos_path}")

    default_out_dir = (Path.cwd() / "outputs" / "gc_line").resolve()
    out_json = (
        Path(args.out_json).expanduser().resolve()
        if args.out_json
        else default_out_dir / f"{pos_path.stem}.gc_line.json"
    )
    out_png = (
        Path(args.out_png).expanduser().resolve()
        if args.out_png
        else default_out_dir / f"{pos_path.stem}.gc_line.png"
    )

    gc, depth = load_gc_depth(pos_path)
    if gc.size == 0:
        raise ValueError("输入数据为空或清洗后无有效点")

    fit = find_split_line(
        gc=gc,
        depth=depth,
        low_depth_max=args.low_depth_max,
        slope_min=args.slope_min,
        slope_max=args.slope_max,
        slope_steps=args.slope_steps,
        residual_bins=args.residual_bins,
        smooth_sigma=args.smooth_sigma,
        peak_min_gap_bins=args.peak_min_gap_bins,
        min_separation=args.min_separation,
        min_balance=args.min_balance,
        side_eps=args.line_eps,
        gc_grid=args.gc_grid,
        depth_grid=args.depth_grid,
    )

    stats = None
    heavy = False
    if fit.exists and (fit.slope is not None) and (fit.intercept is not None):
        stats = compute_global_stats(gc, depth, fit.slope, fit.intercept, line_eps=args.line_eps)
        heavy = bool(stats["below_over_on_ratio"] > args.heavy_threshold)

    result = {
        "input": {
            "pos_path": str(pos_path),
            "total_points_after_clean": int(gc.size),
        },
        "params": {
            "low_depth_max": args.low_depth_max,
            "line_eps": args.line_eps,
            "heavy_threshold": args.heavy_threshold,
            "slope_min": args.slope_min,
            "slope_max": args.slope_max,
            "slope_steps": args.slope_steps,
            "residual_bins": args.residual_bins,
            "smooth_sigma": args.smooth_sigma,
            "peak_min_gap_bins": args.peak_min_gap_bins,
            "min_separation": args.min_separation,
            "min_balance": args.min_balance,
            "gc_grid": args.gc_grid,
            "depth_grid": args.depth_grid,
        },
        "fit": asdict(fit),
        "global_stats": stats,
        "decision": {
            "heavy_contamination": heavy,
            "reason": (
                "未找到满足双峰分割条件的直线"
                if not fit.exists
                else (
                    f"below/on={stats['below_over_on_ratio']:.4f} > {args.heavy_threshold}"
                    if heavy
                    else f"below/on={stats['below_over_on_ratio']:.4f} <= {args.heavy_threshold}"
                )
            ),
        },
        "artifacts": {
            "json": str(out_json),
            "png": str(out_png),
        },
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    plot_title = f"GC-Depth Split Detection | {'Heavy' if heavy else 'Not Heavy'}"
    plot_gc_depth(
        gc=gc,
        depth=depth,
        out_png=out_png,
        fit=fit,
        low_depth_max=args.low_depth_max,
        line_eps=args.line_eps,
        plot_depth_max=args.plot_depth_max,
        title=plot_title,
    )

    print(f"[OK] JSON: {out_json}")
    print(f"[OK] PNG : {out_png}")
    if fit.exists:
        print(f"[FIT] y = {fit.slope:.6f} * GC + {fit.intercept:.6f}")
    else:
        print("[FIT] 未检出可用分割线")
    if stats:
        print(f"[STAT] below={stats['line_below_count']} on={stats['line_on_count']} ratio={stats['below_over_on_ratio']:.6f}")
        print(f"[DECISION] heavy_contamination={heavy}")


if __name__ == "__main__":
    main()
