from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nt_judge


class _FakeResult:
    def __init__(self, category: str):
        self.category = category


class _FakeLLM:
    def __init__(self, category: str):
        self._category = category

    def with_structured_output(self, schema, method="function_calling"):
        return self

    def invoke(self, prompt):
        return _FakeResult(self._category)


def test_infer_category_unknown():
    llm = _FakeLLM("无法识别")
    category = nt_judge._infer_category_by_name("qwen", llm)
    assert category == "无法识别"


def test_judge_nt_contamination_stop_when_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(nt_judge, "get_qwen_plus_llm", lambda: _FakeLLM("无法识别"))

    ntspe_path = tmp_path / "sample.NT.species.xls"
    df = pd.DataFrame(
        [
            {"#class": "Metazoa", "species": "Homo sapiens", "total rate": 0.9},
            {"#class": "Plantae", "species": "Arabidopsis thaliana", "total rate": 0.1},
        ]
    )
    df.to_csv(ntspe_path, sep="\t", index=False)

    result = nt_judge.judge_nt_contamination(
        ntcls_path="",
        ntspe_path=str(ntspe_path),
        target_species="cc07",
    )

    assert result["nt_level"] == "fail"
    assert result["target_category"] == "无法识别"
    assert "无法识别" in result["detail"]


def test_decide_nt_level_threshold_switch():
    level1, threshold1 = nt_judge._decide_nt_level(dominant_ratio=19.9, pollution_ratio=0.41)
    assert threshold1 == 0.4
    assert level1 == "重度污染"

    level2, threshold2 = nt_judge._decide_nt_level(dominant_ratio=20.0, pollution_ratio=0.99)
    assert threshold2 == 1.0
    assert level2 == "正常"
