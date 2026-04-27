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


**比值判定**（以最小峰为基准1，相对误差可配置，默认10%）：

结合判定:

1.SpeFreq.cut的峰数
2.NumFreq.cut的峰数
统计这两个图检测到的总峰数，以及它们的深度、频率，
如果检测到峰的数量为3，判断第三个峰的频率是否在第二个峰频率的70%以上，如果是，则认为是二倍体.

**双文件综合判定实现**：
1. SpeFreq 与 NumFreq 分别检测、分别过滤、分别判定，不再执行双图峰合并。
2. 特殊规则（1:2:4）：
   - 当单个文件峰比值约为 1:2:4 时，若第三峰频率 < 主峰频率的 50%，判为二倍体；
   - 否则判为四倍体。
3. 特殊规则（1:2:3，仅三峰）：
   - 当单个文件峰比值约为 1:2:3 时，若第三峰频率 >= 主峰频率的 40%，判为三倍体；
   - 否则判为二倍体。
4. 输出规则：
   - 二倍体统一输出“二倍体”，不再区分纯合/杂合/高重复二倍体。
5. 结果一致性：
   - SpeFreq 与 NumFreq 倍型结果不一致时，加入 warning，提示“建议人工复核”。
6. 其他情况：按常规比值判定规则处理（每个文件独立判定后再汇总）。
7. 入口函数：`main_dual(spe_filepath, num_filepath, ...)`

8. 物种先验倍型分析（`analysis_ploidy`）：
   - 仅当 `kmer是否正常(is_normal)=True` 时启用。
   - 通过 agent 联网查询物种倍型先验（染色体数/是否有多倍体报道），写入 `analysis_ploidy` 字段。
   - 若脚本峰型（`pattern`）与 `analysis_ploidy.pattern` 明显冲突，且 `analysis_ploidy.confidence` 为中/高，则在 `warnings` 追加“建议转人工复核”提示。
   - 若 k-mer 异常（`is_normal=False`），则不做物种先验分析，`analysis_ploidy.enabled=False`。

| 峰数 | 深度比值 | 判定 |
|------|---------|------|
| 1 | — | 正常，二倍体 |
| 2 | 1:2 | 正常，二倍体 |
| 3 | 1:2:3 | 正常，三倍体 |
| 3 | 1:2:4 | 第三峰<主峰50%判二倍体，否则判四倍体 |
| 4 | 1:2:3:4 | 正常，四倍体 |
| 其他 | — | unknown，暂不处理 |

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
| `min_width` | 10 | 峰宽最小阈值（索引单位）；当前实现使用 `peak_widths(rel_height=0.5)` 的半高宽（FWHM），不足则过滤 |
| `min_width_shoulder` | 6 | 肩峰宽度最小阈值（索引单位）；同样使用 `peak_widths(rel_height=0.5)` 半高宽，阈值比普通峰更宽松以平衡召回 |
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
2. 根据目标物种确定所属大类（动物/植物/细菌/真菌/病毒）。
3. 过滤掉以下记录：目标同类、细菌、真菌、病毒、人（`Homo sapiens/human/人`）。
4. 对剩余候选记录按每批 3 条并发调用 agent（LLM）判定是否“可能/合理污染”，并给出原因。
5. 输出两份文件：
   - 小类判定文件：在原始小类记录上追加 `是否合理`、`原因` 两列。
   - 大类聚合文件：过滤掉不合理记录后，按 `class` 重聚合（`species_count`、`total_rate_sum`）。

兼容说明：
- `judge_nt_contamination` 仍返回 `nt_score/nt_level` 等字段以兼容上层流程；
- 同时新增 `nt_rule_version/small_judged_path/class_filtered_path` 等新字段。




### 判定脚本
1. 批量判定（Excel）：
`conda run -n zhurui_agent python survey_judge_batch.py --max 2 --verbose`

2. 单样本判定（自动定位输入）：
`conda run -n zhurui_agent python survey_judge_single.py`

### 综合判定逻辑

kmer正常时：
| NT等级 | 综合判定 |
|--------|---------|
| 正常/轻度污染 | 正常 |
| 重度污染 | 轻度污染（NT得分<=2时不建议流转） |
| fail | NT得分>=3时轻度污染，否则重度污染 |

kmer异常时：
| NT等级 | 综合判定 |
|--------|---------|
| 正常 | 重度污染 |
| 其他 | fail |

注：当前已移除“疑似多倍体”专门分支，按上述 kmer正常/异常统一处理。

### 输出字段（单样本JSON）

| 字段 | 说明 |
|------|------|
| 原始kmer字段 | 保留 `tmp_kmer_result_with_ai.json` 中的全部字段（如 `pattern/is_normal/detail/warnings/analysis_ploidy`） |
| target_species | 从 `all.ntcls.xls` 读取的目标物种名 |
| nt_result | NT判定结果对象：`nt_score/nt_level/ntcls_score/ntspe_score/ntcls_detail/ntspe_detail/ntcls_top1_pass/ntcls_contamination_pass/ntspe_contamination_pass` |
| survey_result | 综合结果对象：`final_level/should_transfer/remark` |
| result_metrics | 从 `*.Result.xls` 读取并修正后的结果对象：`result_path/ploidy_pattern/ploidy_multiplier/raw/adjusted/remark` |

说明：单样本 JSON 输出采用嵌套结构，不再写入顶层平铺重复字段（如 `nt_score/nt_level/final_level/should_transfer`）。

补充规则（`*.Result.xls`）：
1. 文件需包含 8 列，顺序与语义如下：物种名（`#Sample`）、`Kmer`、主峰深度（`Depth`）、`n_kmer`、基因组大小（`Genome_size(M)`）、校正后基因组大小（`Revised_Genome_size(M)`）、杂合率（`Heterozygous_rate(%)`）、重复率（`Repeat_rate(%)`）。
2. `result_metrics.raw` 直接保存首行原始值；`result_metrics.adjusted` 保存按倍性修正后的值。
3. 倍性修正规则：二倍体不变；三倍体将 `Genome_size(M)` 和 `Revised_Genome_size(M)` 乘 3；四倍体乘 4；并在 `result_metrics.remark` 记录原因。



### 优化逻辑
判定结果: unknown
是否正常: 否
详情: 5个峰，depth=[23, 45, 90, 135, 179]，比值=1.00:1.96:3.91:5.87:7.78，不匹配已知模式

当峰大于等于四个的时候，参照如下字典的判断逻辑，如果符合1:2则接着往下看（三倍体和高重复二倍体可以同步看），如果不符合就停止，直到找到最匹配的模式或者列表被裁剪完：

('diploid_hetero',    [1, 2],    '杂合二倍体'),
('triploid',          [1, 2, 3], '三倍体'),
('high_repetitive_diplo', [1, 2, 4], '高重复二倍体'),
('tetraploid',        [1, 2, 3, 4], '四倍体'),


## 判定算法
1. kmer峰型异常的结论是如何得出的
在 kmer_judge.py:51-63 的 detect_peaks 函数中：

逻辑是检查每个峰的左侧鞍部（局部最小值）与峰高度的比值：


left_min = freq_smooth[:idx].min()   # 峰左侧所有点的最小值
left_ratio = left_min / peak_freq    # 鞍部占峰高的比例
abnormal_flags.append(left_ratio > 0.9)  # 超过90%标记异常
判定逻辑：

对每个检测到的峰，取其左侧（depth更小方向）平滑曲线的全局最小值 left_min
计算 left_min / peak_freq，即左侧最低点占峰高的比例
如果比例 > 0.9（90%），标记为异常峰型
含义：正常的生物学峰应该是左侧有明显下降再上升到峰值的形态。如果左侧鞍部几乎和峰一样高（>90%），说明这个"峰"其实不是一个真正的凸起，可能是噪声或数据质量问题导致的假峰。

注意：异常峰在合并前被过滤掉，不参与后续的峰合并和 classify_peaks 判定逻辑。

2. 当前如何检测峰的宽度
峰宽度检测在 kmer_judge.py:30-47：


# 新版（当前实现）:
# 从峰顶向左扫描，直到频率不再递减（找左侧局部谷底），
# 从峰顶向右扫描，直到频率不再递减（找右侧局部谷底），
# 宽度 = 右谷底位置 - 左谷底位置。
# 如果宽度 >= min_width（默认15），则保留该峰；否则视为窄峰过滤。

关于参数外置情况：

detect_peaks 函数签名中有 min_width=15 参数
main_dual 函数已经外置了 min_width=15（L184），并传递给 detect_peaks


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

## 迭代优化（已经实现）
### 优化v4
1.NT大类算所有比例的10%，而不是固定10%
2.大类里面，改为非本类加一起小于所有比例的10%才算通过
2.小类不再卡固定的2%，改为top1的10%（如果top1<5%，则为20%）

### 优化v5
kmer污染峰，不再卡主峰深度的25%，改为20%
spe左边峰最低点需要低于主峰75%的位置
除了1:2，1:3在2.7-3.3范围内也算正常的倍性模式，1:4在3.5-4.2范围内算正常的倍性模式，其他不变
所有峰太低:最高峰频率低于最高值的20%（从深度3开始的最高点），异常


## NT最新规则
对于NT小类文件（几百-上千个）
1.目标物种名仍由外部传入（默认从 `all.ntcls.xls` 第一行 `Sample name` 读取）；NT小类输入改为 `*_NT.species.xls`（找不到时兼容回退 `all.ntspe.xls`）。
2.读取小类文件（列：`class/species/total rate`，`fq1_number(rate)/fq2_number(rate)` 不参与判定）。
3.先按规则过滤：去掉“目标物种所属大类 + 细菌 + 真菌 + 病毒 + 人（Homo sapiens/human/人）”。
4.对剩余候选按每批 3 条并发调用 agent（LLM）判定“是否可能/合理污染”，并返回简短原因。
5.导出两个文件：
   - 小类明细文件：在原始小类记录上追加两列 `是否合理`、`原因`。
   - 大类聚合文件：仅保留 `是否合理=是` 的物种后，按大类重新聚合（`species_count`、`total_rate_sum`）。
6.NT返回结果保留兼容字段（`nt_level/nt_score/...`）供上层流程使用，同时新增输出文件路径等新字段。
