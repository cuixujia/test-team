"""复盘报告 C 类缺陷修复回归测试（2026-11-04）。

覆盖：
- C1  verify_test_cases.parse_md_table：命中章节后遇后续 ## 不再清空已收集行
- C2  verify_test_cases.warn：函数已定义，降级路径不再 NameError
- C3  verify_test_cases 标签规则：仅「所属业务功能」允许留空；占位词检查作用于非空值
- C4  scan_outline.ID_TOKEN_RE：E- 前缀编号完整捕获（E-BR01 不再截成 BR01）
- C6  verify_quotes.parse_md_quotes：仅解析契约表头（来源文件|行号|原话摘录）的表格，
      混排报告中的主表/覆盖表/语义表整块跳过
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, ".opencode", "skills", "prd-record-spec", "scripts")
TCS = os.path.join(ROOT, ".opencode", "skills", "test-case-spec", "scripts")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(script, *args):
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True)


MIXED_DOC = """# 混排报告示例

## 语义关逐项结论
| 范围对象 | 结论 |
|---|---|
| F02 | 通过 |

## 附录：引文机验引用表
| 来源文件 | 行号 | 原话摘录 |
|---|---|---|
| prd.md | 7 | 提交人仅可查看本项目的风险。 |

## 覆盖对照表（证据→测试点）
| 证据（文件:行号） | 覆盖的 TP 编号 | 未覆盖原因 |
|---|---|---|
| prd.md:L7 | TP-001 | |
"""


class ParseMdQuotesTest(unittest.TestCase):
    """C6：verify_quotes 只认契约表头，混排文件可直接机验。"""

    def setUp(self):
        self.vq = load("vq", os.path.join(SC, "verify_quotes.py"))

    def test_parses_only_contract_header_tables(self):
        quotes = self.vq.parse_md_quotes(MIXED_DOC)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["file"], "prd.md")
        self.assertEqual(quotes[0]["lines"], "7")

    def test_mixed_file_end_to_end_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "prd.md"), "w", encoding="utf-8") as f:
                f.write(
                    "## 提交\n"
                    "2\n3\n4\n5\n6\n"  # 垫行，使引用行号落在第 7 行
                    "提交人仅可查看本项目的风险。\n"
                )
            report = os.path.join(directory, "report.md")
            with open(report, "w", encoding="utf-8") as f:
                f.write(MIXED_DOC)
            result = run(os.path.join(SC, "verify_quotes.py"), report, "--input-dir", directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS=1", result.stdout)

    def test_standalone_quotes_table_still_works(self):
        table = "| 来源文件 | 行号 | 原话摘录 |\n|---|---|---|\n| a.md | 3 | 内容 |\n"
        quotes = self.vq.parse_md_quotes(table)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["file"], "a.md")


class ParseMdTableTest(unittest.TestCase):
    """C1：命中章节后遇后续 ## 保留已收集行。"""

    def setUp(self):
        self.vtc = load("vtc", os.path.join(TCS, "verify_test_cases.py"))

    def test_section_followed_by_other_sections_still_parsed(self):
        header, rows = self.vtc.parse_md_table(MIXED_DOC, "覆盖对照表")
        self.assertEqual(rows, [["prd.md:L7", "TP-001", ""]])

    def test_missing_section_returns_empty(self):
        header, rows = self.vtc.parse_md_table("# 无此章节\n| a | b |\n", "不存在")
        self.assertEqual(rows, [])

    def test_warn_defined(self):
        """C2：warn 已定义（此前未定义导致 6b 降级路径 NameError 崩溃）。"""
        self.assertTrue(callable(self.vtc.warn))


TC_TMPL = """# 用例清单

| 编号 | 标题 | 关联TP | 优先级 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 用例类型 | 标签 |
|---|---|---|---|---|---|---|---|---|---|
| TC-001 | t | TP-001 | P0 | p | d | s | e | 正向 | {label} |

## 覆盖对照表（测试点→用例）
| TP编号 | 覆盖的 TC 编号 | 未覆盖原因 |
|---|---|---|
| TP-001 | TC-001 | |
"""

TP_FILE = """# 测试点清单

| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |
|---|---|---|---|---|
| TP-001 | 验证某行为 | 功能 | 等价类 | prd.md:L7「提交人仅可查看本项目的风险。」 |
"""


class LabelRuleTest(unittest.TestCase):
    """C3：标签规则与 test-case-spec「标签规范」对齐。"""

    def run_tc(self, label):
        with tempfile.TemporaryDirectory() as directory:
            tc = os.path.join(directory, "test-case.md")
            tp = os.path.join(directory, "test-point.md")
            with open(tc, "w", encoding="utf-8") as f:
                f.write(TC_TMPL.format(label=label))
            with open(tp, "w", encoding="utf-8") as f:
                f.write(TP_FILE)
            return run(os.path.join(TCS, "verify_test_cases.py"), tc, "--tp-file", tp)

    def test_function_value_allowed_empty_for_business_function(self):
        result = self.run_tc("所属系统：S；所属业务活动：A；所属业务功能：")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("值为空", result.stdout)

    def test_other_keys_must_not_be_empty(self):
        result = self.run_tc("所属系统：；所属业务活动：A；所属业务功能：F")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("仅「所属业务功能」允许按规范留空", result.stdout)

    def test_placeholder_word_rejected_on_nonempty_value(self):
        result = self.run_tc("所属系统：S；所属业务活动：A；所属业务功能：无")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("占位词", result.stdout)
        # 占位词不应同时触发"值为空"（旧实现为死代码双 fail）
        self.assertNotIn("值为空", result.stdout)


class IdTokenTest(unittest.TestCase):
    """C4：规则编号索引保留完整前缀。"""

    def setUp(self):
        self.so = load("so", os.path.join(SC, "scan_outline.py"))

    def test_e_prefix_kept(self):
        self.assertEqual(self.so.ID_TOKEN_RE.findall("| E-BR01 | 简历投递分支 |"), ["E-BR01"])
        self.assertEqual(self.so.ID_TOKEN_RE.findall("分支 E-BR02 描述"), ["E-BR02"])

    def test_e_ex_and_plain_tokens(self):
        self.assertEqual(self.so.ID_TOKEN_RE.findall("异常 E-EX01 处理"), ["E-EX01"])
        self.assertEqual(self.so.ID_TOKEN_RE.findall("业务规则 BR01"), ["BR01"])
        self.assertEqual(self.so.ID_TOKEN_RE.findall("功能 F01"), ["F01"])

    def test_scan_output_uses_full_id(self):
        with tempfile.TemporaryDirectory() as directory:
            src = os.path.join(directory, "doc.md")
            with open(src, "w", encoding="utf-8") as f:
                f.write("# 文档\n| E-BR01 | 简历投递 | 分支 |\n")
            result = run(os.path.join(SC, "scan_outline.py"), "--input-dir", directory)
            self.assertIn("E-BR01", result.stdout)
            self.assertNotIn("\n  BR01 @", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
