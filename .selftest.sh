#!/usr/bin/env bash
# 交付自检：权限断言 + 纯文本直引校验工具正/负面回归 + 结构完整性
set -u
cd "$(dirname "$0")" || exit 1
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '[PASS] %s\n' "$1"; }
ng(){ FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$1"; }

W="workspace/runtime_demo/file"
S="$W/sess-demo-0001"
PRD="$W/project-docs"
VQ=".opencode/skills/prd-record-spec/scripts/verify_quotes.py"
VB=".opencode/skills/prd-record-spec/scripts/verify_requirement_baseline.py"
VP=".opencode/skills/test-point-spec/scripts/verify_test_points.py"
VC=".opencode/skills/test-case-spec/scripts/verify_test_cases.py"
VT=".opencode/skills/test-point-spec/scripts/verify_traceability.py"
BASE="$S/scope/requirements-baseline.json"
TP="$S/output/tp/test-point.md"
TC="$S/output/tc/test-case.md"

echo "========== 1. Agent 定义完整性 =========="
for a in test-manager test-designer test-qa-expert; do
  f=".opencode/agents/$a.md"
  [ -f "$f" ] && ok "$a.md 存在" || { ng "$a.md 缺失"; continue; }
  grep -q '^mode: ' "$f" && ok "$a.md 有 mode" || ng "$a.md 缺 mode"
  grep -q 'action: edit' "$f" && ok "$a.md 有 edit 权限" || ng "$a.md 缺 edit 权限"
  grep -q 'action: subagent' "$f" && ok "$a.md 有 subagent 权限" || ng "$a.md 缺 subagent 权限"
  grep -q 'action: question' "$f" && ok "$a.md 有 question 权限" || ng "$a.md 缺 question 权限"
done

echo
echo "========== 2. 角色隔离 =========="
grep -q 'mode: subagent' .opencode/agents/test-designer.md && ok "designer 为 subagent" || ng "designer 模式错"
grep -q 'mode: subagent' .opencode/agents/test-qa-expert.md && ok "qa 为 subagent" || ng "qa 模式错"
grep -q 'mode: primary' .opencode/agents/test-manager.md && ok "manager 为 primary" || ng "manager 模式错"
grep -A2 'action: question' .opencode/agents/test-designer.md | grep -q 'deny' && ok "designer 禁止 question" || ng "designer question 未禁用"
grep -A2 'action: question' .opencode/agents/test-qa-expert.md | grep -q 'deny' && ok "qa 禁止 question" || ng "qa question 未禁用"
grep -A2 'action: subagent' .opencode/agents/test-designer.md | grep -q 'deny' && ok "designer 禁止 subagent" || ng "designer subagent 未禁用"
# 单一写入者：只看 permissions 块（frontmatter），不看正文
perm_block(){ sed -n '1,/^---$/p' "$1" | sed -n '2,/^---$/p'; }
perm_block .opencode/agents/test-designer.md | grep -q 'output/reports' && ng "designer 被授予报告写权限" || ok "designer 无报告写权限"
perm_block .opencode/agents/test-designer.md | grep -q 'anchors.md' && ng "designer 仍被授予锚点底册写权限" || ok "designer 无锚点底册写权限"
perm_block .opencode/agents/test-qa-expert.md | grep -q 'output/tp\|output/tc' && ng "qa 被授予产物写权限" || ok "qa 无产物写权限"
perm_block .opencode/agents/test-manager.md | grep -q 'output/tp\|output/tc\|output/reports\|source-catalog' && ng "manager 被授予产物/目录写权限" || ok "manager 无产物与资料目录写权限"

echo
echo "========== 3. Skill 与脚本完整性（V2 唯一，无旧版遗留） =========="
for s in test-knowledge prd-record-spec prd-quality-check tdd-quality-check test-analysis-methods test-point-spec test-case-spec test-script-lib; do
  [ -f ".opencode/skills/$s/SKILL.md" ] && ok "skill $s" || ng "skill $s 缺失"
done
for f in "$VQ" "$VB" "$VP" "$VC" "$VT" .opencode/skills/prd-record-spec/scripts/scan_outline.py .opencode/skills/prd-record-spec/scripts/extract_excerpt.py .opencode/skills/test-point-spec/scripts/check.py .opencode/skills/test-script-lib/scripts/mdtable.py; do
  [ -f "$f" ] && ok "$(basename "$f")" || ng "$(basename "$f") 缺失"
done
for f in build_source_catalog.py verify_source_catalog.py verify_anchors.py; do
  [ -f ".opencode/skills/prd-record-spec/scripts/$f" ] && ng "旧版脚本 $f 未退役" || ok "旧版脚本 $f 已退役"
done
grep -rq 'source_catalog_sha256\|--ledger\|--anchors' .opencode/skills/*/scripts/*.py && ng "脚本仍残留 V1 接口" || ok "脚本无 V1 接口残留"

echo
echo "========== 4. 校验脚本正面回归（应全部通过）=========="
python3 .opencode/skills/prd-record-spec/scripts/scan_outline.py --input-dir "$PRD" --ids-only >/dev/null 2>&1 && ok "scan_outline 轻扫描通过" || ng "scan_outline 失败"
python3 "$VQ" "$TP" --input-dir "$PRD" --extract-from >/dev/null 2>&1 && ok "verify_quotes 直接抽 TP 引用通过" || ng "verify_quotes TP 引用失败"
python3 "$VB" "$BASE" --input-dir "$PRD" --clarifications "$S/state/clarifications.md" --freeze >/dev/null 2>&1 && ok "verify_requirement_baseline（直引+指纹+冻结）通过" || ng "verify_requirement_baseline 失败"
python3 "$VP" "$TP" --input-dir "$PRD" --scope-list "$S/state/scope-list.md" --clarifications "$S/state/clarifications.md" >/dev/null 2>&1 && ok "verify_test_points 通过" || ng "verify_test_points 失败"
python3 "$VC" "$TC" --tp-file "$TP" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ok "verify_test_cases 通过" || ng "verify_test_cases 失败"
python3 "$VT" "$BASE" "$TP" >/dev/null 2>&1 && ok "verify_traceability 通过" || ng "verify_traceability 失败"

echo
echo "========== 5. 负面回归（必须抓到问题）=========="
cp "$TP" /tmp/_tp.bak
cp "$TC" /tmp/_tc.bak
cp "$BASE" /tmp/_base.bak

# 5.1 TP 直引摘录改写 → 引文不再逐字命中
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
s=s.replace('「风险名称必填，长度不超过 50 个字符。」','「风险名称是必填的并且长度须不超过 50 字。」',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$TP" --input-dir "$PRD" >/dev/null 2>&1 && ng "TP 摘录改写未被捕获" || ok "TP 直引摘录改写被捕获"
cp /tmp/_tp.bak "$TP"

# 5.2 TP 直引行号越界 → 必须捕获
python3 - <<'PY'
import re
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
s=re.sub(r'prd-demo\.md:L\d+', 'prd-demo.md:L9999', s, count=1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$TP" --input-dir "$PRD" >/dev/null 2>&1 && ng "TP 行号越界未被捕获" || ok "TP 直引行号越界被捕获"
cp /tmp/_tp.bak "$TP"

# 5.3 TP 依据未以直引/CL 开头（旧式锚点或纯文本）→ 必须捕获
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
s=s.replace('| TP-003 | 验证提交人修改自己创建的风险被受理 | 功能 | 场景法 | prd-demo.md:L',
            '| TP-003 | 验证提交人修改自己创建的风险被受理 | 功能 | 场景法 | M1-S4-P3 ',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$TP" --input-dir "$PRD" >/dev/null 2>&1 && ng "旧式锚点依据未被捕获" || ok "旧式锚点/纯文本依据被捕获"
cp /tmp/_tp.bak "$TP"

# 5.4 悬空 CL-999 → 必须捕获
python3 - <<'PY'
import re
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
row='| TP-099 | 验证挂空澄清编号 | 异常 | 错误推测 | CL-999 用户澄清：不存在。 |'
out=[]
for ln in s.split('\n'):
    out.append(ln)
    if ln.startswith('| TP-006 |'):
        out.append(row)
open(p,'w',encoding='utf-8').write('\n'.join(out))
PY
python3 "$VP" "$TP" --input-dir "$PRD" >/dev/null 2>&1 && ng "悬空 CL-999 未被捕获" || ok "悬空澄清编号被捕获"
cp /tmp/_tp.bak "$TP"

# 5.5 覆盖对照表缺行（被引用证据未上表）→ 必须捕获
python3 - <<'PY'
import re
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
out=[]
for ln in s.split('\n'):
    if re.match(r'^\| prd-demo\.md:L\d+ \|', ln):
        continue  # 删除第一张直引证据覆盖行
    out.append(ln)
open(p,'w',encoding='utf-8').write('\n'.join(out))
PY
python3 "$VP" "$TP" --input-dir "$PRD" >/dev/null 2>&1 && ng "覆盖对照表缺行未被捕获" || ok "被引用证据未上覆盖表被捕获"
cp /tmp/_tp.bak "$TP"

# 5.6 覆盖对照表登记未被引用的证据（幻觉）→ 必须捕获
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
s=s.replace('## 需求→测试点覆盖表','| prd-demo.md:L1 | TP-001 |  |\n\n## 需求→测试点覆盖表',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$TP" --input-dir "$PRD" >/dev/null 2>&1 && ng "覆盖表幻觉证据未被捕获" || ok "覆盖表未被引用证据被捕获"
cp /tmp/_tp.bak "$TP"

# 5.7 基线引文改写 → 必须捕获
python3 - <<'PY'
import json
p='workspace/runtime_demo/file/sess-demo-0001/scope/requirements-baseline.json'
b=json.load(open(p,encoding='utf-8'))
req=next(r for r in b['requirements'] if r['id']=='REQ-001')
req['evidence'][0]['quote']='风险名称必填（上限 50 字）。'
json.dump(b,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
python3 "$VB" "$BASE" --input-dir "$PRD" --freeze >/dev/null 2>&1 && ng "基线引文改写未被捕获" || ok "基线直引摘录改写被捕获"
cp /tmp/_base.bak "$BASE"

# 5.8 基线 input_files 指纹篡改 → 必须捕获
python3 - <<'PY'
import json
p='workspace/runtime_demo/file/sess-demo-0001/scope/requirements-baseline.json'
b=json.load(open(p,encoding='utf-8'))
b['input_files'][0]['sha256']='deadbeef'+b['input_files'][0]['sha256'][8:]
json.dump(b,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
python3 "$VB" "$BASE" --input-dir "$PRD" --freeze >/dev/null 2>&1 && ng "基线指纹篡改未被捕获" || ok "基线 input_files 指纹不符被捕获"
cp /tmp/_base.bak "$BASE"

# 5.9 待澄清需求不能冻结 → 必须捕获
python3 - <<'PY'
import json
p='workspace/runtime_demo/file/sess-demo-0001/scope/requirements-baseline.json'
b=json.load(open(p,encoding='utf-8'))
req=next(r for r in b['requirements'] if r['id']=='REQ-003')
req['status']='needs_clarification'
req['question']='「自己创建」是否包含代创建场景？'
json.dump(b,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
python3 "$VB" "$BASE" --input-dir "$PRD" --freeze >/dev/null 2>&1 && ng "待澄清需求未被冻结关拦截" || ok "待澄清需求冻结被拦截"
cp /tmp/_base.bak "$BASE"

# 5.10 TC 标签编造名称 → 必须捕获
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tc/test-case.md'
s=open(p,encoding='utf-8').read()
s=s.replace('所属业务功能：新增风险','所属业务功能：风险登记管理',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VC" "$TC" --tp-file "$TP" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "标签编造未被捕获" || ok "标签编造名称被捕获"
cp /tmp/_tc.bak "$TC"

# 5.11 悬空 TP 引用 → 必须捕获
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tc/test-case.md'
s=open(p,encoding='utf-8').read()
s=s.replace('| TC-004 | 审核人非本项目测试管理人提交被拒 | TP-004 |','| TC-004 | 审核人非本项目测试管理人提交被拒 | TP-099 |',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VC" "$TC" --tp-file "$TP" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "悬空TP引用未被捕获" || ok "悬空 TP 引用被捕获"
cp /tmp/_tc.bak "$TC"

# 5.12 TP 未覆盖且无原因 → 必须捕获
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tc/test-case.md'
s=open(p,encoding='utf-8').read()
s=s.replace('| TP-003 |  | 可见范围差异由 TC 在 TP-001 下补充，不单列 |','| TP-003 |  |  |',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VC" "$TC" --tp-file "$TP" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "TP未覆盖未被捕获" || ok "TP 未覆盖且无原因被捕获"
cp /tmp/_tc.bak "$TC"

# 5.13 已确认需求无 TP 覆盖 → traceability 必须捕获
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
lines=s.split('\n')
final=[ln for ln in lines if not ln.startswith('| REQ-006 |')]
open(p,'w',encoding='utf-8').write('\n'.join(final))
PY
python3 "$VT" "$BASE" "$TP" >/dev/null 2>&1 && ng "已确认需求无覆盖未被捕获" || ok "已确认需求无 TP 覆盖被捕获"
cp /tmp/_tp.bak "$TP"

# 5.14 verify_quotes 独立漂移检测（引用表直验）
printf '# 引用表\n| 来源文件 | 行号 | 原话摘录 |\n|---|---|---|\n| prd-demo.md | 199 | 风险等级分为高中低三档。 |\n' > /tmp/_q.md
python3 "$VQ" /tmp/_q.md --input-dir "$PRD" >/dev/null 2>&1 && ng "verify_quotes 漂移未被捕获" || ok "verify_quotes 引文漂移被捕获"
rm -f /tmp/_q.md

# 5.15 资料角色登记机制存在性（经理入库登记）
grep -q '资料角色登记' "$S/state/scope-list.md" && ok "scope-list 含资料角色登记表" || ng "scope-list 缺资料角色登记表"

# 5.16 TP 引用 CL 却未提供 --clarifications → 必须捕获
cp "$TP" /tmp/_tp.cl.bak
python3 - <<'PY'
import re
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read()
s=re.sub(r'\| (TP-001 \| [^|]+ \| [^|]+ \| [^|]+ \| )prd-demo\.md:L\d+ 「[^」]+」 \|',
         r'| \1CL-001 用户澄清：名称必填以第 4 章为准。 |', s, count=1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$TP" --input-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "引用 CL 无澄清记录未被捕获" || ok "引用 CL 却未提供 --clarifications 被捕获"
cp /tmp/_tp.cl.bak "$TP"
rm -f /tmp/_tp.cl.bak

# 5.17 机验失败输出口径（「机验转述纪律」的机械保险丝，2026-11-05）：
# check.py FAIL 输出必须含三要素锚点——[FAIL] 步骤行 / [REPORT] 工件行 / 校验汇总: FAIL；
# 内容由报告工件结构化承载，供经理按「编号+违反什么+谁修」向用户转述，不必贴原始报错
if [ -f /tmp/_base.bak ]; then
cp /tmp/_base.bak "$BASE"
python3 - <<'PY'
import json
p='workspace/runtime_demo/file/sess-demo-0001/scope/requirements-baseline.json'
b=json.load(open(p,encoding='utf-8'))
req=next(r for r in b['requirements'] if r['id']=='REQ-001')
req['evidence'][0]['quote']='风险等级分为高中低三档。'
json.dump(b,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
OUT=$(python3 "$VB" "$BASE" --input-dir "$PRD" --freeze 2>&1)
echo "$OUT" | grep -q '^\[FAIL\]' && ok "机验失败输出含 [FAIL] 步骤行" || ng "机验失败输出缺 [FAIL] 步骤行"
echo "$OUT" | grep -q '^\[REPORT\]' && ok "机验失败输出含 [REPORT] 工件行" || ng "机验失败输出缺 [REPORT] 工件行"
echo "$OUT" | grep -q '校验汇总: FAIL$' && ok "机验失败输出含「校验汇总: FAIL」锚点" || ng "机验失败输出缺汇总锚点"
grep -Eq '"label"' "$(echo "$OUT" | sed -n 's/^\[REPORT\] //p' | head -1)" && ok "机验报告工件结构化承载失败明细（steps.label）" || ng "报告工件缺结构化失败明细"
cp /tmp/_base.bak "$BASE"
else
ng "5.17 跳过：fixture 缺失（/tmp/_base.bak 不存在）"
fi


echo
echo "========== 6. 全链交付校验（check full + 报告指纹）=========="
REPORT="$S/output/reports/check-full.json"
python3 .opencode/skills/test-point-spec/scripts/check.py --phase full \
  --input-dir "$PRD" --baseline "$BASE" --scope-list "$S/state/scope-list.md" \
  --tp-file "$TP" --tc-file "$TC" --clarifications "$S/state/clarifications.md" \
  --report "$REPORT" >/dev/null 2>&1 && ok "全链机械校验通过" || ng "全链机械校验失败"
[ -f "$REPORT" ] && python3 -c "import json,sys;d=json.load(open('$REPORT'));exit(0 if d.get('passed') is True else 1)" >/dev/null 2>&1 \
  && ok "校验报告 passed=true 且指纹自检内建通过" || ng "校验报告状态异常"
# TC 引文明细报告按管线契约条件存在：TC 清单含直引 → 必有子报告；无直引 → 正确 skip
if grep -Eq 'prd.*\.md:L[0-9]+「' "$TC" 2>/dev/null; then
  [ -f "${REPORT%.json}.quotes-tc.json" ] && ok "TC 引文明细报告已产出" || ng "TC 引文明细报告缺失"
else
  [ ! -f "${REPORT%.json}.quotes-tc.json" ] && ok "TC 无直引，quote-tc 正确跳过" || ng "TC 无直引却产生了引文报告"
fi
grep -q 'source-catalog\|anchors' "$REPORT" >/dev/null 2>&1 && ng "报告仍含 V1 步骤" || ok "机器报告无 V1 步骤残留"

echo
echo "===== 6b. 摘录定位与批量（纯文本辅助）====="
OUT=$(python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py --prd-dir "$PRD" --locate "4" --max-chars 40 2>&1)
if echo "$OUT" | grep -q "提交时校验审核人身份"; then ok "extract_excerpt 提取正确"; else ng "extract_excerpt 提取失败: $OUT"; fi
LOC=/tmp/_loc.txt
printf '功能需求\n不存在章节\n' > "$LOC"
OUT=$(python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py --prd-dir "$PRD" --locate-file "$LOC" 2>&1)
echo "$OUT" | grep -q "1/2 条命中" && ok "批量定位一次取回多条" || ng "批量定位失败: $OUT"
rm -f "$LOC"
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py --prd-dir "$PRD" --locate "NOT-EXIST" >/dev/null 2>&1 && ng "不存在的定位未拒绝" || ok "不存在的定位被拒绝"

echo
echo "========== 7. 工作流工具单元回归 =========="
python3 -m unittest discover -s tests >/dev/null 2>&1 && ok "工作流工具单元回归通过" || ng "工作流工具单元回归失败"

echo
echo "========== 8. 工作空间结构（V2 产物，无 anchors/source-catalog）=========="
for d in "$W/project-docs" "$S/user-input" "$S/output/tp" "$S/output/tc" "$S/output/reports" "$S/state" "$S/scope"; do
  [ -d "$d" ] && ok "目录 $d" || ng "目录缺失 $d"
done
[ -f "$S/scope/outline.md" ] && ok "outline.md" || ng "outline.md 缺失"
[ -f "$S/scope/files-manifest.md" ] && ok "files-manifest.md" || ng "files-manifest.md 缺失"
[ ! -f "$S/scope/source-catalog.json" ] && ok "source-catalog.json 已不再生成" || ng "source-catalog.json 仍被生成"
[ ! -f "$S/scope/anchors.md" ] && ok "anchors.md 已不再生成" || ng "anchors.md 仍被生成"
[ -f "opencode.jsonc" ] && ok "opencode.jsonc" || ng "opencode.jsonc 缺失"
[ -f "README.md" ] && ok "README.md" || ng "README.md 缺失"
[ -f "工作空间目录结构.md" ] && ok "工作空间目录结构.md" || ng "工作空间目录结构.md 缺失"

echo
echo "========== 9. 知识聚焦（references 无流程/输出包装句）=========="
for f in .opencode/skills/test-knowledge/references/*.md; do
  if grep -qE 'Agent 接到|Agent 拿到|AI 测试 Agent|Agent 生成|Agent 参考|思维导图|记入资料质检报告|适用时机：阶段' "$f"; then
    ng "知识文件含流程/输出包装句: $f"
  else
    ok "知识聚焦: $(basename "$f")"
  fi
done

echo
echo "=========================================="
echo "通过 $PASS 项，失败 $FAIL 项"
[ "$FAIL" -eq 0 ] || exit 1
