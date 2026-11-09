#!/usr/bin/env python3
"""2026-11-05 复盘收敛回归：引文表示法归一、摘录自愈、CL 专属行、辅资料豁免、增量机验。

对应改造（零新增脚本，仅改 test-script-lib/scripts/mdtable.py、verify_quotes.py、verify_requirement_baseline.py、
verify_test_points.py、verify_traceability.py、check.py）：
  A. norm_quote：全/半角标点+引号形制+Markdown 转义归一——表示法差异不再 FAIL
  B. --autofix：行号正确且骨架命中 → 按行号回读原文回填（产物唯一出现时原位回写）
  C. 澄清记录解析改为 行首专属行，留痕行不再污染
  D. 澄清型证据 quote 可选（编号即可）
  E. 覆盖对照表可省略（derive-coverage-table 自动推导）
  F. 辅资料补充验证点豁免需求关联（WARN 不 FAIL）
  G. check.py --only 增量机验
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SK = os.path.join(ROOT, ".opencode", "skill")


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        h.update(stream.read())
    return h.hexdigest()


class ToleranceTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="tol_")
        self.docs = os.path.join(self.base, "docs")
        os.makedirs(self.docs, exist_ok=True)
        # 原资料：第 1 行普通句；第 2 行表格行（含管道符）；第 3 行全角标点句
        with open(os.path.join(self.docs, "doc.md"), "w", encoding="utf-8") as f:
            f.write(
                "无需登录即可浏览全部公开内容\n"
                "| 2 | productListPage | 产品线列表页 | M02 | 展示存款、贷款、理财、信用卡四大产品线分类 |\n"
                "网点信息以静态列表/页面呈现（可按区域筛选），构建周期为两周。\n"
            )

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def quotes_run(self, source, extra=(), use_tmp_copy=True):
        path = os.path.join(self.base, os.path.basename(source))
        content = open(source, encoding="utf-8").read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return run(
            [sys.executable, os.path.join(SK, "prd-record-spec", "scripts", "verify_quotes.py"),
             path, "--input-dir", self.docs, *extra]
        ), path

    # A1: 全/半角标点折叠——摘录与原文仅标点形制差异时 PASS
    def test_a1_punctuation_folded(self):
        q = os.path.join(self.base, "q.md")
        with open(q, "w", encoding="utf-8") as f:
            f.write("| 来源文件 | 行号 | 原话/摘录 |\n|---|---|---|\n| doc.md | 3 | 网点信息以静态列表/页面呈现,可按区域筛选,构建周期为两周 |\n")
        result = run([sys.executable, os.path.join(SK, "prd-record-spec", "scripts", "verify_quotes.py"),
                      q, "--input-dir", self.docs])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # A2 + B: Markdown 表格 `\|` 转义还原即命中；漏字摘录 → 骨架子序列自愈并回写唯一产物
    def test_b_autofix_escape_and_recovery(self):
        tp = os.path.join(self.base, "tp.md")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(
                "TP 依据首条（转义形制错误，应归一还原即命中）：\n"
                "doc.md:L2「\\| 2 \\| productListPage |」\n"
                "TP 依据次条（漏字，应按行号自愈回填）：\n"
                "doc.md:L1「无需即可浏览全部公开内容」\n"
            )
        result = run([sys.executable, os.path.join(SK, "prd-record-spec", "scripts", "verify_quotes.py"),
                      tp, "--input-dir", self.docs, "--extract-from", "--autofix"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("AUTOFIX"), 1, result.stdout)  # 仅漏字段自愈；转义条归一直接 PASS
        fixed = open(tp, encoding="utf-8").read()
        self.assertIn("无需登录即可浏览全部公开内容", fixed)  # 漏字按原文回填

    # B 反例: 行号指错（骨架不命中）→ 仍 FAIL
    def test_b2_wrong_line_still_fails(self):
        q = os.path.join(self.base, "q.md")
        with open(q, "w", encoding="utf-8") as f:
            f.write("| 来源文件 | 行号 | 原话/摘录 |\n|---|---|---|\n| doc.md | 1 | 网点信息以静态列表呈现 |\n")
        result = run([sys.executable, os.path.join(SK, "prd-record-spec", "scripts", "verify_quotes.py"),
                      q, "--input-dir", self.docs])
        self.assertEqual(result.returncode, 1)
        self.assertIn("未在指定行命中", result.stdout)

    # C + D: CL 行首专属行解析 + 澄清证据 quote 可选
    def test_cd_cl_dedicated_row_and_optional_quote(self):
        clar = os.path.join(self.base, "clar.md")
        with open(clar, "w", encoding="utf-8") as f:
            f.write(
                "| CL编号 | 结论 |\n|---|---|\n"
                "| CL-001 | 点击首页顶部搜索跳转至资讯检索，范围为已发布资讯 |\n"
                "| CL-002 | 仅记录字段，不控制对外可见 |\n"
                "\n> 基线修复项登记：按第一条结论补 P-04/P-05 挂号（CL-001/CL-002 为其编号），不要覆盖前面行。\n"
            )
        baseline = {
            "schema_version": 1,
            "selected_scope": [{"feature_id": "F01", "name": "官网首页展示"}],
            "input_files": [{"file": "doc.md", "sha256": sha256_of(os.path.join(self.docs, "doc.md"))}],
            "requirements": [
                {"id": "REQ-001", "feature_id": "F01", "statement": "搜索跳转资讯检索", "risk": "P2",
                 "status": "confirmed",
                 "evidence": [{"clarification_id": "CL-001"}]},
            ],
        }
        bpath = os.path.join(self.base, "baseline.json")
        with open(bpath, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False)
        result = run([sys.executable, os.path.join(SK, "prd-record-spec", "scripts", "verify_requirement_baseline.py"),
                      bpath, "--input-dir", self.docs, "--clarifications", clar])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)  # D: 仅编号即可

        # 反例: CL 编号不存在 → FAIL
        baseline["requirements"][0]["evidence"] = [{"clarification_id": "CL-009"}]
        with open(bpath, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False)
        result = run([sys.executable, os.path.join(SK, "prd-record-spec", "scripts", "verify_requirement_baseline.py"),
                      bpath, "--input-dir", self.docs, "--clarifications", clar])
        self.assertEqual(result.returncode, 1)
        self.assertIn("CL-009", result.stdout)

    # E + F: TP 辅资料豁免 + 覆盖对照表可省略；G: check.py --only
    def test_ef_trace_aux_and_missing_coverage_table(self):
        tp = os.path.join(self.base, "test-point.md")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(
                "| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |\n"
                "|---|---|---|---|---|\n"
                "| TP-001 | 验证公开内容免登录可达 | 功能 | 等价类 | doc.md:L1「无需登录即可浏览全部公开内容」 |\n"
                "| TP-002 | 验证主流浏览器渲染兼容 | 非功能 | 等价类 | doc.md:L3「网点信息以静态列表/页面呈现」辅资料补充（渲染兼容维度，无基线需求） |\n"
                "\n## 需求→测试点覆盖表\n\n"
                "| 需求编号 | 测试点 | 未覆盖原因 |\n|---|---|---|\n"
                "| REQ-001 | TP-001 | |\n"
            )
        baseline = {
            "schema_version": 1,
            "selected_scope": [{"feature_id": "F01", "name": "官网首页展示"}],
            "input_files": [{"file": "doc.md", "sha256": sha256_of(os.path.join(self.docs, "doc.md"))}],
            "requirements": [
                {"id": "REQ-001", "feature_id": "F01", "statement": "公开内容免登录可达", "risk": "P2",
                 "status": "confirmed",
                 "evidence": [{"file": "doc.md", "lines": "1", "quote": "无需登录即可浏览全部公开内容"}]},
            ],
        }
        bpath = os.path.join(self.base, "baseline.json")
        with open(bpath, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False)

        # 语义关: 辅资料豁免 → WARN 不 FAIL
        result = run([sys.executable, os.path.join(SK, "test-point-spec", "scripts", "verify_traceability.py"),
                      bpath, tp])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("辅资料补充验证点", result.stdout)

        # 结构关: 覆盖对照表缺失 → 不 FAIL
        result = run([sys.executable, os.path.join(SK, "test-point-spec", "scripts", "verify_test_points.py"),
                      tp, "--input-dir", self.docs])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("覆盖对照表未手工提供", result.stdout)

        # 统一入口: 全量 PASS 且自动生成 derived-coverage；--only 只跑指定步骤
        reports = os.path.join(self.base, "r")
        os.makedirs(reports, exist_ok=True)
        report1 = os.path.join(reports, "check-tp.json")
        full = run([sys.executable, os.path.join(SK, "test-point-spec", "scripts", "check.py"),
                    "--phase", "tp", "--input-dir", self.docs, "--baseline", bpath,
                    "--tp-file", tp, "--report", report1])
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        derived = os.path.join(reports, "check-tp.derived-coverage.md")
        self.assertTrue(os.path.isfile(derived), full.stdout)
        self.assertIn("| doc.md:L1 | TP-001 |", open(derived, encoding="utf-8").read())

        report2 = os.path.join(reports, "check-tp-only.json")
        only = run([sys.executable, os.path.join(SK, "test-point-spec", "scripts", "check.py"),
                    "--phase", "tp", "--input-dir", self.docs, "--baseline", bpath,
                    "--tp-file", tp, "--report", report2,
                    "--only", "requirement-to-test-point"])
        self.assertEqual(only.returncode, 0, only.stdout + only.stderr)
        steps = [s["label"] for s in json.load(open(report2, encoding="utf-8"))["steps"]]
        self.assertIn("requirement-to-test-point", steps)
        # --only 未选中的步骤以 skipped 占位保留（exit 0），报告仍完整记录增量口径
        self.assertEqual([s for s in steps if "(skipped" not in s], ["requirement-to-test-point"])


if __name__ == "__main__":
    unittest.main()
