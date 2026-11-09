#!/usr/bin/env python3
"""test_prompt_hygiene.py — 提示词洁净锁（2026-11-08 瘦身整改的回归护栏）。

提示词层（agent/*.md 与 skill/*/SKILL.md，test-knowledge 豁免）只允许存在
"当前有效规则与判据"，四类记录性内容一旦写回即 FAIL：

  1. 日期注记：`2026-11-05 收敛` 类括号——溯源单处记账于 AgentDesign 决策记录；
  2. 事故叙事：复盘/实测/上轮 等历史对照词——反向教学即锚定风险；
  3. 硬编码历史会话路径：sess-xxx；
  4. 已收敛/废止的旧命令、旧报告、旧路径残留。

说明句（为何如此）允许保留一句因果；本锁只拦截"历史对照"类写法。
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXEMPT_DIRS = {"test-knowledge"}

BANNED = [
    (r"2026-\d{2}-\d{2}", "日期注记应只存在于 AgentDesign 决策记录"),
    (r"复盘", "复盘叙事违规（规则应写成祈使句，历史对照归档于 AgentDesign）"),
    (r"实测", "实测叙事违规（机器行为由脚本裁决，人读规则不需实验对照）"),
    (r"上轮", "历史轮次对照违规"),
    (r"sess-\w+", "历史会话路径硬编码违规"),
    (r"本会话实例", "会话实例残留违规"),
    (r"validate_delivery|verify_validation_report", "被收敛旧命令名提及违规"),
    (r"tp-machine-check|tc-machine-check|machine-full", "旧机验报告名提及违规"),
    (r"tp-input-check|tc-input-check|tp-check\.md|tc-check\.md|baseline-reconcile", "废止报告文件名提及违规（qa-report.md 已取代）"),
    (r"process-log", "process-log 已并入 status.md 流水账节"),
    (r"skill/_lib|opencode/_lib", "旧 _lib 路径提及违规（唯一实现在 test-script-lib）"),
]


def prompt_files():
    files = []
    agents = os.path.join(ROOT, ".opencode", "agent")
    for name in sorted(os.listdir(agents)):
        if name.endswith(".md"):
            files.append(os.path.join(agents, name))
    skills = os.path.join(ROOT, ".opencode", "skill")
    for skill in sorted(os.listdir(skills)):
        if skill in EXEMPT_DIRS:
            continue
        path = os.path.join(skills, skill, "SKILL.md")
        if os.path.isfile(path):
            files.append(path)
    return files


class TestPromptHygiene(unittest.TestCase):
    def test_no_record_types_in_prompts(self):
        for path in prompt_files():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for pattern, reason in BANNED:
                self.assertIsNone(
                    re.search(pattern, src),
                    f"{os.path.relpath(path, ROOT)} 含{reason}: 命中 /{pattern}/",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
