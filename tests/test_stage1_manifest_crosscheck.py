"""阶段 1 优化自检（2026-11-06）：
① 基线 input_files ↔ files-manifest 交叉校验；② scan_outline 索引为 0 的告警。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, ".opencode", "skill", "prd-record-spec", "scripts")
BASELINE = os.path.join(SC, "verify_requirement_baseline.py")
SCAN = os.path.join(SC, "scan_outline.py")


def run(script, *args):
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True)


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as s:
        s.write(text)


class ManifestCrossCheck(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="stage1check-")
        self.input_dir = os.path.join(self.d, "src")
        write(os.path.join(self.input_dir, "a.md"), "## 提交\n提交人仅可查看本项目的风险。\n")
        import hashlib
        with open(os.path.join(self.input_dir, "a.md"), "rb") as s:
            self.sha = hashlib.sha256(s.read()).hexdigest()

    def baseline(self):
        return {
            "schema_version": 1,
            "input_files": [{"file": "a.md", "sha256": self.sha}],
            "selected_scope": [{"feature_id": "F01", "name": "x"}],
            "requirements": [{"id": "REQ-001", "feature_id": "F01", "statement": "s",
                              "risk": "P1", "status": "confirmed",
                              "evidence": [{"file": "a.md", "lines": "2",
                                            "quote": "提交人仅可查看本项目的风险。"}]}],
        }

    def test_crosscheck_pass_and_fail(self):
        baseline_path = os.path.join(self.d, "baseline.json")
        write(baseline_path, json.dumps(self.baseline(), ensure_ascii=False))
        manifest_path = os.path.join(self.d, "manifest.md")
        # 一致 → PASS
        write(manifest_path, "# files-manifest（指纹清单）\n\n| 文件 | sha256 |\n|---|---|\n| a.md | %s |\n" % self.sha)
        self.assertEqual(run(BASELINE, baseline_path, "--input-dir", self.input_dir,
                            "--manifest", manifest_path).returncode, 0)
        # 指纹被抄错 → FAIL（复制失误必须有机验裁决）
        write(manifest_path, "# h\n\n| 文件 | sha256 |\n|---|---|\n| a.md | %s |\n" % ("0" * 64))
        res = run(BASELINE, baseline_path, "--input-dir", self.input_dir, "--manifest", manifest_path)
        self.assertEqual(res.returncode, 1)
        self.assertIn("基线指纹与入库清单不一致", res.stdout)
        # 未入库文件写入基线（清单非空但缺该文件）→ FAIL
        write(manifest_path, "# h\n\n| 文件 | sha256 |\n|---|---|\n| other.md | %s |\n" % ("1" * 64))
        res = run(BASELINE, baseline_path, "--input-dir", self.input_dir, "--manifest", manifest_path)
        self.assertEqual(res.returncode, 1)
        self.assertIn("未在入库指纹清单登记", res.stdout)

    def test_scan_outline_warns_when_zero_ids(self):
        res = run(SCAN, "--input-dir", self.input_dir)
        self.assertIn("规则编号数: 0", res.stdout)
        self.assertIn("规则编号索引为 0 条", res.stdout)


if __name__ == "__main__":
    unittest.main()
