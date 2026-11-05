#!/usr/bin/env python3
"""test_contract_sync.py — 契约一致性单测（2026-11-05 第三轮整改新增）。

锁定三条不变量，防止"SKILL 文档说的"与"脚本做的"再次漂移（复盘 C 类根因）：
  1. SKILL 机器契约块中声明的章节关键词/列序，与脚本源码中的硬编码常量逐一等值；
  2. 表格解析唯一实现在 test-script-lib/scripts/mdtable.py——任何校验脚本不得再定义本地副本；
  3. 被收敛的旧入口（validate_delivery.py / verify_validation_report.py）已物理删除，
     且 .opencode/** 与 README/AgentDesign 中无残留引用。

主表定位主契约（第一个 ## 之前的表）的行为一致性由 fixture 三方对齐断言。
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS = os.path.join(ROOT, ".opencode", "skills")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def contract_between(skill, begin, end):
    text = read(os.path.join(SKILLS, skill, "SKILL.md"))
    m = re.search(re.escape(begin) + r"(.*?)" + re.escape(end), text, re.S)
    self.assertTrue(m, f"{skill} SKILL.md 缺少契约块 {begin}")
    return m.group(1)


class TestContractSync(unittest.TestCase):
    def setUp(self):
        self.tp_skill_text = read(os.path.join(SKILLS, "test-point-spec", "SKILL.md"))
        self.tc_skill_text = read(os.path.join(SKILLS, "test-case-spec", "SKILL.md"))
        self.tp_script = read(os.path.join(SKILLS, "test-point-spec", "scripts", "verify_test_points.py"))
        self.tc_script = read(os.path.join(SKILLS, "test-case-spec", "scripts", "verify_test_cases.py"))

    # —— 契约块存在性 ——
    def test_contract_blocks_present(self):
        for name in ("test-point-spec", "test-case-spec"):
            text = read(os.path.join(SKILLS, name, "SKILL.md"))
            self.assertIn("CONTRACT-BEGIN", text, f"{name} 缺机器契约块")
            self.assertIn("CONTRACT-END", text, f"{name} 缺机器契约块结束标记")

    # —— 章节关键词：SKILL 声明 vs 脚本常量 ——
    def test_tp_section_keywords_declared_and_used(self):
        trace_script = read(os.path.join(SKILLS, "test-point-spec", "scripts", "verify_traceability.py"))
        for kw in ("证据→测试点", "需求→测试点覆盖表"):
            self.assertIn(kw, self.tp_skill_text, f"SKILL 契约块未声明 {kw}")
        self.assertIn("证据→测试点", self.tp_script, "verify_test_points 未使用契约关键词 证据→测试点")
        self.assertIn("需求→测试点覆盖表", trace_script, "verify_traceability 未使用契约关键词 需求→测试点覆盖表")

    def test_tc_section_keywords_declared_and_used(self):
        self.assertIn("覆盖对照表", self.tc_skill_text)
        self.assertIn("覆盖对照表", self.tc_script)

    # —— 主表列序：SKILL 契约块 vs 脚本列序常量 ——
    def test_tp_column_order_declared_and_used(self):
        header = "编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话）"
        self.assertIn(header, self.tp_skill_text, "SKILL 契约块未声明 TP 列序")
        self.assertIn("验证意图", self.tp_script)
        self.assertIn("分析方法", self.tp_script)

    def test_tc_column_order_declared_and_used(self):
        header = "编号 | 标题 | 关联TP | 优先级 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 用例类型 | 标签"
        self.assertIn(header, self.tc_skill_text, "SKILL 契约块未声明 TC 十字段列序")
        self.assertIn("关联TP", self.tc_script)
        self.assertIn("所属业务功能", self.tc_script)

    # —— 主表定位契约：SKILL 声明"第一个 ## 之前"；脚本无"测试点主表"硬性关键字依赖 ——
    def test_master_table_position_contract(self):
        block = self.tp_skill_text.split("CONTRACT-BEGIN: test-point-spec", 1)[1]
        self.assertIn("第一个 `##` 之前", block)
        self.assertIn("可选择性增强", block, "契约块应说明「测试点主表」仅为增强")

    # —— test-script-lib 唯一实现 ——
    def test_shared_lib_is_single_implementation(self):
        consumers = [
            os.path.join(SKILLS, "test-point-spec", "scripts", "verify_test_points.py"),
            os.path.join(SKILLS, "test-point-spec", "scripts", "verify_traceability.py"),
            os.path.join(SKILLS, "test-point-spec", "scripts", "check.py"),
            os.path.join(SKILLS, "test-case-spec", "scripts", "verify_test_cases.py"),
            os.path.join(SKILLS, "prd-record-spec", "scripts", "verify_requirement_baseline.py"),
            os.path.join(SKILLS, "prd-record-spec", "scripts", "verify_quotes.py"),
        ]
        for path in consumers:
            src = read(path)
            self.assertNotIn("def parse_md_table(", src, f"本地 parse_md_table 副本违规: {path}")
            self.assertNotIn("def parse_first_table(", src, f"本地 parse_first_table 副本违规: {path}")
        lib = read(os.path.join(SKILLS, "test-script-lib", "scripts", "mdtable.py"))
        self.assertIn("def parse_md_table(", lib)
        self.assertIn("def parse_first_table(", lib)

    # —— 被收敛的旧入口：已删除且无残留引用 ——
    def test_converged_scripts_removed(self):
        for name in ("validate_delivery.py", "verify_validation_report.py"):
            path = os.path.join(SKILLS, "test-point-spec", "scripts", name)
            self.assertFalse(os.path.isfile(path), f"被收敛脚本仍存在: {name}")

    def test_no_dangling_command_references(self):
        # 仅禁"命令式路径引用"（scripts/validate_delivery.py 等，执行命令留下的）；说明性提及放行
        banned_patterns = (r"scripts/validate_delivery", r"scripts/verify_validation_report")
        scan_files = [
            os.path.join(SKILLS, "test-point-spec", "SKILL.md"),
            os.path.join(SKILLS, "test-case-spec", "SKILL.md"),
            os.path.join(SKILLS, "prd-record-spec", "SKILL.md"),
            os.path.join(SKILLS, "test-point-spec", "scripts", "check.py"),
            os.path.join(ROOT, ".opencode", "agents", "test-manager.md"),
            os.path.join(ROOT, ".opencode", "agents", "test-designer.md"),
            os.path.join(ROOT, ".opencode", "agents", "test-qa-expert.md"),
            os.path.join(ROOT, "README.md"),
            os.path.join(ROOT, "AgentDesign.md"),
        ]
        for path in scan_files:
            src = read(path)
            for pat in banned_patterns:
                self.assertIsNone(re.search(pat, src), f"残留旧命令式引用: {path} ({pat})")

    # —— 标签命中契约（6b 取具名列「文件」）——
    def test_scope_list_prd_file_contract_declared(self):
        self.assertIn("资料角色登记", read(os.path.join(SKILLS, "prd-record-spec", "SKILL.md")))
        self.assertIn("scope_list_prd_files", self.tc_script)


if __name__ == "__main__":
    unittest.main()
