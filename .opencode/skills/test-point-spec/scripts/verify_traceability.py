#!/usr/bin/env python3
"""Check requirement -> TP -> TC links across the approved baseline and lists.

2026-11-05 收敛（B1）：表格解析迁移至 test-script-lib/mdtable.parse_md_table 唯一实现，
删除本地 parse_table 副本（契约散落回点）。
2026-11-05 收敛（#6）：辅资料补充验证点（主表含「辅资料补充」标记）豁免需求关联 → WARN。
"""
import argparse
import json
import os
import re
import sys

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "test-script-lib", "scripts"))
from mdtable import parse_md_table, read_text  # noqa: E402  表格解析唯一实现


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", help="已冻结的 requirements-baseline.json")
    parser.add_argument("tp_file", help="测试点清单")
    parser.add_argument("tc_file", nargs="?", help="测试用例清单（阶段 5 尚未生成时可省略）")
    args = parser.parse_args()
    required_paths = [args.baseline, args.tp_file] + ([args.tc_file] if args.tc_file else [])
    for path in required_paths:
        if not os.path.isfile(path):
            print(f"[FAIL] 文件不存在: {path}")
            return 1

    with open(args.baseline, encoding="utf-8") as stream:
        baseline = json.load(stream)
    tp_text = read_text(args.tp_file)
    tc_text = read_text(args.tc_file) if args.tc_file else ""
    tp_header, tp_rows = parse_md_table(tp_text, "")
    tc_header, tc_rows = parse_md_table(tc_text, "") if tc_text else (None, [])
    tp_ids = {r[0] for r in tp_rows if r and re.fullmatch(r"TP-\d{3}", r[0])}
    tc_ids = {r[0] for r in tc_rows if r and re.fullmatch(r"TC-\d{3}", r[0])}
    failures = []

    req_header, req_rows = parse_md_table(tp_text, "需求→测试点覆盖表")
    if not req_rows:
        failures.append("测试点清单缺少「需求→测试点覆盖表」")
    else:
        links = {}
        covered_tps = set()
        for row in req_rows:
            if len(row) < 3:
                continue
            req_id = row[0]
            tps = [x.strip() for x in re.split(r"[,，、]", row[1]) if x.strip()]
            reason = row[2].strip()
            if req_id in links:
                failures.append(f"需求覆盖表重复登记: {req_id}")
            links[req_id] = (tps, reason)
            covered_tps.update(tps)
            invalid = [tp for tp in tps if tp not in tp_ids]
            if invalid:
                failures.append(f"{req_id}: 引用了不存在的测试点 {' '.join(invalid)}")

        for req in baseline.get("requirements", []):
            req_id, status = req.get("id"), req.get("status")
            tps, reason = links.get(req_id, ([], ""))
            if status == "confirmed" and not tps:
                failures.append(f"已确认需求 {req_id} 没有测试点覆盖")
            if status == "out_of_scope" and not reason:
                failures.append(f"范围外需求 {req_id} 没有说明原因")
            if status == "needs_clarification":
                failures.append(f"需求 {req_id} 仍待澄清，不能进入追溯验收")
        known_req_ids = {r.get("id") for r in baseline.get("requirements", [])}
        for req_id in links:
            if req_id not in known_req_ids:
                failures.append(f"覆盖表中的需求不在基线中: {req_id}")
        # 2026-11-05 收敛：辅资料补充验证点豁免需求关联（resolve: 与其语义牵强地伪挂靠，
        # 不如明说"此验证点来自辅资料、无基线户口"）。
        # 豁免条件：TP 主表行中包含「辅资料补充」标记（spec 定义的归属声明），仅 WARN 不 FAIL。
        warnings = []
        uncovered = sorted(tp_ids - covered_tps)
        fail_uncovered, aux_uncovered = [], []
        for tp_id in uncovered:
            tp_row = next((r for r in tp_rows if r and r[0] == tp_id), [])
            if any("辅资料补充" in cell for cell in tp_row):
                aux_uncovered.append(tp_id)
            else:
                fail_uncovered.append(tp_id)
        if aux_uncovered:
            warnings.append(
                f"辅资料补充验证点（豁免需求关联，留痕采信）: {' '.join(aux_uncovered)}"
            )
        for tp_id in fail_uncovered:
            failures.append(
                f"测试点 {tp_id} 未关联到任何需求基线条目。"
                "请在「需求→测试点覆盖表」章节登记该 TP；"
                "若它来自辅资料且无基线需求可挂，在主表行内标注 `辅资料补充`（仅 WARN 不 FAIL）"
            )

    # 关联TP 必须单值（裁例通告裁决二：一 TC = 一 TP，"相关 TP"多挂靠已废止）；
    # 引用有效性的主裁在 verify_test_cases.py，此处为端到端追溯关的同口径防线。
    if args.tc_file and len(tc_header or []) >= 3:
        for row in tc_rows:
            if len(row) < 3:
                continue
            ref = row[2].strip()
            if not re.fullmatch(r"TP-\d{3}", ref):
                failures.append(
                    f"{row[0]} 关联TP 必须为单一 TP 编号（一 TC = 一 TP，禁止多挂靠）: {ref or '空'}"
                )
                continue
            if ref not in tp_ids:
                failures.append(f"{row[0]} 关联了不存在的测试点 {ref}")
    if args.tc_file and not tc_ids:
        failures.append("用例清单没有有效测试用例")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
    else:
        summary = f"{len(baseline.get('requirements', []))} 条需求、{len(tp_ids)} 个测试点"
        if args.tc_file:
            summary += f"、{len(tc_ids)} 条用例"
        print(f"[PASS] {summary} 的追溯关系完整")
    for warning in warnings:
        print(f"[WARN] {warning}")
    print(f"========== 校验汇总: PASS={0 if failures else 1} FAIL={len(failures)} ==========")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
