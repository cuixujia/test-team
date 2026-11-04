# 测试 Agent 团队

由测试经理、测试设计专家、测试质检专家协作，从**纯文本资料**生成**有依据、可追溯、可执行**的测试点和测试用例。

## 团队职责

| Agent | 做什么 | 独占写入 |
|---|---|---|
| `test-manager` | 编排流程、入库 fail-fast、确认范围与资料角色、记录澄清和状态、请用户确认 | `state/` |
| `test-designer` | 整理需求基线、生成/修复 TP 与 TC | `scope/requirements-baseline.json`、`output/tp/`、`output/tc/` |
| `test-qa-expert` | 独立做资料与产物语义质检；不修产物 | `output/reports/*.md` |

机械校验由脚本执行。设计专家生成后每个版本运行一次校验流水线；质检专家核对指纹并独立检查语义，不重复跑相同机械校验。用户输入只读。

## 资料约定（唯一流程）

- **只收可定位行号的文本格式**（md/markdown/txt/csv）。发现 docx/pdf/图片等非文本件 → 一次性告知用户替换后再开工，AI 不代转，**无遗留分支**。
- **资料角色主从**（入库登记、选范围确认）：TP 阶段 PRD 为主、其余为辅；TC 阶段开发设计资料为主、PRD 为辅；「主资料有言、辅资料相悖且影响 TP/TC 判定」才进澄清单。

## 工作流

1. **资料入库（fail-fast）**：`scan_outline.py` 生成 `scope/outline.md`（标题树+规则编号索引）与 `scope/files-manifest.md`（Python 侧 sha256 指纹清单，与机验同口径），规则编号对账；非文本件即拦截；预登记资料角色。
2. **轻扫描、选范围**：依据 outline.md 列出候选功能与规则编号索引；用户选范围时一并确认资料角色，之后才做深度质检。
3. **范围闭合**：补入相关全局约束和跨功能依赖；仅对本次范围及依赖质检。
4. **建需求基线+测试点联产**：设计专家整理 `scope/requirements-baseline.json`（证据=`文件:行号`+原话）并同会话联产测试点草稿；PRD 与开发资料检查并行，问题尽量合并一次询问。技术资料缺失只阻塞 TC，不阻塞 TP。
5. **集中澄清**：按主从优先级标准的歧义、矛盾、缺件合并一次询问；结论登记 `CL-xxx`。
6. **机验+用户确认**：`verify_quotes.py` 引文逐字机验 + 覆盖表校验通过后，由用户确认测试点（确认即代基线联签冻结）。
7. **生成 TC**：基于确认 TP 和开发设计主资料生成；机器校验和独立语义质检（引用只机验+定向抽查）通过后由用户确认。
8. **修复与变更**：按问题 ID 和追溯关系增量修复，最终全量校验；资料指纹变化（以 Python 口径为准）时暂停并重评影响范围。

用户正式确认只有 TP 和 TC 两处。真正需要用户决策的问题必须等待，不能猜答案。

## 核心产物

```text
scope/files-manifest.md            # 文本资料指纹清单（Python 侧 sha256）
scope/outline.md                   # 轻扫描：标题树+规则编号索引
scope/requirements-baseline.json   # 结构化需求、input_files 指纹、来源证据（文件:行号+原话）、风险与状态
output/tp/test-point.md            # 含证据→TP、需求→TP 两张覆盖表
output/tc/test-case.md             # 含 TP→TC 覆盖表；TC 可关联主 TP 和相关 TP
output/reports/tp-machine-check.json  # TP 机器结果及产物/脚本指纹
output/reports/tc-machine-check.json  # TC 机器结果及产物/脚本指纹
output/reports/machine-full.json       # 最终全量兜底结果
output/reports/*-check.md          # 独立语义质检报告
```

## 脚本

```bash
# 资料入库：标题树 + 规则编号索引 + 指纹清单（Python 侧 sha256，与机验同口径）
python3 .opencode/skills/prd-record-spec/scripts/scan_outline.py \
  --input-dir <资料目录> --output <会话目录>/scope/outline.md \
  --manifest <会话目录>/scope/files-manifest.md

# 引文机验：对原文件按 文件:行号 逐字比对（--extract-from 直接抽清单自体引用）
python3 .opencode/skills/prd-record-spec/scripts/verify_quotes.py \
  <引用表或清单文件> --input-dir <资料目录> --context

# 摘录定位辅助（可选）：按章节定位并截取 ≤40 字连续原句
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py \
  --prd-dir <资料目录> --locate <定位串> [--candidates N]

# 冻结需求基线前校验结构、范围和逐条证据（input_files 指纹绑定）
python3 .opencode/skills/prd-record-spec/scripts/verify_requirement_baseline.py \
  <requirements-baseline.json> --input-dir <资料目录> \
  --clarifications <clarifications.md> --freeze

# 每个产物版本运行相应校验；最终交付用 full
python3 .opencode/skills/test-point-spec/scripts/validate_delivery.py \
  --phase full --input-dir <资料目录> \
  --baseline <requirements-baseline.json> \
  --scope-list <scope-list.md> --tp-file <test-point.md> --tc-file <test-case.md> \
  --clarifications <clarifications.md> --report <machine-check.json>
python3 .opencode/skills/test-point-spec/scripts/verify_validation_report.py <machine-check.json>
```

来源目录只读；校验报告记录输入和校验脚本指纹。

## 自检

```bash
bash .setup_demo.sh
bash .selftest.sh
```

`tests/` 包含纯文本资料目录、需求基线、追溯关系的回归测试。工作空间约定见[工作空间目录结构](工作空间目录结构.md)，团队设计见[AgentDesign](AgentDesign.md)。
