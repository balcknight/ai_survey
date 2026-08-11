#!/usr/bin/env python3
"""
GC-Depth 边界线 LLM 视觉复核（第二遍）。

第一遍由 gc_depth_line_judge 的确定性算法给出污染带上边界线（端点参数化），
本模块把渲染好的 PNG 发给多模态 VL 模型（qwen3-vl-plus），由其判断：
- no_contamination：图中右下没有可见污染带（覆盖算法结果，最终判正常）；
- no_adjustment：当前绿线已贴合污染带上沿，无需调整；
- adjust：给出新的 gc_start / d_left / d_right，程序 clamp 到可行域后重算并重画。

所有轮次的 prompt / 原始响应 / 提议值 / clamp 值 / 统计均写入
<stem>.gc_line.llm_log.json 便于人工 check。LLM 任何异常都降级为算法结果。
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

GC_VL_MODEL_NAME = "qwen3-vl-plus"
VALID_ACTIONS = {"no_contamination", "no_adjustment", "adjust"}
LOG_SCHEMA_VERSION = 1

RETRY_HINT = "\n\n【重要】上一次输出无法解析为要求的 JSON。请只输出一个 JSON 对象，不要包含任何其他文字。"


@dataclass
class LlmProposal:
    has_contamination: bool
    action: str
    gc_start: float | None
    d_left: float | None
    d_right: float | None
    reason: str


@dataclass
class LlmAdjustmentOutcome:
    status: str  # ok_no_contamination|ok_no_adjustment|ok_adjusted|degraded_json|degraded_error
    rounds: int
    final_action: str  # no_contamination|no_adjustment|adjust|none
    final_params: dict | None  # {gc_start,d_left,d_right,slope,intercept}；no_contamination/降级时为 None 或当前线
    log_path: str | None
    error: str | None = None
    rounds_detail: list[dict] = field(default_factory=list)  # 逐轮精简摘要（不含 prompt/raw_response）

    def summary(self) -> dict:
        out = {
            "enabled": True,
            "status": self.status,
            "rounds": self.rounds,
            "final_action": self.final_action,
            "log_path": self.log_path,
            "rounds_detail": self.rounds_detail,
        }
        if self.error:
            out["error"] = self.error
        return out


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "nan"}:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _extract_json(text: str) -> Any:
    """复刻 nt_judge._extract_json 的容错解析：剥 ```json 块 → 直接解析 → 正则取 {...}。"""
    raw = (text or "").strip()
    codeblock = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    if codeblock:
        raw = codeblock.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    obj_match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except Exception:
            pass
    raise ValueError(f"无法解析LLM JSON输出: {raw[:300]}")


def parse_llm_response(text: str, *, require_gc_start: bool = False) -> LlmProposal:
    """解析并校验 VL 模型输出；非法时抛 ValueError（由调用方重试/降级）。"""
    obj = _extract_json(text)
    if not isinstance(obj, dict):
        raise ValueError(f"LLM输出不是JSON对象: {str(obj)[:200]}")
    action = str(obj.get("action", "")).strip()
    if action not in VALID_ACTIONS:
        raise ValueError(f"非法action: {action!r}")
    has_contamination = bool(obj.get("has_contamination", action != "no_contamination"))
    gc_start = _to_float(obj.get("gc_start"))
    d_left = _to_float(obj.get("d_left"))
    d_right = _to_float(obj.get("d_right"))
    if action == "adjust":
        if d_left is None or d_right is None:
            raise ValueError("action=adjust 时 d_left/d_right 必须为有效数值")
        if require_gc_start and gc_start is None:
            raise ValueError("算法未检出线时 action=adjust 必须给出 gc_start")
    return LlmProposal(
        has_contamination=has_contamination,
        action=action,
        gc_start=gc_start,
        d_left=d_left,
        d_right=d_right,
        reason=str(obj.get("reason", ""))[:500],
    )


def clamp_line_params(
    *,
    gc_start: float,
    d_left: float,
    d_right: float,
    g1: float = 95.0,
    low_depth_max: float = 12.0,
    depth_floor: float = 2.0,
    gc_start_min: float = 20.0,
    gc_start_max: float = 90.0,
) -> dict:
    """把 LLM 提议值 clamp 进可行域：g0∈[20,90]、depth_floor≤dL≤dR≤L（非负斜率）。"""
    notes: list[str] = []
    g0 = float(min(max(gc_start, gc_start_min), gc_start_max))
    if g0 != float(gc_start):
        notes.append(f"gc_start {gc_start:.2f}→{g0:.2f}")
    dL = float(min(max(d_left, depth_floor), low_depth_max))
    if dL != float(d_left):
        notes.append(f"d_left {d_left:.2f}→{dL:.2f}")
    dR = float(min(max(d_right, depth_floor), low_depth_max))
    if dR != float(d_right):
        notes.append(f"d_right {d_right:.2f}→{dR:.2f}")
    if dR < dL:
        notes.append(f"d_right<d_left → d_right={dL:.2f}")
        dR = dL
    slope = (dR - dL) / (g1 - g0)
    intercept = dL - slope * g0
    return {
        "gc_start": g0,
        "d_left": dL,
        "d_right": dR,
        "slope": float(slope),
        "intercept": float(intercept),
        "clamped": bool(notes),
        "clamp_notes": notes,
    }


def _encode_png_base64(png_path: Path) -> str:
    return base64.b64encode(png_path.read_bytes()).decode("ascii")


def build_prompt(
    *,
    round_idx: int,
    max_rounds: int,
    current: dict | None,
    stats: dict | None,
    context: dict,
    history: list[dict],
) -> str:
    """组装发给 VL 模型的中文 prompt；current=None 表示算法第一遍未检出线。"""
    lines: list[str] = []
    lines.append("你是基因组 survey 项目的 GC-Depth 质控图污染复核员。")
    lines.append("")
    lines.append("【图元说明】")
    lines.append("- 横轴 x = GC(%)，纵轴 y = 测序深度；灰→红密度图中越红代表点越多。")
    lines.append(f"- 蓝色水平虚线 = 低深度上限 low_depth_max={context['low_depth_max']:g}。")
    lines.append("- 橙色曲线 = 主云团主脊线（主物种基因组的深度趋势）。")
    lines.append("- 绿色实线 = 当前污染带上边界线（自 GC=20 画至 GC=95；gc_start 为污染带 GC 起点，d_left 是线在 GC=gc_start 处的深度锚点）。")
    if current is None:
        lines.append("- 注意：本图当前没有绿色边界线（算法第一遍未检出）。")
    lines.append("")
    lines.append("【污染形态定义】")
    lines.append("污染表现为：主脊线右下方、蓝虚线以下的一条低深度富集带（横向红色带状区域），其上边界近似一条斜率非负的直线。")
    lines.append("")
    lines.append("【当前数值上下文】")
    lines.append(json.dumps(context, ensure_ascii=False))
    lines.append("")
    if history:
        lines.append("【历史轮次（提议 → clamp 后 → 新 contam/total）】")
        for h in history:
            lines.append(json.dumps(h, ensure_ascii=False))
        lines.append("提示：若上一轮 clamp 后的线已贴合污染带上沿、本轮调整幅度很小，请优先返回 no_adjustment。")
        lines.append("")
    lines.append("【你的任务】")
    lines.append("判断图中右下是否存在污染带、当前绿线是否合适，并只输出一个 JSON 对象（不得输出任何其他文字）：")
    lines.append('{"has_contamination": true或false, "action": "no_contamination|no_adjustment|adjust", '
                 '"gc_start": 数值或null, "d_left": 数值或null, "d_right": 数值或null, "reason": "简短理由"}')
    lines.append("action 取值：")
    lines.append("- no_contamination：图中右下没有可见污染带；")
    lines.append("- no_adjustment：当前绿线已贴合污染带上沿（盖住带顶、未切入主云团），无需调整；")
    lines.append("- adjust：线位置明显不当（横穿污染带/过高/过低），或算法未检出但你看到了污染带；此时必须给出 gc_start、d_left、d_right。")
    lines.append("")
    lines.append("【硬约束】")
    lines.append(f"- d_left/d_right 是 y 轴“测序深度”值（不是像素坐标）：d_left = 线在 GC=gc_start 处的深度，d_right = 线在 GC={context['g1']:g} 处的深度；")
    lines.append(f"- 必须满足 {context['depth_floor']:g} <= d_left <= d_right <= {context['low_depth_max']:g}；")
    lines.append("- 拿不准时优先 no_adjustment。")
    lines.append("")
    lines.append(f"（当前第 {round_idx}/{max_rounds} 轮）")
    return "\n".join(lines)


def _invoke_vl(llm: Any, png_path: Path, prompt: str, timeout_sec: float | None) -> tuple[str, dict, float]:
    """把 PNG(base64) + prompt 发给 VL 模型，返回 (原始文本, token usage, 耗时秒)。"""
    from langchain_core.messages import HumanMessage

    b64 = _encode_png_base64(png_path)
    msg = HumanMessage(content=[
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        {"type": "text", "text": prompt},
    ])
    t0 = time.time()
    try:
        rsp = llm.invoke([msg], timeout=timeout_sec) if timeout_sec else llm.invoke([msg])
    except TypeError:
        rsp = llm.invoke([msg])  # 旧版 langchain 不支持 timeout kwarg 时兜底
    content = rsp.content
    if isinstance(content, list):
        raw = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    else:
        raw = str(content)
    usage = getattr(rsp, "usage_metadata", None)
    return raw, dict(usage or {}), time.time() - t0


def write_llm_log(log_path: Path, payload: dict) -> str | None:
    """写调试日志；失败不得影响判定主流程。"""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return str(log_path)
    except OSError:
        return None


def review_and_adjust(
    *,
    algo_params: dict | None,
    algo_stats: dict | None,
    png_path: Path,
    log_path: Path,
    render_png: Callable[[dict], None],
    compute_stats: Callable[[float, float, float], dict],
    heavy_threshold: float,
    depth_floor: float,
    low_depth_max: float,
    g1: float = 95.0,
    max_rounds: int = 2,
    timeout_sec: float | None = 60.0,
    llm: Any = None,
    pos_path: str | None = None,
) -> LlmAdjustmentOutcome:
    """LLM 视觉复核主循环。任何 API 异常/解析失败都降级为当前（算法）结果。"""
    if llm is None:
        from models.models import get_qwen_plus_llm

        llm = get_qwen_plus_llm()

    current = dict(algo_params) if algo_params else None
    current_stats = dict(algo_stats) if algo_stats else None
    rounds_log: list[dict] = []
    history: list[dict] = []

    status = "ok_no_adjustment"
    final_action = "none"
    final_params = current
    has_adjusted = False

    for r in range(1, max_rounds + 1):
        context = {
            "g1": g1,
            "low_depth_max": low_depth_max,
            "depth_floor": depth_floor,
            "heavy_threshold": heavy_threshold,
            "line_exists": current is not None,
            "gc_start": (current or {}).get("gc_start"),
            "d_left": (current or {}).get("d_left"),
            "d_right": (current or {}).get("d_right"),
            "slope": (current or {}).get("slope"),
            "intercept": (current or {}).get("intercept"),
            "contam_over_total_ratio": (current_stats or {}).get("contam_over_total_ratio"),
        }
        prompt = build_prompt(
            round_idx=r,
            max_rounds=max_rounds,
            current=current,
            stats=current_stats,
            context=context,
            history=history,
        )
        round_log: dict[str, Any] = {
            "round": r,
            "png_path": str(png_path),
            "prompt": prompt,
            "raw_response": None,
            "parse_error": None,
            "retried_parse": False,
            "parsed": None,
            "proposed": None,
            "clamped": None,
            "stats_after": None,
            "usage": None,
            "elapsed_sec": None,
            "error": None,
        }

        proposal: LlmProposal | None = None
        for attempt in (0, 1):
            try:
                raw, usage, elapsed = _invoke_vl(
                    llm, png_path, prompt if attempt == 0 else prompt + RETRY_HINT, timeout_sec
                )
            except Exception as exc:  # API 异常/超时 → 降级
                round_log["error"] = f"{type(exc).__name__}: {exc}"
                rounds_log.append(round_log)
                outcome = LlmAdjustmentOutcome(
                    status="degraded_error",
                    rounds=len(rounds_log),
                    final_action="none",
                    final_params=current,
                    log_path=None,
                    error=round_log["error"],
                )
                outcome.log_path = _finalize_log(log_path, pos_path, png_path, max_rounds, algo_params, rounds_log, outcome)
                return outcome
            round_log["raw_response"] = raw
            round_log["usage"] = usage
            round_log["elapsed_sec"] = round(elapsed, 3)
            try:
                proposal = parse_llm_response(raw, require_gc_start=current is None)
                break
            except Exception as exc:
                round_log["parse_error"] = str(exc)
                if attempt == 0:
                    round_log["retried_parse"] = True
        if proposal is None:  # 两次解析失败 → 降级
            rounds_log.append(round_log)
            outcome = LlmAdjustmentOutcome(
                status="degraded_json",
                rounds=len(rounds_log),
                final_action="none",
                final_params=current,
                log_path=None,
                error=round_log["parse_error"],
            )
            outcome.log_path = _finalize_log(log_path, pos_path, png_path, max_rounds, algo_params, rounds_log, outcome)
            return outcome

        round_log["parsed"] = asdict(proposal)

        if proposal.action == "no_contamination":
            rounds_log.append(round_log)
            status = "ok_no_contamination"
            final_action = "no_contamination"
            final_params = None
            break

        if proposal.action == "no_adjustment":
            rounds_log.append(round_log)
            if current is None:
                # 算法无线且 LLM 也不给线 → 视为无污染
                status = "ok_no_contamination"
                final_action = "no_contamination"
                final_params = None
            elif has_adjusted:
                # 前几轮曾 adjust，本轮 LLM 判定已贴合 → 采纳当前（已 clamp）线
                status = "ok_adjusted"
                final_action = "adjust"
                final_params = current
            else:
                status = "ok_no_adjustment"
                final_action = "no_adjustment"
                final_params = current
            break

        # adjust：clamp → 重算 → 重画 → （未至末轮）继续问
        gc_start = proposal.gc_start
        if gc_start is None and current is not None:
            gc_start = current["gc_start"]
        clamped = clamp_line_params(
            gc_start=gc_start,
            d_left=proposal.d_left,
            d_right=proposal.d_right,
            g1=g1,
            low_depth_max=low_depth_max,
            depth_floor=depth_floor,
        )
        # LLM 提议与当前线几乎一致（<0.05 差异）→ 视为 no_adjustment
        if current is not None and all(
            abs(clamped[k] - current[k]) < 0.05 for k in ("gc_start", "d_left", "d_right")
        ):
            round_log["proposed"] = {
                "gc_start": proposal.gc_start, "d_left": proposal.d_left, "d_right": proposal.d_right,
            }
            round_log["clamped"] = clamped
            round_log["parsed"]["action"] = "no_adjustment"  # 归一化留痕
            rounds_log.append(round_log)
            if has_adjusted:
                status = "ok_adjusted"
                final_action = "adjust"
            else:
                status = "ok_no_adjustment"
                final_action = "no_adjustment"
            final_params = current
            break
        round_log["proposed"] = {
            "gc_start": proposal.gc_start,
            "d_left": proposal.d_left,
            "d_right": proposal.d_right,
        }
        round_log["clamped"] = clamped
        new_stats = compute_stats(clamped["gc_start"], clamped["slope"], clamped["intercept"])
        round_log["stats_after"] = {
            "line_below_count": new_stats.get("line_below_count"),
            "contam_over_total_ratio": new_stats.get("contam_over_total_ratio"),
        }
        render_png(clamped)
        history.append({
            "round": r,
            "proposed": round_log["proposed"],
            "clamped": {k: clamped[k] for k in ("gc_start", "d_left", "d_right", "slope", "intercept")},
            "contam_over_total_ratio": new_stats.get("contam_over_total_ratio"),
        })
        rounds_log.append(round_log)
        current = clamped
        current_stats = new_stats
        final_params = clamped
        final_action = "adjust"
        status = "ok_adjusted"
        has_adjusted = True

    outcome = LlmAdjustmentOutcome(
        status=status,
        rounds=len(rounds_log),
        final_action=final_action,
        final_params=final_params,
        log_path=None,
    )
    outcome.log_path = _finalize_log(log_path, pos_path, png_path, max_rounds, algo_params, rounds_log, outcome)
    return outcome


def _summarize_rounds(rounds_log: list[dict]) -> list[dict]:
    """从逐轮完整日志抽取精简摘要（不含 prompt/raw_response），用于内联进 gc_raw 供前端展示。"""
    out: list[dict] = []
    for r in rounds_log:
        parsed = r.get("parsed") or {}
        out.append(
            {
                "round": r.get("round"),
                "action": parsed.get("action"),
                "has_contamination": parsed.get("has_contamination"),
                "reason": parsed.get("reason"),
                "proposed": r.get("proposed"),
                "clamped": r.get("clamped"),
                "stats_after": r.get("stats_after"),
                "retried_parse": r.get("retried_parse"),
                "parse_error": r.get("parse_error"),
                "error": r.get("error"),
                "elapsed_sec": r.get("elapsed_sec"),
            }
        )
    return out


def _finalize_log(
    log_path: Path,
    pos_path: str | None,
    png_path: Path,
    max_rounds: int,
    algo_params: dict | None,
    rounds_log: list[dict],
    outcome: LlmAdjustmentOutcome,
) -> str | None:
    total_elapsed = sum(float(r.get("elapsed_sec") or 0.0) for r in rounds_log)
    # 所有退出路径都经过此处，rounds_detail 只在这里赋值一次
    outcome.rounds_detail = _summarize_rounds(rounds_log)
    payload = {
        "schema_version": LOG_SCHEMA_VERSION,
        "model": GC_VL_MODEL_NAME,
        "pos_path": pos_path,
        "png_path": str(png_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "max_rounds": max_rounds,
        "algo_initial": algo_params,
        "rounds": rounds_log,
        "final": {
            "status": outcome.status,
            "final_action": outcome.final_action,
            "rounds": outcome.rounds,
            "params": outcome.final_params,
            "total_elapsed_sec": round(total_elapsed, 3),
            "error": outcome.error,
        },
    }
    return write_llm_log(log_path, payload)
