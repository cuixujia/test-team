#!/usr/bin/env python3
"""Run deterministic checks once and save a hash-bound validation report.

纯文本机验管线（V2 唯一流程）：依赖 --input-dir + 产物中的 文件:行号「原话」直引，
引文逐字校验由 verify_quotes 承接。规范见 prd-record-spec/SKILL.md。"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
SCRIPT = os.path.join(ROOT, ".opencode", "skills")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run(label, command, artifacts):
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "label": label,
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
        "artifacts": {os.path.abspath(path): digest(path) for path in artifacts if path and os.path.isfile(path)},
        "scripts": {path: digest(path) for path in command[1:] if path.endswith(".py") and os.path.isfile(path)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("tp", "tc", "full"), required=True)
    parser.add_argument("--input-dir", required=True, help="资料目录（纯文本：md/markdown/txt/csv）")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--quote-table", default="", help="引文机验输入；缺省时直接从 tp/tc 清单按引用语法抽引用")
    parser.add_argument("--scope-list", required=True)
    parser.add_argument("--tp-file", required=True)
    parser.add_argument("--tc-file", default="")
    parser.add_argument("--clarifications", default="")
    parser.add_argument("--prd-dir", default="")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    tools = {
        "baseline": os.path.join(SCRIPT, "prd-record-spec/scripts/verify_requirement_baseline.py"),
        "quotes": os.path.join(SCRIPT, "prd-record-spec/scripts/verify_quotes.py"),
        "tp": os.path.join(SCRIPT, "test-point-spec/scripts/verify_test_points.py"),
        "trace": os.path.join(SCRIPT, "test-point-spec/scripts/verify_traceability.py"),
        "tc": os.path.join(SCRIPT, "test-case-spec/scripts/verify_test_cases.py"),
    }
    started = time.monotonic()
    steps = []
    # 引文人肉面收口到 verify_quotes；缺省从 TP 清单自体抽引用（直引证据的单一来源是 TP）。
    # TP 无直引（纯 CL 证据）时不强制跑，避免“引用表为空”误判 FAIL。
    import re as _re
    CITE_SCAN = _re.compile(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L\d")
    quote_src = args.quote_table or args.tp_file
    cite_probe = (
        open(quote_src, encoding="utf-8-sig").read() if os.path.isfile(quote_src) else ""
    )
    if args.quote_table or CITE_SCAN.search(cite_probe):
        steps.append(run("source-quotes", [sys.executable, tools["quotes"], quote_src, "--input-dir", args.input_dir, "--extract-from"], [quote_src]))
    else:
        steps.append({"label": "source-quotes(skipped: 清单无直引引用，引文校验由基线机验覆盖)", "command": [], "exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.0, "artifacts": {}, "scripts": {}})
    baseline_command = [sys.executable, tools["baseline"], args.baseline, "--input-dir", args.input_dir, "--freeze"]
    if args.clarifications:
        baseline_command += ["--clarifications", args.clarifications]
    steps.append(run("requirements-baseline", baseline_command, [args.baseline]))

    if args.phase in ("tp", "full"):
        tp_command = [sys.executable, tools["tp"], args.tp_file, "--scope-list", args.scope_list, "--input-dir", args.input_dir]
        if args.clarifications:
            tp_command += ["--clarifications", args.clarifications]
        steps.append(run("test-points", tp_command, [args.tp_file, args.scope_list, args.clarifications]))
        steps.append(run("requirement-to-test-point", [sys.executable, tools["trace"], args.baseline, args.tp_file], [args.baseline, args.tp_file]))

    if args.phase in ("tc", "full"):
        if not args.tc_file:
            parser.error("--phase tc/full 必须提供 --tc-file")
        tc_command = [sys.executable, tools["tc"], args.tc_file, "--tp-file", args.tp_file, "--prd-dir", args.input_dir, "--scope-list", args.scope_list]
        steps.append(run("test-cases", tc_command, [args.tc_file, args.tp_file, args.scope_list]))
        steps.append(run("end-to-end-traceability", [sys.executable, tools["trace"], args.baseline, args.tp_file, args.tc_file], [args.baseline, args.tp_file, args.tc_file]))

    report = {
        "schema_version": 1,
        "phase": args.phase,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": round(time.monotonic() - started, 3),
        "toolchain": {
            os.path.abspath(__file__): digest(__file__),
            os.path.join(os.path.dirname(__file__), "verify_validation_report.py"): digest(os.path.join(os.path.dirname(__file__), "verify_validation_report.py")),
        },
        "steps": steps,
        "passed": all(step["exit_code"] == 0 for step in steps),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    for step in steps:
        print(f"[{ 'PASS' if step['exit_code'] == 0 else 'FAIL' }] {step['label']} (exit={step['exit_code']})")
        if step["stdout"].strip():
            print(step["stdout"].rstrip())
        if step["stderr"].strip():
            print(step["stderr"].rstrip(), file=sys.stderr)
    print(f"[REPORT] {args.report}")
    print(f"========== 校验汇总: {'PASS' if report['passed'] else 'FAIL'} ==========")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
