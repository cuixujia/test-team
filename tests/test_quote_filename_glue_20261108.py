#!/usr/bin/env python3
"""2026-11-08 回归：文件名被散文前缀黏连时的引文机验鲁棒性。

对应改造（仅改 prd-record-spec/scripts/verify_quotes.py）：
  A. 文件 token 与资料目录实际文件对照消歧：token 以真实文件名为后缀时按最长命中解析，
     散文前缀（如「对应」「依据」）不再被当作文件名 → 原先的 FileNotFoundError 整轮崩溃消除；
  B. 资料文件不存在 / 消歧不唯一 → 记 FAIL 行并继续跑完剩余条目，不再抛异常中断；
  C. 消歧结果写入报告工件 resolved_files，质检可按工件采信。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SK = os.path.join(ROOT, ".opencode", "skill")
QUOTES = os.path.join(SK, "prd-record-spec", "scripts", "verify_quotes.py")


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


class FilenameGlueTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="glue_")
        self.docs = os.path.join(self.base, "docs")
        os.makedirs(self.docs, exist_ok=True)
        with open(os.path.join(self.docs, "需求平台前端设计文档.md"), "w", encoding="utf-8") as f:
            f.write("第一行内容\n第二行内容\n")
        self.tc = os.path.join(self.base, "tc.md")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def write_tc(self, body):
        with open(self.tc, "w", encoding="utf-8") as f:
            f.write(body)

    def verify(self, extra=()):
        return run([sys.executable, QUOTES, self.tc, "--input-dir", self.docs, "--extract-from", *extra])

    def test_glued_filename_resolved_to_real_file(self):
        self.write_tc("步骤引用（对应需求平台前端设计文档.md:L2「第二行内容」）\n")
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RESOLVED", result.stdout)
        self.assertIn("PASS", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_file_is_fail_row_not_crash(self):
        self.write_tc(
            "首条坏引用（完全不存在资料.md:L1「x」）\n"
            "末条好引用（需求平台前端设计文档.md:L2「第二行内容」）\n"
        )
        report = os.path.join(self.base, "q.json")
        result = self.verify(["--report", report])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("资料文件不存在", result.stdout)
        self.assertIn("PASS", result.stdout)  # 坏条目之后的条目仍被校验
        with open(report, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["failed"], 1)
        self.assertEqual(data["passed"], 1)

    def test_ambiguous_filename_not_guessed(self):
        sub = os.path.join(self.docs, "sub")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, "需求平台前端设计文档.md"), "w", encoding="utf-8") as f:
            f.write("同名另一份\n")
        self.write_tc("引用（对应需求平台前端设计文档.md:L1「同名另一份」）\n")
        result = self.verify()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("文件名消歧不唯一", result.stdout)


if __name__ == "__main__":
    unittest.main()
