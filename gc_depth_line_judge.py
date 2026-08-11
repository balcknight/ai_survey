#!/usr/bin/env python3
"""
GC-Depth 线性分割判定脚本（端点参数化 + LLM 视觉复核）

输入: .pos 文件（第3列GC，第4列Depth）
输出:
1) JSON 结果（线参数、计数、比值、判定、LLM 复核摘要）
2) PNG 可视化（密度图 + 污染带上边界线）
3) LLM 复核调试日志 <stem>.gc_line.llm_log.json（仅 LLM 实际运行时）

第一遍（确定性算法）:
- 估计主脊线；在“主脊线显著高于蓝虚线”的 GC 区间内寻找低深度富集 run，得到 gc_start；
- 端点参数化网格搜索边界线：dL/dR ∈ [depth_floor, low_depth_max]、dL<=dR，
  取满足覆盖率(区域低深度点中位于线下的比例)>=min_coverage 的最低线。
- 判定口径不变: 污染点 = gc>=gc_start 且 depth<=low_depth_max 且 depth<=线值；
  contam_over_total_ratio > heavy_threshold(0.07) 判重度污染。

第二遍（可选，默认开启）: 多模态 VL 模型看图复核/调参，见 gc_llm_adjust.py。
LLM 不可用或输出非法时自动降级为第一遍结果。
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

G1_GC = 95.0  # 边界线评估区间右端点


@dataclass
class RidgeResult:
    exists: bool
    gc_min: float | None
    gc_max: float | None
    peak_gc: float | None
    peak_depth: float | None
    points_used: int


@dataclass
class LineCandidate:
    exists: bool
    gc_start: float | None
    gc_end: float | None
    d_left: float | None
    d_right: float | None
    slope: float | None
    intercept: float | None
    coverage: float | None
    low_points_in_region: int
    low_depth_points: int


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


def detect_gc_start(
    gc: np.ndarray,
    depth: np.ndarray,
    ridge: RidgeResult,
    ridge_profile: dict[str, np.ndarray],
    *,
    low_depth_max: float = 12.0,
    gc_grid: float = 0.5,
    min_low_points: int = 100,
    ridge_margin: float = 5.0,
    rise_delta: float = 0.15,
    abs_threshold: float = 0.15,
    min_run_bins: int = 3,
) -> tuple[tuple[float, float] | None, int]:
    """污染带上边界 GC 起点检测。

    思路：污染表现为主脊线右侧 low_ratio 陡升。
    - 先用“高脊掩码”排除主云低/高 GC 尾（那里主脊沉入低深度区，低深度点属于主物种）；
    - 在高脊内找 low_ratio 谷底 → 视为主云中心 valley_gc；
    - 阈值 = max(valley_ratio + rise_delta, abs_threshold)；
    - 从 valley_gc 向右首次进入阈值的连续 run 起点作为 gc_start，向右扩展到 run 尾（右端加半阈值容差）。
    """
    low_mask = depth <= low_depth_max
    low_depth_points = int(low_mask.sum())
    if (not ridge.exists) or low_depth_points < min_low_points:
        return None, low_depth_points

    gc_centers = ridge_profile["gc_centers"]
    counts = ridge_profile["counts"]
    low_counts = ridge_profile["low_counts"]
    low_ratios = ridge_profile["low_ratios"]
    ridge_depths = ridge_profile["ridge_depths"]

    high_ridge = np.isfinite(ridge_depths) & (ridge_depths >= low_depth_max + ridge_margin)
    valid_bin = high_ridge & (counts >= 40)
    valid_idx = np.where(valid_bin)[0]
    if valid_idx.size < min_run_bins:
        return None, low_depth_points

    # 主云中心：high_ridge 内 low_ratio 谷底
    valley_pos = int(np.argmin(low_ratios[valid_idx]))
    valley_i = int(valid_idx[valley_pos])
    valley_ratio = float(low_ratios[valley_i])

    threshold = max(valley_ratio + rise_delta, abs_threshold)
    half = threshold * 0.5

    # 从 valley 向右找连续 low_ratio >= threshold 的 run
    right_valid = valid_idx[valid_idx > valley_i]
    if right_valid.size == 0:
        return None, low_depth_points

    hit_mask = (low_ratios >= threshold) & valid_bin & (low_counts >= 20)
    hit_right = right_valid[hit_mask[right_valid]]
    if hit_right.size < min_run_bins:
        return None, low_depth_points

    # 取最靠左的一段连续 run
    diffs = np.diff(hit_right)
    breaks = np.where(diffs != 1)[0]
    if breaks.size == 0:
        run_idx = hit_right
    else:
        run_idx = hit_right[: breaks[0] + 1]
    if run_idx.size < min_run_bins:
        return None, low_depth_points

    # 右端以半阈值容差向右扩展（把污染带尾部略微稀释的箱并入）
    ext_mask = (low_ratios >= half) & valid_bin & (low_counts >= 20)
    lo, hi = int(run_idx[0]), int(run_idx[-1])
    while hi + 1 < len(gc_centers) and ext_mask[hi + 1]:
        hi += 1

    run_low = float(gc_centers[lo])
    run_high = float(gc_centers[hi])
    expanded = (gc >= run_low - gc_grid / 2) & (gc <= run_high + gc_grid / 2) & low_mask
    if expanded.sum() < 50:
        return None, low_depth_points

    ridge_profile["contam_gc_start"] = run_low
    ridge_profile["contam_gc_end"] = run_high
    ridge_profile["valley_gc"] = float(gc_centers[valley_i])
    ridge_profile["valley_low_ratio"] = valley_ratio
    ridge_profile["low_ratio_threshold"] = float(threshold)
    return (run_low, run_high), low_depth_points


def fit_contamination_line(
    gc: np.ndarray,
    depth: np.ndarray,
    gc_start: float | None,
    *,
    low_depth_max: float = 12.0,
    depth_floor: float = 2.0,
    depth_step: float = 0.5,
    min_coverage: float = 0.9,
    g1: float = G1_GC,
    min_region_points: int = 50,
    max_sample_points: int = 20000,
) -> LineCandidate:
    """端点参数化网格搜索：在 [depth_floor, low_depth_max]^2 上搜 (d_left, d_right)，
    取覆盖率 >= min_coverage 的最低线（d_left + d_right 最小）。"""
    low_depth_points = int((depth <= low_depth_max).sum())
    empty = LineCandidate(False, gc_start, None, None, None, None, None, None, 0, low_depth_points)
    if gc_start is None:
        return empty

    region = (gc >= gc_start) & (gc <= g1) & (depth <= low_depth_max) & (depth >= 0)
    gr, dr = gc[region], depth[region]
    empty.low_points_in_region = int(gr.size)
    if gr.size < min_region_points:
        return empty
    if gr.size > max_sample_points:
        rng = np.random.default_rng(0)  # 固定种子，保证确定性
        sel = rng.choice(gr.size, max_sample_points, replace=False)
        gr, dr = gr[sel], dr[sel]

    t = (gr - gc_start) / (g1 - gc_start)
    grid = np.arange(depth_floor, low_depth_max + depth_step / 2, depth_step)
    dL = grid[:, None, None]
    dR = grid[None, :, None]
    tt = t[None, None, :]
    line_vals = dL * (1.0 - tt) + dR * tt  # (N, N, M)
    cover = (dr[None, None, :] <= line_vals).mean(axis=2)  # (N, N)

    idx = np.arange(grid.size)
    order_ok = idx[:, None] <= idx[None, :]  # d_left <= d_right（非负斜率）
    valid = order_ok & (cover >= min_coverage)
    if not valid.any():
        empty.coverage = float(cover[order_ok].max()) if order_ok.any() else 0.0
        return empty

    key = np.where(valid, grid[:, None] + grid[None, :], np.inf)
    iL, iR = np.unravel_index(int(np.argmin(key)), key.shape)
    d_left = float(grid[iL])
    d_right = float(grid[iR])
    slope = (d_right - d_left) / (g1 - gc_start)
    intercept = d_left - slope * gc_start
    return LineCandidate(
        True,
        gc_start,
        None,
        d_left,
        d_right,
        float(slope),
        float(intercept),
        float(cover[iL, iR]),
        int(gr.size),
        low_depth_points,
    )


def compute_global_stats(
    gc: np.ndarray,
    depth: np.ndarray,
    slope: float,
    intercept: float,
    gc_start: float,
    line_eps: float,
    low_depth_max: float,
) -> dict:
    """按右下污染区统计点数与占比（判定口径不变）。"""
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


def _draw_line(ax, line: LineCandidate, low_depth_max: float, line_eps: float, *, color: str, style: str, label: str) -> None:
    xs = np.linspace(line.gc_start, G1_GC, 240)
    ys = np.minimum(line.slope * xs + line.intercept, low_depth_max)
    ys = np.maximum(ys, 0.0)
    ax.plot(xs, ys, color=color, linestyle=style, linewidth=2.0, label=label)
    if style == "-":
        ax.plot(xs, np.minimum(ys + line_eps, low_depth_max), color=color, linewidth=1.0, alpha=0.6)
        ax.plot(xs, np.maximum(ys - line_eps, 0.0), color=color, linewidth=1.0, alpha=0.6, label=f"boundary band (+/-{line_eps:g})")
        ax.axvline(line.gc_start, color=color, linestyle=":", linewidth=1.2, alpha=0.9, label=f"contam GC start {line.gc_start:.1f}")


def plot_gc_depth(
    gc: np.ndarray,
    depth: np.ndarray,
    out_png: Path,
    ridge: RidgeResult,
    ridge_profile: dict[str, np.ndarray],
    line: LineCandidate | None,
    low_depth_max: float,
    line_eps: float,
    plot_depth_max: float | None,
    title: str,
    prev_line: LineCandidate | None = None,
) -> None:
    """输出密度图 + 直线可视化。prev_line 非空时以灰虚线画出算法第一遍线作对照。"""
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

    if prev_line is not None and prev_line.exists:
        _draw_line(
            ax, prev_line, low_depth_max, line_eps,
            color="#999999", style="--",
            label=f"algo first line: dL={prev_line.d_left:.1f} dR={prev_line.d_right:.1f}",
        )

    if line is not None and line.exists:
        _draw_line(
            ax, line, low_depth_max, line_eps,
            color="#006d2c", style="-",
            label=f"contam top: dL={line.d_left:.1f} dR={line.d_right:.1f} (y={line.slope:.4f}x+{line.intercept:.3f})",
        )

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
    parser = argparse.ArgumentParser(description="GC-Depth 低深度线性分割与重度污染判定（端点参数化 + LLM 视觉复核）")
    parser.add_argument("--pos", required=True, help="输入 .pos 文件路径")
    parser.add_argument("--out-json", default=None, help="输出 JSON 路径（默认: outputs/gc_line/<样本名>.gc_line.json）")
    parser.add_argument("--out-png", default=None, help="输出 PNG 路径（默认: outputs/gc_line/<样本名>.gc_line.png）")

    parser.add_argument("--low-depth-max", type=float, default=12.0, help="低深度搜索区上限（蓝虚线）")
    parser.add_argument("--line-eps", type=float, default=0.4, help="诊断带宽阈值（仅诊断统计与绘图）")
    parser.add_argument("--heavy-threshold", type=float, default=0.07, help="重度污染阈值: contam/total > threshold")
    parser.add_argument("--min-coverage", type=float, default=0.9, help="边界线覆盖率下限（区域低深度点位于线下的比例）")
    parser.add_argument("--depth-floor", type=float, default=2.0, help="端点深度下限（避开 depth≈0 伪迹）")
    parser.add_argument("--depth-step", type=float, default=0.5, help="端点深度网格步长")
    parser.add_argument("--gc-grid", type=float, default=0.5, help="GC 分箱步长")
    parser.add_argument("--smooth-sigma", type=float, default=2.0, help="主脊线平滑强度")
    parser.add_argument("--no-llm", action="store_true", help="关闭 LLM 视觉复核（默认开启）")
    parser.add_argument("--llm-rounds", type=int, default=2, help="LLM 复核最大轮数")
    parser.add_argument("--llm-timeout", type=float, default=60.0, help="单轮 LLM 调用超时秒数")
    parser.add_argument("--plot-depth-max", type=float, default=None, help="绘图 y 轴上限；默认自动取 depth 99.5 分位")
    return parser.parse_args()


def run_gc_depth_line(
    pos_path: str | Path,
    out_json: str | Path | None = None,
    out_png: str | Path | None = None,
    *,
    low_depth_max: float = 12.0,
    line_eps: float = 0.4,
    heavy_threshold: float = 0.07,
    min_coverage: float = 0.9,
    depth_floor: float = 2.0,
    depth_step: float = 0.5,
    gc_grid: float = 0.5,
    smooth_sigma: float = 2.0,
    plot_depth_max: float | None = None,
    llm_adjust: bool = True,
    llm_max_rounds: int = 2,
    llm_timeout_sec: float = 60.0,
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

    run_range, low_depth_points = detect_gc_start(
        gc, depth, ridge, ridge_profile,
        low_depth_max=low_depth_max,
        gc_grid=gc_grid,
    )
    gc_start = run_range[0] if run_range else None

    algo_line = fit_contamination_line(
        gc, depth, gc_start,
        low_depth_max=low_depth_max,
        depth_floor=depth_floor,
        depth_step=depth_step,
        min_coverage=min_coverage,
    )
    if run_range:
        algo_line.gc_end = run_range[1]

    def compute_stats(g0: float, slope: float, intercept: float) -> dict:
        return compute_global_stats(
            gc, depth, slope, intercept,
            gc_start=g0, line_eps=line_eps, low_depth_max=low_depth_max,
        )

    stats = compute_stats(algo_line.gc_start, algo_line.slope, algo_line.intercept) if algo_line.exists else None
    heavy = bool(stats["contam_over_total_ratio"] > heavy_threshold) if stats else False

    def render(line_obj: LineCandidate | None, prev: LineCandidate | None = None, suffix: str = "") -> None:
        plot_gc_depth(
            gc, depth, out_png_path, ridge, ridge_profile, line_obj,
            low_depth_max=low_depth_max, line_eps=line_eps,
            plot_depth_max=plot_depth_max,
            title=f"GC-Depth Split Detection | {'Heavy' if heavy else 'Not Heavy'}{suffix}",
            prev_line=prev,
        )

    render(algo_line)

    # ---- 第二遍：LLM 视觉复核（默认开启，任何异常降级为第一遍结果） ----
    llm_summary: dict
    final_line = algo_line
    final_stats = stats
    if not llm_adjust:
        llm_summary = {"enabled": False, "status": "disabled", "rounds": 0, "final_action": "none", "log_path": None}
    elif not (ridge.exists and low_depth_points >= 100):
        llm_summary = {"enabled": True, "status": "skipped_no_signal", "rounds": 0, "final_action": "none", "log_path": None}
    else:
        try:
            import gc_llm_adjust

            algo_params = (
                {
                    "gc_start": algo_line.gc_start,
                    "d_left": algo_line.d_left,
                    "d_right": algo_line.d_right,
                    "slope": algo_line.slope,
                    "intercept": algo_line.intercept,
                }
                if algo_line.exists
                else None
            )
            log_path = out_json_path.parent / (out_json_path.stem + ".llm_log.json")

            def llm_render(params: dict) -> None:
                line_obj = LineCandidate(
                    True, params["gc_start"], None, params["d_left"], params["d_right"],
                    params["slope"], params["intercept"], None, 0, low_depth_points,
                )
                render(line_obj, suffix=" | LLM adjusting")

            outcome = gc_llm_adjust.review_and_adjust(
                algo_params=algo_params,
                algo_stats=stats,
                png_path=out_png_path,
                log_path=log_path,
                render_png=llm_render,
                compute_stats=compute_stats,
                heavy_threshold=heavy_threshold,
                depth_floor=depth_floor,
                low_depth_max=low_depth_max,
                max_rounds=llm_max_rounds,
                timeout_sec=llm_timeout_sec,
                pos_path=str(pos_path),
            )
            llm_summary = outcome.summary()
            if outcome.final_action == "no_contamination":
                final_line = LineCandidate(
                    False, None, None, None, None, None, None, None,
                    algo_line.low_points_in_region, low_depth_points,
                )
                final_stats = None
            elif outcome.final_action == "adjust" and outcome.final_params:
                p = outcome.final_params
                final_line = LineCandidate(
                    True, p["gc_start"],
                    algo_line.gc_end if algo_line.exists else None,
                    p["d_left"], p["d_right"], p["slope"], p["intercept"],
                    algo_line.coverage if algo_line.exists else None,
                    algo_line.low_points_in_region, low_depth_points,
                )
                final_stats = compute_stats(p["gc_start"], p["slope"], p["intercept"])
        except Exception as exc:  # 导入失败/任何意外 → 降级
            llm_summary = {
                "enabled": True,
                "status": "degraded_error",
                "rounds": 0,
                "final_action": "none",
                "log_path": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

    heavy = bool(final_stats["contam_over_total_ratio"] > heavy_threshold) if final_stats else False
    adjusted = llm_summary.get("final_action") in {"adjust", "no_contamination"} and llm_summary.get("status", "").startswith("ok")
    render(final_line, prev=algo_line if (adjusted and algo_line.exists and final_line.exists) else None)

    # ---- 判定理由 ----
    if final_line.exists and final_stats is not None:
        reason = (
            f"contam/total={final_stats['contam_over_total_ratio']:.4f} > {heavy_threshold}"
            if heavy
            else f"contam/total={final_stats['contam_over_total_ratio']:.4f} <= {heavy_threshold}"
        )
    else:
        reason = "未找到满足右下污染区条件的边界线"
    llm_status = llm_summary.get("status")
    if llm_status == "ok_no_contamination":
        algo_ratio = (stats or {}).get("contam_over_total_ratio")
        if algo_line.exists and algo_ratio is not None:
            reason += f"；LLM复核: 判定无污染带（算法第一遍 ratio={algo_ratio:.4f}）"
        else:
            reason = "LLM视觉复核判定无右下污染带"
    elif llm_status == "ok_adjusted":
        reason += f"；LLM复核: 调整边界线（{llm_summary.get('rounds', 0)}轮）"
    elif llm_status in {"degraded_json", "degraded_error", "degraded_import"}:
        reason += f"；LLM复核降级({llm_status}): {llm_summary.get('error', '')}"

    result = {
        "input": {
            "pos_path": str(pos_path),
            "total_points_after_clean": int(gc.size),
        },
        "params": {
            "low_depth_max": low_depth_max,
            "line_eps": line_eps,
            "heavy_threshold": heavy_threshold,
            "min_coverage": min_coverage,
            "depth_floor": depth_floor,
            "depth_step": depth_step,
            "gc_grid": gc_grid,
            "smooth_sigma": smooth_sigma,
            "llm_adjust": llm_adjust,
            "llm_max_rounds": llm_max_rounds,
            "llm_timeout_sec": llm_timeout_sec,
        },
        "ridge": asdict(ridge),
        "fit": asdict(final_line),
        "global_stats": final_stats,
        "decision": {
            "heavy_contamination": heavy,
            "reason": reason,
        },
        "llm_adjustment": llm_summary,
        "artifacts": {
            "json": str(out_json_path),
            "png": str(out_png_path),
        },
    }

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

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
        min_coverage=args.min_coverage,
        depth_floor=args.depth_floor,
        depth_step=args.depth_step,
        gc_grid=args.gc_grid,
        smooth_sigma=args.smooth_sigma,
        plot_depth_max=args.plot_depth_max,
        llm_adjust=not args.no_llm,
        llm_max_rounds=args.llm_rounds,
        llm_timeout_sec=args.llm_timeout,
    )
    _print_summary(result)


def _print_summary(result: dict) -> None:
    print(f"[OK] JSON: {result['artifacts']['json']}")
    print(f"[OK] PNG : {result['artifacts']['png']}")
    fit = result.get("fit", {})
    stats = result.get("global_stats")
    if fit.get("exists"):
        print(
            f"[FIT] g0={fit['gc_start']:.1f} dL={fit['d_left']:.2f} dR={fit['d_right']:.2f} "
            f"coverage={fit.get('coverage') or 0:.3f} -> y={fit['slope']:.6f}*GC+{fit['intercept']:.6f}"
        )
    else:
        print("[FIT] 未检出可用污染边界线")
    llm = result.get("llm_adjustment", {})
    print(f"[LLM] status={llm.get('status')} rounds={llm.get('rounds', 0)} action={llm.get('final_action')} log={llm.get('log_path')}")
    if stats:
        print(
            f"[STAT] contam={stats['line_below_count']} total={stats['line_below_count'] + stats['line_on_count']} "
            f"contam/total={stats['contam_over_total_ratio']:.6f} below/on={stats['below_over_on_ratio']:.6f}"
        )
        print(f"[DECISION] heavy_contamination={result['decision']['heavy_contamination']}")
    else:
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
