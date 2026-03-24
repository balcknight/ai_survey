import pandas as pd
from models.models import get_qwen_plus_llm


def load_nt_files(ntcls_path, ntspe_path):
    """加载NT比对文件"""
    try:
        # 这些xls文件实际上是制表符分隔的文本文件
        df_cls = pd.read_csv(ntcls_path, sep='\t')
        df_spe = pd.read_csv(ntspe_path, sep='\t')
        return df_cls, df_spe
    except Exception as e:
        print(f"读取文件失败: {e}")
        return None, None


def get_species_category(species_name, llm):
    """使用LLM判断物种属于哪一类生物"""
    prompt = f"""请判断"{species_name}"属于以下哪一类生物，只需回答类别名称：
- 动物
- 植物
- 细菌
- 真菌
- 病毒

只回答一个类别名称，不要有其他内容。"""

    response = llm.invoke(prompt)
    category = response.content.strip()
    return category


def check_ntcls(df_cls, target_species, llm):
    """
    检查all.ntcls.xls大类文件（打分制）
    1.1 top1属于本物种所属类别：是=2.5分，否=0分
    1.2 细菌+真菌+病毒比例总和 < 本物种比例*10%（若本物种比例<5%则阈值为20%）：是=5分，否=0分
    返回 (score, detail, top1_pass, contamination_pass)
    """
    if df_cls is None or len(df_cls) == 0:
        return 0, "ntcls文件为空"

    target_category = get_species_category(target_species, llm)
    print(f"目标物种 '{target_species}' 属于: {target_category}")

    first_row = df_cls.iloc[0]

    categories = {}
    for col in ['First', 'Second', 'Third', 'Fourth', 'Fifth']:
        if col in first_row:
            value = first_row[col]
            if '(' in value and ')' in value:
                cat_name = value.split('(')[0]
                ratio = float(value.split('(')[1].rstrip(')'))
                categories[cat_name] = ratio

    print(f"各类别比例: {categories}")

    if 'First' not in first_row:
        return 0, "数据格式错误"

    top1_value = first_row['First']
    top1_category_name = top1_value.split('(')[0]
    top1_ratio = categories.get(top1_category_name, 0)

    category_map = {
        'Plantae': '植物',
        'Metazoa': '动物',
        'Bacteria': '细菌',
        'Fungi': '真菌',
        'Viruses': '病毒'
    }

    top1_category = category_map.get(top1_category_name, top1_category_name)
    print(f"Top1类别: {top1_category}, 比例: {top1_ratio:.2f}%")

    score = 0
    details = []

    # 1.1 top1类别属于本物种 => 2.5分
    if top1_category == target_category:
        score += 2.5
        details.append(f"Top1类别匹配({top1_category})，+2.5分")
    else:
        details.append(f"Top1类别不匹配(Top1={top1_category}, 目标={target_category})，+0分")

    # 1.2 细菌+真菌+病毒比例总和 < 本物种比例的阈值 => 5分
    # 若本物种比例<5%，阈值为本物种比例*20%；否则阈值为本物种比例*10%
    contamination_sum = categories.get('Bacteria', 0) + categories.get('Fungi', 0) + categories.get('Viruses', 0)
    if top1_ratio < 5:
        threshold_pct = 20
    else:
        threshold_pct = 10
    contamination_threshold = top1_ratio * threshold_pct / 100
    print(f"细菌+真菌+病毒比例总和: {contamination_sum:.2f}%, 本物种比例: {top1_ratio:.2f}%, 阈值: {contamination_threshold:.2f}% ({threshold_pct}%)")

    if contamination_sum < contamination_threshold:
        score += 5
        details.append(f"污染比例({contamination_sum:.2f}%)<本物种{top1_ratio:.2f}%的{threshold_pct}%({contamination_threshold:.2f}%)，+5分")
    else:
        details.append(f"污染比例({contamination_sum:.2f}%)>=本物种{top1_ratio:.2f}%的{threshold_pct}%({contamination_threshold:.2f}%)，+0分")

    detail = f"ntcls得分={score}分: {'; '.join(details)}"
    print(f"  {detail}")

    # 返回子判断结果
    top1_pass = (top1_category == target_category)
    contamination_pass = (contamination_sum < contamination_threshold)
    return score, detail, top1_pass, contamination_pass


def check_ntspe(df_spe, target_species, llm):
    """
    检查all.ntspe.xls小类文件（打分制）
    规则：top6中细菌+真菌+病毒比例总和<2% => 2.5分，否则0分
    返回 (score, detail)
    """
    if df_spe is None or len(df_spe) == 0:
        return 0, "ntspe文件为空"

    target_category = get_species_category(target_species, llm)
    print(f"\n目标物种 '{target_species}' 属于: {target_category}")

    category_map = {
        'Plantae': '植物',
        'Metazoa': '动物',
        'Bacteria': '细菌',
        'Fungi': '真菌',
        'Viruses': '病毒'
    }

    contamination_categories = {'Bacteria', 'Fungi', 'Viruses'}

    first_row = df_spe.iloc[0]
    comparison_cols = [
        'The first comparison', 'The second comparison', 'The third comparison',
        'The fourth comparison', 'The fifth comparison', 'The sixth comparison'
    ]

    contamination_sum = 0
    parsed_count = 0

    for i, col in enumerate(comparison_cols):
        if col not in first_row:
            break
        value = str(first_row[col])
        if ':' not in value:
            continue

        category_en = value.split(':')[0]
        species_info = ':'.join(value.split(':')[1:])
        category_cn = category_map.get(category_en, category_en)

        # 提取比例
        ratio = 0
        if '(' in value and ')' in value:
            try:
                ratio = float(value.split('(')[-1].rstrip(')'))
            except ValueError:
                pass

        print(f"Top{i+1}: {category_cn} - {species_info} ({ratio:.2f}%)")

        if category_en in contamination_categories:
            contamination_sum += ratio

        parsed_count += 1

    if parsed_count == 0:
        return 0, "没有找到比对数据"

    print(f"Top6中细菌+真菌+病毒比例总和: {contamination_sum:.2f}%")

    if contamination_sum < 2:
        detail = f"ntspe得分=2.5分: 污染比例({contamination_sum:.2f}%)<2%，+2.5分"
        print(f"  {detail}")
        return 2.5, detail, True
    else:
        detail = f"ntspe得分=0分: 污染比例({contamination_sum:.2f}%)>=2%，+0分"
        print(f"  {detail}")
        return 0, detail, False


def judge_nt_contamination(ntcls_path, ntspe_path, target_species):
    """
    综合判断NT比对结果（打分制）
    总分10分：ntcls最高7.5分(2.5+5)，ntspe最高2.5分
    <4分: fail
    4<=score<6: 重度污染
    6<=score<8: 轻度污染
    >=8: 正常
    """
    print("="*60)
    print("开始NT比对污染判断（打分制）")
    print("="*60)

    llm = get_qwen_plus_llm()

    df_cls, df_spe = load_nt_files(ntcls_path, ntspe_path)

    if df_cls is None or df_spe is None:
        return {
            'nt_score': 0,
            'nt_level': 'fail',
            'ntcls_score': 0,
            'ntspe_score': 0,
            'detail': '文件加载失败'
        }

    # 1. 检查ntcls
    print("\n【步骤1】检查all.ntcls.xls大类文件")
    print("-"*60)
    ntcls_score, ntcls_detail, ntcls_top1_pass, ntcls_contamination_pass = check_ntcls(df_cls, target_species, llm)

    # 2. 检查ntspe
    print("\n【步骤2】检查all.ntspe.xls小类文件")
    print("-"*60)
    ntspe_score, ntspe_detail, ntspe_contamination_pass = check_ntspe(df_spe, target_species, llm)

    # 综合打分
    total_score = ntcls_score + ntspe_score

    if total_score < 4:
        nt_level = 'fail'
    elif total_score < 6:
        nt_level = '重度污染'
    elif total_score < 8:
        nt_level = '轻度污染'
    else:
        nt_level = '正常'

    print("\n" + "="*60)
    print(f"【NT打分结果】: 总分={total_score}, 等级={nt_level}")
    print(f"  ntcls={ntcls_score}分, ntspe={ntspe_score}分")
    print("="*60)

    return {
        'nt_score': total_score,
        'nt_level': nt_level,
        'ntcls_score': ntcls_score,
        'ntspe_score': ntspe_score,
        'ntcls_detail': ntcls_detail,
        'ntspe_detail': ntspe_detail,
        'ntcls_top1_pass': ntcls_top1_pass,
        'ntcls_contamination_pass': ntcls_contamination_pass,
        'ntspe_contamination_pass': ntspe_contamination_pass,
    }


if __name__ == '__main__':
    # 测试
    base_path = 'data/FDES250026022-1a_Sdis'
    result = judge_nt_contamination(
        ntcls_path=f'{base_path}/all.ntcls.xls',
        ntspe_path=f'{base_path}/all.ntspe.xls',
        target_species='Salvia discolor'  # 丹参
    )
    print(f"\n返回结果: {result}")

