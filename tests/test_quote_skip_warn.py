#!/usr/bin/env python3
"""test_quote_skip_warn.py — quote-tp/quote-tc skip 分支的「无 L 前缀引用」告警护栏。

回归：跳过=静默放弃逐字保真（2026-11-06 实测双翻车：早期 check-tc 裸奔 quote-tc、
QA 语义报告把「已跑 AUTOFIX」误述为 skipped）。本测试锁：
  1. 主件引用带 L → 正常抽取，无 WARN；
  2. 主件引用漏 L（`文件:数字`）→ skip 分支降级为 warn 步骤，报告留 WARN 工件；
  3. 主件完全无引用 → 保持原 skip 逻辑不变。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHECK = os.path.join(ROOT, ".opencode", "skill", "test-point-spec", "scripts", "check.py")

PRD = """# 产品需求说明书
验证登录需密码校验规则。
首页展示验证词块。
完成标准：输入错误密码被拒绝。
"""

BASELINE = {
    "schema_version": 1,
    "selected_scope": [{"feature_id": "F01", "name": "登录展示"}],
    "requirements": [],
}


def make_baseline_files(base, tp_text):
    input_dir = os.path.join(base, "docs")
    sessions = os.path.join(base, "sess")
    os.makedirs(input_dir)
    for d in ("scope", "state", os.path.join("output", "reports"), os.path.join("output", "tp")):
        os.makedirs(os.path.join(sessions, d))
    with open(os.path.join(input_dir, "prd.md"), "w", encoding="utf-8") as f:
        f.write(PRD)
    import hashlib
    baseline = dict(BASELINE)
    baseline["input_files"] = [{"file": "prd.md", "sha256": hashlib.sha256(PRD.encode("utf-8")).hexdigest()}]
    baseline_path = os.path.join(sessions, "scope", "requirements-baseline.json")
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False)
    tp_path = os.path.join(sessions, "output", "tp", "test-point.md")
    with open(tp_path, "w", encoding="utf-8") as f:
        f.write(tp_text)
    report_path = os.path.join(sessions, "output", "reports", "check-tp.json")
    return input_dir, baseline_path, tp_path, report_path


def run_check(base, tp_text):
    input_dir, baseline_path, tp_path, report_path = make_baseline_files(base, tp_text)
    proc = subprocess.run(
        [sys.executable, CHECK, "--phase", "tp",
         "--input-dir", input_dir, "--baseline", baseline_path,
         "--tp-file", tp_path, "--report", report_path],
        cwd=ROOT, text=True, capture_output=True)
    report = json.load(open(report_path, encoding="utf-8")) if os.path.isfile(report_path) else None
    labels = [s["label"] for s in report["steps"]] if report else []
    return proc, labels


TP_WITH_L = """# 测试点清单
| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |
|---|---|---|---|---|
| TP-001 | 验证登录需密码校验 | 功能 | 场景法 | prd.md:L2「验证登录需密码校验规则。」 |
"""

TP_NO_L = """# 测试点清单
| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |
|---|---|---|---|---|
| TP-001 | 验证登录需密码校验 | 功能 | 场景法 | prd.md:2「验证登录需密码校验规则。」 |
"""

TP_NONE = """# 测试点清单
| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |
|---|---|---|---|---|
| TP-001 | 验证登录需密码校验 | 功能 | 场景法 | CL-001 |
"""


class QuoteSkipWarn(unittest.TestCase):
    def test_skip_warn_on_no_l_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, labels = run_check(tmp, TP_NO_L)
            self.assertTrue(any("quote-tp(warn" in x for x in labels), labels)
            self.assertIn("未带 L 前缀", proc.stdout)

    def test_no_warn_with_l_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, labels = run_check(tmp, TP_WITH_L)
            self.assertFalse(any("quote-tp(warn" in x for x in labels), labels)
            self.assertIn("PASS", proc.stdout)

    def test_plain_skip_retained_when_no_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, labels = run_check(tmp, TP_NONE)
            self.assertTrue(any(x.startswith("quote-tp(skipped") for x in labels), labels)
            self.assertNotIn("未带 L 前缀", proc.stdout)


if __name__ == "__main__":
    unittest.main()
