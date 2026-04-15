"""
Survey 单样本联合判定脚本
基于已有 kmer 结果 JSON，补充 NT 判断与最终 survey 结果。
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from nt_judge import judge_nt_contamination


def load_target_species(ntcls_path: Path) -> str:
    """从 all.ntcls.xls 第一行读取目标物种名。"""
    df_cls = pd.read_csv(ntcls_path, sep='\t')
    return str(df_cls.iloc[0]['Sample name'])


def build_final_survey(kmer_result: dict, nt_result: dict) -> dict:
    """沿用 survey_judge_batch.py 的联合判定逻辑。"""
    kmer_normal = bool(kmer_result.get('is_normal', False))
    nt_level = nt_result.get('nt_level', 'fail')
    nt_score = nt_result.get('nt_score', 0)

    final = {
        'final_level': 'fail',
        'should_transfer': '否',
        'remark': '',
    }

    if kmer_normal:
        if nt_level in ('正常', '轻度污染'):
            final['final_level'] = '正常'
            final['should_transfer'] = '是'
            final['remark'] = ''
        elif nt_level == '重度污染':
            if nt_score <= 2:
                final['final_level'] = '轻度污染'
                final['should_transfer'] = '否'
                final['remark'] = 'NT得分<=2分，不建议流转'
            else:
                final['final_level'] = '轻度污染'
                final['should_transfer'] = '是'
                final['remark'] = ''
        else:
            if nt_score >= 3:
                final['final_level'] = '轻度污染'
                final['should_transfer'] = '是'
                final['remark'] = ''
            else:
                final['final_level'] = '重度污染'
                final['should_transfer'] = '否'
                final['remark'] = 'NT得分<=2分，不建议流转'
    else:
        if nt_level == '正常':
            final['final_level'] = '重度污染'
            final['should_transfer'] = '否'
            final['remark'] = 'NT正常但kmer异常，不建议流转'
        else:
            final['final_level'] = 'fail'
            final['should_transfer'] = '否'
            final['remark'] = ''

    return final


def append_nt_and_survey(
    kmer_json_path: Path,
    ntcls_path: Path,
    ntspe_path: Path,
    output_path: Path | None = None,
) -> dict:
    """读取 kmer JSON，追加 nt_result/survey_result 字段并写回。"""
    with open(kmer_json_path, 'r', encoding='utf-8') as f:
        result = json.load(f)

    target_species = load_target_species(ntcls_path)
    nt_result = judge_nt_contamination(str(ntcls_path), str(ntspe_path), target_species)
    survey_result = build_final_survey(result, nt_result)

    result['target_species'] = target_species
    result['nt_result'] = nt_result
    result['survey_result'] = survey_result

    save_path = output_path or kmer_json_path
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(description='Survey 单样本联合判定')
    parser.add_argument(
        '--kmer-json',
        default='data/tmp_kmer_result_with_ai.json',
        help='已有 kmer 结果 JSON 路径',
    )
    parser.add_argument('--ntcls', required=True, help='all.ntcls.xls 路径')
    parser.add_argument('--ntspe', required=True, help='all.ntspe.xls 路径')
    parser.add_argument('--output', default=None, help='输出 JSON 路径，默认覆盖 --kmer-json')
    args = parser.parse_args()

    merged = append_nt_and_survey(
        kmer_json_path=Path(args.kmer_json),
        ntcls_path=Path(args.ntcls),
        ntspe_path=Path(args.ntspe),
        output_path=Path(args.output) if args.output else None,
    )

    print('单样本联合判定完成')
    print(f"kmer峰型: {merged.get('pattern')}, 是否正常: {merged.get('is_normal')}")
    nt = merged.get('nt_result', {})
    survey = merged.get('survey_result', {})
    print(f"NT等级: {nt.get('nt_level')}, NT得分: {nt.get('nt_score')}")
    print(f"综合判定: {survey.get('final_level')}, 是否流转: {survey.get('should_transfer')}")


if __name__ == '__main__':
    main()
