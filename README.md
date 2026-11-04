# 测试专家 Agent 团队

由三个 OpenCode Agent 组成的"虚拟测试团队"，从 PRD 出发生成**条条有依据、条条可追溯**的测试点（TP）与测试用例（TC）。

方案依据：[AgentDesign.md](AgentDesign.md)。

## 团队构成

| Agent | 模式 | 职责 | 唯一可写产物 |
|---|---|---|---|
| `test-manager` | primary | 阶段编排、派发、用户确认、状态登记、澄清记录、任务功能清单 | `state/scope-list.md`、`state/clarifications.md`、`state/status.md` |
| `test-designer` | subagent | 建锚点底册(阶段2)、生成测试点(阶段5)、生成测试用例(阶段10)、修复 | `scope/anchors.md`、`output/tp/test-point.md`、`output/tc/test-case.md` |
| `test-qa-expert` | subagent | 资料质检(阶段3/8)、产物质检(阶段6/11) | `output/reports/*.md` |

**权限是平台级强制，不是提示词约定**：每个 Agent 的 `permissions` 先 `deny` 兜底再逐项 `allow` 例外，越权写入/执行被 OpenCode 直接拦截。设计/质检专家 `deny question`（无法与用户对话）、`deny subagent`（无法再生子 Agent）；经理 `subagent` 只允许派发两位专家。

> ⚠️ 权限规则**顺序敏感**——OpenCode 为有序规则列表，最后一条匹配生效，任何 `deny` 命中即拒绝整个操作。写反（allow 在前、deny 在后）会使隔离完全失效。

## 目录

```text
.opencode/
├── agents/                    # 三个 Agent 定义（权限在此）
│   ├── test-manager.md
│   ├── test-designer.md
│   └── test-qa-expert.md
└── skills/                    # 共享知识库（6 个 skill）
    ├── prd-record-spec/       # S2 锚点底册规则 + 段落账 + extract_excerpt.py + verify_anchors.py
    ├── prd-quality-check/     # 阶段3 PRD 五维质检 + 矛盾检测 + 漏锚按段落账抽查
    ├── tdd-quality-check/     # 阶段8 开发设计文档质检
    ├── test-analysis-methods/ # 八种分析方法 + 领域检查单
    ├── test-point-spec/       # TP 权威定义 + verify_test_points.py
    └── test-case-spec/        # TC 权威定义 + verify_test_cases.py

opencode.jsonc                 # default_agent = test-manager
工作空间目录结构.md              # 工作空间契约
AgentDesign.md                 # 方案设计文档
workspace/                     # 运行时工作空间（含演示数据）
.selftest.sh                   # 交付自检（60 项）
.setup_demo.sh                 # 重建自检用演示工作空间
```

## 阶段流程

| 阶段 | 执行者 | 产物 | 机械校验 |
|---|---|---|---|
| 1 任务范围确认 | manager | `state/scope-list.md`、`state/status.md` | — |
| 2 建立锚点底册 | designer | `scope/anchors.md`（含段落账） | `verify_anchors.py` |
| 2R 底册保真自检与修复 | designer | 同上 | `verify_anchors.py` |
| 3 测试点资料质检 | qa | `reports/tp-input-check.md` | `verify_anchors.py` |
| 4 用户澄清 | manager → 用户 | 报告（含澄清结果）、`state/clarifications.md` | — |
| 5 生成测试点 | designer | `output/tp/test-point.md` | `verify_test_points.py` |
| 6 测试点质检 | qa | `reports/tp-check.md` | `verify_test_points.py` |
| 6R 修复 | designer | 同上 | — |
| **7 测试点确认** | **manager → 用户（签字）** | 已验收测试点 | — |
| 8 用例资料质检 | qa | `reports/tc-input-check.md` | — |
| 9 用户澄清 | manager → 用户 | 报告（含澄清结果） | — |
| 10 生成测试用例 | designer | `output/tc/test-case.md` | `verify_test_cases.py` |
| 11 用例质检 | qa | `reports/tc-check.md` | `verify_test_cases.py` |
| 11R 修复 | designer | 同上 | — |
| **12 用例确认** | **manager → 用户（签字）** | 已评审测试用例 | — |

签字关口只有两处（阶段 7、12）；但澄清问答（阶段 4、9）与前置补件（阶段 1 选功能、阶段 8 补开发设计文档）也是人工介入节点——**待澄清问题汇总为一张清单、每阶段只问一次**。修复只做**定点修复**，复检默认**增量**（只查被修条目、覆盖对照表牵连项与脚本 FAIL 项），终轮做一次全量兜底；**连续 3 轮未收敛**则升级给用户裁定。多功能任务在阶段 2/5/10 及修复轮启用**功能级并行（起草并行、落盘合并）**。用户在阶段 7/12 的删改即刻生效、不回炉复检，与两分支口径一致。

## 机械校验

机械项由确定性脚本执行、语义项由质检专家裁决——**客观项不走 LLM 主观判断**。

```bash
# 摘录程序化提取（禁止手抄——手抄是摘录漂移的唯一根因）
# 单条提取
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py \
  --prd-dir <PRD目录> --locate "M1-S4-P6"
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py \
  --prd-dir <PRD目录> --ledger <底册> --anchor M1-S4-P6
# 批量提取（一次调用取回多个定位串，建册必用，避免 N 条锚点 N 次调用）
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py \
  --prd-dir <PRD目录> --locate-file <定位串清单.txt>
# 候选句模式（一次给 top-N 句候选，专家点名采用）
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py \
  --prd-dir <PRD目录> --locate "M1-S4-P6" --candidates 3

# 底册保真：摘录按「来源PRD文件」逐字命中、≤40字、锚点唯一、功能编号有效、段落账齐备
python3 .opencode/skills/prd-record-spec/scripts/verify_anchors.py <底册> \
  --prd-dir <PRD目录> --scope-list <任务功能清单> [--tp-file <测试点清单>]

# 测试点：编号格式/唯一/连续、命名、必填、锚点分类校验（锚点ID须为依据列首个 token；
#         PRD锚点查底册+摘录逐字一致；CL锚点查澄清记录防悬空）、底册全覆盖、未覆盖须写原因、无功能编号泄漏
python3 .opencode/skills/test-point-spec/scripts/verify_test_points.py <测试点清单> \
  --ledger <底册> --scope-list <任务功能清单> --clarifications <澄清记录>

# 测试用例：十字段（含标签列）、关联TP引用、TP全覆盖、标签结构与取值命中 PRD、无功能编号泄漏
python3 .opencode/skills/test-case-spec/scripts/verify_test_cases.py <用例清单> \
  --tp-file <测试点清单> --prd-dir <PRD目录> --scope-list <任务功能清单>
```

- 退出码 `0` = 通过；非 0 = 存在 FAIL，**必须修复后重跑**，禁止带 FAIL 定稿。
- 每个脚本输出尾部有 **`[SHA256]` 行**——设计专家交稿自证、质检报告取证共用同一指纹来源；**经理收回核验只比对指纹与汇总行，不重跑校验脚本**（机械校验的独立复跑归质检专家，避免三方重复劳动）。
- **PRD 支持 md / markdown / txt / doc / docx**：docx 由脚本零依赖解析（`word/document.xml`），doc 经 macOS `textutil` 转临时目录后再读，全程只读输入目录。
- **标签/摘录的"逐字命中"按文件精确比对**：摘录查锚点的「来源PRD文件」，标签取值查任务功能清单锁定的 PRD 文件——其他文档（如开发设计文档）中出现不算命中，防"张冠李戴"假通过。

## 编号与标签约定

- **业务功能编号**（`BF01`…）由经理在阶段 1 生成，**不依赖 PRD 是否提供编号**，仅用于过程定位，**不得出现在最终产物**中。
- **锚点编号**：PRD 有编号则直用；无编号则用 `M<模块>-S<章节>-P<段落>`。
- **TP/TC 编号**：`TP-NNN` / `TC-NNN`，本次任务内连续，只增不改不复用，**不含业务功能编号**。
- **测试用例标签**（可多个标签值）：`所属系统` / `所属业务活动` / `所属业务功能`，取值必须来自 PRD 真实内容（功能矩阵总表的功能名称、模块划分说明的模块名称）；PRD 中确实没有的**留空即可，不得编造**。

## 目录硬约束

```
workspace/runtime_<projectId>/file/<uuid>/
├── output/{tp,tc,reports}/    # 产物
├── state/                     # 经理侧产物
├── scope/anchors.md           # 锚点底册
└── user-input/                # 用户上传（只读）
```

详见 [工作空间目录结构.md](工作空间目录结构.md)。

## 自检

```bash
bash .selftest.sh      # 60 项：权限断言 + 校验脚本正/负面回归 + 结构完整性
bash .setup_demo.sh    # 重建自检用演示工作空间（改动脚本/权限前后各跑一次）
```
