from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    title: str = Field(description="证据标题")
    detail: str = Field(description="证据说明")


class WebSource(BaseModel):
    title: str = Field(description="网页标题")
    url: str = Field(description="网页链接")
    snippet: str = Field(default="", description="简短摘要")


class PloidyCorrectionResult(BaseModel):
    final_ploidy: Literal["二倍体", "三倍体", "四倍体", "疑似多倍体", "未知"] = Field(
        description="最终倍性结论"
    )
    corrected: bool = Field(description="是否推翻脚本原判定")
    confidence: Literal["高", "中", "低"] = Field(description="结论置信度")
    script_ploidy: str = Field(description="脚本原始判定")
    correction_summary: str = Field(description="一句话总结（若纠正，说明为何纠正）")
    reasoning: list[EvidenceItem] = Field(
        description="核心判断依据，至少包含脚本事实和物种知识两类信息"
    )
    conflict_explanation: str = Field(
        description="当脚本与物种先验冲突时，解释可能原因；无冲突时可简述一致性"
    )
    sources: list[WebSource] = Field(
        default_factory=list, description="联网检索到的外部证据来源"
    )
    notes: str = Field(default="", description="其他补充说明")

