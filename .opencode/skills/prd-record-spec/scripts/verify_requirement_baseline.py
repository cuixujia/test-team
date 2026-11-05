#!/usr/bin/env python3
"""Verify a structured requirements baseline against the source text files.

纯文本直引模式（唯一流程）：--input-dir + input_files 指纹绑定，证据对原文件逐字比对。
规范见 ../SKILL.md。

Baseline format (JSON):
   {"schema_version": 1,
    "input_files": [{"file": "...", "sha256": "..."}],
    "selected_scope": [{"feature_id": "BF01", "name": "..."}],
    "requirements": [{"id": "REQ-001", "feature_id": "BF01",
      "statement": "...", "risk": "P1", "status": "confirmed",
      "evidence": [{"file": "...", "lines": "596", "quote": "verbatim text"}]}]}
"""
import argparse
import hashlib
import json
import os
import re
import sys
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "test-script-lib", "scripts"))
from mdtable import norm_quote as norm  # noqa: E402 主表逐字比对口径：引文归一（2026-11-05 收敛）


VALID_STATUS = {"confirmed", "needs_clarification", "out_of_scope"}
VALID_RISK = {"P0", "P1", "P2", "P3"}

# 澄清记录解析口径（2026-11-05 收敛）：**行首**（允许表格竖线/引用前缀）必须是 CL-编号，
# 该行才登记为该 CL 的专属记录行——正文/留痕行中提到的 CL 编号不再污染登记表
# （2026-11-05 实测：留痕行首 CL 编号覆盖专属行导致摘录比对假 FAIL）。
CL_ROW_RE = re.compile(r"^\s*(?:\|[>]*\s*)?CL-\d{3}\b")


def load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


# norm 已由 test-script-lib/mdtable.py 提供（norm_quote：空白单格化+标点折叠+转义还原——与 verify_quotes 同口径）


def clarification_rows(path):
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8-sig") as stream:
        text = stream.read()
    rows = {}
    for line in text.splitlines():
        if CL_ROW_RE.match(line):
            m = re.search(r"CL-\d{3}", line)
            if m:
                rows[m.group(0)] = line
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", help="requirements-baseline.json")
    parser.add_argument("--input-dir", required=True, help="资料目录：证据 file+lines+quote 对原文件逐字比对")
    parser.add_argument("--clarifications", default="", help="澄清记录；引用 CL 证据时必填")
    parser.add_argument("--freeze", action="store_true", help="冻结前校验：不允许待澄清需求")
    args = parser.parse_args()
    baseline = load_json(args.baseline)
    errors, passes = [], []

    # 指纹绑定 + 引文对原文件逐字比对
    file_texts, file_digest = {}, {}

    def load_v2_file(rel):
        if rel not in file_texts:
            path = os.path.join(args.input_dir, rel)
            if not os.path.isfile(path):
                raise RuntimeError(f"资料文件不存在: {rel}")
            with open(path, encoding="utf-8-sig") as stream:
                file_texts[rel] = stream.read().splitlines()
            with open(path, "rb") as stream:
                file_digest[rel] = hashlib.sha256(stream.read()).hexdigest()
        return file_texts[rel]

    manifest = baseline.get("input_files")
    if not isinstance(manifest, list) or not manifest:
        errors.append("基线必须提供 input_files（file+sha256 指纹清单）")
        manifest = []
    for item in manifest:
        rel = str(item.get("file", ""))
        try:
            load_v2_file(rel)
            digest_actual = file_digest[rel]
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        if str(item.get("sha256", "")).lower() != digest_actual.lower():
            errors.append(
                f"指纹不一致（资料已变更）: {rel}（基线登记 {str(item.get('sha256', ''))[:12]} / 实际 {digest_actual[:12]}）"
            )

    def v2_quote_ok(rel, lines_spec, quote):
        try:
            lines = load_v2_file(rel)
        except RuntimeError:
            return False
        m = re.fullmatch(r"(\d+)(?:\s*[-~]\s*(\d+))?", str(lines_spec).strip())
        if not m:
            return False
        start, end = int(m.group(1)), int(m.group(2) or m.group(1))
        if start < 1 or end < start or end > len(lines):
            return False
        haystack = norm("\n".join(lines[start - 1:end]))
        return bool(quote) and norm(quote) in haystack

    if baseline.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")

    features = baseline.get("selected_scope", [])
    feature_ids = {item.get("feature_id") for item in features if isinstance(item, dict)}
    if not feature_ids:
        errors.append("selected_scope 至少要有一个 feature_id")
    if len(feature_ids) != len(features):
        errors.append("selected_scope 存在重复或无效的 feature_id")

    cl_map = clarification_rows(args.clarifications)

    requirements = baseline.get("requirements", [])
    if not isinstance(requirements, list) or not requirements:
        errors.append("requirements 必须是非空数组")
        requirements = []
    ids = [item.get("id") for item in requirements if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        errors.append("需求编号重复")

    for req in requirements:
        rid = req.get("id", "(无编号)")
        if not isinstance(rid, str) or not rid.startswith("REQ-"):
            errors.append(f"{rid}: 需求编号必须以 REQ- 开头")
        if req.get("feature_id") not in feature_ids:
            errors.append(f"{rid}: feature_id 不在 selected_scope 中")
        if not str(req.get("statement", "")).strip():
            errors.append(f"{rid}: statement 不能为空")
        status = req.get("status")
        if status not in VALID_STATUS:
            errors.append(f"{rid}: status 必须是 {', '.join(sorted(VALID_STATUS))}")
        if req.get("risk") not in VALID_RISK:
            errors.append(f"{rid}: risk 必须是 P0/P1/P2/P3")
        if status == "needs_clarification":
            if not str(req.get("question", "")).strip():
                errors.append(f"{rid}: 待澄清需求必须写明 question")
            if args.freeze:
                errors.append(f"{rid}: 仍待澄清，不能冻结需求基线")
        elif status == "out_of_scope" and not str(req.get("reason", "")).strip():
            errors.append(f"{rid}: 范围外需求必须写明 reason")

        evidence = req.get("evidence", [])
        if status == "confirmed" and not evidence:
            errors.append(f"{rid}: 已确认需求至少需要一条原文证据")
        for item in evidence:
            source_id = item.get("source_id")
            clarification_id = item.get("clarification_id")
            quote = str(item.get("quote", ""))
            if clarification_id:
                if source_id or item.get("file"):
                    errors.append(f"{rid}: 单条证据不能同时引用 PRD 和澄清")
                elif clarification_id not in cl_map:
                    errors.append(f"{rid}: 澄清证据不存在或未提供澄清记录 ({clarification_id})")
                elif quote and norm(quote) not in norm(cl_map[clarification_id]):
                    # 2026-11-05 收敛：澄清证据必填项 = 编号本身；quote 为可选的指向性摘录（比对按归一口径）。
                    errors.append(f"{rid}: 澄清证据摘录与记录不一致 ({clarification_id})")
                continue
            # 证据：{"file", "lines", "quote"} 对原文件逐字比对
            if source_id:
                errors.append(f"{rid}: 证据必须使用 file+lines+quote，不得使用 source_id")
                continue
            rel, lines_spec = str(item.get("file", "")), item.get("lines")
            if not rel or not lines_spec:
                errors.append(f"{rid}: 证据缺少 file 或 lines")
                continue
            if not v2_quote_ok(rel, lines_spec, quote):
                errors.append(f"{rid}: 引文未在 {rel}:L{lines_spec} 逐字命中")
            continue

    if not errors:
        passes.append(f"需求基线结构、范围、状态和证据校验通过（{len(requirements)} 条）")
    for item in passes:
        print(f"[PASS] {item}")
    for item in errors:
        print(f"[FAIL] {item}")
    print(f"========== 校验汇总: PASS={len(passes)} FAIL={len(errors)} ==========")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
