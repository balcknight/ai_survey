#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   bash scripts/run_gc_line_batch.sh
#   bash scripts/run_gc_line_batch.sh data/survey_nt_correct_20260421
#   bash scripts/run_gc_line_batch.sh <base_dir> <log_path>

base_dir="${1:-data/survey_nt_correct_20260421}"
log="${2:-outputs/gc_line_batch_$(date +%Y%m%d_%H%M%S).log}"

if [[ ! -d "$base_dir" ]]; then
  echo "[ERROR] 目录不存在: $base_dir" >&2
  exit 1
fi

mkdir -p "$(dirname "$log")"
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
    processed=$((processed + 1))
  else
    failed=$((failed + 1))
    echo "[FAIL] $pos" | tee -a "$log"
  fi

  if [ $(((processed + failed) % 10)) -eq 0 ]; then
    echo "[PROGRESS] done=$((processed + failed)) processed=$processed failed=$failed" | tee -a "$log"
  fi
done < <(find "$base_dir" \( -type f -o -type l \) -name '*.pos' -print0)

echo "[SUMMARY] processed=$processed failed=$failed log=$log" | tee -a "$log"
