from __future__ import annotations

from pathlib import Path
import traceback

import pandas as pd

from nt_judge import judge_nt_contamination


def read_target_species_from_ntspe_new(path: Path) -> str:
    df = pd.read_csv(path, sep='\t', header=None)
    if df.empty:
        raise ValueError('ntspe.xls.new 文件为空')
    species = str(df.iloc[0, 0]).strip()
    if not species:
        raise ValueError('ntspe.xls.new 第一列物种名为空')
    return species


def find_nt_species_file(sample_dir: Path, ntspe_new: Path) -> Path:
    # 优先同名前缀
    prefix = ntspe_new.name.replace('.ntspe.xls.new', '')
    prefer = sample_dir / f'{prefix}_NT.species.xls'
    if prefer.exists():
        return prefer

    cands = sorted(sample_dir.glob('*_NT.species.xls'))
    if not cands:
        raise FileNotFoundError(f'未找到 *_NT.species.xls: {sample_dir}')
    return cands[0]


def find_ntcls_file(sample_dir: Path) -> Path | None:
    path = sample_dir / 'all.ntcls.xls'
    return path if path.exists() else None


def run_batch(root_dir: str = 'data/survey_nt_correct_20260421') -> None:
    root = Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f'目录不存在: {root}')

    ntspe_new_files = sorted(root.glob('**/*.ntspe.xls.new'))
    print(f'扫描目录: {root}')
    print(f'共发现 .ntspe.xls.new 文件: {len(ntspe_new_files)}')

    ok = 0
    fail = 0

    for i, ntspe_new in enumerate(ntspe_new_files, 1):
        sample_dir = ntspe_new.parent
        print('\n' + '=' * 80)
        print(f'[{i}/{len(ntspe_new_files)}] 处理目录: {sample_dir}')

        try:
            target_species = read_target_species_from_ntspe_new(ntspe_new)
            nt_species_file = find_nt_species_file(sample_dir, ntspe_new)
            ntcls_file = find_ntcls_file(sample_dir)

            print(f'  目标物种: {target_species}')
            print(f'  NT小类文件: {nt_species_file.name}')
            print(f'  ntcls文件: {ntcls_file.name if ntcls_file else "(缺失，按空路径传入)"}')

            res = judge_nt_contamination(
                ntcls_path=str(ntcls_file) if ntcls_file else '',
                ntspe_path=str(nt_species_file),
                target_species=target_species,
            )

            print(f'  NT等级: {res.get("nt_level")}, 重度污染: {res.get("is_heavy_contamination")}')
            print(
                f'  污染合计={res.get("pollution_ratio_percent")}%, '
                f'阈值={res.get("pollution_threshold_percent")}%'
            )
            print(f'  小类输出: {res.get("small_judged_path", "")}')
            print(f'  大类输出: {res.get("class_filtered_path", "")}')
            ok += 1
        except Exception as e:
            fail += 1
            print(f'  失败: {e}')
            print(traceback.format_exc())

    print('\n' + '#' * 80)
    print(f'批量处理完成: 成功={ok}, 失败={fail}, 总数={len(ntspe_new_files)}')


if __name__ == '__main__':
    run_batch('data/survey_nt_correct_20260421')
