#!/usr/bin/env python3
"""check.py — 交付机验统一入口（唯一命令，2026-11-05 收敛取代 validate_delivery.py + verify_validation_report.py）。

一次运行 = 一条命令产一份带指纹的 JSON 报告，供质检专家按工件采信（不重复跑机械校验）。

步骤清单（--phase tp | tc | full）：
  1. quote-tp          TP 清单直引逐字机验（verify_quotes.py --extract-from --report）
  2. quote-tc          TC 清单直引逐字机验（同上；--phase tc/full 时执行）——
                       2026-11-05 收敛：此前 TC 清单引文不在管线内，字面保真缺机器裁决（复盘复盘 A5/C2）
  3. requirements-baseline  基线结构/范围/证据/指纹校验（冻结场景附加 --freeze）
  4. test-points               TP 编号/列序/必填/覆盖表/标签泄漏（--phase tp/full）
  5. requirement-to-test-point 需求→TP 追溯（--phase tp/full）
  6. test-cases                TC 结构/标签/关联TP 单值/每 TP ≥2 TC/覆盖对账（--phase tc/full）
  7. end-to-end-traceability   需求→TP→TC 端到端追溯（含关联TP 单值，--phase tc/full）
  8. report-freshness          内建：报告写入后自检（工具链指纹与产物指纹复核），
                               取代独立脚本 verify_validation_report.py

典型用法：
  python3 .opencode/skills/test-point-spec/scripts/check.py --phase full \
    --input-dir <资料目录> --baseline <requirements-baseline.json> \
    --scope-list <state/scope-list.md> --tp-file <test-point.md> --tc-file <test-case.md> \
    --clarifications <state/clarifications.md> --report <output/reports/check-full.json>

退出码：0 = 全部步骤与新鲜度自检通过；1 = 任一 FAIL。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
SCRIPT_DAT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # scripts → test-point-spec → skills，树内引用以 __file__ 为锚，不依赖仓库目录名


def digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def revalidate_report(report_path):
    """报告新鲜度自检（原 verify_validation_report.py 的逻辑内建）。返回失败列表。"""
    with open(report_path, encoding="utf-8") as stream:
        report = json.load(stream)
    failures = []
    if report.get("schema_version") != 1:
        failures.append("报告 schema_version 必须为 1")
    if not report.get("steps"):
        failures.append("报告中没有校验步骤")
    if not report.get("toolchain"):
        failures.append("报告中没有校验工具链指纹")
    for path, expected in report.get("toolchain", {}).items():
        if not os.path.isfile(path) or digest(path) != expected:
            failures.append(f"校验流水线工具已变化或不存在: {path}")
    for step in report.get("steps", []):
        if step.get("exit_code") != 0:
            failures.append(f"校验步骤未通过: {step.get('label')}")
        for path, expected in step.get("artifacts", {}).items():
            if not os.path.isfile(path) or digest(path) != expected:
                failures.append(f"产物已变化或不存在: {path}")
        for path, expected in step.get("scripts", {}).items():
            if not os.path.isfile(path) or digest(path) != expected:
                failures.append(f"校验脚本已变化或不存在: {path}")
    if report.get("passed") is not True:
        failures.append("报告状态不是全通过")
    return failures


# 覆盖对照表自动推导（2026-11-05 收敛）：从 TP 主表"依据"列抽取 文件:行号「摘录」，
# 汇总为 证据→TP 数据视图。零新增脚本，归属 check.py 内建推导步骤。
import sys as _sys
import os as _os
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "test-script-lib", "scripts"))
from mdtable import parse_md_table  # noqa: E402

DCITE_RE = re.compile(
    r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L(\d+(?:\s*[-~]\s*\d+)?)\s*「([^」]{1,300})」"
)


def derive_coverage_md(tp_file):
    try:
        with open(tp_file, encoding="utf-8-sig") as stream:
            text = stream.read()
    except OSError:
        return ""
    _header, main_rows = parse_md_table(text, "")
    mapping = {}
    for row in main_rows:
        if not row or not re.fullmatch(r"TP-\d{3}", row[0]):
            continue
        tp_id = row[0]
        cited_cell = ""
        # 依据列：主表第 5 列（列序契约 编号|验证意图|类型|分析方法|依据）
        if len(row) > 4:
            cited_cell = row[4]
        for m in DCITE_RE.finditer(cited_cell):
            key = f"{m.group(1)}:L{m.group(2)}"
            entry = mapping.setdefault(key, {"quote": m.group(3), "tps": []})
            if tp_id not in entry["tps"]:
                entry["tps"].append(tp_id)
    if not mapping:
        return ""
    lines = [
        "# 覆盖对照表（机验管线自动推导，勿手工维护）",
        "",
        "| 证据（文件:行号） | 测试点 | 摘录片段 |",
        "|---|---|---|",
    ]
    for key in sorted(mapping, key=lambda k: (k.rsplit(":", 1)[0], [int(x) for x in re.findall(r"\d+", k.rsplit(":", 1)[1])])):
        entry = mapping[key]
        snippet = entry["quote"][:20] + ("…" if len(entry["quote"]) > 20 else "")
        lines.append(f"| {key} | {', '.join(entry['tps'])} | {snippet} |")
    lines.append("")
    lines.append(f"合计 {len(mapping)} 条证据、{len(main_rows)} 个测试点。生成时间：机验管线运行时。")
    return "\n".join(lines)


def run(label, command, artifacts, extra_scripts=()):
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    paths = list(artifacts) + list(extra_scripts)
    return {
        "label": label,
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
        "artifacts": {os.path.abspath(p): digest(p) for p in paths if p and os.path.isfile(p)},
        "scripts": {p: digest(p) for p in command[1:] if p.endswith(".py") and os.path.isfile(p)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("tp", "tc", "full"), required=True)
    parser.add_argument("--input-dir", required=True, nargs="+",
                        help="资料目录（可传多个：文本资料目录 + 会话转换区 user-input-converted）")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--quote-table", default="", help="引文机验输入覆盖；缺省时直接从 tp/tc 清单按引用语法抽引用")
    parser.add_argument("--scope-list", default="")
    parser.add_argument("--tp-file", required=True)
    parser.add_argument("--tc-file", default="")
    parser.add_argument("--clarifications", default="")
    parser.add_argument("--manifest", default="", help="files-manifest.md 路径；提供时基线 input_files 与入库指纹交叉校验")
    parser.add_argument("--only", default="", help="增量机验：只跑指定步骤（逗号分隔，如 --only quote-tp,requirement-to-test-point）；缺省全量")
    parser.add_argument("--report", required=True, help="机验 JSON 输出路径（约定 check-<phase>.json）")
    args = parser.parse_args()

    tools = {
        "baseline": os.path.join(SCRIPT_DAT, "prd-record-spec/scripts/verify_requirement_baseline.py"),
        "quotes": os.path.join(SCRIPT_DAT, "prd-record-spec/scripts/verify_quotes.py"),
        "tp": os.path.join(SCRIPT_DAT, "test-point-spec/scripts/verify_test_points.py"),
        "trace": os.path.join(SCRIPT_DAT, "test-point-spec/scripts/verify_traceability.py"),
        "tc": os.path.join(SCRIPT_DAT, "test-case-spec/scripts/verify_test_cases.py"),
    }
    report_abspath = os.path.abspath(args.report)
    report_dir = os.path.dirname(report_abspath)
    report_stem = os.path.splitext(os.path.basename(args.report))[0]

    # 引文报告由 --report 同目录派生命名：<stem>.quotes-tp.json / .quotes-tc.json
    def quote_report_path(kind):
        return os.path.join(report_dir, f"{report_stem}.quotes-{kind}.json")

    started = time.monotonic()
    steps = []

    # --only 增量机验（2026-11-05 收敛）：修复轮只跑受影响步骤，终轮全量兜底。
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None

    if args.phase in ("tc", "full") and not args.scope_list:
        parser.error("--phase tc/full 必须提供 --scope-list")

    def want(label):
        return only is None or label in only

    def skipped(label, note):
        return {"label": f"{label}(skipped: {note})", "command": [], "exit_code": 0,
                "stdout": "", "stderr": "", "duration_seconds": 0.0, "artifacts": {}, "scripts": {}}

    # 引文人肉面收口到 verify_quotes；缺省从 TP/TC 清单自体抽引用（直引证据的单一来源是清单本身）。
    import re as _re
    CITE_SCAN = _re.compile(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L\d")
    # 无 L 前缀探测（2026-11-06 收敛）：跳过=静默放弃逐字保真，实测已双次翻车（早期 check-tc 裸奔、
    # QA 语义报告误述 skip）；主件引用契约 = `文件:L行号「摘录」`，形如 `文件:数字` 视为漏写 L。
    NO_L_SCAN = _re.compile(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):\s?\d")

    def _no_l_warn(src_path, kind):
        text = _text_of(src_path)
        hits = [m.group(0) for m in NO_L_SCAN.finditer(text) if not CITE_SCAN.search(m.group(0))]
        if hits:
            note = (
                f"[WARN] {src_path} 发现 {len(hits)} 处疑似未带 L 前缀的引用（如 {hits[0]}），"
                f"quote-{kind} 未抽中=放弃逐字保真；主件引用须写 `文件:L行号「摘录」`，请修正后重跑机验"
            )
            print(note)
            return {"label": f"quote-{kind}(warn: 未带L前缀引用×{len(hits)}，未抽中)", "command": [],
                    "exit_code": 0, "stdout": note, "stderr": "", "duration_seconds": 0.0,
                    "artifacts": {}, "scripts": {}}
        return None

    def _text_of(path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                return f.read()
        except OSError:
            return ""

    # 1) TP 清单引文（--quote-table 显式给引用表时以其为源）
    tp_quote_src = args.quote_table or args.tp_file
    if args.quote_table or CITE_SCAN.search(_text_of(tp_quote_src)):
        if want("quote-tp"):
            qr_tp = quote_report_path("tp")
            steps.append(run("quote-tp", [sys.executable, tools["quotes"], tp_quote_src, "--input-dir", *args.input_dir, "--extract-from", "--report", qr_tp, "--autofix"], [tp_quote_src, qr_tp]))
        else:
            steps.append(skipped("quote-tp", "--only 增量机验未选中"))
    else:
        warn_step = _no_l_warn(tp_quote_src, "tp")
        if warn_step:
            steps.append(warn_step)
        else:
            steps.append({"label": "quote-tp(skipped,如实声明: 清单无直引引用语法，TP 主件证据列未做逐字机验，语义关须抽验补充；不走基线机验)", "command": [], "exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.0, "artifacts": {}, "scripts": {}})

    # 2) TC 清单引文（2026-11-05 新增：字面保真必须有机验裁决）
    if args.phase in ("tc", "full"):
        if args.tc_file:
            if args.quote_table:
                steps.append({"label": "quote-tc(skipped: 使用 --quote-table 显式引用表，见 quote-tp)", "command": [], "exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.0, "artifacts": {}, "scripts": {}})
            elif CITE_SCAN.search(_text_of(args.tc_file)):
                if want("quote-tc"):
                    qr_tc = quote_report_path("tc")
                    steps.append(run("quote-tc", [sys.executable, tools["quotes"], args.tc_file, "--input-dir", *args.input_dir, "--extract-from", "--report", qr_tc, "--autofix"], [args.tc_file, qr_tc]))
                else:
                    steps.append(skipped("quote-tc", "--only 增量机验未选中"))
            else:
                warn_step = _no_l_warn(args.tc_file, "tc")
                if warn_step:
                    steps.append(warn_step)
                else:
                    steps.append({"label": "quote-tc(skipped: TC 清单无直引引用)", "command": [], "exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.0, "artifacts": {}, "scripts": {}})

    if want("requirements-baseline"):
        baseline_command = [sys.executable, tools["baseline"], args.baseline, "--input-dir", *args.input_dir, "--freeze"]
        if args.clarifications:
            baseline_command += ["--clarifications", args.clarifications]
        if args.manifest:
            # 入库指纹交叉校验：基线 input_files 必须逐条命中入库清单（同名同 sha256）
            baseline_command += ["--manifest", args.manifest]
        steps.append(run("requirements-baseline", baseline_command, [args.baseline, args.manifest, args.clarifications]))
    else:
        steps.append(skipped("requirements-baseline", "--only 增量机验未选中"))

    if args.phase in ("tp", "full"):
        if want("test-points"):
            tp_command = [sys.executable, tools["tp"], args.tp_file, "--input-dir", *args.input_dir]
            if args.scope_list:
                tp_command += ["--scope-list", args.scope_list]
            if args.clarifications:
                tp_command += ["--clarifications", args.clarifications]
            steps.append(run("test-points", tp_command, [args.tp_file, args.scope_list, args.clarifications]))
        else:
            steps.append(skipped("test-points", "--only 增量机验未选中"))
        if want("requirement-to-test-point"):
            steps.append(run("requirement-to-test-point", [sys.executable, tools["trace"], args.baseline, args.tp_file], [args.baseline, args.tp_file]))
        else:
            steps.append(skipped("requirement-to-test-point", "--only 增量机验未选中"))

    if args.phase in ("tc", "full"):
        if not args.tc_file:
            parser.error("--phase tc/full 必须提供 --tc-file")
        if want("test-cases"):
            tc_command = [sys.executable, tools["tc"], args.tc_file, "--tp-file", args.tp_file, "--prd-dir", *args.input_dir, "--scope-list", args.scope_list]
            steps.append(run("test-cases", tc_command, [args.tc_file, args.tp_file, args.scope_list]))
        else:
            steps.append(skipped("test-cases", "--only 增量机验未选中"))
        if want("end-to-end-traceability"):
            steps.append(run("end-to-end-traceability", [sys.executable, tools["trace"], args.baseline, args.tp_file, args.tc_file], [args.baseline, args.tp_file, args.tc_file]))
        else:
            steps.append(skipped("end-to-end-traceability", "--only 增量机验未选中"))

    # derive-coverage-table（2026-11-05 收敛）：覆盖对照表由主表自动推导生成数据视图，
    # 专家不再手工维护该表（verify_test_points 对未提供该表已放行）。
    if args.phase in ("tp", "full") and want("derive-coverage-table"):
        derived = derive_coverage_md(args.tp_file)
        if derived:
            derived_path = os.path.join(report_dir, f"{report_stem}.derived-coverage.md")
            os.makedirs(report_dir, exist_ok=True)
            with open(derived_path, "w", encoding="utf-8") as stream:
                stream.write(derived)
            steps.append({
                "label": "derive-coverage-table",
                "command": [f"(inline) parse {args.tp_file} 主表证据列 → 证据→TP 视图"],
                "exit_code": 0,
                "stdout": f"[DERIVED] {derived_path}",
                "stderr": "", "duration_seconds": 0.0,
                "artifacts": {os.path.abspath(derived_path): digest(derived_path)},
                "scripts": {},
            })

    report = {
        "schema_version": 1,
        "phase": args.phase,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": round(time.monotonic() - started, 3),
        "toolchain": {
            os.path.abspath(__file__): digest(__file__),
            tools["quotes"]: digest(tools["quotes"]),
            tools["baseline"]: digest(tools["baseline"]),
            tools["tp"]: digest(tools["tp"]),
            tools["tc"]: digest(tools["tc"]),
            tools["trace"]: digest(tools["trace"]),
        },
        "steps": steps,
        "passed": all(step["exit_code"] == 0 for step in steps),
    }
    os.makedirs(report_dir, exist_ok=True)
    with open(report_abspath, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    # 报告时效自检：写入后立即按指纹复核（取代独立的 verify_validation_report.py）。
    freshness_failures = revalidate_report(report_abspath)
    report["passed"] = report["passed"] and not freshness_failures
    with open(report_abspath, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    for step in steps:
        print(f"[{'PASS' if step['exit_code'] == 0 else 'FAIL'}] {step['label']} (exit={step['exit_code']})")
        if step["stdout"].strip() and "skipped" not in step["label"]:
            print(step["stdout"].rstrip())
        if step["stderr"].strip():
            print(step["stderr"].rstrip(), file=sys.stderr)
    if freshness_failures:
        print("[FAIL] report-freshness")
        for item in freshness_failures:
            print(f"  - {item}", file=sys.stderr)
    else:
        print(f"[PASS] report-freshness（工具链与产物指纹复核通过）")
    print(f"[REPORT] {report_abspath}")
    exit_code = 0 if (report["passed"] and not freshness_failures) else 1
    print(f"========== 校验汇总: {'PASS' if exit_code == 0 else 'FAIL'} ==========")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        print(f"[FAIL] 校验脚本异常: {e}")
        sys.exit(1)
