## 文档边界说明
- 本文档仅维护判定规则与判定脚本说明（kmer/nt/survey规则）。
- 后端系统设计、数据库结构、接口与迭代路线见 `docs/` 目录：
  - `docs/backend_v1.md`
  - `docs/backend_roadmap.md`

## 数据处理
/data/work/zhurui/survey_rec/data/survey 信息表.xlsx
sheet:处理后信息

第一列是文件路径信息:
例如:
/TJPROJ12/RESEQ/User/shenshaoqi/survey/X101SC2501/X101SC25015691-Z01-F009/CNST1239_CNST1239
截取 X101SC2501/X101SC25015691-Z01-F009/CNST1239_CNST1239
拼接 /data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1
得到真实路径:/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2501/X101SC25015691-Z01-F009/CNST1239_CNST1239
(base) [zhurui@novoagi02 13:39:24 ~/.claude]
$ls /data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2501/X101SC25015691-Z01-F009/CNST1239_CNST1239
all.ntcls.xls                   CNST1239.17merFreq.SpeFreq.cut  GC.pdf
all.ntspe.xls                   CNST1239.17merFreq.spe.pdf      X101SC25015691-Z01-F009.CNST1239.Survey_Report.zip
CNST1239.17merFreq.NumFreq.cut  CNST1239.pos
CNST1239.17merFreq.num.pdf      CNST1239.Result.xls


'是否流转-结果' 列
不属于['是', '否']的值，统一删除所在行.


## 判定规则

### k-mer图判定规则

**输入**：
1.SpeFreq.cut，有效范围 depth 3~300
2.NumFreq.cut(SpeFreq x 深度)，depth 3~300，供比值判定用


思路:用 11 点平滑掉小于 10 范围内的抖动，再用 distance=10 防止残留重复检峰。
window很像一个”低通滤波器”：
window 越大 → 截止更低 → 越”糊” → 小结构更容易消失（极端情况，window=1，所有小凸起都不变）

1. Savitzky-Golay 平滑（window=11，poly=3），消除低深度端噪声和宽峰顶部抖动
2. `scipy.signal.find_peaks` 检测极大值：
   - 仅用 `distance ≥ 10` 宽松找所有候选峰
   - 再过滤：保留高度 ≥ 候选峰中最高峰 × `prominence_ratio`（默认0.9%）的峰
   - `prominence_ratio`：峰高度相对于最高峰的最小比例阈值，用于过滤噪声峰
     - 值越小（如0.01=1%）→ 保留更多小峰，可能包含噪声
     - 值越大（如0.1=10%）→ 只保留显著峰，可能漏掉真实小峰
   - 阈值基于峰自身相对高度，不受样本绝对频率量级影响，对不同测序深度样本更鲁棒
3. 峰型异常检测：
   - 不再使用“主峰左侧最低点”方法，改为检测主峰左侧急降拐点
   - 拐点定义：主峰左侧“第一个谷底拐点”（一阶导数由负转正，且该点为局部最低点）
   - 拐点检测时单独使用 depth=0 到主峰深度的数据窗口（仅用于拐点，不影响主流程 depth_min=3 的峰检测）
   - 为避免低深度边界振荡伪谷底，拐点检测默认使用原始频率（不额外做Savitzky-Golay平滑）
   - 计算拐点频率占主峰频率比例：inflection_freq / main_peak_freq
   - spe 阈值：比例 >= 0.75 则异常
   - num 阈值：比例 >= 0.6 则异常
   - 预警规则（不影响最终判定）：当比例低于阈值但落入阈值前 `0.1` 区间时提示“疑似左侧最低点偏高”
     - spe 预警区间：`[0.65, 0.75)`
     - num 预警区间：`[0.50, 0.60)`
   - 正常峰型：左侧急降拐点频率应明显低于主峰
   - **综合判断前检测**：如果 spe 或 num 任一异常，直接判为 peak_shape_abnormal，不进行后续合并和判定
   - **异常峰在合并前被过滤**，不参与后续合并和判定
4. 宽度过滤（当前实现）:
   - 使用 `scipy.signal.peak_widths(..., rel_height=0.5)` 计算峰宽（半高宽/FWHM）
   - 计算方式：先由峰顶高度与 prominence 得到测宽高度 `h_eval = h_peak - 0.5 * prominence`，再求该高度在峰左右两侧的交点 `left_ip`、`right_ip`，宽度=`right_ip-left_ip`
   - 宽度 >= `min_width`（默认10）保留，否则丢弃
   - 作用：尖小毛刺（伪峰）半高宽很小，真实主峰半高宽明显更大，区分更稳健
   - 示例（Sf-1）：
     - `depth=9` 伪峰：`left_ip=5.500`，`right_ip=6.278`，宽度 `0.778`（被过滤）
     - `depth=110`：宽度 `30.586`（保留）
     - `depth=219`：宽度 `48.070`（保留）
5. 肩峰（shoulder）检测（`detect_shoulder=True`，默认开启）：
   - 对平滑曲线求一阶导数并再次 Savitzky-Golay 平滑
   - 找一阶导数的局部极小值（增长速率最慢的位置），即曲线上升段中增长减缓形成的"肩部"
   - 过滤条件：
     - 一阶导数 > 0（确保在上升段，排除下降段的凹陷）
     - 频率 >= 全局最高频率 × `prominence_ratio`（过滤低频噪声）
     - 与已有普通峰的距离 >= `min_distance`（避免重复检测）
   - 通过过滤的肩峰加入普通峰列表，后续参与合并和比值判定
   - 适用场景：人眼可见增长减缓形成的"凸起"，但不是真正的极大值点
6. 返回峰的 depth 列表、frequency 列表、异常标记列表，按升序排列


**比值判定**（以最小峰为基准 1，相对误差默认 16%）：

进入比值判定前，先按以下优先级做短路检查（任一命中即判异常返回）：
1. 所有峰太低：检测到的最高峰频率 < depth≥10 范围内全局最高值的 15% → 异常（“所有峰过低”）。
2. 0 峰：SpeFreq 或 NumFreq 任一未检测到峰 → 异常（“未检测到峰”）。
3. 峰型异常：主峰左侧急降拐点频率比例超阈值（SpeFreq≥0.75 / NumFreq≥0.6）→ 异常（“峰型异常”）。

通过上述检查后，SpeFreq 与 NumFreq **分别检测、分别过滤、分别判定**，再汇总比对。单文件按以下优先级匹配，且**峰数与比值必须完整符合已知峰型，不再截断部分峰勉强判定**：

1. n==1 → 二倍体
2. 门控：首两峰 ≈ 1:2？不满足时仅 n==2 允许扩展：≈1:3→三倍体 / ≈1:4→四倍体；否则判 unknown
3. n==3 且 ≈ 1:2:3 → 第三峰频率 ≥ 主峰 40% 判三倍体，否则二倍体
4. n==4 且 ≈ 1:2:3:4 → 四倍体
5. n==4 且 ≈ 1:2:3:6 → 六倍体
6. n==3 且 ≈ 1:2:4 → 第三峰频率 < 主峰 50% 判二倍体，否则四倍体（优先级低于 1:2:3:4）
7. n==3 且 ≈ 1:2:6 → 六倍体
8. n==2 且 ≈ 1:2 → 二倍体
9. 其余峰数或比值（如 5 个峰、1:2:4:8 等）→ unknown，转人工复核

注：旧实现对 5+ 峰会做前缀截断匹配（前几个峰满足某模式即忽略后续峰直接判定），已废弃；现在凡不属于已知峰型一律 unknown 转人工。

输出统一为“二倍体/三倍体/四倍体/六倍体”，不再区分纯合/杂合/高重复二倍体。

**双文件一致性检查**（两者均正常时触发）：
- 倍型结果不一致 → warning，建议人工复核
- 任意一份判型未使用全部检测峰（如低深度污染峰被过滤）→ 比对主峰位置（取实际参与判型的峰中频率最高者）
- 主峰深度相对差 >10% → warning，建议人工复核
- warning 非空时最终综合判定转人工复核

**物种先验倍型分析**（`analysis_ploidy`）：仅当 kmer 正常时启用，通过 agent 联网查询物种倍型先验；若脚本峰型与先验明显冲突且置信度为中/高，追加 warning 建议转人工复核。kmer 异常时不执行该分析。

| 峰数 | 深度比值 | 判定 |
|------|---------|------|
| 1 | — | 正常，二倍体 |
| 2 | 1:2 | 正常，二倍体 |
| 2 | 1:3 | 正常，三倍体 |
| 2 | 1:4 | 正常，四倍体 |
| 3 | 1:2:3 | 第三峰≥主峰40%判三倍体，否则二倍体 |
| 3 | 1:2:4 | 第三峰<主峰50%判二倍体，否则四倍体 |
| 3 | 1:2:6 | 正常，六倍体 |
| 4 | 1:2:3:4 | 正常，四倍体 |
| 4 | 1:2:3:6 | 正常，六倍体 |
| 其他 | — | unknown，转人工复核 |

**实现**：`kmer_judge.py`，入口 `main_dual(spe_filepath, num_filepath, ...)`

**main_dual函数参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `spe_filepath` | 必填 | SpeFreq.cut文件路径 |
| `num_filepath` | 必填 | NumFreq.cut文件路径 |
| `depth_min` | 3 | 有效深度下限，过滤低深度噪声 |
| `depth_max` | 300 | 有效深度上限，截断高深度区域 |
| `use_smoothing` | True | 是否启用Savitzky-Golay平滑；True时对频率与导数做平滑，False时使用原始频率（便于排查低深度伪峰） |
| `smooth_window` | 11 | Savitzky-Golay平滑窗口大小（必须为奇数），越大越平滑 |
| `smooth_poly` | 3 | Savitzky-Golay多项式阶数，控制平滑曲线的拟合灵活度 |
| `prominence_ratio` | 0.009 | 峰高度相对最高峰的最小比例阈值（0.9%），低于此比例的峰视为噪声过滤掉 |
| `min_distance` | 10 | 相邻峰之间的最小距离（索引单位），防止同一峰被重复检测 |
| `min_width` | 8 | 峰宽最小阈值（索引单位）；当前实现使用 `peak_widths(rel_height=0.5)` 的半高宽（FWHM），不足则过滤 |
| `min_width_left_of_main` | 3.9 | 主峰左侧峰宽最小阈值（索引单位）；主峰左侧的峰使用更宽松的宽度阈值 |
| `min_width_shoulder` | 4 | 肩峰宽度最小阈值（索引单位）；同样使用 `peak_widths(rel_height=0.5)` 半高宽，阈值比普通峰更宽松以平衡召回 |
| `tolerance` | 0.16 | 比值匹配的相对误差容忍度（16%），用于判定峰深度比是否符合已知倍性模式 |
| `low_depth_ratio` | 0.2 | 低深度污染峰过滤阈值，深度小于主峰深度×此比例的第一个峰在不成比例且高度不足时会被忽略 |
| `low_peak_freq_ratio` | 0.6 | 低深度峰高度比例阈值（60%），低深度峰高度不及最高峰此比例时忽略 |
| `spe_left_inflection_threshold` | 0.75 | SpeFreq 主峰左侧急降拐点频率比例阈值（75%），达到或超过此值判为异常 |
| `num_left_inflection_threshold` | 0.6 | NumFreq 主峰左侧急降拐点频率比例阈值（60%），达到或超过此值判为异常 |
| `inflection_warn_margin` | 0.1 | 拐点比例预警边界（不影响判定）；当 ratio 落入 `[threshold-0.1, threshold)` 时输出预警 |
| `shoulder_min_freq_ratio` | 0.25 | 肩峰频率最低比例阈值（25%），肩峰频率需达到全局最高峰的此比例才保留，防止低深度噪声区误检 |
| `all_peaks_too_low_ratio` | 0.15 | 所有峰太低判定阈值（15%），检测到的最高峰频率低于depth>=10范围内全局最高值的此比例时判为异常（排除depth<10的错误k-mer噪声峰） |
| `verbose` | True | 是否打印详细检测过程 |
| `species_name` | None | 物种名；仅在 `is_normal=True` 时用于触发 agent 联网倍型分析并补充 `analysis_ploidy` |

**使用示例**：

1. 正常样本（启用 `analysis_ploidy`）
```python
from kmer_judge import main_dual

res = main_dual(
    spe_filepath="data/.../IAC105.17merFreq.SpeFreq.cut",
    num_filepath="data/.../IAC105.17merFreq.NumFreq.cut",
    species_name="锤头双髻鲨",
    verbose=False,
)
print(res["is_normal"], res["analysis_ploidy"]["enabled"], res["analysis_ploidy"]["pattern"])
```

2. 已有结果补充分析（仅 `is_normal=True` 才会联网）
```python
import json
from kmer_judge import enrich_kmer_result

data = json.load(open("data/tmp_kmer_result.json", "r", encoding="utf-8"))
data = enrich_kmer_result(data, species_name="锤头双髻鲨")
print(data["analysis_ploidy"]["enabled"], data["warnings"])
```

### NT比对规则（新规则）
输入：
- 目标物种名由外部传入（默认由 `all.ntcls.xls` 第一行 `Sample name` 读取）。
- 小类文件优先使用 `*_NT.species.xls`（若不存在则回退 `all.ntspe.xls`）。

流程：
1. 读取 NT 小类数据（核心列：`class`、`species`、`total rate`；`fq1/fq2` 不参与判定）。
2. 根据目标物种确定所属大类（动物/植物/细菌/真菌/病毒）；若目标物种无法识别则直接返回 `fail`。
3. 过滤掉以下记录：目标同类、细菌、真菌、病毒、人（`Homo sapiens/human/人`）；其余进入候选（含无法识别类别）。
4. 对候选记录按每批 3 条并发调用 agent（LLM）判定是否“可能/合理污染”，并给出原因。
   - 兜底策略：单批失败、单条漏返回、未完成判定时，默认按“不合理”处理，避免漏报。
5. 输出两份文件：
   - 小类判定文件：在原始小类记录上追加 `是否合理`、`原因` 两列。
   - 大类聚合文件：过滤掉“合理污染”记录后，按 `class` 重聚合（保留不合理/未判定记录）。

判级规则：
- 主导大类比例：`dominant_ratio = max(Metazoa, Plantae, Bacteria, Fungi, Viruses)`。
- 污染合计：`pollution_ratio = Bacteria + Fungi + Viruses + 合理污染占比`。
- 阈值：当 `dominant_ratio < 20` 时阈值为 `0.4%`，否则为 `1.0%`。
- 最终等级：`pollution_ratio > threshold` 判 `重度污染`，否则判 `正常`（等于阈值判正常）。

兼容说明：
- `judge_nt_contamination` 当前返回以 `nt_level/is_heavy_contamination` 为核心，不再返回 `nt_score`。
- 同时返回 `nt_rule_version/target_species/target_category` 及污染比例字段（如 `dominant_ratio_percent`、`pollution_ratio_percent`、`pollution_threshold_percent`）。
- 输出路径字段包含：`small_judged_path`、`class_filtered_path`。




### 判定脚本
1. 批量判定（Excel）：
`conda run -n zhurui_agent python survey_judge_batch.py --max 2 --verbose`

2. 单样本判定（自动定位输入）：
`conda run -n zhurui_agent python survey_judge_single.py`

### 综合判定逻辑

> **GC 执行时机说明**：GC 复核在**每次** survey 判定中都无条件执行（产出 GC 图与判定数据，
> 便于前端展示与追溯，`gc_result.executed=true`）；但是否**参与最终裁决**由下方规则决定——
> 仅当 kmer 无警告且 kmer 与 NT 判定不一致时参与（`gc_result.participated=true`），
> 其余情况下 `participated=false`，GC 结果仅用于展示，不影响 `survey_result`。
> GC 执行失败（如无 `.pos` 文件）不会阻断非冲突样本的判定流程。

1. `kmer.warnings` 非空：
   - `survey_result.should_transfer = 转人工`
   - `survey_result.final_level = 待人工复核`
   - 备注：`kmer存在警告信息，转人工复核`
   - GC 照常执行但不参与裁决（`participated=false`）

2. `NT` 判定为 `fail`：
   - `survey_result.should_transfer = 转人工`
   - `survey_result.final_level = 待人工复核`
   - 备注：`NT判定失败，无法自动识别，转人工复核`

3. `kmer` 与 `NT` 判定一致（`kmer正常+NT正常` 或 `kmer异常+NT异常`）时：
   - 按常规规则判定（见下表）

4. `kmer` 与 `NT` 判定不一致（`kmer正常+NT重度污染` 或 `kmer异常+NT正常`）时：
   - GC 判定结果参与裁决（`participated=true`，GC 已随本次 survey 执行）
   - GC 重度污染阈值：`contam_over_total_ratio`（= 污染点数 `line_below_count` / 总点数，全 GC 区间、线下方且 `depth<=low_depth_max`）`> 0.07` 记为重度污染，否则记为正常（`below/on` 仅保留作诊断字段，不参与判定）。
   - 若 GC 判定失败，则：
     - `survey_result.should_transfer = 转人工`
     - `survey_result.final_level = 待人工复核`
   - 若冲突为 `kmer正常+NT重度污染`：
     - GC 判定正常（`heavy_contamination=False`）时允许流转：
       - `survey_result.should_transfer = 是`
       - `survey_result.final_level = 正常`
       - 备注：`kmer与NT判定不一致，但GC判定正常，允许流转`
     - GC 判定为重度污染（`heavy_contamination=True`）时转人工：
       - `survey_result.should_transfer = 转人工`
       - `survey_result.final_level = 待人工复核`
       - 备注：`kmer与NT判定不一致，GC判定重度污染，转人工复核`
   - 若冲突为 `kmer异常+NT正常`：
     - GC 判定正常（`heavy_contamination=False`）时转人工：
       - `survey_result.should_transfer = 转人工`
       - `survey_result.final_level = 待人工复核`
       - 备注：`kmer异常且NT正常，GC判定正常，转人工复核`
     - GC 判定为重度污染（`heavy_contamination=True`）时不流转：
       - `survey_result.should_transfer = 否`
       - `survey_result.final_level = 重度污染`
       - 备注：`kmer与NT判定不一致，GC判定重度污染，不流转`

常规规则（仅适用于 kmer 与 NT 判定一致的两种组合；不一致组合由上文 GC 仲裁分支裁决，NT fail 已在规则 2 处理）：

| kmer是否正常 | NT等级 | 综合判定(final_level) | 是否流转(should_transfer) | 备注 |
|-------------|--------|-----------------------|----------------------------|------|
| 是 | 正常 | 正常 | 是 |  |
| 否 | 重度污染 | 重度污染 | 否 |  |

说明：
- `final_level` 取值仅有 `正常 / 重度污染 / 待人工复核` 三种。原 `fail` 等级已去除，与 `重度污染` 含义合并（kmer异常+NT重度污染 现判为 `重度污染/否`），历史数据已同步迁移。
- 原「kmer正常+NT重度污染 → 轻度污染」与「kmer异常+NT正常 → 重度污染(备注 NT正常但kmer异常)」两行属于不一致组合，实际始终走 GC 仲裁分支，不可达，已删除；`轻度污染` 等级不再产出。
- 当前 NT 正常流程仅产出 `正常/重度污染/fail`。若出现其他异常值，按异常输入转人工复核处理。

GC 判定失败的常见原因（转人工合理）：
- 样本目录内找不到 `*.pos` 文件，或目录本身无效。
- `.pos` 文件不存在、不可读，或读入后清洗无有效点（GC/Depth 全部无效）。
- GC 处理中出现运行异常（如输出文件写入失败等）。

### 输出字段（单样本JSON）

| 字段 | 说明 |
|------|------|
| 原始kmer字段 | 保留 `tmp_kmer_result_with_ai.json` 中的全部字段（如 `pattern/is_normal/detail/warnings/analysis_ploidy`） |
| spe_main_peak_depth / num_main_peak_depth | SpeFreq/NumFreq 各自主峰深度（按最终判型使用峰计算） |
| target_species | 从 `all.ntcls.xls` 读取的目标物种名 |
| nt_result | NT聚合判定对象：如 `nt_level/is_heavy_contamination/nt_rule_version/target_species/target_category/source_nt_count/valid_nt_count/dominant_category/dominant_ratio_percent/pollution_ratio_percent/pollution_threshold_percent/class_filtered_path/class_filtered_paths/small_judged_paths/nt_results/ntcls_detail/ntspe_detail` |
| gc_result | GC复核结果对象：`executed/status/reason/participated`（`participated=true` 表示本次 GC 参与最终裁决，仅 kmer 无警告且 kmer/NT 不一致时成立）；执行成功时额外包含 `pos_path/heavy_contamination/gc_raw`（详细判定位于 `gc_raw.decision/global_stats/artifacts`，演进过程位于 `gc_raw.artifacts.png_steps` 与 `gc_raw.llm_adjustment.rounds_detail`） |
| survey_result | 综合结果对象：`final_level/should_transfer/remark` |
| result_metrics | 从 `*.Result.xls` 读取并修正后的结果对象：`result_path/ploidy_pattern/ploidy_multiplier/raw/adjusted/remark` |

说明：单样本 JSON 输出采用嵌套结构，不再写入顶层平铺重复字段（如 `nt_score/nt_level/final_level/should_transfer`）。

补充规则（`*.Result.xls`）：
1. 文件需包含 8 列，顺序与语义如下：物种名（`#Sample`）、`Kmer`、主峰深度（`Depth`）、`n_kmer`、基因组大小（`Genome_size(M)`）、校正后基因组大小（`Revised_Genome_size(M)`）、杂合率（`Heterozygous_rate(%)`）、重复率（`Repeat_rate(%)`）。
2. `result_metrics.raw` 直接保存首行原始值；`result_metrics.adjusted` 保存按倍性修正后的值。
3. 倍性修正规则：二倍体不变；三倍体将 `Genome_size(M)` 和 `Revised_Genome_size(M)` 乘 3；四倍体乘 4；六倍体乘 6；并在 `result_metrics.remark` 记录原因。



## 相关知识 

Prominence 计算原理
以 depth=49 的峰为例：

频率
 ↑
 |   ★ 主峰(depth=27, freq=5,927,536)
 |  / \
 | /   \
 |/     \
 |       \  ☆ 次峰(depth=49, freq=4,706,528)
 |        \ /\
 |         ✕   \      ← 谷底(depth≈41, freq≈4,527,450)
 |              \
 +——————————————————→ depth

计算步骤：

从峰顶（depth=49, freq=4,706,528）向左走，找到与更高峰之间的最低谷底（depth≈41, freq≈4,527,450）
从峰顶向右走，找到与更高峰（或边界）之间的最低谷底
取两侧谷底中较高的那个作为"基准线"
prominence = 峰顶频率 - 基准线 = 4,706,528 - 4,527,555 ≈ 178,973
所以 prominence 衡量的是"把这个峰淹没需要多少水"，而不是峰的绝对高度。

现在把 prominence_ratio 从 0.05 降到 0.04，让 0.0486 能通过。
