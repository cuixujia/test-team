#!/usr/bin/env python3
"""Create the small, deterministic requirements baseline used by self-tests.

纯文本直引（V2 唯一流程）：证据 = 文件:行号+原话；input_files 指纹 = Python 侧 sha256。
行号在运行时对资料文件动态定位，避免硬编码漂移。
"""
import hashlib
import json
import os
import re
import sys

TEXTS = [
    "风险名称必填，长度不超过 50 个字符。",
    "风险等级分为高、中、低三档，默认选中。",
    "提交人仅可修改自己创建的风险。",
    "项目成员仅可查看本项目的风险。",
    "普通测试人员只能查看自己创建的风险。",
    "提交时校验审核人身份，未认证账号提交被拒绝。",
    "风险状态初始为待审核。",
    "审核通过后状态变更为已审核；审核不通过则退回，状态为已关闭。",
]


def main():
    input_dir, output_path = sys.argv[1:] if len(sys.argv) == 3 else sys.argv[1:] or (None, None)
    if not input_dir or not output_path:
        print("用法: create_demo_baseline.py <资料目录> <baseline 输出路径>", file=sys.stderr)
        return 2
    prd_name = "prd-demo.md"
    prd_path = os.path.join(input_dir, prd_name)
    with open(prd_path, encoding="utf-8-sig") as stream:
        lines = stream.read().splitlines()

    norm = lambda s: re.sub(r"\s+", "", s)
    requirements = []
    for index, text in enumerate(TEXTS, start=1):
        hit = next(i for i, ln in enumerate(lines, 1) if norm(text) and norm(text) in norm(ln))
        requirements.append({
            "id": f"REQ-{index:03d}",
            "feature_id": "BF01" if index <= 5 else "BF02",
            "statement": text,
            "risk": "P1" if index in (3, 4, 6, 8) else "P2",
            "status": "confirmed",
            "evidence": [{"file": prd_name, "lines": str(hit), "quote": text}],
        })

    digest = hashlib.sha256(open(prd_path, "rb").read()).hexdigest()
    baseline = {
        "schema_version": 1,
        "input_files": [{"file": prd_name, "sha256": digest}],
        "selected_scope": [
            {"feature_id": "BF01", "name": "新增风险"},
            {"feature_id": "BF02", "name": "审核处理"},
        ],
        "requirements": requirements,
    }
    with open(output_path, "w", encoding="utf-8") as stream:
        json.dump(baseline, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
