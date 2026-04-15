"""
Survey 单样本联合判定脚本
直接调用 kmer 判断与 NT 判断，输出最终 survey 结果。
"""

import pandas as pd

from kmer_judge import main_dual
from nt_judge import judge_nt_contamination


def load_target_species(ntcls_path: str) -> str:
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


def run_single_survey(
    spe_path: str,
    num_path: str,
    ntcls_path: str,
    ntspe_path: str,
    verbose: bool = True,
) -> dict:
    """执行单样本联合判定（kmer + NT），并返回汇总结果。"""
    result = main_dual(
        spe_filepath=spe_path,
        num_filepath=num_path,
        verbose=verbose,
    )
    target_species = load_target_species(ntcls_path)
    nt_result = judge_nt_contamination(ntcls_path, ntspe_path, target_species)
    survey_result = build_final_survey(result, nt_result)

    result['target_species'] = target_species
    result['nt_result'] = nt_result
    result['survey_result'] = survey_result

    return result


def main():
    # 直接在这里修改路径即可（适配 VSCode 直接运行）
    spe_path = 'data/your_sample.17merFreq.SpeFreq.cut'
    num_path = 'data/your_sample.17merFreq.NumFreq.cut'
    ntcls_path = 'data/your_sample/all.ntcls.xls'
    ntspe_path = 'data/your_sample/all.ntspe.xls'
    verbose = True

    merged = run_single_survey(
        spe_path=spe_path,
        num_path=num_path,
        ntcls_path=ntcls_path,
        ntspe_path=ntspe_path,
        verbose=verbose,
    )

    print('单样本联合判定完成')
    print(f"kmer峰型: {merged.get('pattern')}, 是否正常: {merged.get('is_normal')}")
    nt = merged.get('nt_result', {})
    survey = merged.get('survey_result', {})
    print(f"NT等级: {nt.get('nt_level')}, NT得分: {nt.get('nt_score')}")
    print(f"综合判定: {survey.get('final_level')}, 是否流转: {survey.get('should_transfer')}")


if __name__ == '__main__':
    main()
