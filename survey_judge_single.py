"""
Survey 单样本联合判定脚本
直接调用 kmer 判断与 NT 判断，输出最终 survey 结果。
"""

from pathlib import Path
from typing import Any

import pandas as pd

from kmer_judge import main_dual
from nt_judge import judge_nt_contamination


def _find_in_sample_dir(sample_path: Path, pattern: str) -> Path | None:
    """仅在 sample_dir 内查找匹配文件（含子目录），不向上层目录扩展。"""
    candidates = sorted(sample_path.glob(f'**/{pattern}'))
    if not candidates:
        return None
    return candidates[0]


def _find_all_in_sample_dir(sample_path: Path, pattern: str) -> list[Path]:
    """仅在 sample_dir 内查找全部匹配文件（含子目录），不向上层目录扩展。"""
    return sorted(sample_path.glob(f'**/{pattern}'))


def resolve_input_files(sample_dir: str) -> dict[str, Any]:
    """输入样本目录，仅在该目录内自动定位 5 个输入文件路径。"""
    sample_path = Path(sample_dir).expanduser().resolve()
    if not sample_path.exists() or not sample_path.is_dir():
        raise FileNotFoundError(f'样本目录不存在或不是目录: {sample_path}')

    spe_file = _find_in_sample_dir(sample_path, '*.SpeFreq.cut')
    num_file = _find_in_sample_dir(sample_path, '*.NumFreq.cut')
    ntcls_file = _find_in_sample_dir(sample_path, 'all.ntcls.xls')
    ntcls_source = 'primary:all.ntcls.xls'
    if ntcls_file is None:
        ntcls_file = _find_in_sample_dir(sample_path, '*.ntcls.xls')
        ntcls_source = 'backup:*.ntcls.xls'
    ntspe_source = 'primary:*.species.xls'
    ntspe_files = _find_all_in_sample_dir(sample_path, '*.species.xls')

    if not ntspe_files:
        ntspe_source = 'backup:*.species.test.xls'
        ntspe_files = _find_all_in_sample_dir(sample_path, '*.species.test.xls')

    result_file = _find_in_sample_dir(sample_path, '*.Result.xls')

    missing = []
    if spe_file is None:
        missing.append('*.SpeFreq.cut')
    if num_file is None:
        missing.append('*.NumFreq.cut')
    if ntcls_file is None:
        missing.append('all.ntcls.xls（备选：*.ntcls.xls）')
    if not ntspe_files:
        missing.append('至少一个 *.species.xls（备选：*.species.test.xls）')
    if result_file is None:
        missing.append('*.Result.xls')

    if missing:
        raise FileNotFoundError(
            f'在目录 {sample_path} 内未找到以下文件: {", ".join(missing)}。'
            '请确认输入文件都在该目录（或其子目录）中。'
        )

    return {
        'spe_path': str(spe_file),
        'num_path': str(num_file),
        'ntcls_path': str(ntcls_file),
        'ntcls_source': ntcls_source,
        'ntspe_path': str(ntspe_files[0]),  # 兼容旧调用方
        'ntspe_paths': [str(p) for p in ntspe_files],
        'ntspe_source': ntspe_source,
        'result_path': str(result_file),
    }


def load_target_species(ntcls_path: str) -> str:
    """从 ntcls 文件第一行读取目标物种名。"""
    df_cls = pd.read_csv(ntcls_path, sep='\t')
    return str(df_cls.iloc[0]['Sample name'])


def _load_ntcls_meta(ntcls_path: str, target_species: str) -> tuple[str, str]:
    sample_name = target_species
    library_name = ''
    try:
        df_cls = pd.read_csv(ntcls_path, sep='\t')
        if not df_cls.empty:
            first = df_cls.iloc[0]
            sample_name = str(first.get('Sample name', sample_name))
            library_name = str(first.get('Library name', ''))
    except Exception:
        pass
    return sample_name, library_name


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _fmt_cat_value(name: str, value: float) -> str:
    ratio = f'{value:.4f}'.rstrip('0').rstrip('.')
    if not ratio:
        ratio = '0'
    return f'{name}({ratio})'


def _aggregate_nt_results(
    nt_results: list[dict[str, Any]],
    ntcls_path: str,
    target_species: str,
    sample_dir: str | None = None,
) -> dict[str, Any]:
    valid = [r for r in nt_results if r.get('nt_level') in ('正常', '重度污染')]
    if not valid:
        return {
            'nt_level': 'fail',
            'is_heavy_contamination': False,
            'nt_rule_version': 'nt_rule_v3_ratio_gate_multi_avg',
            'detail': '所有 NT 结果均失败，无法聚合',
            'target_species': target_species,
            'target_category': nt_results[0].get('target_category') if nt_results else None,
            'source_nt_count': len(nt_results),
            'valid_nt_count': 0,
        }

    metazoa = _mean([float(r.get('metazoa_ratio_percent', 0.0)) for r in valid])
    plantae = _mean([float(r.get('plantae_ratio_percent', 0.0)) for r in valid])
    bacteria = _mean([float(r.get('bacteria_ratio_percent', 0.0)) for r in valid])
    fungi = _mean([float(r.get('fungi_ratio_percent', 0.0)) for r in valid])
    viruses = _mean([float(r.get('viruses_ratio_percent', 0.0)) for r in valid])
    reasonable = _mean([float(r.get('reasonable_contamination_ratio_percent', 0.0)) for r in valid])

    class_ratio_map = {
        'Metazoa': metazoa,
        'Plantae': plantae,
        'Bacteria': bacteria,
        'Fungi': fungi,
        'Viruses': viruses,
    }
    dominant_category = max(class_ratio_map, key=class_ratio_map.get)
    dominant_ratio = class_ratio_map[dominant_category]
    pollution_threshold = 0.4 if dominant_ratio < 20 else 1.0
    pollution_ratio = bacteria + fungi + viruses + reasonable
    nt_level = '重度污染' if pollution_ratio > pollution_threshold else '正常'
    is_heavy = nt_level == '重度污染'

    sample_name, library_name = _load_ntcls_meta(ntcls_path, target_species)
    final_class_path = None
    if sample_dir:
        out_path = Path(sample_dir) / 'all.ntcls.xls.class.filtered.final.tsv'
        final_df = pd.DataFrame(
            [
                {
                    'Sample name': sample_name,
                    'Library name': library_name,
                    'First': _fmt_cat_value('Metazoa', metazoa),
                    'Second': _fmt_cat_value('Plantae', plantae),
                    'Third': _fmt_cat_value('Bacteria', bacteria),
                    'Fourth': _fmt_cat_value('Fungi', fungi),
                    'Fifth': _fmt_cat_value('Viruses', viruses),
                }
            ]
        )
        final_df.to_csv(out_path, sep='\t', index=False)
        final_class_path = str(out_path)

    return {
        'nt_level': nt_level,
        'is_heavy_contamination': is_heavy,
        'nt_rule_version': 'nt_rule_v3_ratio_gate_multi_avg',
        'target_species': target_species,
        'target_category': valid[0].get('target_category'),
        'source_nt_count': len(nt_results),
        'valid_nt_count': len(valid),
        'dominant_category': dominant_category,
        'dominant_ratio_percent': round(dominant_ratio, 4),
        'metazoa_ratio_percent': round(metazoa, 4),
        'plantae_ratio_percent': round(plantae, 4),
        'bacteria_ratio_percent': round(bacteria, 4),
        'fungi_ratio_percent': round(fungi, 4),
        'viruses_ratio_percent': round(viruses, 4),
        'reasonable_contamination_ratio_percent': round(reasonable, 4),
        'pollution_ratio_percent': round(pollution_ratio, 4),
        'pollution_threshold_percent': round(pollution_threshold, 4),
        'class_filtered_path': final_class_path,
        'class_filtered_paths': [r.get('class_filtered_path') for r in nt_results if r.get('class_filtered_path')],
        'small_judged_paths': [r.get('small_judged_path') for r in nt_results if r.get('small_judged_path')],
        'nt_results': nt_results,
        'ntcls_detail': (
            f'多文件聚合: 有效={len(valid)}/{len(nt_results)}; '
            f'主导大类={dominant_category}({dominant_ratio:.4f}%)'
        ),
        'ntspe_detail': (
            f'均值污染合计=细菌({bacteria:.4f}%)'
            f'+真菌({fungi:.4f}%)'
            f'+病毒({viruses:.4f}%)'
            f'+合理污染({reasonable:.4f}%)'
            f'={pollution_ratio:.4f}%; 阈值={pollution_threshold:.4f}%'
        ),
    }


def _ploidy_multiplier(pattern: str) -> int | None:
    mapping = {
        '二倍体': 1,
        '三倍体': 3,
        '四倍体': 4,
    }
    return mapping.get(pattern)


def _has_kmer_warnings(kmer_result: dict) -> bool:
    warnings = kmer_result.get('warnings') or []
    return any(str(w).strip() for w in warnings)


def _is_kmer_nt_conflict(kmer_result: dict, nt_result: dict) -> bool:
    kmer_normal = bool(kmer_result.get('is_normal', False))
    nt_level = nt_result.get('nt_level', 'fail')
    return (kmer_normal and nt_level == '重度污染') or ((not kmer_normal) and nt_level == '正常')


def _run_gc_check(sample_dir: str) -> dict[str, Any]:
    try:
        from gc_depth_line_judge import resolve_gc_input_file, run_gc_depth_line
        from backend.app.services.gc_plot import build_gc_output_paths

        gc_paths = resolve_gc_input_file(sample_dir)
        pos_path = gc_paths['pos_path']
        output_paths = build_gc_output_paths(sample_dir=sample_dir, pos_path=pos_path)
        out_json = output_paths['out_json']
        out_png = output_paths['out_png']
        gc_raw = run_gc_depth_line(pos_path=pos_path, out_json=out_json, out_png=out_png)
        decision = gc_raw.get('decision') or {}
        return {
            'executed': True,
            'status': 'ok',
            'reason': decision.get('reason', ''),
            'pos_path': pos_path,
            'heavy_contamination': bool(decision.get('heavy_contamination', True)),
            'gc_raw': gc_raw,
        }
    except Exception as exc:
        return {
            'executed': True,
            'status': 'fail',
            'reason': f'GC判定失败: {exc}',
        }


def load_and_adjust_result_metrics(result_path: str, pattern: str) -> dict:
    """读取 *.Result.xls 并按倍性规则修正基因组大小字段。"""
    required_cols = [
        '#Sample',
        'Kmer',
        'Depth',
        'n_kmer',
        'Genome_size(M)',
        'Revised_Genome_size(M)',
        'Heterozygous_rate(%)',
        'Repeat_rate(%)',
    ]
    df = pd.read_csv(result_path, sep='\t')
    if df.empty:
        raise ValueError(f'Result 文件为空: {result_path}')

    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f'Result 文件缺少字段: {", ".join(missing_cols)}; 文件: {result_path}'
        )

    row = df.iloc[0]
    multiplier = _ploidy_multiplier(pattern)

    raw_info = {
        'sample_name': str(row['#Sample']),
        'kmer': int(row['Kmer']),
        'depth': int(row['Depth']),
        'n_kmer': int(row['n_kmer']),
        'genome_size_m': float(row['Genome_size(M)']),
        'revised_genome_size_m': float(row['Revised_Genome_size(M)']),
        'heterozygous_rate_percent': float(row['Heterozygous_rate(%)']),
        'repeat_rate_percent': float(row['Repeat_rate(%)']),
    }

    adjusted = dict(raw_info)
    remark = '无法识别的倍型，未对 Genome_size(M)/Revised_Genome_size(M) 做倍数修正'
    if multiplier is not None:
        adjusted['genome_size_m'] = round(raw_info['genome_size_m'] * multiplier, 2)
        adjusted['revised_genome_size_m'] = round(raw_info['revised_genome_size_m'] * multiplier, 2)
        if multiplier == 1:
            remark = '二倍体，Genome_size(M)/Revised_Genome_size(M) 保持原值'
        else:
            remark = (
                f'{pattern}，按约定将 Genome_size(M)/Revised_Genome_size(M) 乘 {multiplier} '
                '以换算到该倍体总基因组大小'
            )

    return {
        'result_path': result_path,
        'ploidy_pattern': pattern,
        'ploidy_multiplier': multiplier,
        'raw': raw_info,
        'adjusted': adjusted,
        'remark': remark,
    }


def build_final_survey(kmer_result: dict, nt_result: dict, gc_result: dict[str, Any] | None = None) -> dict:
    """沿用 survey_judge_batch.py 的联合判定逻辑。"""
    kmer_normal = bool(kmer_result.get('is_normal', False))
    nt_level = nt_result.get('nt_level', 'fail')
    conflict_type = None
    if kmer_normal and nt_level == '重度污染':
        conflict_type = 'kmer_normal_nt_heavy'
    elif (not kmer_normal) and nt_level == '正常':
        conflict_type = 'kmer_abnormal_nt_normal'

    final = {
        'final_level': 'fail',
        'should_transfer': '否',
        'remark': '',
    }

    if _has_kmer_warnings(kmer_result):
        final['final_level'] = '待人工复核'
        final['should_transfer'] = '转人工'
        final['remark'] = 'kmer存在警告信息，转人工复核'
        return final

    if nt_level == 'fail':
        final['final_level'] = '待人工复核'
        final['should_transfer'] = '转人工'
        final['remark'] = 'NT判定失败，无法自动识别，转人工复核'
        return final

    if _is_kmer_nt_conflict(kmer_result, nt_result):
        if gc_result is None:
            final['final_level'] = '待人工复核'
            final['should_transfer'] = '转人工'
            final['remark'] = 'kmer与NT判定不一致，GC未执行，转人工复核'
            return final
        if gc_result.get('status') != 'ok':
            final['final_level'] = '待人工复核'
            final['should_transfer'] = '转人工'
            final['remark'] = gc_result.get('reason') or 'kmer与NT判定不一致，GC判定失败，转人工复核'
            return final
        if not bool(gc_result.get('heavy_contamination', True)):
            if conflict_type == 'kmer_abnormal_nt_normal':
                final['final_level'] = '待人工复核'
                final['should_transfer'] = '转人工'
                final['remark'] = 'kmer异常且NT正常，GC判定正常，转人工复核'
                return final
            final['final_level'] = '正常'
            final['should_transfer'] = '是'
            final['remark'] = 'kmer与NT判定不一致，但GC判定正常，允许流转'
            return final
        final['final_level'] = '重度污染'
        final['should_transfer'] = '否'
        final['remark'] = 'kmer与NT判定不一致，GC判定重度污染，不流转'
        return final

    if kmer_normal:
        if nt_level == '正常':
            final['final_level'] = '正常'
            final['should_transfer'] = '是'
            final['remark'] = ''
        elif nt_level == '重度污染':
            final['final_level'] = '轻度污染'
            final['should_transfer'] = '否'
            final['remark'] = 'NT判定重度污染，不建议流转'
        else:
            final['final_level'] = '待人工复核'
            final['should_transfer'] = '转人工'
            final['remark'] = f'NT判定结果异常({nt_level})，转人工复核'
    else:
        if nt_level == '正常':
            final['final_level'] = '重度污染'
            final['should_transfer'] = '否'
            final['remark'] = 'NT正常但kmer异常，不建议流转'
        else:
            final['final_level'] = '待人工复核'
            final['should_transfer'] = '转人工'
            final['remark'] = f'NT判定结果异常({nt_level})，转人工复核'

    return final


def run_single_survey(
    spe_path: str,
    num_path: str,
    ntcls_path: str,
    ntspe_path: str | None = None,
    ntspe_paths: list[str] | None = None,
    result_path: str | None = None,
    verbose: bool = True,
) -> dict:
    """执行单样本联合判定（kmer + NT），并返回汇总结果。"""
    # 统一由 ntcls 推导目标物种名，kmer/nt 都使用该物种名参与 LLM 分析与判定
    target_species = load_target_species(ntcls_path)
    result = main_dual(
        spe_filepath=spe_path,
        num_filepath=num_path,
        species_name=target_species,
        verbose=verbose
    )

    selected_ntspe_paths = list(ntspe_paths or [])
    if not selected_ntspe_paths and ntspe_path:
        selected_ntspe_paths = [ntspe_path]
    if not selected_ntspe_paths:
        raise ValueError('未提供 NT species 文件路径（至少一个）')

    nt_each: list[dict[str, Any]] = []
    for one_nt in selected_ntspe_paths:
        one_res = judge_nt_contamination(ntcls_path, one_nt, target_species)
        one_res['input_ntspe_path'] = one_nt
        nt_each.append(one_res)

    sample_dir = str(Path(ntcls_path).resolve().parent)
    nt_result = _aggregate_nt_results(
        nt_results=nt_each,
        ntcls_path=ntcls_path,
        target_species=target_species,
        sample_dir=sample_dir,
    )
    if verbose:
        print('=' * 60)
        if len(selected_ntspe_paths) > 1:
            print(
                'NT聚合说明: 检测到多个 NT species 小类文件，'
                '按各文件污染比例做算术平均后进行统一判定。'
            )
        else:
            print('NT聚合说明: 仅检测到 1 个 NT species 小类文件，直接使用单文件判定结果。')
        print(
            f"  文件数: 来源={nt_result.get('source_nt_count')}，"
            f"有效={nt_result.get('valid_nt_count')}"
        )
        print(f"  聚合细节: {nt_result.get('ntcls_detail')}")
        print(f"  污染细节: {nt_result.get('ntspe_detail')}")
        print('=' * 60)

    gc_result: dict[str, Any] = {
        'executed': False,
        'status': 'skipped',
        'reason': 'kmer与NT判定一致，未触发GC复核',
    }
    if _has_kmer_warnings(result):
        gc_result = {
            'executed': False,
            'status': 'skipped',
            'reason': 'kmer存在警告信息，按规则直接转人工，跳过GC复核',
        }
    elif _is_kmer_nt_conflict(result, nt_result):
        if verbose:
            print('=' * 60)
            print('检测到 kmer 与 NT 判定不一致，触发 GC 复核裁决。')
            print('=' * 60)
        gc_result = _run_gc_check(sample_dir)
    if verbose:
        print('=' * 60)
        print('GC复核说明:')
        print(f"  executed={gc_result.get('executed')}, status={gc_result.get('status')}")
        print(f"  reason={gc_result.get('reason')}")
        if gc_result.get('status') == 'ok':
            decision = (gc_result.get('gc_raw') or {}).get('decision') or {}
            print(
                f"  GC结论: heavy_contamination={gc_result.get('heavy_contamination')}, "
                f"判定理由={decision.get('reason')}"
            )
        print('=' * 60)

    survey_result = build_final_survey(result, nt_result, gc_result=gc_result)
    result_metrics = None
    if result_path:
        result_metrics = load_and_adjust_result_metrics(result_path, result.get('pattern', ''))

    result['target_species'] = target_species
    result['nt_result'] = nt_result
    result['gc_result'] = gc_result
    result['survey_result'] = survey_result
    result['result_metrics'] = result_metrics

    return result


def main():
    # 只需要修改样本目录（适配 VSCode 直接运行）
    sample_dir = 'data/to_zhurui_surey_jinxianlan/FDSW260017063-1r_BYL叶_1'
    verbose = True

    paths = resolve_input_files(sample_dir)
    print('自动定位输入文件:')
    print(f"  SpeFreq.cut: {paths['spe_path']}")
    print(f"  NumFreq.cut: {paths['num_path']}")
    print(f"  ntcls 来源: {paths['ntcls_source']}")
    print(f"  ntcls 文件: {paths['ntcls_path']}")
    print(f"  NT species 来源: {paths['ntspe_source']}")
    print(f"  NT species 文件数: {len(paths['ntspe_paths'])}")
    for p in paths['ntspe_paths']:
        print(f"    - {p}")
    print(f"  *.Result.xls: {paths['result_path']}")

    merged = run_single_survey(
        spe_path=paths['spe_path'],
        num_path=paths['num_path'],
        ntcls_path=paths['ntcls_path'],
        ntspe_paths=paths['ntspe_paths'],
        result_path=paths['result_path'],
        verbose=verbose,
    )

    print(merged)  # 输出完整结果字典，便于调试和验证

    print('单样本联合判定完成')
    print(f"kmer峰型: {merged.get('pattern')}, 是否正常: {merged.get('is_normal')}")
    nt = merged.get('nt_result', {})
    gc = merged.get('gc_result', {})
    survey = merged.get('survey_result', {})
    print(
        f"NT等级: {nt.get('nt_level')}, 污染合计: {nt.get('pollution_ratio_percent')}%, "
        f"阈值: {nt.get('pollution_threshold_percent')}%"
    )
    if nt.get('source_nt_count', 0) > 1:
        print(
            f"NT聚合策略: 多文件均值（来源={nt.get('source_nt_count')}，"
            f"有效={nt.get('valid_nt_count')}）"
        )
    print(
        f"GC复核: executed={gc.get('executed')}, status={gc.get('status')}, "
        f"reason={gc.get('reason')}"
    )
    print(f"综合判定: {survey.get('final_level')}, 是否流转: {survey.get('should_transfer')}")


if __name__ == '__main__':
    main()
