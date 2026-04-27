from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from models.models import get_qwen_plus_llm

CATEGORY_EN_TO_CN = {
    "Metazoa": "动物",
    "Plantae": "植物",
    "Bacteria": "细菌",
    "Fungi": "真菌",
    "Viruses": "病毒",
}
CATEGORY_CN_TO_EN = {v: k for k, v in CATEGORY_EN_TO_CN.items()}

CATEGORY_CN_SET = {"动物", "植物", "细菌", "真菌", "病毒"}
UNKNOWN_CATEGORY = "无法识别"
EXCLUDED_CATEGORY = {"细菌", "真菌", "病毒"}
HUMAN_NAMES = {
    "homo sapiens",
    "human",
    "人",
}
CLASS_ORDER = ["Metazoa", "Plantae", "Bacteria", "Fungi", "Viruses"]


class CategoryInferResult(BaseModel):
    category: Literal["动物", "植物", "细菌", "真菌", "病毒", "无法识别"] = Field(
        ...,
        description=(
            "目标物种所属生物大类。若名称无法映射到明确生物实体，"
            "如无意义字符、模型名、代号等，返回无法识别。"
        ),
    )


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def _normalize_species_name(value: str) -> str:
    text = _normalize_text(value)
    text = re.sub(r"^PREDICTED:\s*", "", text, flags=re.IGNORECASE)
    return text


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(str(value).strip())
    except Exception:
        return default


def _format_ratio(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    if not text:
        return "0"
    return text


def _extract_json(text: str) -> Any:
    raw = _normalize_text(text)
    if not raw:
        raise ValueError("LLM返回为空")

    # 兼容 ```json ... ``` 代码块
    codeblock = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    if codeblock:
        raw = codeblock.group(1).strip()

    # 先直接解析
    try:
        return json.loads(raw)
    except Exception:
        pass

    # 再尝试截取第一个 JSON 对象/数组
    obj_match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    arr_match = re.search(r"\[.*\]", raw, flags=re.DOTALL)

    candidates = []
    if obj_match:
        candidates.append(obj_match.group(0))
    if arr_match:
        candidates.append(arr_match.group(0))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue

    raise ValueError(f"无法解析LLM JSON输出: {raw[:300]}")


def _infer_category_by_name(species_name: str, llm) -> str:
    prompt = (
        "请判断输入名称对应的生物大类。\n"
        "可选值仅限：动物、植物、细菌、真菌、病毒、无法识别。\n"
        "规则：\n"
        "1) 只有在能明确识别为真实生物名称时，才能返回前五类之一；\n"
        "2) 若输入是无意义字符串、模型名、缩写代号、拼写噪声或无法确定具体生物（如 cc07、qwen 等），必须返回“无法识别”；\n"
        f"3) 输入名称：{species_name}\n"
    )
    structured_llm = llm.with_structured_output(CategoryInferResult, method="function_calling")
    result = structured_llm.invoke(prompt)
    category = _normalize_text(getattr(result, "category", ""))
    if category == UNKNOWN_CATEGORY:
        return UNKNOWN_CATEGORY
    if category not in CATEGORY_CN_SET:
        raise ValueError(f"类别不在允许集合: {category}")
    return category


def _judge_chunk_reasonability(
    target_species: str,
    target_category: str,
    rows: list[dict[str, Any]],
    llm,
) -> list[dict[str, Any]]:
    """每批最多3条记录，调用一次LLM并返回逐条合理性判断。"""
    payload = []
    for row in rows:
        payload.append(
            {
                "idx": int(row["idx"]),
                "species": row["species"],
                "class": row["class"],
                "total_rate": row["total_rate"],
            }
        )

    prompt = (
        "你是测序污染判定助手。\n"
        "目标样本信息：\n"
        f"- target_species: {target_species}\n"
        f"- target_category: {target_category}\n\n"
        "请判断以下候选物种是否属于“可能/合理污染”（例如生态接触、采样链或实验流程中可能残留），"
        "并给出简短原因。\n"
        "要求：\n"
        "1) 对每条都必须输出结果；\n"
        "2) 只输出JSON数组；\n"
        "3) reason简洁明确，避免空泛。\n\n"
        "输入记录(JSON)：\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "输出格式(JSON数组)：\n"
        "[\n"
        "  {\"idx\": 1, \"is_reasonable\": true, \"reason\": \"...\"}\n"
        "]"
    )

    response = llm.invoke(prompt)
    parsed = _extract_json(getattr(response, "content", ""))
    if not isinstance(parsed, list):
        raise ValueError("LLM未返回JSON数组")

    out: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "idx": int(item.get("idx")),
                "is_reasonable": bool(item.get("is_reasonable")),
                "reason": _normalize_text(item.get("reason")) or "LLM未提供原因",
            }
        )
    return out


def _build_chunks(items: list[dict[str, Any]], chunk_size: int = 3) -> list[list[dict[str, Any]]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _to_cn_category(raw_class: Any) -> str:
    c = _normalize_text(raw_class)
    if c in CATEGORY_CN_SET:
        return c
    return CATEGORY_EN_TO_CN.get(c, "")


def _to_en_category(raw_class: Any) -> str:
    c = _normalize_text(raw_class)
    if c in CLASS_ORDER:
        return c
    return CATEGORY_CN_TO_EN.get(c, "")


def _read_nt_species_file(ntspe_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(ntspe_path, sep="\t")

    lower_map = {c.lower(): c for c in df.columns}
    class_col = "#class" if "#class" in df.columns else lower_map.get("class")
    species_col = "species" if "species" in df.columns else None
    total_rate_col = "total rate" if "total rate" in df.columns else lower_map.get("total rate")

    if class_col is None or species_col is None or total_rate_col is None:
        raise ValueError(
            "NT小类文件缺少必需列，需包含 class/species/total rate（支持#class列名）"
        )

    out = df.copy()
    out["class"] = df[class_col].astype(str)
    out["species"] = df[species_col].astype(str)
    out["total_rate"] = df[total_rate_col]
    out["total_rate"] = out["total_rate"].apply(_safe_float)
    out["class_cn"] = out["class"].apply(_to_cn_category)
    out["species_norm"] = out["species"].apply(_normalize_species_name)
    return out, df


def _write_outputs(
    original_df: pd.DataFrame,
    judged_df: pd.DataFrame,
    class_line_df: pd.DataFrame,
    ntspe_path: str,
) -> tuple[str, str]:
    src = Path(ntspe_path)
    stem = src.name

    export_small = original_df.copy()
    export_small["是否合理"] = judged_df["是否合理"]
    export_small["原因"] = judged_df["原因"]

    primary_judged = src.with_name(f"{stem}.judged.tsv")
    primary_class = src.with_name(f"{stem}.class.filtered.tsv")
    export_small.to_csv(primary_judged, sep="\t", index=False)
    class_line_df.to_csv(primary_class, sep="\t", index=False)
    return str(primary_judged), str(primary_class)


def _build_class_line(
    kept_df: pd.DataFrame,
    ntcls_path: str,
    target_species: str,
) -> pd.DataFrame:
    class_sum = kept_df.groupby("class", as_index=False)["total_rate"].sum()
    class_sum_map = {
        _normalize_text(row["class"]): _safe_float(row["total_rate"])
        for _, row in class_sum.iterrows()
    }

    sample_name = target_species
    library_name = ""
    if ntcls_path and Path(ntcls_path).exists():
        try:
            df_cls = pd.read_csv(ntcls_path, sep="\t")
            if not df_cls.empty:
                first = df_cls.iloc[0]
                sample_name = _normalize_text(first.get("Sample name", sample_name)) or sample_name
                library_name = _normalize_text(first.get("Library name", ""))
        except Exception:
            pass

    values = []
    for cat in CLASS_ORDER:
        ratio = class_sum_map.get(cat, 0.0)
        values.append(f"{cat}({_format_ratio(ratio)})")

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


def _calc_class_ratio_map(kept_df: pd.DataFrame) -> dict[str, float]:
    ratio_map = {k: 0.0 for k in CLASS_ORDER}
    for _, row in kept_df.iterrows():
        cat = _to_en_category(row.get("class", ""))
        if not cat:
            continue
        ratio_map[cat] += _safe_float(row.get("total_rate", 0.0))
    return ratio_map


def _decide_nt_level(dominant_ratio: float, pollution_ratio: float) -> tuple[str, float]:
    # 最大类比例 <20% 时阈值 0.4%，否则阈值 1%
    threshold = 0.4 if dominant_ratio < 20 else 1.0
    if pollution_ratio > threshold:
        return "重度污染", threshold
    return "正常", threshold


def judge_nt_contamination(ntcls_path: str, ntspe_path: str, target_species: str) -> dict:
    """
    NT新规则（完全替换旧打分法）：
    1) 读取 *_NT.species.xls（或等价格式）
    2) 过滤掉：目标所属大类 + 细菌/真菌/病毒 + 人
    3) 对剩余候选按每批3条并发调用LLM，判定“是否合理污染”
    4) 导出：
       - 小类判定文件（追加“是否合理/原因”）
       - 大类聚合文件（排除“合理污染”，保留“不合理/未判定”后重聚合）
    """
    print("=" * 60)
    print("开始NT比对污染判断（新规则）")
    print("=" * 60)

    llm = get_qwen_plus_llm()

    try:
        df_small, df_small_raw = _read_nt_species_file(ntspe_path)
    except Exception as e:
        return {
            "nt_level": "fail",
            "is_heavy_contamination": False,
            "nt_rule_version": "nt_rule_v3_ratio_gate",
            "detail": f"NT小类文件读取失败: {e}",
        }

    if df_small.empty:
        return {
            "nt_level": "fail",
            "is_heavy_contamination": False,
            "nt_rule_version": "nt_rule_v3_ratio_gate",
            "detail": "NT小类文件为空",
        }

    try:
        target_category = _infer_category_by_name(target_species, llm)
    except Exception as e:
        return {
            "nt_level": "fail",
            "is_heavy_contamination": False,
            "nt_rule_version": "nt_rule_v3_ratio_gate",
            "detail": f"目标物种分类失败: {e}",
        }
    if target_category == UNKNOWN_CATEGORY:
        detail = f"目标物种无法识别: {target_species}"
        return {
            "nt_level": "fail",
            "is_heavy_contamination": False,
            "nt_rule_version": "nt_rule_v3_ratio_gate",
            "detail": detail,
            "target_species": target_species,
            "target_category": UNKNOWN_CATEGORY,
        }

    print(f"目标物种: {target_species}，所属大类: {target_category}")

    judged_df = df_small.copy()
    judged_df["是否合理"] = ""
    judged_df["原因"] = ""
    judged_df["_entered"] = False
    judged_df["_keep"] = True

    # 候选：排除目标同类 + 细菌真菌病毒 + 人
    candidate_idx: list[int] = []
    for idx, row in judged_df.iterrows():
        class_cn = _normalize_text(row.get("class_cn", ""))
        species_norm = _normalize_species_name(str(row.get("species", ""))).lower()

        if species_norm in HUMAN_NAMES:
            continue
        if class_cn == target_category:
            continue
        if class_cn in EXCLUDED_CATEGORY:
            continue

        # 未识别类别也纳入候选，让LLM辅助判定
        candidate_idx.append(int(idx))
        judged_df.at[idx, "_entered"] = True

    candidates: list[dict[str, Any]] = []
    for idx in candidate_idx:
        r = judged_df.loc[idx]
        candidates.append(
            {
                "idx": idx,
                "species": _normalize_text(r["species"]),
                "class": _normalize_text(r["class"]),
                "total_rate": _safe_float(r["total_rate"]),
            }
        )

    print(f"总物种数: {len(judged_df)}，进入LLM合理性判定数: {len(candidates)}")

    # 并发：每批3条
    chunk_size = 3
    chunks = _build_chunks(candidates, chunk_size=chunk_size)
    judged_map: dict[int, tuple[bool, str]] = {}

    if chunks:
        max_workers = min(8, len(chunks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    _judge_chunk_reasonability,
                    target_species,
                    target_category,
                    chunk,
                    llm,
                ): chunk
                for chunk in chunks
            }

            for future in as_completed(future_map):
                chunk = future_map[future]
                try:
                    results = future.result()
                except Exception as e:
                    # 单批失败时按“可疑（不合理）”兜底，避免漏报
                    for item in chunk:
                        judged_map[item["idx"]] = (
                            False,
                            f"LLM判定失败，按不合理处理: {e}",
                        )
                    continue

                for item in results:
                    idx = item["idx"]
                    judged_map[idx] = (item["is_reasonable"], item["reason"])

                # 兜底：若某条未返回
                for item in chunk:
                    if item["idx"] not in judged_map:
                        judged_map[item["idx"]] = (False, "LLM未返回该条结果，按不合理处理")

    for idx in candidate_idx:
        is_reasonable, reason = judged_map.get(idx, (False, "未完成判定，按不合理处理"))
        judged_df.at[idx, "是否合理"] = "是" if is_reasonable else "否"
        judged_df.at[idx, "原因"] = reason
        # 取反逻辑：合理污染不计入大类，不合理污染计入大类
        judged_df.at[idx, "_keep"] = (not bool(is_reasonable))

    kept_df = judged_df[judged_df["_keep"]].copy()
    reasonable_df = judged_df[(judged_df["_entered"]) & (judged_df["是否合理"] == "是")].copy()

    class_line_df = _build_class_line(kept_df=kept_df, ntcls_path=ntcls_path, target_species=target_species)

    original_cols = list(df_small_raw.columns)
    judged_path, class_path = _write_outputs(
        judged_df[original_cols],
        judged_df,
        class_line_df,
        ntspe_path,
    )

    class_ratio_map = _calc_class_ratio_map(kept_df)
    dominant_category = max(class_ratio_map, key=class_ratio_map.get)
    dominant_ratio = class_ratio_map[dominant_category]
    reasonable_ratio = float(reasonable_df["total_rate"].sum()) if not reasonable_df.empty else 0.0
    pollution_ratio = (
        class_ratio_map["Bacteria"]
        + class_ratio_map["Fungi"]
        + class_ratio_map["Viruses"]
        + reasonable_ratio
    )
    nt_level, threshold = _decide_nt_level(dominant_ratio, pollution_ratio)

    candidate_total = len(candidates)
    reasonable_count = int(len(reasonable_df))
    is_heavy = nt_level == "重度污染"

    ntcls_detail = (
        f"目标大类={target_category}; 过滤规则=去除目标同类+细菌+真菌+病毒+人; "
        f"进入LLM判定={candidate_total}; 合理污染数={reasonable_count}"
    )
    ntspe_detail = (
        f"主导大类={dominant_category}({_format_ratio(dominant_ratio)}%); "
        f"污染合计=细菌({_format_ratio(class_ratio_map['Bacteria'])}%)"
        f"+真菌({_format_ratio(class_ratio_map['Fungi'])}%)"
        f"+病毒({_format_ratio(class_ratio_map['Viruses'])}%)"
        f"+合理污染({_format_ratio(reasonable_ratio)}%)="
        f"{_format_ratio(pollution_ratio)}%; 阈值={_format_ratio(threshold)}%; "
        f"小类输出={judged_path}; 大类输出={class_path}"
    )

    print("\n" + "=" * 60)
    print(f"【NT新规则结果】等级={nt_level}")
    print(f"  {ntcls_detail}")
    print(f"  {ntspe_detail}")
    print("=" * 60)

    return {
        "nt_level": nt_level,
        "is_heavy_contamination": is_heavy,
        "ntcls_detail": ntcls_detail,
        "ntspe_detail": ntspe_detail,
        "nt_rule_version": "nt_rule_v3_ratio_gate",
        "target_species": target_species,
        "target_category": target_category,
        "total_species": int(len(judged_df)),
        "candidate_species": int(candidate_total),
        "reasonable_species": reasonable_count,
        "dominant_category": dominant_category,
        "dominant_ratio_percent": round(dominant_ratio, 4),
        "metazoa_ratio_percent": round(class_ratio_map["Metazoa"], 4),
        "plantae_ratio_percent": round(class_ratio_map["Plantae"], 4),
        "bacteria_ratio_percent": round(class_ratio_map["Bacteria"], 4),
        "fungi_ratio_percent": round(class_ratio_map["Fungi"], 4),
        "viruses_ratio_percent": round(class_ratio_map["Viruses"], 4),
        "reasonable_contamination_ratio_percent": round(reasonable_ratio, 4),
        "pollution_ratio_percent": round(pollution_ratio, 4),
        "pollution_threshold_percent": round(threshold, 4),
        "small_judged_path": judged_path,
        "class_filtered_path": class_path,
    }


if __name__ == "__main__":
    base_path = "data/to_zhurui_surey_jinxianlan/FDSW260016098-2r_DaYuanYe叶-1"
    result = judge_nt_contamination(
        ntcls_path=f"{base_path}/test.ntcls.xls",
        ntspe_path=f"{base_path}/FDSW260016098-2r_L1_NT.species.test.xls",
        target_species="金线莲",
    )
    print(f"\n返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
