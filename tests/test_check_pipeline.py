#!/usr/bin/env python3
"""test_check_pipeline.py — check.py 统一机验入口的端到端冒烟（fixture 最小闭环）。

验证收敛后的管线行为：
  - --phase full 一次跑出 7 个步骤（quote-tp / quote-tc / requirements-baseline /
    test-points / requirement-to-test-point / test-cases / end-to-end-traceability）
    + report-freshness，全 PASS 且报告工件含引文子报告；
  - 主表定位主契约（第一个 ## 之前的表）对 verify_test_points / verify_test_cases /
    export_tables / check 四方一致生效（此前三套规则打架的回归护栏）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHECK = os.path.join(ROOT, ".opencode", "skills", "test-point-spec", "scripts", "check.py")
EXPORT = os.path.join(ROOT, ".opencode", "skills", "test-point-spec", "scripts", "export_tables.py")

PRD = """# 产品需求说明书
所属系统：测试系统 ｜ 所属业务活动：登录活动 ｜ 所属业务功能：登录展示

验证登录需密码校验规则。
首页展示验证词块。

完成标准：输入错误密码被拒绝，且名称为 登录展示。
"""

TP_MD = """# 测试点主表（登录展示，fixture）

| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |
|---|---|---|---|---|
| TP-001 | 验证错误密码登录被拒绝 | 功能 | 场景法 | prd.md:L4「验证登录需密码校验规则。」 |

## 覆盖对照表（证据→测试点）
| 证据（文件:行号） | 覆盖的 TP 编号 | 未覆盖原因 |
|---|---|---|
| prd.md:L4 | TP-001 |  |

## 需求→测试点覆盖表
| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |
|---|---|---|
| REQ-001 | TP-001 |  |
"""

TC_MD = """# 测试用例主表（登录展示，fixture）

| 编号 | 标题 | 关联TP | 优先级 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 用例类型 | 标签 |
|---|---|---|---|---|---|---|---|---|---|
| TC-001 | 错误密码登录，密码校验拒绝 | TP-001 | P1 | 已注册账户 | prd.md:L4「验证登录需密码校验规则。」造数口径 | ① 用错误密码登录 | ① 登录被拒绝，与 prd.md:L7「输入错误密码被拒绝」一致 | 反向 | 所属系统：测试系统；所属业务活动：登录活动；所属业务功能：登录展示 |

## 覆盖对照表（测试点→用例）
| TP编号 | 覆盖的 TC 编号 | 未覆盖原因 |
|---|---|---|
| TP-001 | TC-001 |  |
"""


class TestCheckPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = cls._tmp.name
        cls.input_dir = os.path.join(base, "docs")
        cls.sessions = os.path.join(base, "sess")
        os.makedirs(cls.input_dir)
        os.makedirs(os.path.join(cls.sessions, "scope"))
        os.makedirs(os.path.join(cls.sessions, "state"))
        os.makedirs(os.path.join(cls.sessions, "output", "reports"))
        os.makedirs(os.path.join(cls.sessions, "output", "tp"))
        os.makedirs(os.path.join(cls.sessions, "output", "tc"))

        prd_path = os.path.join(cls.input_dir, "prd.md")
        with open(prd_path, "w", encoding="utf-8") as f:
            f.write(PRD)
        tp_path = os.path.join(cls.sessions, "output", "tp", "test-point.md")
        with open(tp_path, "w", encoding="utf-8") as f:
            f.write(TP_MD)
        tc_path = os.path.join(cls.sessions, "output", "tc", "test-case.md")
        with open(tc_path, "w", encoding="utf-8") as f:
            f.write(TC_MD)

        import hashlib
        prd_sha = hashlib.sha256(PRD.encode("utf-8")).hexdigest()
        baseline = {
            "schema_version": 1,
            "selected_scope": [{"feature_id": "F01", "name": "登录展示"}],
            "input_files": [{"file": "prd.md", "sha256": prd_sha}],
            "requirements": [{
                "id": "REQ-001", "feature_id": "F01",
                "statement": "复述：登录需密码校验规则。", "risk": "P2", "status": "confirmed",
                "evidence": [{"file": "prd.md", "lines": "4", "quote": "验证登录需密码校验规则。"}],
            }],
        }
        with open(os.path.join(cls.sessions, "scope", "requirements-baseline.json"), "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)

        scope_list = """# 任务功能清单

## 一、功能清单
| 业务功能编号 | 业务功能名称 |
|---|---|
| F01 | 登录展示 |

## 二、资料角色登记
| 文件 | 角色 | 主用阶段 |
|---|---|---|
| prd.md | PRD 主资料 | 生成测试点（为主） |

## 三、归属登记
| 功能/依赖名称 | 所属系统 | 所属业务活动 |
|---|---|---|
| 登录展示 | 测试系统 | 登录活动 |
"""
        with open(os.path.join(cls.sessions, "state", "scope-list.md"), "w", encoding="utf-8") as f:
            f.write(scope_list)

        cls.tp_path = tp_path
        cls.tc_path = tc_path
        cls.baseline_path = os.path.join(cls.sessions, "scope", "requirements-baseline.json")
        cls.scope_path = os.path.join(cls.sessions, "state", "scope-list.md")
        cls.report_path = os.path.join(cls.sessions, "output", "reports", "check-full.json")

        result = subprocess.run(
            [sys.executable, CHECK, "--phase", "full",
             "--input-dir", cls.input_dir,
             "--baseline", cls.baseline_path,
             "--scope-list", cls.scope_path,
             "--tp-file", cls.tp_path, "--tc-file", cls.tc_path,
             "--report", cls.report_path],
            cwd=ROOT, text=True, capture_output=True)
        cls.proc = result

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_full_phase_all_steps_pass(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"check --phase full 应 PASS\nstdout:\n{self.proc.stdout}\nstderr:\n{self.proc.stderr}")
        report = json.load(open(self.report_path, encoding="utf-8"))
        labels = [s["label"] for s in report["steps"]]
        self.assertIn("quote-tp", labels)
        self.assertIn("quote-tc", labels)
        self.assertIn("requirements-baseline", labels)
        self.assertIn("test-points", labels)
        self.assertIn("test-cases", labels)
        self.assertIn("end-to-end-traceability", labels)
        self.assertTrue(report["passed"])
        quote_counts = {}
        for step in report["steps"]:
            if step["label"] in ("quote-tp", "quote-tc"):
                quote_counts[step["label"]] = step["stdout"].count("PASS 引用#")
        self.assertGreater(quote_counts.get("quote-tc", 0), 0, "TC 清单引文应进管线（quote-tc）")

    def test_sub_quote_reports_written(self):
        base = os.path.dirname(self.report_path)
        self.assertTrue(os.path.isfile(os.path.join(base, "check-full.quotes-tp.json")))
        self.assertTrue(os.path.isfile(os.path.join(base, "check-full.quotes-tc.json")))
        qtc = json.load(open(os.path.join(base, "check-full.quotes-tc.json"), encoding="utf-8"))
        self.assertEqual(qtc["failed"], 0)
        self.assertGreater(qtc["passed"], 0)

    def test_master_table_contract_consistent_across_consumers(self):
        # 主契约（第一个 ## 前的主表）对 verify_test_points / verify_test_cases / export_tables 一致生效
        tp_out = subprocess.run(
            [sys.executable, os.path.join(ROOT, ".opencode", "skills", "test-point-spec", "scripts", "verify_test_points.py"),
             self.tp_path, "--input-dir", self.input_dir, "--scope-list", self.scope_path],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(tp_out.returncode, 0, tp_out.stdout + tp_out.stderr)
        tc_out = subprocess.run(
            [sys.executable, os.path.join(ROOT, ".opencode", "skills", "test-case-spec", "scripts", "verify_test_cases.py"),
             self.tc_path, "--tp-file", self.tp_path, "--prd-dir", self.input_dir, "--scope-list", self.scope_path],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(tc_out.returncode, 0, tc_out.stdout + tc_out.stderr)
        view_path = os.path.join(os.path.dirname(self.tp_path), "test-point-table.md")
        ex_out = subprocess.run(
            [sys.executable, EXPORT, "--phase", "tp", "--tp-file", self.tp_path,
             "--baseline", self.baseline_path, "--scope-list", self.scope_path, "--output", view_path],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(ex_out.returncode, 0, ex_out.stdout + ex_out.stderr)
        view = open(view_path, encoding="utf-8").read()
        self.assertIn("登录展示", view, "视图业务功能列应为功能名称原文")
        self.assertNotIn("F01", view, "视图不应出现业务功能编号")


if __name__ == "__main__":
    unittest.main()
