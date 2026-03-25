import pandas as pd
import numpy as np
from scipy.signal import find_peaks, savgol_filter


def load_data(filepath, depth_min=3, depth_max=300):
    df = pd.read_csv(filepath, sep=r'\s+', header=None, names=['Depth', 'Frequency'])
    df['Depth'] = pd.to_numeric(df['Depth'], errors='coerce')
    df['Frequency'] = pd.to_numeric(df['Frequency'], errors='coerce')
    df = df.dropna()
    df = df[(df['Depth'] >= depth_min) & (df['Depth'] <= depth_max)]
    df = df.sort_values('Depth').reset_index(drop=True)
    return df


def detect_peaks(df, smooth_window=11, smooth_poly=3,
                 prominence_ratio=0.05, min_distance=10, min_width=15):
    freq = df['Frequency'].values.astype(float)
    depth = df['Depth'].values

    freq_smooth = savgol_filter(freq, window_length=smooth_window, polyorder=smooth_poly)

    # 宽松条件找候选峰，再按峰自身高度相对最高峰的比例过滤
    peaks_idx, properties = find_peaks(freq_smooth, distance=min_distance, prominence=0, width=0)
    if len(peaks_idx) > 0:
        max_peak_freq = freq_smooth[peaks_idx].max()
        peaks_idx = peaks_idx[freq_smooth[peaks_idx] >= max_peak_freq * prominence_ratio]

    # 计算峰宽度并过滤（从峰顶向两侧查找局部最小值）
    valid_peaks = []
    for idx in peaks_idx:
        # 左侧：从峰顶向左移动，直到频率不再递减（达到局部谷底）
        left = idx
        while left > 0 and freq_smooth[left - 1] < freq_smooth[left]:
            left -= 1

        # 右侧：从峰顶向右移动，直到频率不再递减（达到局部谷底）
        right = idx
        while right < len(freq_smooth) - 1 and freq_smooth[right + 1] < freq_smooth[right]:
            right += 1

        width = right - left
        if width >= min_width:
            valid_peaks.append(idx)

    peaks_idx = np.array(valid_peaks)

    # 峰型异常检测：检查左侧鞍部是否过高
    abnormal_flags = []
    for i, idx in enumerate(peaks_idx):
        peak_freq = freq_smooth[idx]
        # 找峰左侧的局部最小值（鞍部）
        left_min = freq_smooth[:idx].min() if idx > 0 else 0

        # 左侧鞍部占峰高度比例过高则标记为异常
        if peak_freq > 0:
            left_ratio = left_min / peak_freq
            abnormal_flags.append(left_ratio > 0.9)  # 左侧鞍部超过峰高90%视为异常
        else:
            abnormal_flags.append(False)

    peak_depths = depth[peaks_idx]
    peak_freqs = freq_smooth[peaks_idx]
    return peak_depths, peak_freqs, abnormal_flags


def _match_ratios(actual_ratios, expected_ratios, tolerance):
    for a, e in zip(actual_ratios, expected_ratios):
        if abs(a - e) / e > tolerance:
            return False
    return True


def filter_low_depth_peak(peak_depths, peak_freqs, tolerance=0.10,
                          low_depth_threshold=10, low_peak_freq_ratio=0.6):
    """
    过滤深度<low_depth_threshold且高度不及最高峰low_peak_freq_ratio的第一个峰。
    条件：第一个峰和第二个峰不成1:2比例，且第一个峰深度<阈值，且第一个峰高度<最高峰*比例。
    """
    if len(peak_depths) < 2:
        return peak_depths, peak_freqs

    sorted_indices = np.argsort(peak_depths)
    sorted_depths = peak_depths[sorted_indices]
    sorted_freqs = peak_freqs[sorted_indices]

    first_depth = sorted_depths[0]
    second_depth = sorted_depths[1]

    # 只看第一个峰深度<阈值的情况
    if first_depth >= low_depth_threshold:
        return peak_depths, peak_freqs

    # 检查第一个峰和第二个峰是否不成1:2比例
    ratio = second_depth / first_depth
    if abs(ratio - 2) / 2 <= tolerance:
        # 成比例，不过滤
        return peak_depths, peak_freqs

    # 检查第一个峰高度是否不及最高峰的指定比例
    max_freq = peak_freqs.max()
    first_freq = sorted_freqs[0]
    if first_freq < max_freq * low_peak_freq_ratio:
        # 忽略第一个峰
        mask = sorted_indices[1:]
        return peak_depths[mask], peak_freqs[mask]

    return peak_depths, peak_freqs


def classify_peaks(peak_depths, tolerance=0.10):
    peak_depths = sorted(peak_depths)
    n = len(peak_depths)

    if n == 0:
        return 'no_peak', False, '未检测到峰'

    if n == 1:
        return 'diploid_homo', True, f'1个峰，depth={peak_depths[0]:.0f}，纯合二倍体'

    base = peak_depths[0]
    ratios = [d / base for d in peak_depths]

    PATTERNS = [
        ('diploid_hetero',    [1, 2],    '杂合二倍体'),
        ('triploid',          [1, 2, 3], '三倍体'),
        ('high_repetitive_diplo', [1, 2, 4], '高重复二倍体'),
        ('tetraploid',        [1, 2, 3, 4], '四倍体'),
    ]

    # 新逻辑：n>=2 时先检查 1:2，若不符合则检查1:4（疑似多倍体），否则直接停止
    if not _match_ratios(ratios[:2], [1, 2], tolerance):
        # 检查是否为1:4（疑似多倍体）
        if n == 2 and _match_ratios(ratios[:2], [1, 4], tolerance):
            depths_str = ', '.join(f'{d:.0f}' for d in peak_depths)
            return 'suspected_polyploid', False, f'2个峰，depth=[{depths_str}]，比值≈1:4，疑似多倍体'
        ratio_str = ':'.join(f'{r:.2f}' for r in ratios)
        depths_str = ', '.join(f'{d:.0f}' for d in peak_depths)
        return 'unknown', False, f'{n}个峰，depth=[{depths_str}]，比值={ratio_str}，不符合1:2，停止判定'

    # 先尝试更高倍体判定，triploid/high_repetitive_diplo 同步看，然后尝试 tetraploid
    best_match = None
    best_len = 0
    for name, expected, desc in PATTERNS[1:]:
        if len(expected) > n:
            continue
        if _match_ratios(ratios[:len(expected)], expected, tolerance):
            if len(expected) > best_len:
                best_match = (name, expected, desc)
                best_len = len(expected)

    if best_match is not None:
        name, expected, desc = best_match
        ratio_str = ':'.join(map(str, expected))
        depths_str = ', '.join(f'{d:.0f}' for d in peak_depths[:len(expected)])
        return name, True, f'{n}个峰，depth=[{depths_str}]，比值≈{ratio_str}，{desc}'

    # 1:2 符合，但没有更高倍体匹配 -> 视为杂合二倍体
    ratio_str = ':'.join(map(str, [1, 2]))
    depths_str = ', '.join(f'{d:.0f}' for d in peak_depths[:2])
    return 'diploid_hetero', True, f'{n}个峰，depth=[{depths_str}]，比值≈{ratio_str}，杂合二倍体（其余峰未计入判定）'



def merge_peaks(peaks1, peaks2, tolerance=0.15, low_depth_abs=8, low_depth_threshold=50):
    depths1, freqs1 = peaks1
    depths2, freqs2 = peaks2

    all_peaks = []
    for d, f in zip(depths1, freqs1):
        all_peaks.append({'depth': d, 'freq': f, 'source': 'spe'})
    for d, f in zip(depths2, freqs2):
        all_peaks.append({'depth': d, 'freq': f, 'source': 'num'})

    all_peaks.sort(key=lambda x: x['depth'])

    merged = []
    i = 0
    while i < len(all_peaks):
        current = all_peaks[i].copy()
        j = i + 1
        while j < len(all_peaks):
            # 低深度区用绝对值差，高深度区用比例容差
            if current['depth'] < low_depth_threshold:
                max_delta = low_depth_abs
            else:
                max_delta = np.ceil(tolerance * current['depth'])
            if abs(all_peaks[j]['depth'] - current['depth']) <= max_delta:
                if all_peaks[j]['freq'] > current['freq']:
                    current['freq'] = all_peaks[j]['freq']
                current['depth'] = (current['depth'] + all_peaks[j]['depth']) / 2
                current['source'] = 'both'
                j += 1
            else:
                break
        merged.append(current)
        i = j

    return merged


def main_dual(
    spe_filepath,
    num_filepath,
    depth_min=3,
    depth_max=300,
    smooth_window=11,
    smooth_poly=3,
    prominence_ratio=0.05,
    min_distance=10,
    min_width=10,
    tolerance=0.2,
    merge_tolerance=0.17,
    merge_low_depth_abs=4,
    merge_low_depth_threshold=30,
    low_depth_threshold=11,
    low_peak_freq_ratio=0.6,
    verbose=True,
):
    df_spe = load_data(spe_filepath, depth_min, depth_max)
    peak_depths_spe, peak_freqs_spe, abnormal_flags_spe = detect_peaks(
        df_spe, smooth_window, smooth_poly, prominence_ratio, min_distance, min_width
    )

    df_num = load_data(num_filepath, depth_min, depth_max)
    peak_depths_num, peak_freqs_num, abnormal_flags_num = detect_peaks(
        df_num, smooth_window, smooth_poly, prominence_ratio, min_distance, min_width
    )

    if verbose:
        print(f"SpeFreq.cut 检测到 {len(peak_depths_spe)} 个峰:")
        for d, f, ab in zip(peak_depths_spe, peak_freqs_spe, abnormal_flags_spe):
            flag = " [异常峰型，已过滤]" if ab else ""
            print(f"  depth={d:.0f}, frequency={f:.0f}{flag}")
        print(f"\nNumFreq.cut 检测到 {len(peak_depths_num)} 个峰:")
        for d, f, ab in zip(peak_depths_num, peak_freqs_num, abnormal_flags_num):
            flag = " [异常峰型，已过滤]" if ab else ""
            print(f"  depth={d:.0f}, frequency={f:.0f}{flag}")

    # 过滤异常峰后再合并
    spe_mask = np.array([not ab for ab in abnormal_flags_spe])
    num_mask = np.array([not ab for ab in abnormal_flags_num])
    peak_depths_spe_f = peak_depths_spe[spe_mask]
    peak_freqs_spe_f = peak_freqs_spe[spe_mask]
    peak_depths_num_f = peak_depths_num[num_mask]
    peak_freqs_num_f = peak_freqs_num[num_mask]

    # 在合并前对每份数据单独过滤低深度噪声峰
    peak_depths_spe_f, peak_freqs_spe_f = filter_low_depth_peak(
        peak_depths_spe_f, peak_freqs_spe_f, tolerance,
        low_depth_threshold, low_peak_freq_ratio
    )
    peak_depths_num_f, peak_freqs_num_f = filter_low_depth_peak(
        peak_depths_num_f, peak_freqs_num_f, tolerance,
        low_depth_threshold, low_peak_freq_ratio
    )

    if verbose:
        print(f"\n单独过滤低深度峰后:")
        print(f"  SpeFreq: {len(peak_depths_spe_f)} 个峰 {list(peak_depths_spe_f)}")
        print(f"  NumFreq: {len(peak_depths_num_f)} 个峰 {list(peak_depths_num_f)}")

    merged_peaks = merge_peaks(
        (peak_depths_spe_f, peak_freqs_spe_f),
        (peak_depths_num_f, peak_freqs_num_f),
        merge_tolerance,
        merge_low_depth_abs,
        merge_low_depth_threshold,
    )
    total_count = len(merged_peaks)

    if verbose:
        print(f"\n合并后总峰数: {total_count}")
        for p in merged_peaks:
            print(f"  depth={p['depth']:.0f}, frequency={p['freq']:.0f}, source={p['source']}")

    if total_count == 3:
        sorted_peaks = sorted(merged_peaks, key=lambda x: x['depth'])
        d1, d2, d3 = sorted_peaks[0]['depth'], sorted_peaks[1]['depth'], sorted_peaks[2]['depth']
        f1, f2, f3 = sorted_peaks[0]['freq'], sorted_peaks[1]['freq'], sorted_peaks[2]['freq']
        # 判断是否符合杂合二倍体模式：depth3 ≈ 2*depth1（纯合峰），且频率合理
        depth_ratio_ok = abs(d3 / d1 - 2) / 2 <= tolerance if d1 > 0 else False
        freq_ratio_ok = f3 >= f2 * 0.7
        if depth_ratio_ok and freq_ratio_ok:
            pattern = 'diploid_hetero'
            is_normal = True
            detail = f"3个峰，depth=[{d1:.0f},{d2:.0f},{d3:.0f}]，第3峰depth≈2*第1峰且频率({f3:.0f})>=第2峰*0.7，判定为杂合二倍体"
        else:
            depths = [d1, d2]
            pattern, is_normal, detail = classify_peaks(np.array(depths), tolerance)
            detail += f"（第3峰不符合杂合二倍体模式，忽略）"
    else:
        depths = [p['depth'] for p in merged_peaks]
        pattern, is_normal, detail = classify_peaks(depths, tolerance)

    print(f"\n判定结果: {pattern}")
    print(f"是否正常: {'是' if is_normal else '否'}")
    print(f"详情: {detail}")

    return {
        'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
        'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
        'merged_peaks': merged_peaks,
        'total_peak_count': total_count,
        'pattern': pattern,
        'is_normal': is_normal,
        'detail': detail,
    }


if __name__ == '__main__':
    base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2508/X101SC25083784-Z01-J001/FDSW250024085-1r_叶片1/叶片1.17merFreq'
    main_dual(
        spe_filepath=f'{base_path}.SpeFreq.cut',
        num_filepath=f'{base_path}.NumFreq.cut'
    )