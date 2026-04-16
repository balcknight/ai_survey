"""
Survey 单样本联合判定脚本
直接调用 kmer 判断与 NT 判断，输出最终 survey 结果。
"""

from pathlib import Path

import pandas as pd

from kmer_judge import main_dual
from nt_judge import judge_nt_contamination


def _find_in_sample_dir(sample_path: Path, pattern: str) -> Path | None:
    """仅在 sample_dir 内查找匹配文件（含子目录），不向上层目录扩展。"""
    candidates = sorted(sample_path.glob(f'**/{pattern}'))
    if not candidates:
        return None
    return candidates[0]


def resolve_input_files(sample_dir: str) -> dict[str, str]:
    """输入样本目录，仅在该目录内自动定位 4 个输入文件路径。"""
    sample_path = Path(sample_dir).expanduser().resolve()
    if not sample_path.exists() or not sample_path.is_dir():
        raise FileNotFoundError(f'样本目录不存在或不是目录: {sample_path}')

    spe_file = _find_in_sample_dir(sample_path, '*.SpeFreq.cut')
    num_file = _find_in_sample_dir(sample_path, '*.NumFreq.cut')
    ntcls_file = _find_in_sample_dir(sample_path, 'all.ntcls.xls')
    ntspe_file = _find_in_sample_dir(sample_path, 'all.ntspe.xls')

    missing = []
    if spe_file is None:
        missing.append('*.SpeFreq.cut')
    if num_file is None:
        missing.append('*.NumFreq.cut')
    if ntcls_file is None:
        missing.append('all.ntcls.xls')
    if ntspe_file is None:
        missing.append('all.ntspe.xls')

    if missing:
        raise FileNotFoundError(
            f'在目录 {sample_path} 内未找到以下文件: {", ".join(missing)}。'
            '请确认 4 个输入文件都在该目录（或其子目录）中。'
        )

    return {
        'spe_path': str(spe_file),
        'num_path': str(num_file),
        'ntcls_path': str(ntcls_file),
        'ntspe_path': str(ntspe_file),
    }


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
    # 统一由 ntcls 推导目标物种名，kmer/nt 都使用该物种名参与 LLM 分析与判定
    target_species = load_target_species(ntcls_path)
    result = main_dual(
        spe_filepath=spe_path,
        num_filepath=num_path,
        species_name=target_species,
        verbose=verbose
    )
    
    nt_result = judge_nt_contamination(ntcls_path, ntspe_path, target_species)
    survey_result = build_final_survey(result, nt_result)

    result['target_species'] = target_species
    result['nt_result'] = nt_result
    result['survey_result'] = survey_result

    return result


def main():
    # 只需要修改样本目录（适配 VSCode 直接运行）
    sample_dir = 'data/shenshaoqi_data/survey1/X101SC2507/X101SC25070200-Z01-J002/FDSW250019884-2a_百花山C-嫩茎_1管'
    verbose = True

    paths = resolve_input_files(sample_dir)
    print('自动定位输入文件:')
    print(f"  SpeFreq.cut: {paths['spe_path']}")
    print(f"  NumFreq.cut: {paths['num_path']}")
    print(f"  all.ntcls.xls: {paths['ntcls_path']}")
    print(f"  all.ntspe.xls: {paths['ntspe_path']}")

    merged = run_single_survey(
        spe_path=paths['spe_path'],
        num_path=paths['num_path'],
        ntcls_path=paths['ntcls_path'],
        ntspe_path=paths['ntspe_path'],
        verbose=verbose,
    )

    print(merged)  # 输出完整结果字典，便于调试和验证

    print('单样本联合判定完成')
    print(f"kmer峰型: {merged.get('pattern')}, 是否正常: {merged.get('is_normal')}")
    nt = merged.get('nt_result', {})
    survey = merged.get('survey_result', {})
    print(f"NT等级: {nt.get('nt_level')}, NT得分: {nt.get('nt_score')}")
    print(f"综合判定: {survey.get('final_level')}, 是否流转: {survey.get('should_transfer')}")


if __name__ == '__main__':
    main()
