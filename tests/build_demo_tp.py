#!/usr/bin/env python3
"""Generate demo test-point.md（纯文本直引，V2 唯一格式）。

运行时对资料文件动态定位行号，输出：
  - 主表（依据列 = `文件:行号「原话」` 或 `CL-xxx …`）
  - 覆盖对照表（证据→测试点，每条被引用的直引证据一行）
  - 需求→测试点覆盖表
"""
import hashlib
import os
import re
import sys

PRD_NAME = "prd-demo.md"
INPUT_DIR = "input_dir"
OUTPUT = "output"

# (TP, 意图, 类型, 方法, 证据样本索引 or "CL")
ROWS = [
    ("TP-001", "验证风险名称必填并按 50 字上限拒绝", "边界", "等价类", 0),
    ("TP-002", "验证风险等级按三档默认选中处理", "功能", "等价类", "CL-001 用户澄清：「默认选中」以三档中的中档为准（关联 TRD-01）"),
    ("TP-003", "验证提交人修改自己创建的风险被受理", "功能", "场景法", 2),
    ("TP-004", "验证项目成员仅可查看本项目风险", "功能", "场景法", 3),
    ("TP-005", "验证未认证账号提交风险被拒绝", "异常", "错误推测", 5),
    ("TP-006", "验证审核通过后风险状态变更为已审核", "流程", "状态迁移", 7),
]
QUOTE_PARAMS = [(2, 0), (2, 13), (2, 2), (2, 3), (2, 5), (2, 7)]

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
        print("用法: build_demo_tp.py <资料目录> <test-point.md 输出路径>", file=sys.stderr)
        return 2
    prd_path = os.path.join(input_dir, PRD_NAME)
    with open(prd_path, encoding="utf-8-sig") as stream:
        lines = stream.read().splitlines()
    norm = lambda s: re.sub(r"\s+", "", s)
    line_of = {}
    for index, text in enumerate(TEXTS, start=1):
        line_of[index] = next(i for i, ln in enumerate(lines, 1) if norm(text) and norm(text) in norm(ln))

    out = [
        "# 风险管理演示系统 测试点清单",
        "",
        "| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |",
        "|---|---|---|---|---|",
    ]
    cited = []
    for tp, intent, tp_type, method, sample in ROWS:
        if isinstance(sample, str):
            evidence = sample
        else:
            evidence = f"{PRD_NAME}:L{line_of[sample + 1]} 「{TEXTS[sample]}」"
            cited.append((evidence.split(" ")[0], tp))
        out.append(f"| {tp} | {intent} | {tp_type} | {method} | {evidence} |")

    out += [
        "",
        "## 覆盖对照表（证据→测试点）",
        "| 证据（文件:行号） | 覆盖的 TP 编号 | 未覆盖原因 |",
        "|---|---|---|",
    ]
    for ev, tp in cited:
        out.append(f"| {ev} | {tp} |  |")

    out += [
        "",
        "## 需求→测试点覆盖表",
        "| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |",
        "|---|---|---|",
        "| REQ-001 | TP-001 |  |",
        "| REQ-002 | TP-002 |  |",
        "| REQ-003 | TP-003 |  |",
        "| REQ-004 | TP-004 |  |",
        "| REQ-005 | TP-004 |  |",
        "| REQ-006 | TP-005 |  |",
        "| REQ-007 | TP-006 |  |",
        "| REQ-008 | TP-006 |  |",
        "",
    ]
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as stream:
        stream.write("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
