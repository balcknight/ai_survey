## GC-Depth 主脊线 + 右下污染区域判定方案

脚本文件：`gc_depth_line_judge.py`

用途：
- 输入 `.pos` 原始数据（第3列 GC，第4列 Depth）。
- 先在全局点云上估计主云团的 GC-Depth 主脊线。
- 再在 `Depth<=low_depth_max` 的蓝线以下，自动寻找主峰右侧的低深度污染区域，并拟合其上边界直线。
- 最终按“污染区域点数 / 总点数”判定是否为重度污染。

---

## 1. 算法实现方法

1. 数据读取与清洗
- 读取 `.pos` 第3列（GC）和第4列（Depth）。
- 保留有效数值点，并限制 `20<=GC<=95`、`Depth>=0`。

2. 主脊线估计
- 按 GC 分箱统计深度分布，优先在 `Depth>low_depth_max` 的主云团中寻找每个 GC bin 的主峰深度。
- 对各 bin 主峰做插值和平滑，得到 `main_depth(gc)` 主脊线。

3. 右下污染区域定位
- 只看 `Depth<=low_depth_max` 的点。
- 在主脊线峰值右侧，统计各 GC bin 的低深度点比例。
- 自动找到低深度点显著富集的一段 GC 区间，视为候选污染区。

4. 污染区上边界拟合
- 对候选污染区内的低深度点，按 GC bin 取高分位深度作为“上包络”。
- 对这些上包络点做加权直线拟合，得到污染区上边界：
  `depth = slope * gc + intercept`

5. 全局计数与污染判定
- 污染点定义为：
  `gc >= contam_gc_start` 且 `depth <= low_depth_max` 且 `depth <= slope*gc+intercept`
- `line_below_count`：污染区域内点数。
- `line_on_count`：非污染区域点数。
- `contam_over_total_ratio = line_below_count / total_points`。
- `below_over_on_ratio = line_below_count / line_on_count` 仅保留作兼容诊断。
- 当 `contam_over_total_ratio > heavy_threshold`（默认0.07）判定为“重度污染”。

---

## 2. 输出内容

1. JSON（默认 `outputs/gc_line/<样本名>.gc_line.json`）
- 输入信息与有效点数
- 核心参数
- 主脊线摘要（`ridge`）
- 拟合结果（是否存在线、`slope/intercept` 等）
- 全局统计（污染区点数、污染占总点数比例、诊断带宽计数）
- 判定结果（`heavy_contamination`）

2. PNG（默认 `outputs/gc_line/<样本名>.gc_line.png`）
- GC-Depth 二维密度图（高密度偏红）
- `Depth=low_depth_max` 参考虚线
- 主脊线
- 污染区上边界线与带宽（±eps）
- 污染区 GC 起点

---

## 3. 关键参数说明

常用参数：
- `--low-depth-max`：低深度搜索区上限，默认 `10`。
- `--line-eps`：`eps`，线附近带宽阈值，默认 `0.4`（仅用于拟合阶段侧边计数与诊断统计，不用于最终分母定义）。
- `--heavy-threshold`：重度污染阈值，默认 `0.07`，作用于 `contam_over_total_ratio`。
- `--gc-grid`：GC 分箱步长。
- `--smooth-sigma`：主脊线平滑强度。
- 其余历史参数仍保留在 CLI 中做兼容，但当前实现不再依赖旧的双峰分割逻辑。

建议：
- 若线检出过少：可适当降低 `--min-separation`（如0.30）或 `--min-balance`（如0.08）。
- 若误检较多：可提高 `--min-separation`（如0.40）并适度增大 `--line-eps`（如0.5）。

---

## 4. 关键概念

1. 分割线（split line）
- 形式：`depth = slope * gc + intercept`。
- 这条线只在 `Depth<=10` 区域搜索得到，但用于全局统计。

2. 残差（residual）
- 定义：`d = depth - (slope*gc + intercept)`。
- `d<0` 在线下，`d>=0` 在线上或线本身。

3. `below` 与 `on`（最终判定口径）
- `line_below_count`：`d < 0`（整条线下方所有点）。
- `line_on_count`：`d >= 0`（线本身及线上方所有点）。
- 判定比值：`below_over_on_ratio = below / on`。

4. `eps`（诊断口径）
- `eps` 即 `--line-eps`。
- 脚本会额外输出窄带诊断字段：
  - `diagnostic_on_band_count`：`|d|<=eps`
  - `diagnostic_below_band_count`：`d<-eps`
  - `diagnostic_above_band_count`：`d>eps`
- 这些字段用于理解“线附近厚度”，不参与最终污染判定。

---

## 5. 关于“斜率是否越大越好”

结论：不一定。  
在当前示例样本（`尾肌-1-1.pos`）上，自动搜索给出的 `slope=0.08` 仍是综合分离度最优；提升斜率并未带来更好的分离评分。

实操建议：
- 保持默认自动搜索，让算法按分离评分选择最优直线。

---

## 6. 详细示例：分割线是怎么找到的

下面用一个“简化小样本”说明流程，帮助开发者理解代码在做什么。

示例低深度点（`Depth<=10`）：

| GC | Depth |
|---|---|
| 30 | 3.2 |
| 32 | 3.5 |
| 34 | 4.0 |
| 36 | 4.4 |
| 38 | 5.0 |
| 42 | 6.3 |
| 44 | 6.8 |
| 46 | 7.2 |
| 48 | 7.8 |
| 50 | 8.1 |

这些点可粗看成两条带：
- 下带：大致在 `Depth ≈ 0.10*GC + 0.2` 附近。
- 上带：大致在 `Depth ≈ 0.10*GC + 2.0` 附近。

算法步骤：

1. 扫描斜率 `m`
- 比如先试 `m=0.08`，再试 `m=0.10`，再试 `m=0.12`。

2. 对每个斜率算残差 `r = depth - m*gc`
- 以 `m=0.10` 为例：
  - 点 `(30,3.2)` 的 `r = 3.2 - 3.0 = 0.2`
  - 点 `(44,6.8)` 的 `r = 6.8 - 4.4 = 2.4`
- 这时 `r` 会聚成两团（约 `0.3` 一团、`2.2` 一团），在直方图上表现为“双峰”。

3. 找双峰之间的“谷值”并反推截距 `b`
- 若谷值在 `r=1.2`，则分割线是：
- `depth = 0.10 * gc + 1.2`
- 直观理解：`r` 小于 1.2 的点在线下侧，大于 1.2 的点在线上侧。

4. 给这条线打分（是否“分得开”）
- `separation`：两峰比谷底高多少（峰谷对比）。
- `balance`：线两侧点是否都够多（避免把点都分到一边）。
- `score = separation * balance`。

5. 在所有 `m` 的候选线里取 `score` 最大
- 这就是最终自动找到的分割线（`slope/intercept`）。

6. 用最终线做全局统计（不再限制 `Depth<=10`）
- 对全体点计算 `d = depth - (slope*gc + intercept)`。
- `below = count(d<0)`，`on = count(d>=0)`。
- `ratio = below/on`，若 `ratio > 0.25` 则判重度污染。

开发调试建议：
- 先看 `fit.separation` 和 `fit.balance` 是否达标。
- 再看 `diagnostic_on_band_count`、`diagnostic_below_band_count` 判断线附近“厚度”是否符合直觉。
- 最后再看 `below_over_on_ratio` 做业务判定，避免仅凭视觉误判。

---

## 7. 使用示例

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
