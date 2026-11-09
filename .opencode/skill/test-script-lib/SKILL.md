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
- `norm_quote`（引文机验统一口径）：空白单格化 + Markdown 表格 `\|` 转义还原 + 全/半角标点折叠——表示法差异不再 FAIL；行号才是定位锚点；**流程统一不带 `--autofix`**（脚本参数保留，流程禁用），摘录字符误植=FAIL，由生成者按 `extract_excerpt.py` 输出重抄。

**主表定位契约**：`parse_md_table` 的主表 = 第一个 `##` 章节之前的表（进入下一章节即结束）。

### scripts/new_session_dir.py — 会话目录生成

按命名规范 `session-<6位随机数>` 新建会话目录并铺好骨架（`user-input`/`scope`/`state`/`output/{tp,tc,reports}`），输出目录路径。`file` 目录直接位于工作空间根目录下；流水号取 6 位随机数（000000~999999），与既有同名目录撞号则自动重取，绝不覆盖既有目录。

**归属说明**：本脚本是经理侧唯一可用的会话目录命名入口——经理的 shell 授权只放行 `python3 <skill>/scripts/<脚本>.py <参数>` 一类形态，编号只能由脚本的随机数生成器产出并查重；agent 不得手编、凑号或照抄历史目录号。

### scripts/convert_office.py — docx/xlsx 入库前转换

纯标准库（zipfile + ElementTree）确定性映射，不做渲染猜测。唯一实现在本模块，`prd-record-spec` 的入库仪式是唯一调用方（SKILL §一）。

- **docx**：只取**定稿**（`w:ins` 合并、`w:del`/批注剔除），标题样式→`#`、表格→md 表格、列表→`- `；图片/公式落留痕注记+丢弃清单。
- **xlsx**：一工作簿一 md；Sheet→`##`、首行表头、每行数据=md 表格一行（行号直引天然成立）；公式取缓存值；合并单元格只留左上值+留痕；日期/数字按显示值（numFmt）。
- **落盘/幂等/防漂移**：产品控制见脚本头注释；转换产物必须能被 `mdtable.py` 解析（兼容性自验收），全部失败不落盘。

## 消费方（只读引用，二次分布声明）

- `test-point-spec/scripts/check.py`、`verify_traceability.py`、`verify_test_points.py`
- `test-case-spec/scripts/verify_test_cases.py`
- `prd-record-spec/scripts/verify_requirement_baseline.py`、`verify_quotes.py`
- `test-manager`（会话目录生成，唯一调用方）
- `prd-record-spec`（`convert_office.py` 入库前唯一调用方）

## 维护规则

1. 任何校验脚本不得定义 `def parse_md_table(` 或 `def parse_first_table(`（`tests/test_contract_sync.py` 断言）；
2. 归一口径与表解析规则改动只在本 skill 进行，改后必须跑 `tests/test_contract_sync.py`；
3. 引用方 SKILL.md 一律指向 `test-script-lib/scripts/mdtable.py`，不再使用其他路径写法；
4. 会话目录命名规范的改动（编号取法、骨架清单）只在本 skill 与 `test-manager` 的会话目录命名条款同步进行，改后必须跑 `tests/test_new_session_dir.py`。

