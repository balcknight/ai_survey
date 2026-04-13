import pandas as pd
import numpy as np
from scipy.signal import find_peaks, peak_widths, savgol_filter

PATTERN_CN = {
    'no_peak': '未检测到峰',
    'diploid_homo': '纯合二倍体',
    'diploid_hetero': '杂合二倍体',
    'triploid': '三倍体',
    'high_repetitive_diplo': '高重复二倍体',
    'tetraploid': '四倍体',
    'unknown': '未知倍型',
    'all_peaks_too_low': '所有峰过低',
    'no_peak_detected': '未检测到峰',
    'peak_shape_abnormal': '峰型异常',
}


def to_pattern_cn(pattern):
    if '+' in pattern:
        return '+'.join(PATTERN_CN.get(p, p) for p in pattern.split('+'))
    return PATTERN_CN.get(pattern, pattern)


def load_data(filepath, depth_min=3, depth_max=300):
    df = pd.read_csv(filepath, sep=r'\s+', header=None, names=['Depth', 'Frequency'])
    df['Depth'] = pd.to_numeric(df['Depth'], errors='coerce')
    df['Frequency'] = pd.to_numeric(df['Frequency'], errors='coerce')
    df = df.dropna()
    df = df[(df['Depth'] >= depth_min) & (df['Depth'] <= depth_max)]
    df = df.sort_values('Depth').reset_index(drop=True)
    return df


def detect_peaks(df, smooth_window=11, smooth_poly=3,
                 prominence_ratio=0.04, min_distance=10, min_width=15,
                 left_min_threshold=0.33, detect_shoulder=True,
                 shoulder_min_freq_ratio=0.3, shoulder_min_d1_ratio=0.30,
                 use_smoothing=True, min_width_shoulder=6):
    freq = df['Frequency'].values.astype(float)
    depth = df['Depth'].values

    if use_smoothing:
        freq_smooth = savgol_filter(freq, window_length=smooth_window, polyorder=smooth_poly)
    else:
        freq_smooth = freq.copy()

    # 宽松条件找候选峰，再按 prominence 相对最高峰的比例过滤
    peaks_idx, properties = find_peaks(freq_smooth, distance=min_distance, prominence=0, width=0)
    if len(peaks_idx) > 0:
        prominences = properties['prominences']
        max_prominence = prominences.max()
        # 同时满足：prominence 达到最高峰 prominence 的 prominence_ratio 比例
        # 且频率达到最高峰频率的 prominence_ratio 比例
        max_peak_freq = freq_smooth[peaks_idx].max()
        mask = (prominences >= max_prominence * prominence_ratio) & \
               (freq_smooth[peaks_idx] >= max_peak_freq * prominence_ratio)
        peaks_idx = peaks_idx[mask]

    # 使用半高宽过滤窄峰：边界伪峰通常半高宽极小，真实主峰半高宽明显更大
    if len(peaks_idx) > 0:
        widths, _, _, _ = peak_widths(freq_smooth, peaks_idx, rel_height=0.5)
        peaks_idx = peaks_idx[widths >= min_width]
    else:
        peaks_idx = np.array([], dtype=int)

    # 肩峰检测：在上升段找一阶导数的局部极小值（增长减缓处）
    if detect_shoulder and len(freq_smooth) > smooth_window:
        d1 = np.gradient(freq_smooth)
        if use_smoothing:
            d1_smooth = savgol_filter(d1, window_length=smooth_window, polyorder=smooth_poly)
        else:
            d1_smooth = d1

        # 一阶导数的局部极小值 = 增长速率最慢的位置
        neg_d1 = -d1_smooth
        shoulder_candidates, _ = find_peaks(neg_d1, distance=min_distance)

        # 全局最高频率（用于高度过滤）
        global_max_freq = freq_smooth.max()

        max_d1 = d1_smooth.max()

        for s_idx in shoulder_candidates:
            # 条件1：仍在上升段（一阶导数>0）
            if d1_smooth[s_idx] <= 0:
                continue
            # 条件2：导数值足够大（排除微弱的减速点）
            if d1_smooth[s_idx] < max_d1 * shoulder_min_d1_ratio:
                continue
            # 条件3：频率高度达到全局最高峰的shoulder_min_freq_ratio（肩峰用更高阈值）
            if freq_smooth[s_idx] < global_max_freq * shoulder_min_freq_ratio:
                continue
            # 条件3：不与已有的普通峰太近
            if len(peaks_idx) > 0 and np.min(np.abs(peaks_idx - s_idx)) < min_distance:
                continue
            # 条件4：肩峰半高宽过滤（比普通峰更宽松）
            s_width, _, _, _ = peak_widths(freq_smooth, [s_idx], rel_height=0.5)
            if s_width[0] < min_width_shoulder:
                continue
            # 加入峰列表
            peaks_idx = np.append(peaks_idx, s_idx)

        # 平台型肩峰检测：找一阶导数由正变负的零交叉点（上升段中的微弱局部峰/平台）
        # 这类点 prominence 极低，普通峰检测会漏掉，但人眼可见
        for i in range(1, len(d1_smooth)):
            # 找零交叉：前一点 d1>0，当前点 d1<=0
            if d1_smooth[i - 1] > 0 and d1_smooth[i] <= 0:
                # 取零交叉附近频率较高的那个点作为平台峰位置
                plat_idx = i - 1 if freq_smooth[i - 1] >= freq_smooth[i] else i
                # 条件1：频率高度达到全局最高峰的 shoulder_min_freq_ratio
                if freq_smooth[plat_idx] < global_max_freq * shoulder_min_freq_ratio:
                    continue
                # 条件2：不与已有峰太近
                if len(peaks_idx) > 0 and np.min(np.abs(peaks_idx - plat_idx)) < min_distance:
                    continue
                # 条件3：肩峰半高宽过滤（比普通峰更宽松）
                p_width, _, _, _ = peak_widths(freq_smooth, [plat_idx], rel_height=0.5)
                if p_width[0] < min_width_shoulder:
                    continue
                # 条件4：零交叉后频率需要先下降再回升（排除单调上升中的噪声抖动）
                # 检查右侧是否存在一个局部最低点，且之后频率回升
                right_region = freq_smooth[plat_idx:min(plat_idx + min_distance * 2, len(freq_smooth))]
                if len(right_region) > 2:
                    min_after = right_region[1:].min()
                    max_after = right_region[1:].max()
                    # 需要右侧先下降（有低于平台的点）且之后回升
                    if min_after >= freq_smooth[plat_idx] or max_after <= min_after:
                        continue
                peaks_idx = np.append(peaks_idx, plat_idx)

        # 重新排序
        peaks_idx = np.sort(peaks_idx)

    # 峰型异常检测：检查主峰左侧最低点
    abnormal_flags = []
    is_abnormal = False
    if len(peaks_idx) > 0:
        # 找到主峰（最高峰）
        main_peak_idx = peaks_idx[np.argmax(freq_smooth[peaks_idx])]
        main_peak_freq = freq_smooth[main_peak_idx]

        # 找主峰左侧的最低点
        left_min = freq_smooth[:main_peak_idx].min() if main_peak_idx > 0 else 0
        left_ratio = left_min / main_peak_freq if main_peak_freq > 0 else 0

        # 使用传入的阈值判断
        is_abnormal = left_ratio > left_min_threshold

        # 所有峰共享同一个异常标记
        abnormal_flags = [is_abnormal] * len(peaks_idx)

    peak_depths = depth[peaks_idx]
    peak_freqs = freq_smooth[peaks_idx]
    return peak_depths, peak_freqs, abnormal_flags, is_abnormal


def _match_ratios(actual_ratios, expected_ratios, tolerance):
    for a, e in zip(actual_ratios, expected_ratios):
        if abs(a - e) / e > tolerance:
            return False
    return True


def filter_low_depth_peak(peak_depths, peak_freqs, tolerance=0.10,
                          low_depth_ratio=0.2, low_peak_freq_ratio=0.6):
    """
    过滤低深度污染峰。阈值为主峰深度的low_depth_ratio（默认20%）。
    条件：第一个峰和第二个峰不成1:2比例，且第一个峰深度<阈值，且第一个峰高度<最高峰*比例。
    """
    if len(peak_depths) < 2:
        return peak_depths, peak_freqs

    sorted_indices = np.argsort(peak_depths)
    sorted_depths = peak_depths[sorted_indices]
    sorted_freqs = peak_freqs[sorted_indices]

    # 动态计算阈值：主峰（频率最高的峰）深度的 low_depth_ratio
    main_peak_idx = np.argmax(peak_freqs)
    main_peak_depth = peak_depths[main_peak_idx]
    low_depth_threshold = main_peak_depth * low_depth_ratio

    first_depth = sorted_depths[0]
    second_depth = sorted_depths[1]

    # 只看第一个峰深度<=阈值的情况
    if first_depth > low_depth_threshold:
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

    # 新逻辑：n>=2 时先检查 1:2，若不符合则检查1:3和1:4（扩展范围），否则直接停止
    if not _match_ratios(ratios[:2], [1, 2], tolerance):
        # 检查是否为1:3（2.7-3.3范围）
        if n == 2 and 2.7 <= ratios[1] <= 3.3:
            depths_str = ', '.join(f'{d:.0f}' for d in peak_depths)
            return 'triploid', True, f'2个峰，depth=[{depths_str}]，比值≈1:3，三倍体'
        # 检查是否为1:4（3.5-4.2范围）
        if n == 2 and 3.5 <= ratios[1] <= 4.2:
            depths_str = ', '.join(f'{d:.0f}' for d in peak_depths)
            return 'tetraploid', True, f'2个峰，depth=[{depths_str}]，比值≈1:4，四倍体'
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
    prominence_ratio=0.009,
    min_distance=10,
    min_width=8,
    min_width_shoulder=4,
    tolerance=0.16,
    merge_tolerance=0.17,
    merge_low_depth_abs=7,
    merge_low_depth_threshold=30,
    low_depth_ratio=0.2,
    low_peak_freq_ratio=0.6,
    spe_left_min_threshold=0.75,
    num_left_min_threshold=0.6,
    shoulder_min_freq_ratio=0.25,
    all_peaks_too_low_ratio=0.15,
    use_smoothing=True,
    verbose=True,
):
    df_spe = load_data(spe_filepath, depth_min, depth_max)
    peak_depths_spe, peak_freqs_spe, abnormal_flags_spe, is_abnormal_spe = detect_peaks(
        df_spe, smooth_window, smooth_poly, prominence_ratio, min_distance, min_width, spe_left_min_threshold,
        shoulder_min_freq_ratio=shoulder_min_freq_ratio,
        use_smoothing=use_smoothing,
        min_width_shoulder=min_width_shoulder
    )

    df_num = load_data(num_filepath, depth_min, depth_max)
    peak_depths_num, peak_freqs_num, abnormal_flags_num, is_abnormal_num = detect_peaks(
        df_num, smooth_window, smooth_poly, prominence_ratio, min_distance, min_width, num_left_min_threshold,
        shoulder_min_freq_ratio=shoulder_min_freq_ratio,
        use_smoothing=use_smoothing,
        min_width_shoulder=min_width_shoulder
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
    spe_mask = np.array([not ab for ab in abnormal_flags_spe], dtype=bool)
    num_mask = np.array([not ab for ab in abnormal_flags_num], dtype=bool)
    peak_depths_spe_f = peak_depths_spe[spe_mask]
    peak_freqs_spe_f = peak_freqs_spe[spe_mask]
    peak_depths_num_f = peak_depths_num[num_mask]
    peak_freqs_num_f = peak_freqs_num[num_mask]

    # 在合并前对每份数据单独过滤低深度噪声峰
    peak_depths_spe_f, peak_freqs_spe_f = filter_low_depth_peak(
        peak_depths_spe_f, peak_freqs_spe_f, tolerance,
        low_depth_ratio, low_peak_freq_ratio
    )
    peak_depths_num_f, peak_freqs_num_f = filter_low_depth_peak(
        peak_depths_num_f, peak_freqs_num_f, tolerance,
        low_depth_ratio, low_peak_freq_ratio
    )

    if verbose:
        print(f"\n单独过滤低深度峰后:")
        print(f"  SpeFreq: {len(peak_depths_spe_f)} 个峰 {list(peak_depths_spe_f)}")
        print(f"  NumFreq: {len(peak_depths_num_f)} 个峰 {list(peak_depths_num_f)}")

    # 检测所有峰太低：最高峰频率低于全局最高值的指定比例（默认10%）
    # 全局最高值从 depth >= 10 开始计算，排除极低深度的错误 k-mer 噪声峰
    global_max_freq_spe = df_spe[df_spe['Depth'] >= 10]['Frequency'].max()
    global_max_freq_num = df_num[df_num['Depth'] >= 10]['Frequency'].max()

    if len(peak_freqs_spe_f) > 0:
        max_peak_freq_spe = peak_freqs_spe_f.max()
        if max_peak_freq_spe < global_max_freq_spe * all_peaks_too_low_ratio:
            detail = f"SpeFreq 最高峰频率({max_peak_freq_spe:.0f})低于全局最高值({global_max_freq_spe:.0f})的{all_peaks_too_low_ratio*100:.0f}%，所有峰太低"
            if verbose:
                print(f"\n判定结果: {to_pattern_cn('all_peaks_too_low')}")
                print(f"是否正常: 否")
                print(f"详情: {detail}")
            return {
                'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
                'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
                'merged_peaks': [],
                'total_peak_count': 0,
                'pattern': to_pattern_cn('all_peaks_too_low'),
                'is_normal': False,
                'detail': detail,
            }

    if len(peak_freqs_num_f) > 0:
        max_peak_freq_num = peak_freqs_num_f.max()
        if max_peak_freq_num < global_max_freq_num * all_peaks_too_low_ratio:
            detail = f"NumFreq 最高峰频率({max_peak_freq_num:.0f})低于全局最高值({global_max_freq_num:.0f})的{all_peaks_too_low_ratio*100:.0f}%，所有峰太低"
            if verbose:
                print(f"\n判定结果: {to_pattern_cn('all_peaks_too_low')}")
                print(f"是否正常: 否")
                print(f"详情: {detail}")
            return {
                'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
                'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
                'merged_peaks': [],
                'total_peak_count': 0,
                'pattern': to_pattern_cn('all_peaks_too_low'),
                'is_normal': False,
                'detail': detail,
            }

    # 如果 spe 或 num 检测到 0 个峰，直接判为异常
    if len(peak_depths_spe) == 0 or len(peak_depths_num) == 0:
        zero_source = []
        if len(peak_depths_spe) == 0:
            zero_source.append('SpeFreq')
        if len(peak_depths_num) == 0:
            zero_source.append('NumFreq')
        detail = f"{'/'.join(zero_source)} 未检测到任何峰，数据异常"
        if verbose:
            print(f"\n判定结果: {to_pattern_cn('no_peak_detected')}")
            print(f"是否正常: 否")
            print(f"详情: {detail}")
        return {
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': to_pattern_cn('no_peak_detected'),
            'is_normal': False,
            'detail': detail,
        }

    # 综合判断前检测：如果 spe 或 num 任一异常，直接判为异常
    if is_abnormal_spe or is_abnormal_num:
        abnormal_source = []
        if is_abnormal_spe:
            abnormal_source.append('SpeFreq')
        if is_abnormal_num:
            abnormal_source.append('NumFreq')
        print(f"\n判定结果: {to_pattern_cn('peak_shape_abnormal')}")
        print(f"是否正常: 否")
        print(f"详情: {'/'.join(abnormal_source)} 主峰左侧最低点过高，峰型异常")
        return {
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': to_pattern_cn('peak_shape_abnormal'),
            'is_normal': False,
            'detail': f"{'/'.join(abnormal_source)} 主峰左侧最低点过高，峰型异常",
        }

    # 顺序检测：两个峰时，如果主峰在前且比例为1:2，判为四倍体
    def check_order_tetraploid(depths, freqs, tolerance):
        if len(depths) == 2:
            # 找到频率最高的峰的索引
            max_freq_idx = np.argmax(freqs)
            # 如果主峰在前（索引0），检查比例是否为1:2
            if max_freq_idx == 0:
                ratio = depths[1] / depths[0]
                if abs(ratio - 2.0) <= tolerance * 2.0:
                    return True, f"2个峰，主峰在前，depth=[{depths[0]:.0f}, {depths[1]:.0f}]，比值≈1:2，判定为四倍体"
        return False, None

    spe_is_order_tetra, spe_order_detail = check_order_tetraploid(peak_depths_spe_f, peak_freqs_spe_f, tolerance)
    num_is_order_tetra, num_order_detail = check_order_tetraploid(peak_depths_num_f, peak_freqs_num_f, tolerance)

    # 如果两者都符合顺序四倍体，直接返回正常
    if spe_is_order_tetra and num_is_order_tetra:
        pattern = 'tetraploid'
        pattern_cn = to_pattern_cn(pattern)
        is_normal = True
        detail = f"SpeFreq与NumFreq均符合顺序四倍体。SpeFreq: {spe_order_detail}; NumFreq: {num_order_detail}"
        if verbose:
            print(f"\n顺序检测: 两者均为四倍体")
            print(f"判定结果: {pattern_cn}")
            print(f"是否正常: 是")
            print(f"详情: {detail}")
        return {
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': pattern_cn,
            'is_normal': is_normal,
            'detail': detail,
        }

    # 分别对 spe 和 num 单独判定
    spe_pattern, spe_is_normal, spe_detail = classify_peaks(list(peak_depths_spe_f), tolerance)
    num_pattern, num_is_normal, num_detail = classify_peaks(list(peak_depths_num_f), tolerance)

    if verbose:
        print(f"\n单独判定:")
        print(f"  SpeFreq: {to_pattern_cn(spe_pattern)}, 正常={spe_is_normal}, {spe_detail}")
        print(f"  NumFreq: {to_pattern_cn(num_pattern)}, 正常={num_is_normal}, {num_detail}")

    # 新逻辑：只要有一个不合格就判定为不合格
    if not spe_is_normal or not num_is_normal:
        pattern = f"{spe_pattern}+{num_pattern}"
        pattern_cn = to_pattern_cn(pattern)
        is_normal = False
        detail = f"SpeFreq或NumFreq有不合格项。SpeFreq: {spe_detail}; NumFreq: {num_detail}"
        if verbose:
            print(f"\n判定结果: {pattern_cn}")
            print(f"是否正常: 否")
            print(f"详情: {detail}")
        return {
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': pattern_cn,
            'is_normal': is_normal,
            'detail': detail,
        }

    # 两个都合格，返回正常
    pattern = spe_pattern
    pattern_cn = to_pattern_cn(pattern)
    is_normal = True
    detail = f"SpeFreq与NumFreq均合格。SpeFreq: {spe_detail}; NumFreq: {num_detail}"
    if verbose:
        print(f"\n判定结果: {pattern_cn}")
        print(f"是否正常: 是")
        print(f"详情: {detail}")

    return {
        'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
        'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
        'merged_peaks': [],
        'total_peak_count': 0,
        'pattern': pattern_cn,
        'is_normal': is_normal,
        'detail': detail,
    }


if __name__ == '__main__':
        # base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2505/X101SC25052754-Z01-J003/FDSW250015640-1r_Z260/Z260.17merFreq'
        # base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2512/X101SC25128167-Z02-J001/FDSW250056115-1r_9_1/9_1.17merFreq'
        #    左侧鞍部干掉 base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2511/X101SC25114474-Z02-J002/FDSW250056744-1r_1/1.17merFreq'


    base_path = 'data/shenshaoqi_data/survey1/X101SC2504/X101SC25045278-Z02-J002/FDES250029975-1r_TTHF/TTHF.17merFreq'
    main_dual(
        spe_filepath=f'{base_path}.SpeFreq.cut',
        num_filepath=f'{base_path}.NumFreq.cut',
        use_smoothing=True
    )
