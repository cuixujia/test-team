"""export_tables.py 回归测试（2026-11-04 数据视图新增）。

覆盖：
- --phase tp：主表取数、需求→TP 反查归属、依据指针化（文件:行号 / CL-xxx / 未知 token 截断 WARN）
- --phase tp：scope-list 缺「归属登记」表 → 归属留空 + WARN，仍生成（exit 0）
- --phase tc：十字段主表解析、标签三键拆列、主 TP 验证意图与依据回填、主 TP 缺失 WARN
- TC 主表缺契约字段 → exit 1
- TP 主件无「测试点主表」章节标题 → tp/tc 两分支均按主契约回退定位（2026-11-05 复盘）
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, ".opencode", "skill", "test-point-spec", "scripts", "export_tables.py")

TP_MD = """# 示例测试点清单

## 测试点主表

| 编号 | 验证意图 | 类型 | 分析方法 | 依据（文件:行号+原话） |
|---|---|---|---|---|
| TP-001 | 验证登录成功进入首页 | 功能 | 场景法 | prd.md:10「登录成功后进入首页」 |
| TP-002 | 验证超限转账被拒绝 | 边界 | 边界值 | prd.md:20「单笔转账限额为五万元」 ⟂ CL-001（结论要点；推导来源：prd.md:20） |
| 非TP行 | 占位说明 | — | — | — |

## 需求→测试点覆盖表

| 需求ID | 覆盖的 TP 编号 | 未覆盖原因 |
|---|---|---|
| REQ-001（登录展示） | TP-001 | — |
| REQ-002（交易限额） | TP-002 | — |
"""

BASELINE = {
    "requirements": [
        {"id": "REQ-001", "feature_id": "登录查询（登录展示）", "status": "confirmed"},
        {"id": "REQ-002", "feature_id": "依赖级（交易限额管理）", "status": "confirmed"},
    ]
}

SCOPE_MD = """# 任务功能清单

## 归属登记（所属系统 / 所属业务活动）

| 功能/依赖名称 | 所属系统 | 所属业务活动 |
|---|---|---|
| 登录展示 | 星云风险管理系统 | 登录管理 |
| 交易限额管理 | 星云风险管理系统 | 风险管理 |
"""

TC_MD = """# 示例测试用例清单

## 测试用例主表

| 编号 | 标题 | 关联TP | 优先级 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 用例类型 | 标签 |
|---|---|---|---|---|---|---|---|---|---|
| TC-001 | 正常登录进入首页 | TP-001 | P0 | 已注册账户 | 账号A/密码B | 打开登录页并输入账号密码 | 见到首页 | 正向 | 所属系统：星云风险管理系统；所属业务活动：风险管理；所属业务功能：登录展示 |
| TC-002 | 金额超限额，交易拒绝 | TP-002 | P1 | 已登录 | 金额 50001 | 发起转账提交 | 交易被拒 | 边界 | 所属业务功能：交易限额管理 |
"""

TC_BROKEN_MD = TC_MD.replace("操作步骤 | 预期结果", "步骤 | 预期结果")


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


class TestTpExport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.tp = os.path.join(self.d, "test-point.md")
        self.base = os.path.join(self.d, "baseline.json")
        self.scope = os.path.join(self.d, "scope-list.md")
        self.out = os.path.join(self.d, "test-point-table.md")
        write(self.tp, TP_MD)
        write(self.scope, SCOPE_MD)
        with open(self.base, "w", encoding="utf-8") as f:
            json.dump(BASELINE, f, ensure_ascii=False)

    def run_tp(self, tp_file=None, scope=None):
        return run("--phase", "tp", "--tp-file", tp_file or self.tp,
                   "--baseline", self.base, "--scope-list", scope or self.scope,
                   "--output", self.out)

    def test_export_tp_ok(self):
        proc = self.run_tp()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = open(self.out, encoding="utf-8").read()
        self.assertIn("| 编号 | 验证意图 | 类型 | 依据 | 所属系统 | 业务活动 | 业务功能 |", text)
        self.assertIn(
            "| TP-001 | 验证登录成功进入首页 | 功能 | prd.md:10 | 星云风险管理系统 | 登录管理 | 登录展示 |",
            text,
        )
        row2 = [l for l in text.splitlines() if l.startswith("| TP-002")][0]
        self.assertIn("prd.md:20、CL-001", row2)          # 依据指针化 + CL 保留
        self.assertIn("交易限额管理", row2)                # 依赖级 feature_id 取括号内名称
        self.assertNotIn("非TP行", text)                  # 非 TP 行不入视图
        # 视图仅表格（2026-11-05 契约修正）：无标题/引语，行数断言改为直接数数据行
        self.assertTrue(text.startswith("| "), "视图首行应为表头（仅表格契约）")
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("| TP-")]), 2)

    def test_export_tp_missing_registry_warn_blank(self):
        scope = os.path.join(self.d, "scope2.md")
        write(scope, "# 无归属登记表\n")
        proc = self.run_tp(scope=scope)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("[WARN] scope-list 未找到「归属登记」表", proc.stdout)
        text = open(self.out, encoding="utf-8").read()
        self.assertIn("| TP-001 | 验证登录成功进入首页 | 功能 | prd.md:10 |  |  | 登录展示 |", text)

    def test_export_tp_unknown_token_warn(self):
        tp = os.path.join(self.d, "tp2.md")
        write(tp, TP_MD.replace('prd.md:10「登录成功后进入首页」', "某无出处证据"))
        proc = self.run_tp(tp_file=tp)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("[WARN] 依据 token 无法解析为指针", proc.stdout)
        self.assertIn("| TP-001 | 验证登录成功进入首页 | 功能 | 某无出处证据 | ",
                      open(self.out, encoding="utf-8").read())


TP_MD_NO_TITLE = TP_MD.replace("## 测试点主表\n\n", "")


class TestNoMasterTitleFallback(unittest.TestCase):
    """TP 主件无「测试点主表」标题：tp/tc 均按主契约回退定位（2026-11-05 复盘 A5-A7）。"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.tp = os.path.join(self.d, "test-point.md")
        self.tc = os.path.join(self.d, "test-case.md")
        self.base = os.path.join(self.d, "baseline.json")
        self.scope = os.path.join(self.d, "scope-list.md")
        write(self.tp, TP_MD_NO_TITLE)
        write(self.tc, TC_MD)
        write(self.scope, SCOPE_MD)
        with open(self.base, "w", encoding="utf-8") as f:
            json.dump(BASELINE, f, ensure_ascii=False)

    def test_tp_phase_exports_without_title(self):
        out = os.path.join(self.d, "tp-table.md")
        proc = run("--phase", "tp", "--tp-file", self.tp, "--baseline", self.base,
                   "--scope-list", self.scope, "--output", out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[WARN] TP 主件无「测试点主表」章节标题", proc.stdout)
        text = open(out, encoding="utf-8").read()
        self.assertIn("| TP-001 | 验证登录成功进入首页 | 功能 | prd.md:10 |", text)

    def test_tc_phase_exports_without_tp_title(self):
        out = os.path.join(self.d, "tc-table.md")
        proc = run("--phase", "tc", "--tc-file", self.tc, "--tp-file", self.tp, "--output", out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[WARN] TP 主件无「测试点主表」章节标题", proc.stdout)
        text = open(out, encoding="utf-8").read()
        self.assertIn("验证登录成功进入首页", text)


class TestTcExport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.tp = os.path.join(self.d, "test-point.md")
        self.tc = os.path.join(self.d, "test-case.md")
        self.out = os.path.join(self.d, "test-case-table.md")
        write(self.tp, TP_MD)
        write(self.tc, TC_MD)

    def run_tc(self, tc_file=None, tp_file=None):
        return run("--phase", "tc", "--tc-file", tc_file or self.tc,
                   "--tp-file", tp_file or self.tp, "--output", self.out)

    def test_export_tc_ok(self):
        proc = self.run_tc()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = open(self.out, encoding="utf-8").read()
        self.assertIn(
            "| 用例编号 | 标题 | 关联TP | 测试点验证意图 | 优先级 | 用例类型 | 前置条件 | 测试数据 | 操作步骤 | 预期结果 | 所属系统 | 业务活动 | 业务功能 | 依据（主TP） |",
            text,
        )
        row1 = [l for l in text.splitlines() if l.startswith("| TC-001")][0]
        self.assertIn("验证登录成功进入首页", row1)      # 主 TP 验证意图回填
        self.assertIn("星云风险管理系统", row1)
        self.assertIn("风险管理", row1)
        self.assertIn("登录展示", row1)
        self.assertIn("prd.md:10", row1)                # 主 TP 依据指针
        row2 = [l for l in text.splitlines() if l.startswith("| TC-002")][0]
        self.assertIn("验证超限转账被拒绝", row2)
        self.assertIn("| 交易被拒 |  |  | 交易限额管理 |", row2)  # 系统/活动键缺失按规范留空
        self.assertIn("prd.md:20、CL-001", row2)
        # 视图仅表格（2026-11-05 契约修正）：无标题/引语，行数直接数数据行
        self.assertTrue(text.startswith("| 用例编号 | "), "视图首行应为表头（仅表格契约）")
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("| TC-")]), 2)

    def test_export_tc_missing_tp_warn(self):
        tp = os.path.join(self.d, "tp-x.md")
        write(tp, TP_MD.replace("| TP-001 | 验证登录成功进入首页 | 功能 | 场景法 | prd.md:10「登录成功后进入首页」 |",
                                "| TP-999 | 验证登录成功进入首页 | 功能 | 场景法 | prd.md:10「登录成功后进入首页」 |"))
        proc = self.run_tc(tp_file=tp)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("[WARN] TC-001 主 TP TP-001", proc.stdout)

    def test_tc_missing_contract_column_fails(self):
        tc = os.path.join(self.d, "bad.md")
        write(tc, TC_BROKEN_MD)
        proc = self.run_tc(tc_file=tc)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("[FAIL] TC 主表缺少契约字段", proc.stdout)


if __name__ == "__main__":
    unittest.main()
