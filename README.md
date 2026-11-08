# 测试 Agent 团队

由测试经理、测试设计专家、测试质检专家协作，从**纯文本资料**生成**有依据、可追溯、可执行**的测试点和测试用例。

## 团队职责

| Agent | 做什么 | 独占写入 |
|---|---|---|
| `test-manager` | 编排流程、入库 fail-fast、确认范围与资料角色、记录澄清和状态、请用户确认 | `state/` |
| `test-designer` | 整理需求基线、生成/修复 TP 与 TC | `scope/requirements-baseline.json`、`output/tp/`、`output/tc/` |
| `test-qa-expert` | 独立做资料与产物语义质检；不修产物 | `output/reports/*.md` |

机械校验由脚本执行。设计专家生成后每个版本运行一次校验流水线；质检专家核对指纹并独立检查语义，不重复跑相同机械校验。用户输入只读。

## 知识库（唯一语义判据）

测试语义判定的唯一权威在 `.opencode/skills/test-knowledge/`：四份**原文**（①通用测试方法论、②测试维度定义、③通用测试规则、④测试点生成指南；行文中的流程/输出包装已裁剪，只留判定标准）+ 两份**补充件**（TP 切分与命名判别、领域专项检查单）。各 skill 只引用不复述；口径冲突时**以知识库为准**（改 skill，不改知识）。调优路径：改补充件，或经用户决定整体替换原文。导入原始版本留存于仓库根 `测试知识/`（只读存档）。

## 资料约定（唯一流程）

- **只收可定位行号的文本格式**（md/markdown/txt/csv）。发现 docx/pdf/图片等非文本件 → 一次性告知用户替换后再开工，AI 不代转，**无遗留分支**。
- **资料角色主从**（入库登记、选范围确认）：TP 阶段 PRD 为主、其余为辅；TC 阶段开发设计资料为主、PRD 为辅；「主资料有言、辅资料相悖且影响 TP/TC 判定」才进澄清单。

## 工作流

阶段的规范编号以 skills 体系为准：3=资料质检、4=澄清、5=TP 生成、6=TP 质检、7=TP 确认、8=用例资料质检、10=TC 生成、11=TC 质检、12=TC 确认；资料入库与范围步骤为 1/2。下表步骤序号仅用于本列表叙述，不作为阶段号引用（历史文档中的「阶段 N 报告」等指 skills 体系编号）。

1. **阶段 1：资料入库（fail-fast）**：`scan_outline.py` 生成 `scope/outline.md`（标题树+规则编号索引）与 `scope/files-manifest.md`（Python 侧 sha256 指纹清单，与机验同口径），规则编号对账；非文本件即拦截；预登记资料角色。
2. **阶段 2：轻扫描、选范围**：依据 outline.md 列出候选功能与规则编号索引；用户选范围时一并确认资料角色，之后才做深度质检。
3. **阶段 2 尾：范围闭合**（无独立阶段号，随阶段 2 收口）：补入相关全局约束和跨功能依赖；仅对本次范围及依赖质检。
4. **阶段 3：资料质检 ‖ 基线整理（两路并行）**：QA 按角色主从深度检查范围内 PRD 与开发资料，问题单写入 `output/reports/qa-report.md` 的「§阶段3 资料体检」节（收尾基线对账也并入本节）；设计专家同时整理 `scope/requirements-baseline.json`（证据=`文件:行号`+原话，**复述不判读**，含糊项挂 `needs_clarification`）。QA 报告收尾核对基线（先独立提单）。技术资料缺失只阻塞 TC，不阻塞 TP。
5. **阶段 4：集中澄清**：QA 澄清候选与基线占位合并一次询问；结论登记 `CL-xxx`。**影响 TP 判定的澄清闭环后，TP 才生成**（仅影响 TC 数据构造的缺件项登记即可放行）。
6. **阶段 5：生成测试点**：设计专家基于落盘基线、CL 结论与阶段 3 报告生成测试点。
7. **阶段 6/7：机验+质检+修复闭环+出表+用户确认**：`check.py --phase tp` 机验（阶段 6）PASS 后，质检以**主件＋机验工件**做语义关；**修复闭环（一次打包单轮修完→增量机验→终轮全量机验 PASS）后**，经理才生成测试点数据视图 `test-point-table.md`，**以 table 为载体**交用户确认（阶段 7；确认即代基线联签冻结）；确认时的删改意见由经理映射回主件、修订后重导 table。
8. **阶段 8：用例资料质检（先行）**：检查开发设计主资料可测性与缺件，写入 `qa-report.md` 的「§阶段8 用例资料体检」节；缺件经澄清闭环或让步留痕后用例分支才启动。
9. **阶段 10/11/12：生成 TC＋质检＋修复闭环＋确认**：基于确认 TP、阶段 8 结论和开发设计主资料生成 TC（阶段 10）；`check.py --phase full` 全量机验 PASS 后质检以主件＋机验工件做语义关（阶段 11，结论写入 `qa-report.md`「§阶段11 测试用例质检」节），**修复闭环且终轮全量机验 PASS 后**经理出 `test-case-table.md`，以 table 载体交用户确认（阶段 12）。
10. **修复与变更**（贯穿阶段，无编号）：按问题 ID 和追溯关系增量修复（修复单一次性打包，见 AgentDesign 质检收敛），最终全量校验；资料指纹变化（以 Python 口径为准）时暂停并重评影响范围。

用户正式确认只有 TP 和 TC 两处，载体均为 table 数据视图。真正需要用户决策的问题必须等待，不能猜答案。

## 核心产物（10 份持久，2026-11-08 瘦身）

```text
# 用户交互面
scope/outline.md                   # 资料地图：标题树+规则编号索引（阶段 2 选范围用）
state/scope-list.md                # 功能范围 + 资料角色登记 + 归属登记（机器契约，脚本消费）
state/clarifications.md            # 澄清问答（CL-xxx），兼待澄清缺件登记
output/tp/test-point-table.md      # 测试点确认载体（仅一张表；export_tables.py 派生，确认关口前才生成）
output/tc/test-case-table.md       # 测试用例确认载体（同上）

# 静默落盘（可查）
state/status.md                    # 经理唯一状态簿：登记/进度/结论 + 尾部「流水账」节（异常一行一条，2026-11-08 并入 process-log）
scope/requirements-baseline.json   # 结构化需求、input_files 指纹、来源证据（文件:行号+原话）
output/tp/test-point.md            # 含需求→TP 覆盖表（唯一权威；证据→TP 由机验自动推导）
output/tc/test-case.md             # 含 TP→TC 覆盖表；TC 可关联主 TP 和相关 TP（唯一权威）
output/reports/qa-report.md        # 全流程唯一 QA 报告，分节追加：§阶段3 资料体检（含基线对账）/§阶段6 测试点质检/§阶段8 用例资料体检/§阶段11 测试用例质检；每节落盘后只读，每条问题=修复单格式
```

**脚本工作文件（照常生成，不列产物、不主动展示）**：`check-tp.json`、`check-tc.json`、`check-full.json`（+ `.quotes-*.json` 引文逐字明细）——机验工件，质检按指纹采信；`files-manifest.md`——纯文本资料指纹清单（Python 侧 sha256）。

> 旧五份报告文件（`tp-input-check.md`、`tc-input-check.md`、`tp-check.md`、`tc-check.md`、`baseline-reconcile.md`）与 `state/process-log.md` 已废止，新任务一律写 `qa-report.md` 对应节与 `status.md` 流水账。

## 脚本

```bash
# 资料入库：标题树 + 规则编号索引 + 指纹清单（Python 侧 sha256，与机验同口径）
python3 .opencode/skills/prd-record-spec/scripts/scan_outline.py \
  --input-dir <资料目录> --output <会话目录>/scope/outline.md \
  --manifest <会话目录>/scope/files-manifest.md

# 机验统一入口：一条命令产出"引文逐字（TP/TC 各自）+ 基线 + 清单结构 + 追溯 + 报告新鲜度"的
# 带指纹 JSON 报告，供质检按工件采信（阶段/报告命名：check-tp / check-tc / check-full）
python3 .opencode/skills/test-point-spec/scripts/check.py \
  --phase full --input-dir <资料目录> \
  --baseline <requirements-baseline.json> \
  --scope-list <scope-list.md> --tp-file <test-point.md> --tc-file <test-case.md> \
  --clarifications <clarifications.md> --report <output/reports/check-full.json>
#  可加 --manifest <会话目录>/scope/files-manifest.md：基线 input_files 与入库清单逐条交叉校验

# 引文逐字机验（可单独运行；--report 落带清单指纹的 JSON 工件）
python3 .opencode/skills/prd-record-spec/scripts/verify_quotes.py \
  <引用表或清单文件> --input-dir <资料目录> --context --report <引文报告.json>

# 摘录定位辅助（可选）：按章节定位并截取 ≤40 字连续原句
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py \
  --prd-dir <资料目录> --locate <定位串> [--candidates N]

# 冻结需求基线前校验结构、范围和逐条证据（input_files 指纹绑定）
python3 .opencode/skills/prd-record-spec/scripts/verify_requirement_baseline.py \
  <requirements-baseline.json> --input-dir <资料目录> \
  --manifest <会话目录>/scope/files-manifest.md \
  --clarifications <clarifications.md> --freeze

# 数据视图：清单主件 → 纯数据表（语义质检修复闭环、终轮全量机验 PASS 后由经理生成；行数/编号与主表自洽，仅作查看）
python3 .opencode/skills/test-point-spec/scripts/export_tables.py \
  --phase tp --tp-file <test-point.md> --baseline <requirements-baseline.json> \
  --scope-list <scope-list.md> --output <test-point-table.md>
python3 .opencode/skills/test-point-spec/scripts/export_tables.py \
  --phase tc --tc-file <test-case.md> --tp-file <test-point.md> --output <test-case-table.md>
```

> 历史兼容：2026-11-05 前产出的旧命名报告（`tp-machine-check.json` / `tc-machine-check.json` / `machine-full.json`）与历史清单内"待补跑命令清单"中的旧命令名（`validate_delivery.py` 等）均为**历史留痕**，不随本收敛改写；新任务一律使用 `check.py` 与 `check-<phase>.json` 命名。历史清单文件中的旧命令已失效，勿照抄。

来源目录只读；校验报告记录输入和校验脚本指纹。

## 自检

```bash
bash .setup_demo.sh
bash .selftest.sh
```

`tests/` 包含纯文本资料目录、需求基线、追溯关系的回归测试。工作空间约定见[工作空间目录结构](工作空间目录结构.md)，团队设计见[AgentDesign](AgentDesign.md)。
