#!/usr/bin/env python3
r"""check.py — 交付机验统一入口（唯一命令）。

一次运行 = 一条绝对路径命令产一份带指纹的 JSON 报告，供质检专家按工件采信。

路径契约：
  --workspace-root 必填且为绝对路径；所有路径参数必须为绝对路径，相对参数
  直接 parser.error 退出码 2。子进程 cwd = workspace_root，主/子解析基准统一。

步骤与 phase（严格裁剪，不存在「只验 TC 却顺带验基线」的情况）：
  tp   : quote-tp, test-points, requirement-to-test-point, derive-coverage-table
  tc   : quote-tc, test-cases, end-to-end-traceability
  full : 上述全部 + requirements-baseline（终轮兜底）
  --only 可在上述集合内做增量；--only requirements-baseline 可单独跑基线。
  --freeze-baseline 仅在阶段 7 基线联签冻结时显式传入，默认关闭。

引文裁决：quote-tp / quote-tc 永不传 --autofix；verify_quotes.py 默认「误植即 FAIL」。
报告会读取 .quotes-*.json，出现 artifact_changed / auto_fixed 即判 AUTOFIX_DETECTED。

机验共 8 个可调度步骤（quote-tp / quote-tc / requirements-baseline / test-points /
requirement-to-test-point / test-cases / end-to-end-traceability / derive-coverage-table）；
report-freshness 是写报告前的工具链指纹、产物前后指纹与步骤集合复核，属内建自检，
不是 steps 内的步骤。终端输出与 qa-report 中的「全链 9 步」= 8 个步骤 + 该内建自检。

路径基准（由派发单【路径基准】注入实际绝对路径，命令发出前必须替换完毕）：
  <SKILLS_ROOT>    默认 ~/.config/opencode/skills 展开后的绝对路径（换机器自动跟随 HOME）；
                   也可由派发单直接给出绝对目录，或命令中直接写 ~/.config/opencode/skills/...
  <WORKSPACE_ROOT> 本次工作空间根目录绝对路径
  ~ 由 shell 展开、占位符由模型替换，最终传给本脚本的必须是绝对路径；
  未替换的 <…> 占位符与相对路径都会被 fail-fast 拦截（退出码 2）。

典型用法：
  python3 <SKILLS_ROOT>/test-point-spec/scripts/check.py \
    --workspace-root <WORKSPACE_ROOT> --phase tc \
    --input-dir <WORKSPACE_ROOT>/file/project-docs \
    --baseline <WORKSPACE_ROOT>/file/session-002549/scope/requirements-baseline.json \
    --scope-list <WORKSPACE_ROOT>/file/session-002549/state/scope-list.md \
    --tp-file <WORKSPACE_ROOT>/file/session-002549/output/tp/test-point.md \
    --tc-file <WORKSPACE_ROOT>/file/session-002549/output/tc/test-case.md \
    --clarifications <WORKSPACE_ROOT>/file/session-002549/state/clarifications.md \
    --report <WORKSPACE_ROOT>/file/session-002549/output/reports/check-tc.json

退出码：0 = 步骤、步骤集合与产物指纹复核全通过；1 = 任一 FAIL；2 = 用法错误。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

SCRIPT_DAT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # scripts → test-point-spec → skills，树内引用以 __file__ 为锚

STEP_NAMES = (
    "quote-tp", "quote-tc", "requirements-baseline", "test-points",
    "requirement-to-test-point", "test-cases", "end-to-end-traceability",
    "derive-coverage-table",
)
PHASE_STEPS = {
    "tp": ("quote-tp", "test-points", "requirement-to-test-point", "derive-coverage-table"),
    "tc": ("quote-tc", "test-cases", "end-to-end-traceability"),
    "full": tuple(STEP_NAMES),
}


def digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_report(report):
    """写盘前对内存报告复核工具链/产物/脚本指纹与步骤集合，返回失败列表。"""
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
        for key in ("artifacts", "scripts"):
            for path, expected in step.get(key, {}).items():
                if not os.path.isfile(path) or digest(path) != expected:
                    failures.append(f"{key} 已变化或不存在: {path}")
        if "skipped" in step.get("label", "") and not step.get("skip_allowed"):
            failures.append(f"步骤被意外跳过: {step.get('label')}")
    for label in report.get("expected_steps", []):
        if not any(s.get("label") == label or s.get("label", "").startswith(label + "(")
                   for s in report.get("steps", [])):
            failures.append(f"应跑步骤缺失: {label}")
    return failures


# 覆盖对照表自动推导：从 TP 主表「依据」列抽取 文件:行号「摘录」，
# 汇总为 证据→TP 数据视图。零新增脚本，归属 check.py 内建推导步骤。
import sys as _sys
import os as _os
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "test-script-lib", "scripts"))
from mdtable import parse_md_table  # noqa: E402

DCITE_RE = re.compile(
    r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L(\d+(?:\s*[-~]\s*\d+)?)\s*「([^」]{1,300})」"
)


def derive_coverage_md(tp_file):
    with open(tp_file, encoding="utf-8-sig") as stream:
        text = stream.read()
    _header, main_rows = parse_md_table(text, "")
    mapping = {}
    for row in main_rows:
        if not row or not re.fullmatch(r"TP-\d{3}", row[0]):
            continue
        tp_id = row[0]
        cited_cell = ""
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


def run(label, command, artifacts, extra_scripts=(), cwd=None):
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                            encoding="utf-8", errors="replace")
    paths = list(artifacts) + list(extra_scripts)
    return {
        "label": label,
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "duration_seconds": round(time.monotonic() - started, 3),
        "artifacts": {os.path.abspath(p): digest(p) for p in paths if p and os.path.isfile(p)},
        "scripts": {p: digest(p) for p in command[1:] if p.endswith(".py") and os.path.isfile(p)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("tp", "tc", "full"), required=True)
    parser.add_argument("--workspace-root", required=True, help="工作空间根绝对路径（所有工作空间侧路径的基准，也是子进程 cwd）")
    parser.add_argument("--input-dir", required=True, nargs="+",
                        help="资料目录绝对路径（可传多个：文本资料目录 + 会话转换区 user-input-converted）")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--quote-table", default="", help="引文机验输入覆盖（仅 --phase tp 允许；会跳过 quote-tc，tc/full 禁用）")
    parser.add_argument("--scope-list", default="")
    parser.add_argument("--tp-file", required=True)
    parser.add_argument("--tc-file", default="")
    parser.add_argument("--clarifications", default="")
    parser.add_argument("--manifest", default="", help="files-manifest.md 绝对路径；提供时基线 input_files 与入库指纹交叉校验")
    parser.add_argument("--only", default="", help="增量机验：只跑指定步骤（逗号分隔），步骤名须属于当前 phase")
    parser.add_argument("--freeze-baseline", action="store_true",
                        help="基线联签冻结判定；仅阶段 7 确认关口前显式传入，默认关闭")
    parser.add_argument("--report", required=True, help="机验 JSON 输出绝对路径（约定 check-<phase>.json）")
    args = parser.parse_args()

    def abs_arg(name, value):
        if value and not os.path.isabs(value):
            parser.error(f"{name} 必须为绝对路径（禁止相对路径与占位符）: {value}")
        return os.path.abspath(value) if value else value

    args.workspace_root = abs_arg("--workspace-root", args.workspace_root)
    for name in ("baseline", "quote_table", "scope_list", "tp_file", "tc_file",
                 "clarifications", "manifest", "report"):
        setattr(args, name, abs_arg("--" + name.replace("_", "-"), getattr(args, name)))
    args.input_dir = [abs_arg("--input-dir", d) for d in args.input_dir]

    if not os.path.isdir(args.workspace_root):
        parser.error(f"--workspace-root 目录不存在: {args.workspace_root}")
    if args.phase in ("tc", "full") and not args.scope_list:
        parser.error("--phase tc/full 必须提供 --scope-list")
    if args.phase in ("tc", "full") and not args.tc_file:
        parser.error("--phase tc/full 必须提供 --tc-file")
    if args.quote_table and args.phase != "tp":
        parser.error("--quote-table 会跳过 quote-tc 逐字机验，仅 --phase tp 允许；tc/full 请在主件内写 文件:L行号「摘录」 直引语法")
    if args.freeze_baseline and args.phase == "tc":
        parser.error("--freeze-baseline 仅阶段 7（--phase tp 关口①前）或 --phase full 可用，--phase tc 禁止")

    required = [("--baseline", args.baseline), ("--tp-file", args.tp_file)]
    if args.phase in ("tc", "full"):
        required += [("--tc-file", args.tc_file), ("--scope-list", args.scope_list)]
    for name, path in required:
        if not os.path.isfile(path):
            parser.error(f"FILE_NOT_FOUND: {name} 不存在或非文件: {path}")
    for d in args.input_dir:
        if not os.path.isdir(d):
            parser.error(f"FILE_NOT_FOUND: --input-dir 不存在或非目录: {d}")
    if args.quote_table and not os.path.isfile(args.quote_table):
        parser.error(f"FILE_NOT_FOUND: --quote-table 不存在或非文件: {args.quote_table}")

    workspace_paths = [("--report", args.report), ("--baseline", args.baseline),
                       ("--tp-file", args.tp_file)]
    if args.phase in ("tc", "full"):
        workspace_paths += [("--tc-file", args.tc_file), ("--scope-list", args.scope_list)]
    for name, path in workspace_paths:
        if os.path.commonpath([args.workspace_root, path]) != args.workspace_root:
            parser.error(f"{name} 必须位于 --workspace-root 内: {path}")

    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    if only:
        unknown = sorted(only - set(STEP_NAMES))
        if unknown:
            parser.error(f"--only 含未知步骤名: {', '.join(unknown)}；可选: {', '.join(STEP_NAMES)}")
        extra = {"requirements-baseline"} if "requirements-baseline" in only else set()
        invalid = sorted(only - set(PHASE_STEPS[args.phase]) - extra)
        if invalid:
            parser.error(f"--only 含不属于 --phase {args.phase} 的步骤: {', '.join(invalid)}")
    selected = [s for s in PHASE_STEPS[args.phase] if only is None or s in only]
    if only and "requirements-baseline" in only and "requirements-baseline" not in selected:
        selected.append("requirements-baseline")
    # 阶段 7 基线联签冻结：显式传 --freeze-baseline 时把基线校验并入本轮步骤
    if args.freeze_baseline and "requirements-baseline" not in selected:
        selected.append("requirements-baseline")

    def active(label):
        return (label in PHASE_STEPS[args.phase]
                or (only is not None and label in only)
                or (label == "requirements-baseline" and args.freeze_baseline))

    def want(label):
        return label in selected

    def skipped(label, note, allowed=False):
        return {"label": f"{label}(skipped: {note})", "command": [], "exit_code": 0,
                "stdout": "", "stderr": "", "duration_seconds": 0.0,
                "artifacts": {}, "scripts": {}, "skip_allowed": bool(allowed)}

    def failure_step(label, note):
        return {"label": label, "command": [], "exit_code": 1,
                "stdout": "", "stderr": note, "duration_seconds": 0.0,
                "artifacts": {}, "scripts": {}, "skip_allowed": False}

    tools = {
        "baseline": os.path.join(SCRIPT_DAT, "prd-record-spec/scripts/verify_requirement_baseline.py"),
        "quotes": os.path.join(SCRIPT_DAT, "prd-record-spec/scripts/verify_quotes.py"),
        "tp": os.path.join(SCRIPT_DAT, "test-point-spec/scripts/verify_test_points.py"),
        "trace": os.path.join(SCRIPT_DAT, "test-point-spec/scripts/verify_traceability.py"),
        "tc": os.path.join(SCRIPT_DAT, "test-case-spec/scripts/verify_test_cases.py"),
    }
    report_abspath = args.report
    report_dir = os.path.dirname(report_abspath)
    report_stem = os.path.splitext(os.path.basename(report_abspath))[0]

    def quote_report_path(kind):
        return os.path.join(report_dir, f"{report_stem}.quotes-{kind}.json")

    def quote_guard(step, qr_path):
        try:
            with open(qr_path, encoding="utf-8") as stream:
                qr = json.load(stream)
        except (OSError, ValueError) as exc:
            step["exit_code"] = 1
            step["stderr"] = f"QUOTE_REPORT_MISSING: {qr_path} ({exc})"
            return step
        if qr.get("artifact_changed") or qr.get("auto_fixed"):
            step["exit_code"] = 1
            step["label"] = step["label"] + "(autofix-detected)"
            step["stderr"] = (step.get("stderr", "") +
                              "\nAUTOFIX_DETECTED: 引文机验发生自愈或回写，产物已被工具改动，禁止采信").strip()
        return step

    def run_step(label, command, artifacts, extra_scripts=()):
        return run(label, command, artifacts, extra_scripts, cwd=args.workspace_root)

    started = time.monotonic()
    steps = []

    CITE_SCAN = re.compile(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L\d")
    NO_L_SCAN = re.compile(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):\s?\d")

    def text_of(path):
        """读取失败返回 None，由调用处生成 FILE_NOT_FOUND 失败步骤。"""
        try:
            with open(path, encoding="utf-8-sig") as stream:
                return stream.read()
        except OSError:
            return None

    def citation_failure(label, path, text):
        hits = [m.group(0) for m in NO_L_SCAN.finditer(text) if not CITE_SCAN.search(m.group(0))]
        if hits:
            return failure_step(label, f"NO_L_PREFIX: {path} 有 {len(hits)} 处疑似未带 L 前缀的引用（如 {hits[0]}），"
                                       "主件引用须写 文件:L行号「摘录」，修正后重跑机验")
        return failure_step(label, f"NO_CITATION_SYNTAX: {path} 未解析到任何 文件:L行号「摘录」 直引证据，逐字保真未被机验")

    watched = [p for p in (args.baseline, args.tp_file, args.tc_file, args.scope_list,
                           args.clarifications, args.manifest, args.quote_table) if p]

    def snapshot():
        return {p: digest(p) for p in watched if os.path.isfile(p)}

    artifacts_before = snapshot()

    # 1) TP 清单引文
    if active("quote-tp"):
        if not want("quote-tp"):
            steps.append(skipped("quote-tp", "--only 增量机验未选中", allowed=True))
        else:
            tp_quote_src = args.quote_table or args.tp_file
            text = text_of(tp_quote_src)
            if text is None:
                steps.append(failure_step("quote-tp", f"FILE_NOT_FOUND: 无法读取 {tp_quote_src}"))
            elif CITE_SCAN.search(text):
                qr_tp = quote_report_path("tp")
                step = run_step("quote-tp", [sys.executable, tools["quotes"], tp_quote_src,
                                            "--input-dir", *args.input_dir, "--extract-from",
                                            "--report", qr_tp], [tp_quote_src, qr_tp])
                steps.append(quote_guard(step, qr_tp))
            else:
                steps.append(citation_failure("quote-tp", tp_quote_src, text))

    # 2) TC 清单引文
    if active("quote-tc"):
        if not want("quote-tc"):
            steps.append(skipped("quote-tc", "--only 增量机验未选中", allowed=True))
        else:
            text = text_of(args.tc_file)
            if text is None:
                steps.append(failure_step("quote-tc", f"FILE_NOT_FOUND: 无法读取 {args.tc_file}"))
            elif CITE_SCAN.search(text):
                qr_tc = quote_report_path("tc")
                step = run_step("quote-tc", [sys.executable, tools["quotes"], args.tc_file,
                                            "--input-dir", *args.input_dir, "--extract-from",
                                            "--report", qr_tc], [args.tc_file, qr_tc])
                steps.append(quote_guard(step, qr_tc))
            else:
                steps.append(citation_failure("quote-tc", args.tc_file, text))

    # 3) 基线（仅 full 或 --only requirements-baseline）
    if active("requirements-baseline"):
        if not want("requirements-baseline"):
            steps.append(skipped("requirements-baseline", "--only 增量机验未选中", allowed=True))
        else:
            baseline_command = [sys.executable, tools["baseline"], args.baseline,
                                "--input-dir", *args.input_dir]
            if args.freeze_baseline:
                baseline_command.append("--freeze")
            if args.clarifications:
                baseline_command += ["--clarifications", args.clarifications]
            if args.manifest:
                baseline_command += ["--manifest", args.manifest]
            artifacts = [args.baseline, args.manifest, args.clarifications]
            steps.append(run_step("requirements-baseline", baseline_command, artifacts))

    # 4) TP 结构与追溯
    if active("test-points"):
        if not want("test-points"):
            steps.append(skipped("test-points", "--only 增量机验未选中", allowed=True))
        else:
            tp_command = [sys.executable, tools["tp"], args.tp_file, "--input-dir", *args.input_dir]
            if args.scope_list:
                tp_command += ["--scope-list", args.scope_list]
            if args.clarifications:
                tp_command += ["--clarifications", args.clarifications]
            steps.append(run_step("test-points", tp_command,
                                  [args.tp_file, args.scope_list, args.clarifications]))
    if active("requirement-to-test-point"):
        if not want("requirement-to-test-point"):
            steps.append(skipped("requirement-to-test-point", "--only 增量机验未选中", allowed=True))
        else:
            steps.append(run_step("requirement-to-test-point",
                                  [sys.executable, tools["trace"], args.baseline, args.tp_file],
                                  [args.baseline, args.tp_file]))

    # 5) TC 结构与端到端追溯
    if active("test-cases"):
        if not want("test-cases"):
            steps.append(skipped("test-cases", "--only 增量机验未选中", allowed=True))
        else:
            tc_command = [sys.executable, tools["tc"], args.tc_file, "--tp-file", args.tp_file,
                          "--prd-dir", *args.input_dir, "--scope-list", args.scope_list]
            steps.append(run_step("test-cases", tc_command,
                                  [args.tc_file, args.tp_file, args.scope_list]))
    if active("end-to-end-traceability"):
        if not want("end-to-end-traceability"):
            steps.append(skipped("end-to-end-traceability", "--only 增量机验未选中", allowed=True))
        else:
            steps.append(run_step("end-to-end-traceability",
                                  [sys.executable, tools["trace"], args.baseline,
                                   args.tp_file, args.tc_file],
                                  [args.baseline, args.tp_file, args.tc_file]))

    # 6) 覆盖对照表自动推导
    if active("derive-coverage-table"):
        if not want("derive-coverage-table"):
            steps.append(skipped("derive-coverage-table", "--only 增量机验未选中", allowed=True))
        else:
            derived = derive_coverage_md(args.tp_file)
            if not derived:
                steps.append(failure_step("derive-coverage-table",
                                          "NO_COVERAGE_DATA: TP 主表依据列未解析到任何 文件:L行号「摘录」 证据"))
            else:
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
                    "scripts": {}, "skip_allowed": False,
                })

    artifacts_after = snapshot()
    artifact_drift = [p for p in watched if artifacts_before.get(p) != artifacts_after.get(p)]
    for path in artifact_drift:
        steps.append(failure_step("ARTIFACT_CHANGED_DURING_CHECK",
                                  f"机验期间产物被改动: {path}（{artifacts_before.get(path)} → {artifacts_after.get(path)}）"))

    report = {
        "schema_version": 1,
        "phase": args.phase,
        "workspace_root": args.workspace_root,
        "expected_steps": selected,
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
        "artifacts_before": artifacts_before,
        "artifacts_after": artifacts_after,
        "artifact_drift": artifact_drift,
        "failure_summary": [
            {"step": s["label"],
             "detail": ((s.get("stderr") or s.get("stdout") or "").strip().splitlines() or [""])[0]}
            for s in steps if s["exit_code"] != 0
        ],
        "passed": True,
    }
    freshness_failures = validate_report(report)
    report["passed"] = not freshness_failures and not artifact_drift
    report["freshness_failures"] = freshness_failures

    os.makedirs(report_dir, exist_ok=True)
    with open(report_abspath, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    with open(report_abspath, encoding="utf-8") as stream:
        written = json.load(stream)
    reread_failures = []
    if written.get("schema_version") != 1:
        reread_failures.append("读回复核: schema_version 不为 1")
    if written.get("passed") is not report["passed"]:
        reread_failures.append("读回复核: passed 与内存判定不一致")
    if [s.get("label") for s in written.get("steps", [])] != [s["label"] for s in steps]:
        reread_failures.append("读回复核: steps 与内存不一致")
    if written.get("artifact_drift") != artifact_drift:
        reread_failures.append("读回复核: artifact_drift 与内存不一致")

    for step in steps:
        print(f"[{'PASS' if step['exit_code'] == 0 else 'FAIL'}] {step['label']} (exit={step['exit_code']})")
        stdout = step.get("stdout") or ""
        stderr = step.get("stderr") or ""
        if stdout.strip() and "skipped" not in step["label"]:
            print(stdout.rstrip())
        if stderr.strip():
            print(stderr.rstrip(), file=sys.stderr)
    if freshness_failures or reread_failures:
        print("[FAIL] report-freshness")
        for item in freshness_failures + reread_failures:
            print(f"  - {item}", file=sys.stderr)
    else:
        print("[PASS] report-freshness（工具链、产物指纹、步骤集合与读回独立复核通过）")
    print(f"[REPORT] {report_abspath}")
    exit_code = 0 if (report["passed"] and not reread_failures) else 1
    print(f"========== 校验汇总: {'PASS' if exit_code == 0 else 'FAIL'} ==========")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileNotFoundError as exc:
        print(f"[FAIL] FILE_NOT_FOUND: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa
        print(f"[FAIL] 校验脚本异常: {exc}")
        sys.exit(1)
