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

    min_prominence = freq_smooth.max() * prominence_ratio
    peaks_idx, _ = find_peaks(freq_smooth, prominence=min_prominence, distance=min_distance)

    peak_depths = depth[peaks_idx]
    peak_freqs = freq_smooth[peaks_idx]
    return peak_depths, peak_freqs


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


def main(
    filepath,
    depth_min=3,
    depth_max=300,
    smooth_window=11,
    smooth_poly=3,
    prominence_ratio=0.05,
    min_distance=10,
    tolerance=0.10,
    verbose=True,
):
    df = load_data(filepath, depth_min, depth_max)
    peak_depths, peak_freqs = detect_peaks(
        df, smooth_window, smooth_poly, prominence_ratio, min_distance
    )

    if verbose:
        print(f"检测到 {len(peak_depths)} 个峰:")
        for d, f in zip(peak_depths, peak_freqs):
            print(f"  depth={d:.0f}, frequency={f:.0f}")

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


if __name__ == '__main__':
    main('FDES250026022-1a_Sdis/01Survey/Sdis.17merFreq.SpeFreq.cut')
