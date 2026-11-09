#!/usr/bin/env python3
"""test_new_session_dir.py — 会话目录生成脚本的契约回归。

锁定三件事：命名格式（session-<6位随机数>）、骨架齐全、重复调用不覆盖。
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, ".opencode", "skill", "test-script-lib", "scripts", "new_session_dir.py")
NAME_RE = re.compile(r"^session-(?P<sno>\d{6})$")


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def make_file_dir(root):
    """工作空间根目录下直接是 file，无 runtime_* 中间层。"""
    file_dir = os.path.join(root, "file")
    os.makedirs(file_dir)
    return file_dir


class TestNewSessionDir(unittest.TestCase):
    def test_name_format_is_six_digit_serial(self):
        with tempfile.TemporaryDirectory() as root:
            file_dir = make_file_dir(root)
            result = run("--file-dir", file_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            name = os.path.basename(result.stdout.strip())
            self.assertIsNotNone(NAME_RE.match(name), name)
            self.assertEqual(os.path.dirname(os.path.abspath(result.stdout.strip())),
                             os.path.abspath(file_dir))

    def test_skeleton_created(self):
        with tempfile.TemporaryDirectory() as root:
            file_dir = make_file_dir(root)
            result = run("--file-dir", file_dir)
            session_dir = result.stdout.strip()
            for relative in ("user-input", "scope", "state", "output/tp", "output/tc", "output/reports"):
                self.assertTrue(os.path.isdir(os.path.join(session_dir, relative)), relative)

    def test_repeat_runs_never_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            file_dir = make_file_dir(root)
            first = run("--file-dir", file_dir)
            session_dir = first.stdout.strip()
            marker = os.path.join(session_dir, "state", "keep.txt")
            with open(marker, "w", encoding="utf-8") as stream:
                stream.write("keep")
            for _ in range(3):
                second = run("--file-dir", file_dir)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertNotEqual(second.stdout.strip(), first.stdout.strip())
            self.assertTrue(os.path.isfile(marker))

    def test_print_only_creates_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            file_dir = make_file_dir(root)
            result = run("--file-dir", file_dir, "--print-only")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(NAME_RE.match(os.path.basename(result.stdout.strip())))
            self.assertEqual(os.listdir(file_dir), [])

    def test_missing_dir_fails_loudly(self):
        with tempfile.TemporaryDirectory() as root:
            result = run("--file-dir", os.path.join(root, "nope", "file"))
            self.assertEqual(result.returncode, 2)
            self.assertIn("不存在", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
