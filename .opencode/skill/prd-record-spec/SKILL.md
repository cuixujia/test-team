---
name: prd-record-spec
description: 溯源规范（唯一流程）——纯文本资料直引（文件:行号+原话）、指纹清单、引文机验、资料角色与主从优先级、澄清触发标准
---

# 溯源规范（纯文本直引，唯一流程）

> 资料只收**可定位行号的文本格式**（UTF-8、行导向：.md/.markdown/.txt/.csv）。
> 全流程不再存在目录/锚点底册分支；引用一律 `文件:行号「原话」`，保真由脚本裁决。

## 一、入库仪式（经理执行，fail-fast）

1. **格式确认**：资料目录内**只收文本格式**（.md/.markdown/.txt/.csv）。
   发现 .docx/.xlsx → 经理在轻扫描**之前**先跑一次 `convert_office.py`（每份含 doc/xlsx 的资料目录各跑一次，秒级一次性）：

   ```bash
   python3 ~/.config/opencode/skill/test-script-lib/scripts/convert_office.py \
     --input-dir <含docx/xlsx的资料目录> --output-dir <会话目录>/user-input-converted/
   ```

   - 转换成功的 md 是**后续全流程唯一文本权威**（引文、指纹一律指向它）；
     **原件目录的 docx/xlsx 只读存档，任何阶段禁止引用**，AI 不再打开原件。
   - **转换失败**（或出现 doc/pdf/图片等既不转也不收的件）→
     **一次性告知用户「请替换为文本格式后再开工」并停止流程**；AI 不代转其余格式、无遗留分支。
   - 幂等：转换区同名 md 已存在则跳过；产物路径=`转换区/<来源目录名>/原名.md`
     （来源目录名前缀，杜绝跨资料目录同名互踩），来源内部子目录原样保留。
2. **轻扫描一条命令**（Python 侧 sha256，与机验管线同口径；指纹段落同步登记 `state/status.md`）：

   ```bash
   python3 ~/.config/opencode/skill/prd-record-spec/scripts/scan_outline.py \
     --input-dir <资料目录> [<资料目录> ...] --output <会话目录>/scope/outline.md \
     --manifest <会话目录>/scope/files-manifest.md
   ```

   （`shasum` 仅可粗查变化，禁止用于登记指纹。）
   存在 `user-input-converted/` 转换区 → 把它作为**一个额外目录**传进同一命令的 `--input-dir`
   列表（scan_outline 可收多个目录，合并为一个 outline/manifest）；之后各阶段以合并登记的
   文本全集为资料范围，docx/xlsx 原件不在清单内，自然进不了任何引文与指纹。
3. **规则编号对账**：`outline.md` 中规则编号索引（BR/GOAL/EXCL/NFR/…）与文档自身附表核对，
   若缺失 → 资料本身残缺，入库即拦截。
4. **资料角色登记**（1 次，用户选范围关口顺手确认）：

   | 角色 | 主用阶段 | 说明 |
   |---|---|---|
   | PRD 主资料 | 生成测试点（为主） | 需求与业务规则唯一权威 |
   | 开发设计资料（前端/后端/数据库） | 生成测试用例（为主） | 步骤、数据、预期与交叉校验 |
   | 全局约束 | 双阶段皆用 | 影响范围一并补入质检 |
   | 其他 | 辅助 | 冲突不得覆盖主资料 |

   登记落 `state/scope-list.md`「资料角色登记」表；判读可依据 `outline.md` 标题树，登记后如报错可由用户纠正。

## 二、资料角色与主从优先级

- **TP 阶段**：以 PRD 主资料为准，其余资料为辅；开发资料仅做交叉校验。
- **TC 阶段**：以已确认 TP + 开发设计主资料为准，PRD 为辅。
- **主资料沉默、辅资料有言** → 可采用辅资料结论，留痕登记即可。
- **主资料有言、辅资料相悖**，且冲突落在用户选定范围内、会改变需求表述/行为规则/TP（或 TC）判定
  → 才进澄清单（按集中澄清合并一次提问）。
- 不影响 TP/TC 生成与判定的资料矛盾：只留痕，不问用户、不阻塞流程。

## 三、引用语法（唯一引用格式）

任何产物（澄清记录、需求基线、测试点、测试用例、质检报告）中的"依据/来源"列一律使用：

```
<文件名>:L<行号>  「<原话摘录>」
```

| 规则 | 说明 |
|---|---|
| 摘录长度 | **≤40 字**连续原文；跨行写行区间 `L279-L280`，摘录用单空格连接 |
| 正文逐字 | 摘录的**汉字/字母/数字内容**与原文件该行一致，禁止拷贝渲染后文本 |
| 表示法差异自动消化 | 空白、全/半角标点、引号形制、Markdown `\|` 转义由机验 `norm_quote` 归一——不是错误，不需人修留痕（算法细节见 `verify_quotes.py` 头注释）。归一只覆盖**摘录文本内部**的表示法差异；**摘录所在单元格的完整性是另一回事**——表格行原文的管道符不转义会切断单元格，须作者自行转义 |
| 行号才是锚 | 机验**不带 `--autofix`**：行号指错、摘录缺字误植均 FAIL（行号错唯一定位那条，误植按 `extract_excerpt.py` 输出重抄）；表示法差异仍由 `norm_quote` 归一不算错 |
| 跨行摘录 | 摘录须包含第二行的行首标记（如列表符 `- `），因原文行连接后含此后缀 |
| 文件标识 | 引用一律写 **files-manifest 登记的 rel 全路径**（如 `user-input-converted/user-input/设计稿.md`）——轻扫描收多目录时同名文件靠路径消歧，写裸文件名遇同名即歧义 FAIL |
| 登记 | 摘录登记时用 `verify_quotes.py --context` 核对前后各 1 行，防断章；引用自带行号即可消歧，禁止"行内找相近句"的近似摘录 |

## 四、机验（零语义，脚本执行）

```bash
python3 ~/.config/opencode/skill/prd-record-spec/scripts/verify_quotes.py \
  <引用表.md 或 .json> --input-dir <资料目录> [<资料目录> ...] --context --report <引文报告.json>
```

- 引用表可为 Markdown 管道表（表头契约：首列=`来源文件`、次列=`行号`）或 JSON 数组；`--extract-from` 直接按引用语法从清单抽引用，免维护引用表；
- `--report` 落 JSON 工件（含清单指纹、失败明细）——**机器关采信以工件为准**，stdout 不作数；`--autofix` 参数保留但**流程统一不带**（摘录自愈停用，误植由生成者按 `extract_excerpt.py` 输出重抄）；
- **增量机验**：修复轮经 `check.py --only <受影响步骤>` 只跑受影响步骤，终轮一次全量兜底；
- **质检报告内引文不重复机验**：产物证据本体已随机验管线裁决，报告内复引由「定向抽查」（见质检契约）覆盖；
- FAIL 指「行号指错/骨架不命中/摘录字符误植」，必须修复后重跑；**引文保真的裁决权在脚本，不在复查者**；
- **交付机验统一入口**：`test-point-spec/scripts/check.py`（一次跑完出一份报告）；`verify_quotes.py` 亦可单独运行；澄清触发与覆盖校验沿用其内置追溯步骤。

## 五、需求基线（结构契约，证据=直引）

```json
{
  "schema_version": 1,
  "selected_scope": [{"feature_id": "F01", "name": "官网首页展示"}],
  "input_files": [{"file": "产品需求说明书PRD.md", "sha256": "…"}],
  "requirements": [{"id": "REQ-001", "feature_id": "F01", "statement": "…",
                    "risk": "P2", "status": "confirmed",
                    "evidence": [{"file": "产品需求说明书PRD.md", "lines": "596", "quote": "六项必填校验"}]}]
}
```

校验器 `verify_requirement_baseline.py` 的硬性契约：

| 字段 | 契约 |
|---|---|
| `schema_version` | 顶层必填，值 = `1` |
| `selected_scope` | 顶层必填非空数组；元素含 `feature_id`+`name`；**每条 requirement 的 `feature_id` 必须在 selected_scope 白名单内** |
| `input_files` | 逐文件 `file`+`sha256`（Python 口径）；**登记本基线证据实际引用的文件**（入库清单的合法子集，未引用的入库文件不必登记）；机验提供 `--manifest` 时**逐条交叉校验**：每个基线登记文件必须命中入库清单且指纹一致，未入库文件不得写入基线（清单多余条目=未被基线引用的资料，属正常不报错） |
| `requirements[].id` | `REQ-\d{3}`，任务内唯一 |
| `risk` | 四值档位 `P0/P1/P2/P3`；映射口径：PRD「高」→P1、「中」→P2、「低」→P3（P0 预留给全景性缺陷，默认不用） |
| `status` | 三态 `confirmed` / `needs_clarification` / `out_of_scope` |
| `status=confirmed` | **必须**至少一条证据 |
| `status=needs_clarification` | **必须**有非空 `question` 字段（写明待澄清问题，不自解释） |
| `status=out_of_scope` | **必须**有非空 `reason` 字段 |
| `evidence[]` | 二选一：①直引 `{file, lines, quote}`（lines=`596` 或 `596-598`，quote 正文逐字）；②澄清 `{clarification_id: "CL-xxx"}`——**quote 可选**：缺省仅凭编号采信，填了才有指向性摘录（澄清记录行内 ≤40 字连续片段）；**单条证据不得同时引原文与澄清** |

**依赖类需求（E-EXxx / NFRxx 等）的挂靠规则**：跨功能规则不单独出现在 selected_scope；以"主受益/首个适用"的选定功能落 `feature_id`，其余适用功能**直接在 `statement` 内一句声明**（如「另适用于 F03/F05」）；不设 `notes`、不设顶层 `coverage_summary`。

**基线增补（TC 阶段增量，不解除冻结）**：阶段 8 体检发现影响需求/TP 判定的开发侧事实，经澄清闭环后可对已冻结基线**追加**条目——编号从现有 REQ 最大号续排，`feature_id` 落主受益/首个适用的选定功能（仍在 selected_scope 白名单内），`status=confirmed`；**首条证据必须是澄清证据** `{"clarification_id": "CL-xxx"}`（原文有原型可另加直引证据，"单条证据不得同时引原文与澄清"规则不变）；**禁止改动既有条目的任何字段**（口径差异在增补条目的 statement 内表述）。增补完成跑 `verify_requirement_baseline.py --freeze --clarifications <澄清记录> --manifest <指纹清单>`（`--clarifications` 必带：CL 证据无澄清记录即 FAIL；`--freeze` 保证全表无待澄清），由经理更新 status.md 冻结基线条目数。

**澄清记录解析口径**：仅**行首**（允许 `|`/`>` 前缀）以 `CL-编号` 开头的行才作为该 CL 的专属记录行参与证据比对；正文/留痕行中提到的 CL 编号不参与解析——防留痕行污染登记表形成假 FAIL。

顶层键白名单：`schema_version` / `selected_scope` / `input_files` / `requirements`——超出即结构违规。

- `input_files` 指纹清单登记证据实际引用的文件（files-manifest 的合法子集，Python 口径，逐条命中且指纹一致）；
- 冻结=TP 用户确认关口代为闭环（TP 确认时基线一并联签）；`verify_requirement_baseline.py --freeze` 通过方可冻结。

## 六、scope-list 机器契约

`state/scope-list.md` 兼做机器输入，结构是契约的一部分：

| 表 | 契约 | 消费方 |
|---|---|---|
| **首表 = 功能清单** | 表头：`业务功能编号｜业务功能名称`；首表首列的编号（除表头"业务功能编号"）= 受控编号集，用于"交付物不得出现业务功能编号"泄漏检查 | `verify_test_points.py` / `verify_test_cases.py` |
| **资料角色登记表** | 首列列名 = `文件`，登记各资料文件名（.md 等）——供 TC 标签命中锁定 PRD 文件；按具名列解析，改名即校验回退全目录并 WARN | `verify_test_cases.py` |
| **归属登记表** | 列名固定：`功能/依赖名称｜所属系统｜所属业务活动`，按**功能名称原文**登记（名称须与 PRD 业务功能分组父标题逐字一致） | `export_tables.py` 视图归属列 |

三张表的结构被上表消费方解析；任何其他表不参与机器解析（留痕用）。

**章节定位契约**：三张表（功能清单/资料角色登记/归属登记）**必须各自置于一个 `##` 章节标题之下**，且功能清单为**第一个 `##` 章节下的第一张表**——解析器按章节边界取表，首表裸置于章节标题之外会与后续表合并解析（fixture 参考 `tests/test_check_pipeline.py`：`## 一、功能清单 / ## 二、资料角色登记 / ## 三、归属登记`）。

> QA 各类报告（资料体检/对账/产物质检）统一写入 `output/reports/qa-report.md` 分节（qa 载体契约见 test-qa-expert）。

## 七、任务期封版

- 行号直引依赖原文稳定：**任务进行中的资料一律封版，变更即停机重评**。
- 变更检测：比对 `files-manifest.md` 登记值（Python 口径）；任何环节发现指纹不符即暂停，重评影响范围。
