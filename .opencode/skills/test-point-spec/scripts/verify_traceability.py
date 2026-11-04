#!/usr/bin/env python3
"""Check requirement -> TP -> TC links across the approved baseline and lists."""
import argparse
import json
import os
import re
import sys


def read_text(path):
    with open(path, encoding="utf-8-sig") as stream:
        return stream.read()


def parse_table(text, heading):
    if not heading:
        header, rows = None, []
        for line in text.splitlines():
            if line.startswith("##"):
                break
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]*", cell) for cell in cells):
                continue
            if header is None:
                header = cells
            else:
                rows.append(cells)
        return header, rows
    lines = text.splitlines()
    in_section = False
    header = None
    rows = []
    for line in lines:
        if line.startswith("##"):
            if in_section and header is not None:
                break
            in_section = heading in line
            header, rows = None, []
            continue
        if not in_section or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]*", cell) for cell in cells):
            continue
        if header is None:
            header = cells
        else:
            rows.append(cells)
    return header, rows


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
    tp_header, tp_rows = parse_table(tp_text, "")
    tc_header, tc_rows = parse_table(tc_text, "") if tc_text else (None, [])
    tp_ids = {r[0] for r in tp_rows if r and re.fullmatch(r"TP-\d{3}", r[0])}
    tc_ids = {r[0] for r in tc_rows if r and re.fullmatch(r"TC-\d{3}", r[0])}
    failures = []

    req_header, req_rows = parse_table(tp_text, "需求→测试点覆盖表")
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
        for tp_id in sorted(tp_ids - covered_tps):
            failures.append(f"测试点 {tp_id} 未关联到任何需求基线条目")

    # TC 关联字段支持逗号分隔的多个 TP；详细有效性也由 verify_test_cases.py 检查。
    if args.tc_file and len(tc_header or []) >= 3:
        for row in tc_rows:
            if len(row) < 3:
                continue
            refs = [x.strip() for x in re.split(r"[,，、]", row[2]) if x.strip()]
            if not refs:
                failures.append(f"{row[0]} 没有关联测试点")
            for ref in refs:
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
    print(f"========== 校验汇总: PASS={0 if failures else 1} FAIL={len(failures)} ==========")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
