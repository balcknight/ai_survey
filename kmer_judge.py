import json
import re

import pandas as pd
import numpy as np
import requests
from scipy.signal import find_peaks, peak_widths, savgol_filter

from models.models import get_qwen_plus_llm

PATTERN_CN = {
    'no_peak': '未检测到峰',
    'diploid': '二倍体',
    'diploid_homo': '二倍体',
    'diploid_hetero': '二倍体',
    'triploid': '三倍体',
    'high_repetitive_diplo': '二倍体',
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


def normalize_ploidy_pattern(pattern):
    diploid_patterns = {'diploid', 'diploid_homo', 'diploid_hetero', 'high_repetitive_diplo'}
    if pattern in diploid_patterns:
        return 'diploid'
    return pattern


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
                 left_inflection_threshold=0.33, detect_shoulder=True,
                 shoulder_min_freq_ratio=0.3, shoulder_min_d1_ratio=0.30,
                 use_smoothing=True, min_width_shoulder=6,
                 min_width_left_of_main=3.9,
                 left_min_threshold=None, return_debug=False,
                 inflection_ignore_min_depth=True, inflection_source_df=None,
                 inflection_use_smoothing=False):
    # 兼容旧参数名：left_min_threshold
    if left_min_threshold is not None:
        left_inflection_threshold = left_min_threshold
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
        main_peak_idx = peaks_idx[np.argmax(freq_smooth[peaks_idx])]
        width_thresholds = np.full(len(peaks_idx), float(min_width))
        width_thresholds[depth[peaks_idx] < depth[main_peak_idx]] = float(min_width_left_of_main)
        peaks_idx = peaks_idx[widths >= width_thresholds]
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

    # 峰型异常检测：检查主峰左侧急降拐点频率
    abnormal_flags = []
    is_abnormal = False
    debug_info = {
        'main_peak_depth': None,
        'main_peak_freq': None,
        'left_inflection_depth': None,
        'left_inflection_freq': None,
        'left_inflection_ratio': None,
        'left_inflection_threshold': left_inflection_threshold,
        'left_inflection_method': None,
    }
    if len(peaks_idx) > 0:
        # 找到主峰（最高峰）
        main_peak_idx = peaks_idx[np.argmax(freq_smooth[peaks_idx])]
        main_peak_freq = freq_smooth[main_peak_idx]
        debug_info['main_peak_depth'] = float(depth[main_peak_idx])
        debug_info['main_peak_freq'] = float(main_peak_freq)
        if main_peak_idx > 0 and main_peak_freq > 0:
            # 低深度端急降拐点：取主峰左侧“第一个谷底拐点”（一阶导数由负转正）
            # 该定义对应“先下降后回升”的第一个转折位置，避免把上升陡段误识别为拐点
            if inflection_source_df is not None and len(inflection_source_df) > 0:
                src_depth = inflection_source_df['Depth'].values.astype(float)
                src_freq = inflection_source_df['Frequency'].values.astype(float)
                if inflection_use_smoothing and len(src_freq) >= smooth_window:
                    src_freq_smooth = savgol_filter(src_freq, window_length=smooth_window, polyorder=smooth_poly)
                else:
                    src_freq_smooth = src_freq.copy()

                main_peak_depth = depth[main_peak_idx]
                valid_mask = src_depth <= main_peak_depth
                if np.any(valid_mask):
                    left_depth = src_depth[valid_mask]
                    left_freq = src_freq_smooth[valid_mask]
                else:
                    left_depth = depth[:main_peak_idx + 1].astype(float)
                    left_freq = freq_smooth[:main_peak_idx + 1]
            else:
                left_depth = depth[:main_peak_idx + 1].astype(float)
                left_freq = freq_smooth[:main_peak_idx + 1]

            left_d1 = np.gradient(left_freq)
            left_d1_smooth = left_d1
            if use_smoothing and len(left_d1) > max(5, smooth_window):
                left_d1_smooth = savgol_filter(left_d1, window_length=smooth_window, polyorder=smooth_poly)

            search_start_idx = 1 if inflection_ignore_min_depth else 0
            inflection_idx = None

            # 优先：下降段“第一个减速拐点”（一阶导数局部极大，且导数仍为负）
            # 适配“肉眼拐点在前、谷底在后”的情况（如 depth≈25）
            d1_for_bend = left_d1_smooth.copy()
            if len(d1_for_bend) >= 7:
                bend_window = min(11, len(d1_for_bend) if len(d1_for_bend) % 2 == 1 else len(d1_for_bend) - 1)
                if bend_window >= 5:
                    d1_for_bend = savgol_filter(d1_for_bend, window_length=bend_window, polyorder=2)

            bend_candidates, _ = find_peaks(d1_for_bend, distance=max(1, min_distance // 2))
            bend_candidates = bend_candidates[bend_candidates >= max(2, search_start_idx)]
            for idx in bend_candidates:
                if idx >= len(left_freq) - 1:
                    continue
                # 仍在下降段
                if d1_for_bend[idx] >= 0:
                    continue
                # 需要相对前段最陡下降有明显“减速”
                prev_start = max(0, idx - max(6, min_distance))
                prev_min = np.min(d1_for_bend[prev_start:idx + 1])
                if prev_min < 0 and (d1_for_bend[idx] - prev_min) >= abs(prev_min) * 0.35:
                    inflection_idx = int(idx)
                    debug_info['left_inflection_method'] = 'first_deceleration_bend'
                    break

            zc_candidates = np.where((left_d1_smooth[:-1] < 0) & (left_d1_smooth[1:] >= 0))[0] + 1
            zc_candidates = zc_candidates[zc_candidates >= max(2, search_start_idx)]
            # 候选点需同时是局部最低点，排除导数抖动造成的伪拐点
            if len(zc_candidates) > 0:
                min_keep = []
                n = len(left_freq)
                for idx in zc_candidates:
                    if idx <= 0 or idx >= n - 1:
                        continue
                    if left_freq[idx] <= left_freq[idx - 1] and left_freq[idx] <= left_freq[idx + 1]:
                        min_keep.append(idx)
                zc_candidates = np.array(min_keep, dtype=int)

            # 同时收集纯局部最低点，处理“真实谷底未形成导数零交叉”的情况
            left_end_idx = len(left_freq) - 1
            local_min_candidates = []
            if left_end_idx > search_start_idx:
                for idx in range(max(1, search_start_idx), left_end_idx):
                    if left_freq[idx] <= left_freq[idx - 1] and left_freq[idx] <= left_freq[idx + 1]:
                        local_min_candidates.append(idx)

            all_candidates = np.array([], dtype=int)
            if len(zc_candidates) > 0:
                all_candidates = zc_candidates
            if len(local_min_candidates) > 0:
                all_candidates = np.unique(np.concatenate([all_candidates, np.array(local_min_candidates, dtype=int)]))

            if inflection_idx is None and len(all_candidates) > 0:
                # 从所有有效谷底中选频率最低者，避免误选后续较高谷底（如 depth=17）
                best_pos = int(np.argmin(left_freq[all_candidates]))
                inflection_idx = int(all_candidates[best_pos])
                debug_info['left_inflection_method'] = 'lowest_valley'
            elif inflection_idx is None:
                # 兜底：无有效谷底时，使用主峰左侧最低点
                if left_end_idx > search_start_idx:
                    rel_idx = int(np.argmin(left_freq[search_start_idx:left_end_idx]))
                    inflection_idx = rel_idx + search_start_idx
                else:
                    inflection_idx = 0
                debug_info['left_inflection_method'] = 'fallback_left_min'

            inflection_freq = left_freq[inflection_idx]
            inflection_depth = left_depth[inflection_idx]

            # 用同一条曲线上的主峰频率作分母，避免边界截断造成偏差
            if inflection_source_df is not None and len(inflection_source_df) > 0:
                same_depth_idx = np.where(left_depth == depth[main_peak_idx])[0]
                ref_main_freq = left_freq[int(same_depth_idx[0])] if len(same_depth_idx) > 0 else main_peak_freq
            else:
                ref_main_freq = main_peak_freq
            inflection_ratio = inflection_freq / ref_main_freq if ref_main_freq > 0 else 0

            debug_info['left_inflection_depth'] = float(inflection_depth)
            debug_info['left_inflection_freq'] = float(inflection_freq)
            debug_info['left_inflection_ratio'] = float(inflection_ratio)
            is_abnormal = inflection_ratio >= left_inflection_threshold
        else:
            is_abnormal = False

        # 所有峰共享同一个异常标记
        abnormal_flags = [is_abnormal] * len(peaks_idx)

    peak_depths = depth[peaks_idx]
    peak_freqs = freq_smooth[peaks_idx]
    if return_debug:
        return peak_depths, peak_freqs, abnormal_flags, is_abnormal, debug_info
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


def classify_peaks(peak_depths, peak_freqs=None, tolerance=0.10):
    if peak_freqs is None:
        peak_freqs = np.ones(len(peak_depths), dtype=float)
    peak_depths = np.array(peak_depths, dtype=float)
    peak_freqs = np.array(peak_freqs, dtype=float)
    sort_idx = np.argsort(peak_depths)
    peak_depths = peak_depths[sort_idx]
    peak_freqs = peak_freqs[sort_idx]
    n = len(peak_depths)

    if n == 0:
        return 'no_peak', False, '未检测到峰'

    if n == 1:
        return 'diploid_homo', True, f'1个峰，depth={peak_depths[0]:.0f}，二倍体'

    base = peak_depths[0]
    ratios = [d / base for d in peak_depths]

    PATTERNS = [
        ('diploid_hetero',    [1, 2],    '杂合二倍体'),
        ('triploid',          [1, 2, 3], '三倍体'),
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

    # 1:2:3 特判：仅三峰时，第三峰频率达到主峰40%才判三倍体，否则判二倍体
    if n == 3 and _match_ratios(ratios[:3], [1, 2, 3], tolerance):
        main_peak_freq = float(np.max(peak_freqs))
        third_peak_freq = float(peak_freqs[2])
        depths_str = ', '.join(f'{d:.0f}' for d in peak_depths[:3])
        if third_peak_freq >= main_peak_freq * 0.4:
            return 'triploid', True, (
                f'{n}个峰，depth=[{depths_str}]，比值≈1:2:3，'
                f'第三峰频率({third_peak_freq:.0f})>=主峰40%({main_peak_freq * 0.4:.0f})，判为三倍体'
            )
        return 'diploid_hetero', True, (
            f'{n}个峰，depth=[{depths_str}]，比值≈1:2:3，'
            f'第三峰频率({third_peak_freq:.0f})<主峰40%({main_peak_freq * 0.4:.0f})，判为二倍体'
        )

    # 1:2:4 特判：第三峰低于主峰50%时判二倍体，否则判四倍体
    if n >= 3 and _match_ratios(ratios[:3], [1, 2, 4], tolerance):
        main_peak_freq = float(np.max(peak_freqs))
        third_peak_freq = float(peak_freqs[2])
        depths_str = ', '.join(f'{d:.0f}' for d in peak_depths[:3])
        if third_peak_freq < main_peak_freq * 0.5:
            return 'high_repetitive_diplo', True, (
                f'{n}个峰，depth=[{depths_str}]，比值≈1:2:4，'
                f'第三峰频率({third_peak_freq:.0f})<主峰50%({main_peak_freq * 0.5:.0f})，判为二倍体'
            )
        return 'tetraploid', True, (
            f'{n}个峰，depth=[{depths_str}]，比值≈1:2:4，'
            f'第三峰频率({third_peak_freq:.0f})>=主峰50%({main_peak_freq * 0.5:.0f})，判为四倍体'
        )

    # 先尝试更高倍体判定，然后尝试 tetraploid
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

    # 1:2 符合，但没有更高倍体匹配 -> 视为二倍体
    ratio_str = ':'.join(map(str, [1, 2]))
    depths_str = ', '.join(f'{d:.0f}' for d in peak_depths[:2])
    return 'diploid_hetero', True, f'{n}个峰，depth=[{depths_str}]，比值≈{ratio_str}，二倍体（其余峰未计入判定）'


def get_main_peak_depth(peak_depths, peak_freqs):
    """返回主峰（频率最高峰）的 depth；无有效峰时返回 None。"""
    if peak_depths is None or peak_freqs is None:
        return None
    if len(peak_depths) == 0 or len(peak_freqs) == 0:
        return None
    idx = int(np.argmax(peak_freqs))
    return float(peak_depths[idx])


def is_main_peak_depth_consistent(depth_a, depth_b, tolerance_ratio=0.10):
    """主峰 depth 一致性判断：相对差值 <= tolerance_ratio 视为一致。"""
    if depth_a is None or depth_b is None:
        return False
    max_depth = max(float(depth_a), float(depth_b))
    if max_depth <= 0:
        return False
    return abs(float(depth_a) - float(depth_b)) / max_depth <= float(tolerance_ratio)


def select_pattern_peaks(peak_depths, peak_freqs, pattern, tolerance=0.10):
    """
    返回“当前判型实际使用到的峰集合”（按 depth 升序）。
    若无法可靠映射，则返回全部输入峰。
    """
    if peak_depths is None or peak_freqs is None:
        return np.array([], dtype=float), np.array([], dtype=float)

    depths = np.array(peak_depths, dtype=float)
    freqs = np.array(peak_freqs, dtype=float)
    if len(depths) == 0 or len(freqs) == 0:
        return depths, freqs

    sort_idx = np.argsort(depths)
    depths = depths[sort_idx]
    freqs = freqs[sort_idx]
    n = len(depths)
    if n == 1:
        return depths[:1], freqs[:1]

    base = depths[0]
    ratios = [d / base for d in depths]
    pat = normalize_ploidy_pattern(pattern)

    # 1:2:3 特判对应的“二倍体”
    if pat == 'diploid' and n == 3 and _match_ratios(ratios[:3], [1, 2, 3], tolerance):
        main_peak_freq = float(np.max(freqs))
        third_peak_freq = float(freqs[2])
        if third_peak_freq < main_peak_freq * 0.4:
            return depths[:3], freqs[:3]

    # 1:2:4 特判对应的“二倍体”
    if pat == 'diploid' and n >= 3 and _match_ratios(ratios[:3], [1, 2, 4], tolerance):
        main_peak_freq = float(np.max(freqs))
        third_peak_freq = float(freqs[2])
        if third_peak_freq < main_peak_freq * 0.5:
            return depths[:3], freqs[:3]

    if pat == 'triploid':
        if n == 2 and 2.7 <= ratios[1] <= 3.3:
            return depths[:2], freqs[:2]
        if n >= 3 and _match_ratios(ratios[:3], [1, 2, 3], tolerance):
            return depths[:3], freqs[:3]
        return depths, freqs

    if pat == 'tetraploid':
        if n == 2 and 3.5 <= ratios[1] <= 4.2:
            return depths[:2], freqs[:2]
        if n >= 3 and _match_ratios(ratios[:3], [1, 2, 4], tolerance):
            main_peak_freq = float(np.max(freqs))
            third_peak_freq = float(freqs[2])
            if third_peak_freq >= main_peak_freq * 0.5:
                return depths[:3], freqs[:3]
        if n >= 4 and _match_ratios(ratios[:4], [1, 2, 3, 4], tolerance):
            return depths[:4], freqs[:4]
        return depths, freqs

    # 其他二倍体判型默认使用前两峰（与 classify_peaks 主流程一致）
    if pat == 'diploid':
        return depths[:2], freqs[:2]

    return depths, freqs


def _normalize_cn_pattern(pattern_cn):
    if not isinstance(pattern_cn, str):
        return '未知倍型'
    if '+' in pattern_cn:
        return '未知倍型'
    if pattern_cn in {'二倍体', '三倍体', '四倍体'}:
        return pattern_cn
    if pattern_cn in {'未知倍型', '峰型异常', '所有峰过低', '未检测到峰'}:
        return '未知倍型'
    return '未知倍型'


_SEARCH_BASE_URL = "https://searchapi.xiaosuai.com"
_SEARCH_ACCESS_KEY = "539vFjvr2m7nwK1mvQAU"
_SEARCH_ENDPOINT = "qGFHlZVNYlphTeXO"


def _search_species_ploidy(species_name, count=5):
    url = f"{_SEARCH_BASE_URL}/search/{_SEARCH_ENDPOINT}/smart"
    headers = {"Authorization": f"Bearer {_SEARCH_ACCESS_KEY}"}
    queries = [
        f"{species_name} chromosome number ploidy",
        f"{species_name} polyploid",
    ]
    results = []
    for query in queries:
        try:
            resp = requests.get(
                url,
                params={"q": query, "count": str(count), "safeSearch": "Moderate", "mkt": "zh-CN"},
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            pages = resp.json().get("webPages", {}).get("value", [])
            for p in pages:
                results.append(
                    {
                        "title": p.get("name", ""),
                        "url": p.get("url", ""),
                        "snippet": p.get("snippet", ""),
                    }
                )
        except Exception:
            continue
    uniq = []
    seen = set()
    for x in results:
        key = x.get("url", "")
        if key and key not in seen:
            seen.add(key)
            uniq.append(x)
    return uniq[:8]


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))
    raise ValueError("无法从模型输出提取JSON")


def _to_jsonable(obj):
    """将 numpy/容器对象递归转换为可 JSON 序列化的原生类型。"""
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, np.ndarray):
        return [_to_jsonable(x) for x in obj.tolist()]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _analyze_ploidy_by_agent(species_name, result):
    if not species_name:
        return {
            "pattern": "未知倍型",
            "confidence": "低",
            "reason": "未提供物种名，无法进行物种先验联网分析。",
            "sources": [],
        }

    sources = _search_species_ploidy(species_name)
    llm = get_qwen_plus_llm()
    prompt = (
        "你是倍性分析助手。根据物种先验证据判断该物种更可能的倍型。"
        "请输出严格JSON，字段: pattern(二倍体/三倍体/四倍体/未知倍型),"
        "confidence(高/中/低), reason(简要原因), sources(数组,每项含title,url,snippet)。\n"
        f"物种: {species_name}\n"
        f"k-mer脚本结果: {json.dumps(_to_jsonable(result), ensure_ascii=False)}\n"
        f"联网检索证据: {json.dumps(_to_jsonable(sources), ensure_ascii=False)}\n"
    )
    try:
        rsp = llm.invoke(prompt)
        parsed = _extract_json(getattr(rsp, "content", str(rsp)))
        pattern = _normalize_cn_pattern(parsed.get("pattern"))
        confidence = parsed.get("confidence", "低")
        if confidence not in {"高", "中", "低"}:
            confidence = "低"
        reason = str(parsed.get("reason", "")).strip() or "未给出明确原因"
        out_sources = parsed.get("sources", [])
        if not isinstance(out_sources, list):
            out_sources = []
        return {
            "pattern": pattern,
            "confidence": confidence,
            "reason": reason,
            "sources": out_sources[:8],
        }
    except Exception as exc:
        return {
            "pattern": "未知倍型",
            "confidence": "低",
            "reason": f"agent分析失败: {exc}",
            "sources": sources[:8],
        }


def _attach_ploidy_analysis(result, tolerance, species_name=None):
    warnings = result.get('warnings', [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
        result['warnings'] = warnings

    if result.get("is_normal") is not True:
        result['analysis_ploidy'] = {
            "pattern": "未知倍型",
            "confidence": "低",
            "reason": "k-mer判定异常，已跳过物种倍型分析。",
            "sources": [],
            "enabled": False,
        }
        return result

    analysis = _analyze_ploidy_by_agent(species_name=species_name, result=result)
    analysis["enabled"] = True
    result['analysis_ploidy'] = analysis

    script_pattern = _normalize_cn_pattern(result.get('pattern'))
    analysis_pattern = _normalize_cn_pattern(analysis.get('pattern'))

    if (
        script_pattern in {'二倍体', '三倍体', '四倍体'}
        and analysis_pattern in {'二倍体', '三倍体', '四倍体'}
        and script_pattern != analysis_pattern
        and analysis.get("confidence") in {"高", "中"}
    ):
        reason = (
            f"脚本判定={script_pattern}，分析判定={analysis_pattern}，两者明显冲突。"
            f"物种先验依据: {analysis.get('reason', '')}。"
            "建议转人工复核（检查重复序列干扰、污染、样本混合或测序偏差）。"
        )
        warnings.append(reason)

    return result


def enrich_kmer_result(result, tolerance=0.16, species_name=None):
    """
    给已有的 k-mer 判定结果补充 analysis_ploidy，并在严重冲突时写入 warnings。
    """
    result_copy = dict(result)
    return _attach_ploidy_analysis(result_copy, tolerance, species_name=species_name)


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
    min_width_left_of_main=3.9,
    min_width_shoulder=4,
    tolerance=0.16,
    low_depth_ratio=0.2,
    low_peak_freq_ratio=0.6,
    spe_left_inflection_threshold=0.75,
    num_left_inflection_threshold=0.6,
    inflection_warn_margin=0.1,
    shoulder_min_freq_ratio=0.25,
    all_peaks_too_low_ratio=0.15,
    use_smoothing=True,
    verbose=True,
    spe_left_min_threshold=None,
    num_left_min_threshold=None,
    species_name=None,
    main_peak_depth_tolerance_ratio=0.10,
):
    # 兼容旧参数名：spe_left_min_threshold / num_left_min_threshold
    if spe_left_min_threshold is not None:
        spe_left_inflection_threshold = spe_left_min_threshold
    if num_left_min_threshold is not None:
        num_left_inflection_threshold = num_left_min_threshold

    df_spe = load_data(spe_filepath, depth_min, depth_max)
    # 仅用于“第一谷底拐点”检测：忽略主流程 depth_min，避免低深度边界截断导致拐点偏移
    df_spe_inflection = load_data(spe_filepath, 0, depth_max)
    peak_depths_spe, peak_freqs_spe, abnormal_flags_spe, is_abnormal_spe, spe_debug = detect_peaks(
        df_spe, smooth_window, smooth_poly, prominence_ratio, min_distance, min_width, spe_left_inflection_threshold,
        shoulder_min_freq_ratio=shoulder_min_freq_ratio,
        use_smoothing=use_smoothing,
        min_width_left_of_main=min_width_left_of_main,
        min_width_shoulder=min_width_shoulder,
        return_debug=True,
        inflection_source_df=df_spe_inflection
    )

    df_num = load_data(num_filepath, depth_min, depth_max)
    df_num_inflection = load_data(num_filepath, 0, depth_max)
    peak_depths_num, peak_freqs_num, abnormal_flags_num, is_abnormal_num, num_debug = detect_peaks(
        df_num, smooth_window, smooth_poly, prominence_ratio, min_distance, min_width, num_left_inflection_threshold,
        shoulder_min_freq_ratio=shoulder_min_freq_ratio,
        use_smoothing=use_smoothing,
        min_width_left_of_main=min_width_left_of_main,
        min_width_shoulder=min_width_shoulder,
        return_debug=True,
        inflection_source_df=df_num_inflection
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
        if spe_debug['main_peak_depth'] is not None and spe_debug['left_inflection_depth'] is not None:
            print(
                "SpeFreq 拐点调试: "
                f"主峰(depth={spe_debug['main_peak_depth']:.0f}, freq={spe_debug['main_peak_freq']:.0f}), "
                f"左侧第一拐点(depth={spe_debug['left_inflection_depth']:.0f}, freq={spe_debug['left_inflection_freq']:.0f}), "
                f"ratio={spe_debug['left_inflection_ratio']:.4f}, "
                f"threshold={spe_debug['left_inflection_threshold']:.2f}, "
                f"method={spe_debug.get('left_inflection_method')}"
            )
        if num_debug['main_peak_depth'] is not None and num_debug['left_inflection_depth'] is not None:
            print(
                "NumFreq 拐点调试: "
                f"主峰(depth={num_debug['main_peak_depth']:.0f}, freq={num_debug['main_peak_freq']:.0f}), "
                f"左侧第一拐点(depth={num_debug['left_inflection_depth']:.0f}, freq={num_debug['left_inflection_freq']:.0f}), "
                f"ratio={num_debug['left_inflection_ratio']:.4f}, "
                f"threshold={num_debug['left_inflection_threshold']:.2f}, "
                f"method={num_debug.get('left_inflection_method')}"
            )

    warnings = []

    def _append_inflection_warning(source_name, debug_info, is_abnormal):
        ratio = debug_info.get('left_inflection_ratio')
        threshold = debug_info.get('left_inflection_threshold')
        if ratio is None or threshold is None or is_abnormal:
            return
        warn_low = threshold - inflection_warn_margin
        if warn_low <= ratio < threshold:
            warnings.append(
                f"{source_name} 左侧谷底拐点比例接近阈值（ratio={ratio:.4f}, 阈值={threshold:.2f}），疑似左侧最低点偏高"
            )

    _append_inflection_warning('SpeFreq', spe_debug, is_abnormal_spe)
    _append_inflection_warning('NumFreq', num_debug, is_abnormal_num)

    if verbose and len(warnings) > 0:
        print("\n警告信息:")
        for w in warnings:
            print(f"  - {w}")

    # 过滤异常峰后，分别处理 SpeFreq 与 NumFreq
    spe_mask = np.array([not ab for ab in abnormal_flags_spe], dtype=bool)
    num_mask = np.array([not ab for ab in abnormal_flags_num], dtype=bool)
    peak_depths_spe_f = peak_depths_spe[spe_mask]
    peak_freqs_spe_f = peak_freqs_spe[spe_mask]
    peak_depths_num_f = peak_depths_num[num_mask]
    peak_freqs_num_f = peak_freqs_num[num_mask]

    # 每份数据单独过滤低深度噪声峰
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
            return _attach_ploidy_analysis({
                'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
                'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
                'spe_main_peak_depth': None,
                'num_main_peak_depth': None,
                'merged_peaks': [],
                'total_peak_count': 0,
                'pattern': to_pattern_cn('all_peaks_too_low'),
                'is_normal': False,
                'detail': detail,
                'warnings': warnings,
            }, tolerance, species_name=species_name)

    if len(peak_freqs_num_f) > 0:
        max_peak_freq_num = peak_freqs_num_f.max()
        if max_peak_freq_num < global_max_freq_num * all_peaks_too_low_ratio:
            detail = f"NumFreq 最高峰频率({max_peak_freq_num:.0f})低于全局最高值({global_max_freq_num:.0f})的{all_peaks_too_low_ratio*100:.0f}%，所有峰太低"
            if verbose:
                print(f"\n判定结果: {to_pattern_cn('all_peaks_too_low')}")
                print(f"是否正常: 否")
                print(f"详情: {detail}")
            return _attach_ploidy_analysis({
                'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
                'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
                'spe_main_peak_depth': None,
                'num_main_peak_depth': None,
                'merged_peaks': [],
                'total_peak_count': 0,
                'pattern': to_pattern_cn('all_peaks_too_low'),
                'is_normal': False,
                'detail': detail,
                'warnings': warnings,
            }, tolerance, species_name=species_name)

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
        return _attach_ploidy_analysis({
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'spe_main_peak_depth': None,
            'num_main_peak_depth': None,
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': to_pattern_cn('no_peak_detected'),
            'is_normal': False,
            'detail': detail,
            'warnings': warnings,
        }, tolerance, species_name=species_name)

    # 综合判断前检测：如果 spe 或 num 任一异常，直接判为异常
    if is_abnormal_spe or is_abnormal_num:
        abnormal_source = []
        if is_abnormal_spe:
            abnormal_source.append('SpeFreq')
        if is_abnormal_num:
            abnormal_source.append('NumFreq')
        print(f"\n判定结果: {to_pattern_cn('peak_shape_abnormal')}")
        print(f"是否正常: 否")
        print(f"详情: {'/'.join(abnormal_source)} 主峰左侧急降拐点频率过高，峰型异常")
        return _attach_ploidy_analysis({
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'spe_main_peak_depth': None,
            'num_main_peak_depth': None,
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': to_pattern_cn('peak_shape_abnormal'),
            'is_normal': False,
            'detail': f"{'/'.join(abnormal_source)} 主峰左侧急降拐点频率过高，峰型异常",
            'warnings': warnings,
        }, tolerance, species_name=species_name)

    # 分别对 spe 和 num 单独判定
    spe_pattern, spe_is_normal, spe_detail = classify_peaks(peak_depths_spe_f, peak_freqs_spe_f, tolerance)
    num_pattern, num_is_normal, num_detail = classify_peaks(peak_depths_num_f, peak_freqs_num_f, tolerance)
    spe_pattern_norm = normalize_ploidy_pattern(spe_pattern)
    num_pattern_norm = normalize_ploidy_pattern(num_pattern)

    # 主峰按“判型使用峰集合”计算：避免被未参与判型的高频峰误导
    spe_used_depths, spe_used_freqs = select_pattern_peaks(
        peak_depths_spe_f, peak_freqs_spe_f, spe_pattern, tolerance
    )
    num_used_depths, num_used_freqs = select_pattern_peaks(
        peak_depths_num_f, peak_freqs_num_f, num_pattern, tolerance
    )
    spe_main_peak_depth = get_main_peak_depth(spe_used_depths, spe_used_freqs)
    num_main_peak_depth = get_main_peak_depth(num_used_depths, num_used_freqs)

    # 只要任意一份“判型未使用全部检测峰”，且两份均判定正常，即触发主峰一致性检查
    spe_not_using_all_detected_peaks = len(spe_used_depths) < len(peak_depths_spe)
    num_not_using_all_detected_peaks = len(num_used_depths) < len(peak_depths_num)
    if (
        (spe_not_using_all_detected_peaks or num_not_using_all_detected_peaks)
        and spe_is_normal
        and num_is_normal
        and spe_main_peak_depth is not None
        and num_main_peak_depth is not None
        and not is_main_peak_depth_consistent(
            spe_main_peak_depth,
            num_main_peak_depth,
            tolerance_ratio=main_peak_depth_tolerance_ratio,
        )
    ):
        main_peak_warning = (
            f"SpeFreq 与 NumFreq 主峰位置不一致（SpeFreq={spe_main_peak_depth:.0f}, "
            f"NumFreq={num_main_peak_depth:.0f}, 容忍度={main_peak_depth_tolerance_ratio:.0%}），建议人工复核"
        )
        warnings.append(main_peak_warning)
        if verbose:
            print("\n警告信息:")
            print(f"  - {main_peak_warning}")

    if spe_pattern_norm != num_pattern_norm:
        inconsistency_warning = (
            f"SpeFreq 与 NumFreq 倍型判断不一致（SpeFreq={to_pattern_cn(spe_pattern_norm)}, "
            f"NumFreq={to_pattern_cn(num_pattern_norm)}），建议人工复核"
        )
        warnings.append(inconsistency_warning)
        if verbose:
            print("\n警告信息:")
            print(f"  - {inconsistency_warning}")

    if verbose:
        print(f"\n单独判定:")
        print(f"  SpeFreq: {to_pattern_cn(spe_pattern)}, 正常={spe_is_normal}, {spe_detail}")
        print(f"  NumFreq: {to_pattern_cn(num_pattern)}, 正常={num_is_normal}, {num_detail}")

    # 新逻辑：只要有一个不合格就判定为不合格
    if not spe_is_normal or not num_is_normal:
        pattern = f"{spe_pattern_norm}+{num_pattern_norm}" if spe_pattern_norm != num_pattern_norm else spe_pattern_norm
        pattern_cn = to_pattern_cn(pattern)
        is_normal = False
        detail = f"SpeFreq或NumFreq有不合格项。SpeFreq: {spe_detail}; NumFreq: {num_detail}"
        if verbose:
            print(f"\n判定结果: {pattern_cn}")
            print(f"是否正常: 否")
            print(f"详情: {detail}")
        return _attach_ploidy_analysis({
            'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
            'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
            'spe_main_peak_depth': spe_main_peak_depth,
            'num_main_peak_depth': num_main_peak_depth,
            'merged_peaks': [],
            'total_peak_count': 0,
            'pattern': pattern_cn,
            'is_normal': is_normal,
            'detail': detail,
            'warnings': warnings,
        }, tolerance, species_name=species_name)

    # 两个都合格，返回正常
    pattern = f"{spe_pattern_norm}+{num_pattern_norm}" if spe_pattern_norm != num_pattern_norm else spe_pattern_norm
    pattern_cn = to_pattern_cn(pattern)
    is_normal = True
    detail = f"SpeFreq与NumFreq均合格。SpeFreq: {spe_detail}; NumFreq: {num_detail}"
    if verbose:
        print(f"\n判定结果: {pattern_cn}")
        print(f"是否正常: 是")
        print(f"详情: {detail}")

    return _attach_ploidy_analysis({
        'spe_peaks': {'depths': list(peak_depths_spe), 'freqs': list(peak_freqs_spe)},
        'num_peaks': {'depths': list(peak_depths_num), 'freqs': list(peak_freqs_num)},
        'spe_main_peak_depth': spe_main_peak_depth,
        'num_main_peak_depth': num_main_peak_depth,
        'merged_peaks': [],
        'total_peak_count': 0,
        'pattern': pattern_cn,
        'is_normal': is_normal,
        'detail': detail,
        'warnings': warnings,
    }, tolerance, species_name=species_name)


if __name__ == '__main__':
        # base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2505/X101SC25052754-Z01-J003/FDSW250015640-1r_Z260/Z260.17merFreq'
        # base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2512/X101SC25128167-Z02-J001/FDSW250056115-1r_9_1/9_1.17merFreq'
        #    左侧鞍部干掉 base_path = '/data/work/zhurui/survey_rec/data/shenshaoqi_data/survey1/X101SC2511/X101SC25114474-Z02-J002/FDSW250056744-1r_1/1.17merFreq'


    base_path = '/data/work/zhurui/survey_rec/data/to_zhurui_surey_jinxianlan/FDSW260016098-2r_DaYuanYe叶-1/DaYuanYe叶-1.17merFreq'
    res = main_dual(
        spe_filepath=f'{base_path}.SpeFreq.cut',
        num_filepath=f'{base_path}.NumFreq.cut',
        use_smoothing=True
    )
    print("\n最终结果:")
    print(res)
