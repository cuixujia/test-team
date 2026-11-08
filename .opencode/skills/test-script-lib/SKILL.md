---
name: test-script-lib
description: 测试流程机器脚本的共享代码库（mdtable 表格解析/引文归一唯一实现）——库声明式 skill，不由对话任务加载；实现改动（归一口径、表解析规则）以本 skill 为唯一权威。生成/校验测试点（阶段 5/6/7）、测试用例（阶段 10/11/12）、需求溯源机验（阶段 3）的脚本从本库导入。
---

# test-script-lib — 共享脚本库（唯一实现）

本 skill 不是工作流，而是**机器脚本共享库的所有权挂载点**。各 skill 的校验脚本从本库导入，禁止在任何 skill 内再写本地副本。

## 模块清单

### scripts/mdtable.py — Markdown 表格解析与基础工具

唯一表格解析实现：此前各校验脚本各自维护语义相近副本、漂移不可见，现全部从 `../../test-script-lib/scripts` 导入。

**导出**：`norm_quote`、`read_text`、`sha256_file`、`norm_space_all`、`norm_ws_single`、`parse_md_table`、`parse_first_table`

**两条既有归一口径红线**：

- `norm_space_all`（TP/TC 清单校验口径：删除全部空白）与 `norm_ws_single`（引文机验口径：空白规范化为单空格）是**两个既有口径**，不得混用，也不得互相"统一"。
- `norm_quote`（引文机验统一口径）：空白单格化 + Markdown 表格 `\|` 转义还原 + 全/半角标点折叠——表示法差异不再 FAIL；行号才是定位锚点，摘录字符由 `verify_quotes.py --autofix` 按行号自愈回填。

**主表定位契约**：`parse_md_table` 的主表 = 第一个 `##` 章节之前的表（进入下一章节即结束）。

## 消费方（只读引用，二次分布声明）

- `test-point-spec/scripts/check.py`、`verify_traceability.py`、`verify_test_points.py`
- `test-case-spec/scripts/verify_test_cases.py`
- `prd-record-spec/scripts/verify_requirement_baseline.py`、`verify_quotes.py`

## 维护规则

1. 任何校验脚本不得定义 `def parse_md_table(` 或 `def parse_first_table(`（`tests/test_contract_sync.py` 断言）；
2. 归一口径与表解析规则改动只在本 skill 进行，改后必须跑 `tests/test_contract_sync.py`；
3. 引用方 SKILL.md 一律指向 `test-script-lib/scripts/mdtable.py`，不再使用其他路径写法。
