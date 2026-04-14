import argparse
import json
from pathlib import Path
from typing import Any

from ploidy_agent.agent import run_ploidy_correction


def _load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_text(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="倍性纠错 Agent（结构化输出）")
    parser.add_argument("--species", required=True, help="物种名，如：锤头双髻鲨")
    parser.add_argument("--kmer-json", required=True, help="main_dual 输出字典保存的 JSON 文件")
    parser.add_argument("--script-text", default=None, help="脚本原始日志文本文件（可选）")
    args = parser.parse_args()

    kmer_result = _load_json(args.kmer_json)
    script_text = _load_text(args.script_text)

    structured = run_ploidy_correction(
        species_name=args.species,
        kmer_result=kmer_result,
        script_text=script_text,
    )

    if hasattr(structured, "model_dump"):
        output = structured.model_dump()
    else:
        output = structured
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

