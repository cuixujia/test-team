import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, ".opencode", "skill", "prd-record-spec", "scripts")
TPS = os.path.join(ROOT, ".opencode", "skill", "test-point-spec", "scripts")
TCS = os.path.join(ROOT, ".opencode", "skill", "test-case-spec", "scripts")

QUOTE_TEXT = "提交人仅可查看本项目的风险。"


def dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
        stream.write("\n")


def run(script, *args):
    return subprocess.run(
        [sys.executable, script, *args], capture_output=True, text=True,
    )


def make_source(directory, name="prd.md", content="## 提交\n提交人仅可查看本项目的风险。\n"):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(content)
    return path


def make_baseline(directory, source_name, *, sha=None):
    path_src = os.path.join(directory, source_name)
    with open(path_src, "rb") as stream:
        digest = sha or hashlib.sha256(stream.read()).hexdigest()
    line_no = next(
        i
        for i, line in enumerate(open(path_src, encoding="utf-8-sig").read().splitlines(), 1)
        if re.sub(r"\s+", "", QUOTE_TEXT) in re.sub(r"\s+", "", line)
    )
    return {
        "schema_version": 1,
        "input_files": [{"file": source_name, "sha256": digest}],
        "selected_scope": [{"feature_id": "BF01", "name": "提交"}],
        "requirements": [{
            "id": "REQ-001", "feature_id": "BF01", "statement": "可见范围",
            "risk": "P1", "status": "confirmed",
            "evidence": [{"file": source_name, "lines": str(line_no), "quote": QUOTE_TEXT}],
        }],
    }


SCOPE_MD = """# 范围
| 业务功能编号 | 业务功能名称 | 来源PRD文件 | PRD位置 | PRD原始编号 |
|---|---|---|---|---|
| BF01 | 提交 | prd.md | 第1章 | R01 |
"""


class WorkflowToolsTest(unittest.TestCase):
    # ---- 基线机验（纯文本直引）----

    def test_requirement_baseline_accepts_direct_quote_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            baseline = make_baseline(directory, "prd.md")
            path = os.path.join(directory, "baseline.json")
            dump_json(path, baseline)
            result = run(os.path.join(SC, "verify_requirement_baseline.py"), path, "--input-dir", directory, "--freeze")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_requirement_baseline_detects_fingerprint_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            baseline = make_baseline(directory, "prd.md")
            baseline["input_files"][0]["sha256"] = "0" * 64
            path = os.path.join(directory, "baseline.json")
            dump_json(path, baseline)
            result = run(os.path.join(SC, "verify_requirement_baseline.py"), path, "--input-dir", directory, "--freeze")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("指纹不一致", result.stdout)

    def test_requirement_baseline_detects_quote_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            baseline = make_baseline(directory, "prd.md")
            baseline["requirements"][0]["evidence"][0]["quote"] = "提交人只可以查看本项目的风险。"
            path = os.path.join(directory, "baseline.json")
            dump_json(path, baseline)
            result = run(os.path.join(SC, "verify_requirement_baseline.py"), path, "--input-dir", directory, "--freeze")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("逐字命中", result.stdout)

    def test_requirement_baseline_freeze_rejects_open_question(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            baseline = make_baseline(directory, "prd.md")
            baseline["requirements"][0]["status"] = "needs_clarification"
            baseline["requirements"][0]["question"] = "可见范围是否包含管理员？"
            path = os.path.join(directory, "baseline.json")
            dump_json(path, baseline)
            result = run(os.path.join(SC, "verify_requirement_baseline.py"), path, "--input-dir", directory, "--freeze")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("不能冻结", result.stdout)

    # ---- 引文机验 ----

    def test_verify_quotes_detects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            quotes = os.path.join(directory, "quotes.md")
            with open(quotes, "w", encoding="utf-8") as stream:
                stream.write("| 来源文件 | 行号 | 原话摘录 |\n|---|---|---|\n| prd.md | 2 | 提交人可以查看项目风险 |\n")
            result = run(os.path.join(SC, "verify_quotes.py"), quotes, "--input-dir", directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL", result.stdout)

    def test_verify_quotes_accepts_verbatim_quote(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            quotes = os.path.join(directory, "quotes.md")
            with open(quotes, "w", encoding="utf-8") as stream:
                stream.write(f"| 来源文件 | 行号 | 原话摘录 |\n|---|---|---|\n| prd.md | 2 | {QUOTE_TEXT} |\n")
            result = run(os.path.join(SC, "verify_quotes.py"), quotes, "--input-dir", directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verify_quotes_rejects_object_json_loudly(self):
        """对象 JSON（如基线整文件）不得静默落为 0 条假 PASS，须显式报错并指引正确工具。"""
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            baseline = os.path.join(directory, "baseline.json")
            dump_json(baseline, make_baseline(directory, "prd.md"))
            result = run(os.path.join(SC, "verify_quotes.py"), baseline, "--input-dir", directory)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("JSON", result.stdout + result.stderr)
            self.assertIn("verify_requirement_baseline", result.stdout + result.stderr)

    # ---- 测试点机械校验（直引/CL 依据）----

    def test_test_point_accepts_multiple_direct_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory, "prd.md", "## 规则一\n提交人仅可查看本项目的风险。\n## 规则二\n风险名称必填，长度不超过 50 个字符。\n")
            scope = os.path.join(directory, "scope.md")
            with open(scope, "w", encoding="utf-8") as stream:
                stream.write(SCOPE_MD)
            tp = os.path.join(directory, "tp.md")
            with open(tp, "w", encoding="utf-8") as stream:
                stream.write(
                    "# TP\n| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |\n|---|---|---|---|---|\n"
                    "| TP-001 | 验证可见与必填组合生效 | 功能 | 场景法 | "
                    "prd.md:L2 「提交人仅可查看本项目的风险。」 ⟂ prd.md:L4 「风险名称必填，长度不超过 50 个字符。」 |\n"
                    "\n## 覆盖对照表（证据→测试点）\n| 证据（文件:行号） | 覆盖的 TP 编号 | 未覆盖原因 |\n|---|---|---|\n"
                    "| prd.md:L2 | TP-001 |  |\n| prd.md:L4 | TP-001 |  |\n"
                    "\n## 需求→测试点覆盖表\n| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |\n|---|---|---|\n"
                )
            result = run(os.path.join(TPS, "verify_test_points.py"), tp, "--input-dir", directory, "--scope-list", scope)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_test_point_rejects_legacy_anchor_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            make_source(directory)
            scope = os.path.join(directory, "scope.md")
            with open(scope, "w", encoding="utf-8") as stream:
                stream.write(SCOPE_MD)
            tp = os.path.join(directory, "tp.md")
            with open(tp, "w", encoding="utf-8") as stream:
                stream.write(
                    "# TP\n| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |\n|---|---|---|---|---|\n"
                    f"| TP-001 | 验证可见范围 | 功能 | 场景法 | M1-S1-P2 {QUOTE_TEXT} |\n"
                    "\n## 覆盖对照表（证据→测试点）\n| 证据（文件:行号） | 覆盖的 TP 编号 | 未覆盖原因 |\n|---|---|---|\n"
                    "\n## 需求→测试点覆盖表\n| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |\n|---|---|---|\n"
                )
            result = run(os.path.join(TPS, "verify_test_points.py"), tp, "--input-dir", directory, "--scope-list", scope)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("未以", result.stdout)

    def test_traceability_accepts_multiple_tps_per_case(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = os.path.join(directory, "baseline.json")
            tp = os.path.join(directory, "tp.md")
            tc = os.path.join(directory, "tc.md")
            prd_dir = os.path.join(directory, "docs")
            os.makedirs(prd_dir)
            with open(os.path.join(prd_dir, "prd.md"), "w", encoding="utf-8") as stream:
                stream.write("功能矩阵总表：提交\n")
            scope = os.path.join(directory, "scope.md")
            with open(scope, "w", encoding="utf-8") as stream:
                stream.write(SCOPE_MD)
            with open(baseline, "w", encoding="utf-8") as stream:
                json.dump({"requirements": [{"id": "REQ-001", "status": "confirmed"}]}, stream)
            with open(tp, "w", encoding="utf-8") as stream:
                stream.write("""# TP\n| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |\n|---|---|---|---|---|\n| TP-001 | 验证A | 功能 | 场景法 | prd.md:L1 「提交」 |\n| TP-002 | 验证B | 功能 | 场景法 | prd.md:L1 「提交」 |\n\n## 覆盖对照表（证据→测试点）\n| 证据（文件:行号） | 覆盖的 TP 编号 | 未覆盖原因 |\n|---|---|---|\n| prd.md:L1 | TP-001, TP-002 |  |\n\n## 需求→测试点覆盖表\n| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |\n|---|---|---|\n| REQ-001 | TP-001, TP-002 |  |\n""")
            with open(tc, "w", encoding="utf-8") as stream:
                stream.write("""# TC\n| 编号 | 标题 | 关联TP | 优先级 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 用例类型 | 标签 |\n|---|---|---|---|---|---|---|---|---|---|\n| TC-001 | 检查 | TP-001, TP-002 | P1 | 已登录 | 数据 | 提交 | 成功 | 正向 | 所属业务功能：提交 |\n\n## 覆盖对照表（测试点→用例）\n| TP编号 | 覆盖的 TC 编号 | 未覆盖原因 |\n|---|---|---|\n| TP-001 | TC-001 |  |\n| TP-002 | TC-001 |  |\n""")
            result = run(os.path.join(TPS, "verify_traceability.py"), baseline, tp, tc)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run(
                os.path.join(TCS, "verify_test_cases.py"), tc,
                "--tp-file", tp, "--prd-dir", prd_dir, "--scope-list", scope,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
