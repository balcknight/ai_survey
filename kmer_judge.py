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
                 prominence_ratio=0.05, min_distance=10):
    freq = df['Frequency'].values.astype(float)
    depth = df['Depth'].values

    freq_smooth = savgol_filter(freq, window_length=smooth_window, polyorder=smooth_poly)

    # 宽松条件找候选峰，再按峰自身高度相对最高峰的比例过滤
    peaks_idx, properties = find_peaks(freq_smooth, distance=min_distance, prominence=0)
    if len(peaks_idx) > 0:
        max_peak_freq = freq_smooth[peaks_idx].max()
        peaks_idx = peaks_idx[freq_smooth[peaks_idx] >= max_peak_freq * prominence_ratio]

    # 峰型异常检测：检查左侧鞍部是否过高
    abnormal_flags = []
    for i, idx in enumerate(peaks_idx):
        peak_freq = freq_smooth[idx]
        # 找峰左侧的局部最小值（鞍部）
        left_min = freq_smooth[:idx].min() if idx > 0 else 0

        # 左侧鞍部占峰高度比例过高则标记为异常
        if peak_freq > 0:
            left_ratio = left_min / peak_freq
            abnormal_flags.append(left_ratio > 0.8)  # 左侧鞍部超过峰高80%视为异常
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
        ('high_hetero_diplo', [1, 2, 4], '高杂合二倍体'),
        ('tetraploid',        [1, 2, 3, 4], '四倍体'),
    ]

    for name, expected, desc in PATTERNS:
        if len(expected) != n:
            continue
        if _match_ratios(ratios, expected, tolerance):
            ratio_str = ':'.join(map(str, expected))
            depths_str = ', '.join(f'{d:.0f}' for d in peak_depths)
            return name, True, f'{n}个峰，depth=[{depths_str}]，比值≈{ratio_str}，{desc}'

    ratio_str = ':'.join(f'{r:.2f}' for r in ratios)
    depths_str = ', '.join(f'{d:.0f}' for d in peak_depths)
    return 'unknown', False, f'{n}个峰，depth=[{depths_str}]，比值={ratio_str}，不匹配已知模式'


def merge_peaks(peaks1, peaks2, tolerance=0.15):
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
        while j < len(all_peaks) and abs(all_peaks[j]['depth'] - current['depth']) <= tolerance * current['depth']:
            if all_peaks[j]['freq'] > current['freq']:
                current['freq'] = all_peaks[j]['freq']
            current['depth'] = (current['depth'] + all_peaks[j]['depth']) / 2
            current['source'] = 'both'
            j += 1
        merged.append(current)
        i = j

    return merged


def main(
    filepath,
    depth_min=3,
    depth_max=300,
    smooth_window=11,
    smooth_poly=3,
    prominence_ratio=0.01,
    min_distance=10,
    tolerance=0.2,
    verbose=True,
):
    df = load_data(filepath, depth_min, depth_max)
    peak_depths, peak_freqs, abnormal_flags = detect_peaks(
        df, smooth_window, smooth_poly, prominence_ratio, min_distance
    )

    if verbose:
        print(f"检测到 {len(peak_depths)} 个峰:")
        for d, f, ab in zip(peak_depths, peak_freqs, abnormal_flags):
            flag = " [异常峰型]" if ab else ""
            print(f"  depth={d:.0f}, frequency={f:.0f}{flag}")

    pattern, is_normal, detail = classify_peaks(peak_depths, tolerance)

    print(f"\n判定结果: {pattern}")
    print(f"是否正常: {'是' if is_normal else '否'}")
    print(f"详情: {detail}")

    return {
        'pattern': pattern,
        'is_normal': is_normal,
        'peak_depths': list(peak_depths),
        'detail': detail,
    }


def main_dual(
    spe_filepath,
    num_filepath,
    depth_min=3,
    depth_max=300,
    smooth_window=11,
    smooth_poly=3,
    prominence_ratio=0.01,
    min_distance=10,
    tolerance=0.2,
    merge_tolerance=0.15,
    verbose=True,
):
    df_spe = load_data(spe_filepath, depth_min, depth_max)
    peak_depths_spe, peak_freqs_spe, abnormal_flags_spe = detect_peaks(
        df_spe, smooth_window, smooth_poly, prominence_ratio, min_distance
    )

    df_num = load_data(num_filepath, depth_min, depth_max)
    peak_depths_num, peak_freqs_num, abnormal_flags_num = detect_peaks(
        df_num, smooth_window, smooth_poly, prominence_ratio, min_distance
    )

    if verbose:
        print(f"SpeFreq.cut 检测到 {len(peak_depths_spe)} 个峰:")
        for d, f, ab in zip(peak_depths_spe, peak_freqs_spe, abnormal_flags_spe):
            flag = " [异常峰型]" if ab else ""
            print(f"  depth={d:.0f}, frequency={f:.0f}{flag}")
        print(f"\nNumFreq.cut 检测到 {len(peak_depths_num)} 个峰:")
        for d, f, ab in zip(peak_depths_num, peak_freqs_num, abnormal_flags_num):
            flag = " [异常峰型]" if ab else ""
            print(f"  depth={d:.0f}, frequency={f:.0f}{flag}")

    merged_peaks = merge_peaks(
        (peak_depths_spe, peak_freqs_spe),
        (peak_depths_num, peak_freqs_num),
        merge_tolerance
    )
    total_count = len(merged_peaks)

    if verbose:
        print(f"\n合并后总峰数: {total_count}")
        for p in merged_peaks:
            print(f"  depth={p['depth']:.0f}, frequency={p['freq']:.0f}, source={p['source']}")

    if total_count == 3:
        sorted_peaks = sorted(merged_peaks, key=lambda x: x['depth'])
        if sorted_peaks[2]['freq'] >= sorted_peaks[1]['freq'] * 0.7:
            pattern = 'diploid_hetero'
            is_normal = True
            detail = f"3个峰，第3峰频率({sorted_peaks[2]['freq']:.0f})>=第2峰*0.7({sorted_peaks[1]['freq']*0.7:.0f})，判定为杂合二倍体"
        else:
            depths = [sorted_peaks[0]['depth'], sorted_peaks[1]['depth']]
            pattern, is_normal, detail = classify_peaks(depths, tolerance)
            detail += f"（第3峰频率{sorted_peaks[2]['freq']:.0f}<第2峰*0.7，忽略）"
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
    base_path = 'data/shenshaoqi_data/survey1/X101SC2502/V-1/V-1.17merFreq'
    main_dual(
        spe_filepath=f'{base_path}.SpeFreq.cut',
        num_filepath=f'{base_path}.NumFreq.cut'
    )
    
