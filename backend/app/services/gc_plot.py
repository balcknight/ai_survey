from __future__ import annotations

import hashlib
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GC_PLOT_ROOT = (PROJECT_ROOT / "data" / "gc_plots").resolve()


def _safe_name(text: str, fallback: str = "sample") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("._-")
    return cleaned or fallback


def _build_output_dir(sample_dir: str) -> Path:
    sample_path = Path(sample_dir).expanduser().resolve()
    digest = hashlib.sha1(str(sample_path).encode("utf-8")).hexdigest()[:16]
    sample_name = _safe_name(sample_path.name, fallback="sample")
    return GC_PLOT_ROOT / f"{sample_name}_{digest}"


def is_managed_gc_plot_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(GC_PLOT_ROOT)
        return True
    except Exception:
        return False


def build_gc_output_paths(sample_dir: str, pos_path: str | Path) -> dict[str, str]:
    pos_file = Path(pos_path).expanduser().resolve()
    sample_stem = pos_file.stem
    out_dir = _build_output_dir(sample_dir)
    return {
        "out_json": str(out_dir / f"{sample_stem}.gc_line.json"),
        "out_png": str(out_dir / f"{sample_stem}.gc_line.png"),
    }


def cleanup_gc_outputs(paths: list[str | None]) -> dict[str, int | list[str]]:
    deleted_files = 0
    ignored_paths: list[str] = []

    for raw in paths:
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if not is_managed_gc_plot_path(path):
            ignored_paths.append(str(path))
            continue
        if path.exists() and path.is_file():
            path.unlink()
            deleted_files += 1

    for parent in sorted({Path(p).expanduser().resolve().parent for p in paths if p}, key=lambda x: len(str(x)), reverse=True):
        if not is_managed_gc_plot_path(parent):
            continue
        try:
            parent.rmdir()
        except OSError:
            pass

    return {
        "deleted_files": deleted_files,
        "ignored_paths": ignored_paths,
    }


def collect_gc_cleanup_paths(gc_raw: dict | None) -> list[str | None]:
    """汇总 gc_raw 中所有应随样本删除清理的 GC 产物路径。

    包括终帧 png/json、演进步骤 png_steps[*].png、LLM 日志 log_path，
    并对受管目录内同 stem 的 *.step*.png 做 glob 兜底（覆盖重跑残留的孤儿文件）。
    """
    paths: list[str | None] = []
    if not isinstance(gc_raw, dict):
        return paths

    artifacts = gc_raw.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else None
    final_png = None
    if artifacts is not None:
        for key in ("png", "json"):
            value = artifacts.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value)
                if key == "png":
                    final_png = value
        for step in artifacts.get("png_steps") or []:
            png = step.get("png") if isinstance(step, dict) else None
            if isinstance(png, str) and png.strip():
                paths.append(png)

    llm = gc_raw.get("llm_adjustment")
    log_path = llm.get("log_path") if isinstance(llm, dict) else None
    if isinstance(log_path, str) and log_path.strip():
        paths.append(log_path)

    # 孤儿 step 文件兜底：重跑时 LLM 轮数变少可能残留旧 step png
    if final_png:
        final_path = Path(final_png).expanduser().resolve()
        if is_managed_gc_plot_path(final_path):
            paths.extend(str(p) for p in final_path.parent.glob(f"{final_path.stem}.step*.png"))

    return paths
