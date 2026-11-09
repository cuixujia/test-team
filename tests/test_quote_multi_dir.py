#!/usr/bin/env python3
"""test_quote_multi_dir.py — 机验多目录契约（2026-11-09 docx/xlsx 转换方案配套）。

锁定三件事：
① verify_quotes.py 可收多个 --input-dir：文本目录 + 转换区分居时，两边登记 rel 的引文都能逐字命中；
② 同名文件跨目录 → 歧义 FAIL（禁止猜）；
③ verify_requirement_baseline.py --input-dir 多目录时按 rel 于各目录定位并核对指纹。
"""
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QS = os.path.join(ROOT, ".opencode", "skill", "prd-record-spec", "scripts", "verify_quotes.py")
BL = os.path.join(ROOT, ".opencode", "skill", "prd-record-spec", "scripts", "verify_requirement_baseline.py")


def run(script, *args):
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True)


def make_workspace(base):
    """文本资料目录 docs/ 与转换区 converted/（内含 user-input 前缀子目录）。"""
    docs = os.path.join(base, "docs")
    conv = os.path.join(base, "converted", "user-input")
    os.makedirs(docs)
    os.makedirs(conv)
    with open(os.path.join(docs, "PRD.md"), "w", encoding="utf-8") as f:
        f.write("# 需求\n用户注册需要手机号验证。\n")
    with open(os.path.join(conv, "设计稿.md"), "w", encoding="utf-8") as f:
        f.write("<!-- converted from: 设计稿.docx -->\n登录方式支持密码、验证码。\n")
    return docs, conv


class TestQuotesMultiDir(unittest.TestCase):
    def test_quotes_hit_across_two_dirs(self):
        base = tempfile.mkdtemp()
        docs, conv = make_workspace(base)
        quotes_path = os.path.join(base, "quotes.json")
        quotes = [
            {"seq": 1, "file": "PRD.md", "lines": "2", "quote": "用户注册需要手机号验证。"},
            {"seq": 2, "file": "user-input/设计稿.md", "lines": "2", "quote": "登录方式支持密码、验证码。"},
        ]
        with open(quotes_path, "w", encoding="utf-8") as f:
            json.dump(quotes, f, ensure_ascii=False)
        result = run(QS, quotes_path, "--input-dir", docs, conv)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS=2", result.stdout)

    def test_same_basename_across_dirs_is_ambiguous(self):
        base = tempfile.mkdtemp()
        docs, conv = make_workspace(base)
        with open(os.path.join(conv, "PRD.md"), "w", encoding="utf-8") as f:
            f.write("另一份同名\n")
        quotes_path = os.path.join(base, "quotes.json")
        quotes = [{"seq": 1, "file": "PRD.md", "lines": "1", "quote": "需求"}]
        with open(quotes_path, "w", encoding="utf-8") as f:
            json.dump(quotes, f, ensure_ascii=False)
        result = run(QS, quotes_path, "--input-dir", docs, conv)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("歧义", result.stdout)
        self.assertIn("FAIL=1", result.stdout)

    def test_single_dir_usage_still_works(self):
        base = tempfile.mkdtemp()
        docs, _conv = make_workspace(base)
        quotes_path = os.path.join(base, "quotes.json")
        quotes = [{"seq": 1, "file": "PRD.md", "lines": "2", "quote": "用户注册需要手机号验证。"}]
        with open(quotes_path, "w", encoding="utf-8") as f:
            json.dump(quotes, f, ensure_ascii=False)
        result = run(QS, quotes_path, "--input-dir", docs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestBaselineMultiDir(unittest.TestCase):
    def test_baseline_fingerprint_locates_file_in_converted_dir(self):
        base = tempfile.mkdtemp()
        docs, _conv_leaf = make_workspace(base)
        conv_root = os.path.join(base, "converted")
        target = os.path.join(conv_root, "user-input", "设计稿.md")
        with open(target, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        baseline_path = os.path.join(base, "baseline.json")
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump({
                "schema_version": 1,
                "input_files": [{"file": "user-input/设计稿.md", "sha256": digest}],
                "selected_scope": [{"feature_id": "BF01", "name": "登录"}],
                "requirements": [{
                    "id": "REQ-001", "feature_id": "BF01",
                    "statement": "登录方式支持密码、验证码",
                    "status": "confirmed", "risk": "P1",
                    "evidence": [{"file": "user-input/设计稿.md", "lines": "2",
                                  "quote": "登录方式支持密码、验证码。"}],
                }],
            }, f, ensure_ascii=False)
        result = run(BL, baseline_path, "--input-dir", docs, conv_root, "--freeze")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
