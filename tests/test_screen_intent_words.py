"""口袋词表 WARN 机检（screen_intent_words.py）本单测固化。

覆盖 2026-11-08 缺陷单修复的三条行为契约：
1. 四类词面筛检命中（结果词/处理逻辑/具体值/并列谓词）逐类各自 WARN；
2. WARN-only：工具不产生 FAIL 语义（退出码恒 0）；
3. 主表契约：只扫第一个 "##" 之前的唯一表格，第二张表（覆盖表）不得当数据行。
"""
import importlib.util
import json
import os
import unittest

spec = importlib.util.spec_from_file_location(
    "screen_intent_words",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".opencode/skill/test-script-lib/scripts/screen_intent_words.py"))
siw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(siw)


def make_tp(rows):
    lines = ["# 需求创建与受理 测试点清单", "",
             "判据版本 = test-knowledge @2026-11-08", "",
             "| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |",
             "|---|---|---|---|---|"]
    lines += rows
    lines += ["", "说明：说明文字。", "",
              "## 需求→测试点覆盖表", "",
              "| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |",
              "|---|---|---|",
              "| REQ-001 | TP-001、TP-002 | |"]
    return "\n".join(lines)


class ScreenIntentWords(unittest.TestCase):

    def test_four_wordface_categories_fire(self):
        text = make_tp([
            "| TP-001 | 验证创建成功后进入待沟通状态 | 功能 | 状态迁移 | PRD.md:L1「成功」 |",
            "| TP-002 | 验证创建并返回需求 ID | 功能 | 场景法 | PRD.md:L2「返回」 |",
            "| TP-003 | 验证修改标题必填校验与 25 字符长度上限 | 边界 | 边界值 | PRD.md:L3「01」 |",
        ])
        warns, n, _ = siw.screen(text)
        ids_cats = {(w["id"], w["category"]) for w in warns}
        self.assertIn(("TP-001", "结果词"), ids_cats)
        self.assertIn(("TP-002", "处理逻辑"), ids_cats)
        self.assertIn(("TP-002", "并列双结果谓词"), ids_cats)
        self.assertIn(("TP-003", "具体值"), ids_cats)
        self.assertEqual(n, 3)

    def test_clean_intent_no_warn(self):
        text = make_tp([
            "| TP-021 | 验证软删除需求在台账的可见状态 | 边界 | 等价类 | PRD.md:L21「可见」 |",
            "| TP-004 | 验证系统调用业务创建协作会话 | 功能 | 场景法 | PRD.md:L4「调用」 |",
        ])
        warns, n, _ = siw.screen(text)
        self.assertEqual(warns, [])
        self.assertEqual(n, 2)

    def test_main_table_contract_second_table_not_scanned(self):
        text = make_tp([
            "| TP-001 | 验证创建受理正常 | 功能 | 场景法 | PRD.md:L1「创建」 |",
        ])
        warns, n, _ = siw.screen(text)
        self.assertEqual([w["id"] for w in warns], [])
        self.assertEqual(n, 1)  # 覆盖表行不得计入

    def test_missing_columns_reports_parse_error(self):
        text = "# 测试点清单\n\n| 编号 | 意图 |\n|---|---|\n| TP-001 | 验证创建受理正常 |\n"
        warns, _, _ = siw.screen(text)
        self.assertEqual(warns[0]["category"], "解析错")

    def test_warn_only_exit_code_zero(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "tp.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(make_tp([
                    "| TP-001 | 验证创建成功 | 功能 | 场景法 | PRD.md:L1「成功」 |",
                ]))
            report = os.path.join(d, "r.json")
            r = subprocess.run(
                ["python3", siw.__file__, "--tp-file", p, "--report", report],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertIn("WARN", r.stdout)
            data = json.load(open(report, encoding="utf-8"))
            self.assertEqual(data["rows"], 1)
            self.assertEqual(len(data["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
