#!/usr/bin/env python3
r"""回归：摘录里的管道符与表格布局——裸管道切断单元格、转义管道可解析、自愈回写指纹透明化。

对应改造：
  A. verify_test_points.py：依据证据项解析失败的报错文案指向真因（裸 `|` 切断单元格）；
     新增主表列数一致性 WARN（数据行单元格数 ≠ 表头列数 → 疑似未转义管道）。
  B. test-point-spec/SKILL.md：补「表格行原文的管道符必须写成 `\|`」「摘录只取一个单元格」纪律。
  C. verify_quotes.py：自愈回写前后指纹透明（source_sha256_after / artifact_changed）。
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

TP_VERIFY = os.path.join(SK, "test-point-spec", "scripts", "verify_test_points.py")
QUOTE_VERIFY = os.path.join(SK, "prd-record-spec", "scripts", "verify_quotes.py")

HEADER = "| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |\n|---|---|---|---|---|\n"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        h.update(stream.read())
    return h.hexdigest()


class QuoteEscapeLayoutTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="esc_")
        self.docs = os.path.join(self.base, "docs")
        os.makedirs(self.docs, exist_ok=True)
        # 原资料第 2 行是含管道符的表格行
        with open(os.path.join(self.docs, "doc.md"), "w", encoding="utf-8") as f:
            f.write(
                "无需登录即可浏览全部公开内容\n"
                "| 2 | productListPage | 产品线列表页 | M02 | 展示存款、贷款、理财、信用卡四大产品线分类 |\n"
            )

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def tp_path(self, name, body):
        path = os.path.join(self.base, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEADER + body)
        return path

    # A1: 裸管道摘录 → 依据单元格被切断 → FAIL 文案指向真因 + 列数不一致 WARN
    def test_a1_raw_pipe_breaks_cell_and_reports_root_cause(self):
        tp = self.tp_path(
            "tp-raw.md",
            "| TP-002 | 验证公开内容免登录可达 | 功能 | 等价类 | doc.md:L2「| 2 | productListPage | 产品线列表页 | M02 |」 |\n",
        )
        result = run([sys.executable, TP_VERIFY, tp, "--input-dir", self.docs])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        # 报错文案必须指向真因（未转义的管道符），而不是笼统的"未以直引开头"
        self.assertIn("依据证据项解析失败", result.stdout)
        self.assertIn("未转义", result.stdout)
        self.assertIn("TP-002", result.stdout)
        # 列数不一致 → WARN（只指方向，不 FAIL）
        self.assertIn("[WARN]", result.stdout)
        self.assertIn("单元格数", result.stdout)

    # A2: 转义管道摘录 → 单元格完整 → token 解析通过 + 逐字比对 PASS
    def test_a2_escaped_pipe_parses_and_matches(self):
        tp = self.tp_path(
            "tp-esc.md",
            "| TP-002 | 验证公开内容免登录可达 | 功能 | 等价类 | doc.md:L2「\\| 2 \\| productListPage \\| 产品线列表页 \\| M02 \\|」 |\n",
        )
        result = run([sys.executable, TP_VERIFY, tp, "--input-dir", self.docs])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("依据证据项解析失败", result.stdout)
        self.assertNotIn("单元格数", result.stdout)

        # 逐字比对：转义形态经归一后应命中原文行
        quoted = run([sys.executable, QUOTE_VERIFY, tp, "--input-dir", self.docs, "--extract-from"])
        self.assertEqual(quoted.returncode, 0, quoted.stdout + quoted.stderr)

    # C1: 自愈回写 → 报告指纹与磁盘一致，且明确标记产物已变更
    def test_c1_autofix_fingerprint_transparency(self):
        tp = os.path.join(self.base, "tp-auto.md")
        with open(tp, "w", encoding="utf-8") as f:
            f.write("TP 依据（漏字，应按行号自愈回填）：\ndoc.md:L1「无需即可浏览全部公开内容」\n")
        report_path = os.path.join(self.base, "quote-report.json")
        result = run([sys.executable, QUOTE_VERIFY, tp, "--input-dir", self.docs,
                      "--extract-from", "--autofix", "--report", report_path])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[产物已变更]", result.stdout)

        with open(report_path, encoding="utf-8") as stream:
            report = json.load(stream)
        self.assertTrue(report["artifact_changed"])
        self.assertEqual(report["source_sha256_after"], sha256_of(tp))
        self.assertNotEqual(report["source_sha256"], report["source_sha256_after"])

    # C2: 无回写时 → artifact_changed=False，前后指纹一致
    def test_c2_no_writeback_keeps_fingerprint(self):
        tp = os.path.join(self.base, "tp-clean.md")
        with open(tp, "w", encoding="utf-8") as f:
            f.write("TP 依据（转义形制，归一即命中，不应回写）：\ndoc.md:L2「\\| 2 \\| productListPage \\|」\n")
        report_path = os.path.join(self.base, "quote-report-clean.json")
        result = run([sys.executable, QUOTE_VERIFY, tp, "--input-dir", self.docs,
                      "--extract-from", "--autofix", "--report", report_path])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(report_path, encoding="utf-8") as stream:
            report = json.load(stream)
        self.assertFalse(report["artifact_changed"])
        self.assertEqual(report["source_sha256"], report["source_sha256_after"])


if __name__ == "__main__":
    unittest.main()
