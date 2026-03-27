"""
峰检测过滤排查脚本：逐步展示 detect_peaks 中每个过滤阶段的结果，
用于定位某个峰在哪一步被过滤掉。

用法:
    python tests/debug_peak_filter.py <SpeFreq.cut 或 NumFreq.cut 文件路径> [depth_min] [depth_max]

示例:
    python tests/debug_peak_filter.py /data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2505/X101SC25052754-Z01-J003/FDSW250015639-1r_Z119/Z119.17merFreq.SpeFreq.cut
    python tests/debug_peak_filter.py /path/to/YB.17merFreq.SpeFreq.cut 3 300
"""
import sys
import pandas as pd
import numpy as np
from scipy.signal import find_peaks, savgol_filter


def debug_peak_filter(filepath, depth_min=3, depth_max=300,
                      smooth_window=11, smooth_poly=3,
                      prominence_ratio=0.04, min_distance=10,
                      min_width=15):
    # 加载数据
    df = pd.read_csv(filepath, sep=r'\s+', header=None, names=['Depth', 'Frequency'])
    df['Depth'] = pd.to_numeric(df['Depth'], errors='coerce')
    df['Frequency'] = pd.to_numeric(df['Frequency'], errors='coerce')
    df = df.dropna()
    df = df[(df['Depth'] >= depth_min) & (df['Depth'] <= depth_max)]
    df = df.sort_values('Depth').reset_index(drop=True)

    freq = df['Frequency'].values.astype(float)
    depth = df['Depth'].values
    freq_smooth = savgol_filter(freq, window_length=smooth_window, polyorder=smooth_poly)

    print(f"数据文件: {filepath}")
    print(f"数据范围: depth {depth_min}-{depth_max}, 共 {len(df)} 个点\n")

    # 第一步：find_peaks 候选峰
    peaks_idx, properties = find_peaks(freq_smooth, distance=min_distance, prominence=0, width=0)
    print(f"=== 第一步: find_peaks 候选峰 ({len(peaks_idx)} 个) ===")
    for i, idx in enumerate(peaks_idx):
        print(f"  idx={idx}, depth={depth[idx]}, freq={freq_smooth[idx]:.0f}, "
              f"prominence={properties['prominences'][i]:.0f}")

    # 第二步：prominence + 频率比例过滤
    if len(peaks_idx) > 0:
        prominences = properties['prominences']
        max_prominence = prominences.max()
        max_peak_freq = freq_smooth[peaks_idx].max()
        mask = ((prominences >= max_prominence * prominence_ratio) &
                (freq_smooth[peaks_idx] >= max_peak_freq * prominence_ratio))

        print(f"\n=== 第二步: prominence 过滤 (ratio={prominence_ratio}, "
              f"max_prom={max_prominence:.0f}, max_freq={max_peak_freq:.0f}) ===")
        for i, idx in enumerate(peaks_idx):
            prom = prominences[i]
            fq = freq_smooth[idx]
            status = 'PASS' if mask[i] else 'FAIL'
            reason = []
            if prom < max_prominence * prominence_ratio:
                reason.append(f"prom_ratio={prom / max_prominence:.4f}<{prominence_ratio}")
            if fq < max_peak_freq * prominence_ratio:
                reason.append(f"freq_ratio={fq / max_peak_freq:.4f}<{prominence_ratio}")
            reason_str = f" ({', '.join(reason)})" if reason else ""
            print(f"  depth={depth[idx]}, prom={prom:.0f}, freq={fq:.0f} -> {status}{reason_str}")

        peaks_after_prom = peaks_idx[mask]
    else:
        peaks_after_prom = peaks_idx

    # 第三步：宽度过滤
    print(f"\n=== 第三步: 宽度过滤 (min_width={min_width}) ===")
    valid_peaks = []
    for idx in peaks_after_prom:
        left = idx
        while left > 0 and freq_smooth[left - 1] < freq_smooth[left]:
            left -= 1
        right = idx
        while right < len(freq_smooth) - 1 and freq_smooth[right + 1] < freq_smooth[right]:
            right += 1
        width = right - left
        status = 'PASS' if width >= min_width else 'FAIL'
        print(f"  depth={depth[idx]}, left=depth {depth[left]}, right=depth {depth[right]}, "
              f"width={width} -> {status}")
        if width >= min_width:
            valid_peaks.append(idx)

    # 第四步：肩峰检测
    peaks_idx_arr = np.array(valid_peaks, dtype=int)
    print(f"\n=== 第四步: 肩峰检测 ===")
    if len(freq_smooth) > smooth_window:
        d1 = np.gradient(freq_smooth)
        d1_smooth = savgol_filter(d1, window_length=smooth_window, polyorder=smooth_poly)
        neg_d1 = -d1_smooth
        shoulder_candidates, _ = find_peaks(neg_d1, distance=min_distance)
        global_max_freq = freq_smooth.max()
        shoulder_min_freq_ratio = 0.3

        max_d1 = d1_smooth.max()
        shoulder_min_d1_ratio = 0.30

        print(f"  候选肩峰点: {len(shoulder_candidates)} 个 (max_d1={max_d1:.0f}, d1阈值={max_d1 * shoulder_min_d1_ratio:.0f})")
        for s_idx in shoulder_candidates:
            reasons = []
            passed = True
            if d1_smooth[s_idx] <= 0:
                reasons.append("非上升段(d1<=0)")
                passed = False
            if d1_smooth[s_idx] > 0 and d1_smooth[s_idx] < max_d1 * shoulder_min_d1_ratio:
                reasons.append(f"导数过小(d1={d1_smooth[s_idx]:.0f}<{max_d1 * shoulder_min_d1_ratio:.0f})")
                passed = False
            if freq_smooth[s_idx] < global_max_freq * shoulder_min_freq_ratio:
                reasons.append(f"频率过低({freq_smooth[s_idx]:.0f}<{global_max_freq * shoulder_min_freq_ratio:.0f})")
                passed = False
            if len(peaks_idx_arr) > 0 and np.min(np.abs(peaks_idx_arr - s_idx)) < min_distance:
                reasons.append("与已有峰太近")
                passed = False

            # 只打印有一定频率的候选点（过滤噪声）
            if freq_smooth[s_idx] >= global_max_freq * 0.05:
                status = 'PASS' if passed else 'FAIL'
                reason_str = f" ({', '.join(reasons)})" if reasons else ""
                print(f"  depth={depth[s_idx]}, freq={freq_smooth[s_idx]:.0f}, "
                      f"d1={d1_smooth[s_idx]:.0f} -> {status}{reason_str}")

            if passed:
                peaks_idx_arr = np.append(peaks_idx_arr, s_idx)

        peaks_idx_arr = np.sort(peaks_idx_arr)

        # 第五步：平台型肩峰检测
        print(f"\n=== 第五步: 平台型肩峰检测 ===")
        for i in range(1, len(d1_smooth)):
            if d1_smooth[i - 1] > 0 and d1_smooth[i] <= 0:
                plat_idx = i - 1 if freq_smooth[i - 1] >= freq_smooth[i] else i
                reasons = []
                passed = True
                if freq_smooth[plat_idx] < global_max_freq * shoulder_min_freq_ratio:
                    reasons.append(f"频率过低({freq_smooth[plat_idx]:.0f}<{global_max_freq * shoulder_min_freq_ratio:.0f})")
                    passed = False
                if len(peaks_idx_arr) > 0 and np.min(np.abs(peaks_idx_arr - plat_idx)) < min_distance:
                    reasons.append("与已有峰太近")
                    passed = False
                # 检查右侧先降后升
                right_region = freq_smooth[plat_idx:min(plat_idx + min_distance * 2, len(freq_smooth))]
                if len(right_region) > 2:
                    min_after = right_region[1:].min()
                    max_after = right_region[1:].max()
                    if min_after >= freq_smooth[plat_idx] or max_after <= min_after:
                        reasons.append("右侧无先降后升")
                        passed = False

                if freq_smooth[plat_idx] >= global_max_freq * 0.05:
                    status = 'PASS' if passed else 'FAIL'
                    reason_str = f" ({', '.join(reasons)})" if reasons else ""
                    print(f"  depth={depth[plat_idx]}, freq={freq_smooth[plat_idx]:.0f}, "
                          f"d1[i-1]={d1_smooth[i-1]:.0f}, d1[i]={d1_smooth[i]:.0f} -> {status}{reason_str}")

                if passed:
                    peaks_idx_arr = np.append(peaks_idx_arr, plat_idx)

        peaks_idx_arr = np.sort(peaks_idx_arr)

    # 最终结果
    print(f"\n=== 最终检测到 {len(peaks_idx_arr)} 个峰 ===")
    for idx in peaks_idx_arr:
        print(f"  depth={depth[idx]}, freq={freq_smooth[idx]:.0f}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    filepath = sys.argv[1]
    depth_min = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    depth_max = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    debug_peak_filter(filepath, depth_min, depth_max)
