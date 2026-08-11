## GC-Depth 主脊线 + 右下污染区域判定方案

脚本文件：`gc_depth_line_judge.py`（LLM 复核模块：`gc_llm_adjust.py`）

用途：
- 输入 `.pos` 原始数据（第3列 GC，第4列 Depth）。
- 先在全局点云上估计主云团的 GC-Depth 主脊线。
- 再在 `Depth<=low_depth_max` 的蓝线以下，自动寻找主脊线右侧的低深度污染带，并拟合其上边界直线（端点参数化网格搜索）。
- 按"污染区域点数 / 总点数"判定是否为重度污染。
- 第二遍（默认开启）：多模态 VL 模型看图复核，可推翻或调整第一遍结果。

---

## 1. 算法实现方法（两遍流程）

### 第一遍：确定性算法

1. 数据读取与清洗
- 读取 `.pos` 第3列（GC）和第4列（Depth）。
- 保留有效数值点，并限制 `20<=GC<=95`、`Depth>=0`。

2. 主脊线估计（`estimate_main_ridge`）
- 按 GC 分箱（步长 `--gc-grid`，默认 0.5）统计深度分布。
- 每个 bin 优先取 `Depth>low_depth_max` 的主云团点做深度直方图（高斯平滑后取主峰深度）；
  主云团点数不足时退回用整个 bin 的点。bin 总点数 `<80` 的跳过。
- 对各 bin 主峰做插值和高斯平滑（`--smooth-sigma`，默认 2.0），得到 `main_depth(gc)` 主脊线。
- 有效 bin `<5` 时视为脊线不存在。

3. 污染带 GC 起点检测（`detect_gc_start`，`gc_start` 门控）
- 只看 `Depth<=low_depth_max` 的点；全局低深度点 `<100` 直接返回"未检出"。
- 用"高脊掩码"排除主云低/高 GC 尾部：只保留脊线深度 `>= low_depth_max + 5` 且 bin 点数 `>=40` 的 bin
  （尾部处主脊本身沉入低深度区，那里的低深度点属于主物种，不是污染）。
- 在高脊区内找低深度点比例（`low_ratio`）的谷底 → 主云中心 `valley_gc`。
- 阈值 = `max(valley_ratio + 0.15, 0.15)`；从 `valley_gc` 向右找第一段
  `low_ratio >= 阈值` 且 `low_counts >= 20` 的连续 run（至少 3 个 bin），
  再以半阈值容差向右扩展（并入污染带尾部被稀释的 bin）。
- 扩展后区间内低深度点 `<50` 视为未检出。
- 检出的 run 左端即 `gc_start`。它的角色：**污染带存在性门控**（未检出则不拟合线）、
  拟合区域左端点、边界线深度锚点（`d_left` 为线在 `GC=gc_start` 处的深度）。

4. 污染带上边界线拟合（`fit_contamination_line`，端点参数化网格搜索）
- 在 `[depth_floor, low_depth_max]²` 上枚举端点深度 `(d_left, d_right)`
  （步长 `--depth-step`，默认 0.5；要求 `d_left <= d_right`，即非负斜率）。
- 线形式：在 `gc_start` 处深度为 `d_left`、在 `GC=95` 处深度为 `d_right` 的直线，
  换算为 `depth = slope * gc + intercept`。
- 覆盖率 = 区域 `[gc_start, 95]` 内低深度点落在线下的比例。
- 取**覆盖率 >= `--min-coverage`（默认 0.9）的最低线**（`d_left + d_right` 最小）。
- 区域内低深度点 `<50` 或无满足覆盖率的线 → 不拟合。

5. 全局计数与污染判定（`compute_global_stats`）
- 污染点定义：`depth <= low_depth_max` 且 `depth <= slope*gc+intercept`
  （**全 GC 区间 20~95 统计，不限制 `gc >= gc_start`**；边界线自 GC=20 画至 GC=95）。
- `line_below_count`：污染点数；`line_on_count`：其余点数。
- `contam_over_total_ratio = line_below_count / total_points`。
- `contam_over_total_ratio > heavy_threshold`（默认 0.07）判定为"重度污染"。
- `below_over_on_ratio` 仅保留作兼容诊断，不参与判定。

### 第二遍：LLM 视觉复核（默认开启，`--no-llm` 关闭）

- 前置条件：脊线存在 且 全局低深度点 `>=100`，否则跳过（`status=skipped_no_signal`）。
- 把第一遍渲染的 PNG（含密度图、蓝虚线、主脊线、绿线）发给 VL 模型（`qwen3-vl-plus`），
  附上当前线参数与 `contam_over_total_ratio` 等数值上下文。
- 最多 `--llm-rounds`（默认 2）轮，单轮超时 `--llm-timeout`（默认 60s）。
- LLM 每轮输出一个 JSON，`action` 三选一：
  - `no_contamination`：图中右下没有可见污染带 → **覆盖算法结果**，最终判无污染（无线）。
  - `no_adjustment`：当前绿线已贴合污染带上沿，维持当前线。
    特殊规则：算法第一遍无线且 LLM 也不给线 → 视为无污染；
    此前轮次曾 adjust 过、本轮判定已贴合 → 最终动作记为 `adjust`（采纳已 clamp 的线）。
  - `adjust`：给出新的 `gc_start / d_left / d_right`。程序先 clamp 到可行域：
    `gc_start ∈ [20, 90]`、`depth_floor <= d_left <= d_right <= low_depth_max`，
    重算统计并重画。若提议值与当前线差异 `<0.05`，归一化为 `no_adjustment`。
- JSON 解析失败会带提示重试一次；仍失败 → `degraded_json`。
  API 异常/超时 → `degraded_error`；模块导入失败 → 同样走降级分支。
  **任何降级都回退为算法第一遍结果，不影响主流程。**
- 最终判定：`heavy_contamination = (最终 contam_over_total_ratio > heavy_threshold)`；
  LLM 判无污染时无线、无统计，直接为 False。

---

## 2. "无污染"判定的所有路径

最终 `heavy_contamination=False` 的四种情况：

1. **门控未检出**（`gc_start=None`，不拟合线）：脊线不存在 / 低深度点 `<100` /
   高脊 bin `<3` / 谷底右侧无连续超阈值 run / run 区域低深度点 `<50`。
2. **拟合失败**：检出 `gc_start` 但区域内点 `<50`，或不存在覆盖率 `>=0.9` 的线。
3. **比例不足**：线存在但 `contam_over_total_ratio <= 0.07`。
4. **LLM 否决**：LLM 返回 `no_contamination`（即使算法第一遍检出了线，也被覆盖为无污染）。

---

## 3. 主脊线与绿线的关系

图上各线（`plot_gc_depth`）：
- **橙色曲线** = 主脊线（main ridge），主物种云团的深度走势。
- **绿色实线** = 污染带上边界线（contam top），自 GC=20 画至 GC=95，附 ±eps 带宽细线。
- **蓝色水平虚线** = `Depth=low_depth_max`（低深度区上限）。
- **灰色虚线**（仅 LLM 调整过时出现）= 算法第一遍的线，供对照。
- 早期的绿色竖直点线（gc_start 标记）已移除，`gc_start` 仅作内部锚点/门控。

依赖关系：
1. 主脊线先定位主云团；污染表现为主脊线**峰值右侧**、蓝线以下的一条低深度富集带。
2. `gc_start` 在高脊区间内依据 `low_ratio` 陡升检出，即污染带在脊线视角下的 GC 起点。
3. 绿线以 `gc_start` 为左端点锚点（`d_left` = 线在 `GC=gc_start` 处的深度），
  对 `[gc_start, 95]` 区域内的低深度点拟合上包络得到。
4. 最终计数时绿线作用于**全 GC 区间**（20~95），`gc_start` 不再限制统计范围。

---

## 4. 输出内容

1. JSON（默认 `outputs/gc_line/<样本名>.gc_line.json`）
- `input`：输入路径与清洗后有效点数
- `params`：本次运行的全部参数（含 LLM 开关/轮数/超时）
- `ridge`：主脊线摘要（是否存在、GC 范围、峰值位置与深度、使用 bin 数）
- `fit`：**最终**边界线（LLM 调整后；`exists/slope/intercept/gc_start/d_left/d_right/coverage` 等）
- `global_stats`：最终统计（污染点数、污染占总点数比例、诊断带宽计数）；LLM 判无污染时为 null
- `decision`：`heavy_contamination` 与 `reason`（含 LLM 复核/降级说明）
- `llm_adjustment`：状态/轮数/最终动作，以及 `rounds_detail`
  （逐轮精简摘要：action/reason/提议值/clamp 值/统计变化，不含 prompt 原文；
  与 `artifacts.png_steps` 通过 `png_step_index` 互链）
- `artifacts.png_steps`：每步的 `index/stage/label/png/line/contam_over_total_ratio`，
  `stage` 取值 `algo`（第一遍）/`llm_round`（LLM 第 N 轮调整）/`final`（最终帧）

2. PNG
- 终帧：`outputs/gc_line/<样本名>.gc_line.png`（即 `artifacts.png`，向后兼容）
- 演进步骤快照：`<样本名>.gc_line.step{N}.png`（每次渲染各保留一张，重跑前自动清理旧快照）
- 图内容：
  - GC-Depth 二维密度图（hexbin，高密度偏红，colorbar 为 log10 点数）
  - `Depth=low_depth_max` 蓝色参考虚线
  - 橙色主脊线
  - 绿色污染区上边界线（自 GC=20 画至 GC=95）与带宽（±eps）

3. LLM 调试日志 `<样本名>.gc_line.llm_log.json`（仅 LLM 实际运行时生成）
- 逐轮完整记录：prompt / 原始响应 / 解析结果 / 提议值 / clamp 值 / 统计变化 / usage / 耗时。

---

## 5. 关键参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--low-depth-max` | `12.0` | 低深度搜索区上限（蓝虚线） |
| `--heavy-threshold` | `0.07` | 重度污染阈值，作用于 `contam_over_total_ratio` |
| `--min-coverage` | `0.9` | 边界线覆盖率下限（区域低深度点位于线下的比例） |
| `--depth-floor` | `2.0` | 端点深度下限（避开 depth≈0 伪迹） |
| `--depth-step` | `0.5` | 端点深度网格步长 |
| `--line-eps` | `0.4` | 诊断带宽阈值（仅诊断统计与绘图，不参与判定） |
| `--gc-grid` | `0.5` | GC 分箱步长 |
| `--smooth-sigma` | `2.0` | 主脊线平滑强度 |
| `--no-llm` | 关 | 关闭 LLM 视觉复核（默认开启） |
| `--llm-rounds` | `2` | LLM 复核最大轮数 |
| `--llm-timeout` | `60.0` | 单轮 LLM 调用超时秒数 |
| `--plot-depth-max` | 自动 | 绘图 y 轴上限；默认取 depth 99.5 分位 |

边界线的选择逻辑：在所有满足覆盖率 `>= min_coverage` 的候选线中取**最低的线**
（`d_left + d_right` 最小），即尽量压低边界以只盖住污染带，而不是追求斜率大小。
斜率由端点搜索自然决定，不存在"越大越好"的说法。

调参建议：
- 若污染带检出不足：可降低 `--min-coverage`（如 0.85）或降低 `--depth-floor`。
- 若误检/线偏高切入主云：提高 `--min-coverage`（如 0.95），或结合 LLM 复核纠偏。

---

## 6. 关键概念

1. 边界线（contamination top line）
- 形式：`depth = slope * gc + intercept`，由端点 `(gc_start, d_left)` 与 `(95, d_right)` 确定。
- 只在 `Depth<=low_depth_max` 的区域内搜索拟合，但用于全 GC 区间统计。

2. 残差（residual）
- 定义：`d = depth - min(slope*gc + intercept, low_depth_max)`。
- `d<=0` 且 `depth<=low_depth_max` → 污染点。

3. `below` 与 `on`（最终判定口径）
- `line_below_count`：污染点数（线下且低深度，全 GC 区间）。
- `line_on_count`：其余点数。
- 判定比值：`contam_over_total_ratio = below / total`（`>0.07` 判重度污染）。
- `below_over_on_ratio = below / on` 仅保留作兼容诊断。

4. `eps`（诊断口径）
- `eps` 即 `--line-eps`，对 `depth<=low_depth_max` 的点额外输出窄带诊断字段：
  - `diagnostic_on_band_count`：`|d|<=eps`
  - `diagnostic_below_band_count`：`d<-eps`
  - `diagnostic_above_band_count`：`d>eps`
- 用于理解"线附近厚度"，不参与最终污染判定。

5. LLM 复核状态（`llm_adjustment.status`）
- `disabled`：`--no-llm` 关闭。
- `skipped_no_signal`：脊线不存在或低深度点 `<100`，跳过。
- `ok_no_contamination`：LLM 判定无污染（含"算法无线且 LLM 不给线"）。
- `ok_no_adjustment`：维持算法第一遍线。
- `ok_adjusted`：采纳 LLM 调整后的线。
- `degraded_json` / `degraded_error`：解析失败/API 异常，降级为算法第一遍结果。

---

## 7. 详细示例：边界线是怎么找到的

用"简化小样本"说明当前流程。假设 `low_depth_max=12`。

1. 主脊线：各 GC bin 主云团主峰连成橙色曲线，设峰值在 `GC≈45`，峰值右侧脊线仍显著高于蓝线。

2. 检测 `gc_start`：在高脊 bin 内统计各 bin 低深度点比例，
   谷底在 `GC=45`（比例 0.05）；阈值 = `max(0.05+0.15, 0.15)=0.20`。
   从 `GC=45` 向右，`GC=60~68` 连续 bin 比例 `>=0.20` → run 左端 `gc_start=60`，
   右端按半阈值（0.10）容差扩展到 `GC=72`。

3. 端点网格搜索：在 `d_left, d_right ∈ {2.0, 2.5, ..., 12.0}` 且 `d_left<=d_right` 上枚举。
   对每条候选线统计区域 `[60, 95]` 内低深度点的覆盖率。
   - 候选 A：`d_left=4.0, d_right=5.5`，覆盖率 0.83（线太低，没盖住带顶）→ 不满足。
   - 候选 B：`d_left=5.0, d_right=6.5`，覆盖率 0.93 → 满足。
   - 候选 C：`d_left=6.0, d_right=7.0`，覆盖率 0.97 → 满足但更高。
   取满足覆盖率 `>=0.9` 中 `d_left+d_right` 最小的候选 B：
   `slope = (6.5-5.0)/(95-60) ≈ 0.0429`，`intercept = 5.0 - 0.0429*60 ≈ 2.43`。

4. 全局统计：对全体点（GC 20~95）计算，污染点 = `depth<=12` 且落在线下。
   设污染点 9000、总点数 120000 → `contam/total = 0.075 > 0.07` → 重度污染。

5. LLM 复核：看图后若认为绿线横穿了污染带中部，返回 `adjust` 并给出更低的端点；
   clamp 到可行域后重算重画；若认为根本没有污染带，返回 `no_contamination`，
   最终判无污染（即使第 4 步算法判了重度污染）。

开发调试建议：
- 先看 `fit.exists` 与 `fit.coverage` 是否达标，`contam_gc_start` 是否落在污染带左缘。
- 再看 `diagnostic_on_band_count`、`diagnostic_below_band_count` 判断线附近"厚度"是否符合直觉。
- 最后看 `contam_over_total_ratio` 与 `decision.reason` 做业务判定；
  LLM 参与的样本务必看 `llm_adjustment.rounds_detail` 与 `.llm_log.json`。

---

## 8. 使用示例

```bash
conda run -n zhurui_agent python gc_depth_line_judge.py \
  --pos data/shenshaoqi_data/survey1/X101SC2502/X101SC25021371-Z03-J001/尾肌-1-1/尾肌-1-1.pos
```

自定义输出路径：

```bash
conda run -n zhurui_agent python gc_depth_line_judge.py \
  --pos /path/to/sample.pos \
  --out-json /path/to/result.json \
  --out-png /path/to/result.png
```

关闭 LLM 复核（只跑确定性算法）：

```bash
conda run -n zhurui_agent python gc_depth_line_judge.py \
  --pos /path/to/sample.pos --no-llm
```

### 批量
```bash
# 推荐：使用仓库内脚本（可复用）
bash scripts/run_gc_line_batch.sh

# 指定目录（可选）
bash scripts/run_gc_line_batch.sh data/survey_nt_correct_20260421

# 指定目录 + 指定日志（可选）
bash scripts/run_gc_line_batch.sh data/survey_nt_correct_20260421 outputs/gc_line_batch_20260422.log
```

如果你想临时一行命令执行，也可以用下面这个版本（已处理软链接 `.pos`）：

```bash
set -euo pipefail
base_dir='data/survey_nt_correct_20260421'
log='outputs/gc_line_batch_20260422.log'
mkdir -p outputs
: > "$log"
processed=0
failed=0

while IFS= read -r -d '' pos; do
  dir=$(dirname "$pos")
  stem=$(basename "$pos" .pos)
  out_json="$dir/${stem}.gc_line.json"
  out_png="$dir/${stem}.gc_line.png"
  echo "[RUN] $pos" | tee -a "$log"
  if conda run -n zhurui_agent python gc_depth_line_judge.py \
      --pos "$pos" \
      --out-json "$out_json" \
      --out-png "$out_png" >> "$log" 2>&1; then
    processed=$((processed+1))
  else
    failed=$((failed+1))
    echo "[FAIL] $pos" | tee -a "$log"
  fi
  if [ $(( (processed+failed) % 10 )) -eq 0 ]; then
    echo "[PROGRESS] done=$((processed+failed)) processed=$processed failed=$failed" | tee -a "$log"
  fi
done < <(find "$base_dir" \( -type f -o -type l \) -name '*.pos' -print0)

echo "[SUMMARY] processed=$processed failed=$failed log=$log" | tee -a "$log"
```
