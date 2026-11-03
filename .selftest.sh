#!/usr/bin/env bash
# 交付自检：权限断言 + 校验脚本正/负面回归 + 结构完整性
set -u
cd "$(dirname "$0")" || exit 1
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '[PASS] %s\n' "$1"; }
ng(){ FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$1"; }

W="workspace/runtime_demo/file"
S="$W/sess-demo-0001"
PRD="$W/project-docs"
VA=".opencode/skills/prd-record-spec/scripts/verify_anchors.py"
VP=".opencode/skills/test-point-spec/scripts/verify_test_points.py"
VC=".opencode/skills/test-case-spec/scripts/verify_test_cases.py"

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
perm_block .opencode/agents/test-qa-expert.md | grep -q 'output/tp\|output/tc' && ng "qa 被授予产物写权限" || ok "qa 无产物写权限"
perm_block .opencode/agents/test-manager.md | grep -q 'output/tp\|output/tc\|output/reports' && ng "manager 被授予产物写权限" || ok "manager 无产物写权限"

echo
echo "========== 3. Skill 与脚本完整性 =========="
for s in prd-record-spec prd-quality-check tdd-quality-check test-analysis-methods test-point-spec test-case-spec; do
  [ -f ".opencode/skills/$s/SKILL.md" ] && ok "skill $s" || ng "skill $s 缺失"
done
[ -f "$VA" ] && ok "verify_anchors.py" || ng "verify_anchors.py 缺失"
[ -f "$VP" ] && ok "verify_test_points.py" || ng "verify_test_points.py 缺失"
[ -f "$VC" ] && ok "verify_test_cases.py" || ng "verify_test_cases.py 缺失"
[ -f ".opencode/skills/prd-record-spec/scripts/extract_excerpt.py" ] && ok "extract_excerpt.py" || ng "extract_excerpt.py 缺失"

echo
echo "========== 4. 校验脚本正面回归（应全部通过）=========="
python3 "$VA" "$S/scope/anchors.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ok "verify_anchors 通过" || ng "verify_anchors 失败"
python3 "$VP" "$S/output/tp/test-point.md" --ledger "$S/scope/anchors.md" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ok "verify_test_points 通过" || ng "verify_test_points 失败"
python3 "$VC" "$S/output/tc/test-case.md" --tp-file "$S/output/tp/test-point.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ok "verify_test_cases 通过" || ng "verify_test_cases 失败"

echo
echo "========== 5. 负面回归（必须抓到问题）=========="
cp "$S/output/tp/test-point.md" /tmp/_tp.bak
cp "$S/output/tc/test-case.md" /tmp/_tc.bak
cp "$S/scope/anchors.md" /tmp/_an.bak

# 5.1 摘录超 40 字
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/scope/anchors.md'
s=open(p,encoding='utf-8').read().replace(
 '风险名称必填，长度不超过 50 个字符。',
 '风险名称必填，长度不超过 50 个字符，风险等级为高、中、低三档，默认中，提交时校验审核人身份。')
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VA" "$S/scope/anchors.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "摘录超长未被捕获" || ok "摘录超 40 字被捕获"
cp /tmp/_an.bak "$S/scope/anchors.md"

# 5.2 摘录非原文（幻觉）
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/scope/anchors.md'
s=open(p,encoding='utf-8').read().replace(
 '风险名称必填，长度不超过 50 个字符。',
 '风险名称必须填写且长度不得超出 50 个字符的限制要求。')
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VA" "$S/scope/anchors.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "幻觉摘录未被捕获" || ok "幻觉摘录被捕获"
cp /tmp/_an.bak "$S/scope/anchors.md"

# 5.3 底册锚点未覆盖
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read().replace('| M1-S4-P5 |  | 与 M1-S4-P4 语义重复，按锚点去重规则由 M1-S4-P4 覆盖 |\n','')
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$S/output/tp/test-point.md" --ledger "$S/scope/anchors.md" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "锚点未覆盖未被捕获" || ok "底册锚点未覆盖被捕获"
cp /tmp/_tp.bak "$S/output/tp/test-point.md"

# 5.4 交付物出现业务功能编号
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md'
s=open(p,encoding='utf-8').read().replace('| TP-001 |','| TP-001 | 属 BF01 |',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VP" "$S/output/tp/test-point.md" --ledger "$S/scope/anchors.md" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "业务功能编号泄漏未被捕获" || ok "交付物业务功能编号泄漏被捕获"
cp /tmp/_tp.bak "$S/output/tp/test-point.md"

# 5.5 标签编造名称
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tc/test-case.md'
s=open(p,encoding='utf-8').read().replace('所属业务功能：新增风险','所属业务功能：风险登记管理',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VC" "$S/output/tc/test-case.md" --tp-file "$S/output/tp/test-point.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "标签编造未被捕获" || ok "标签编造名称被捕获"
cp /tmp/_tc.bak "$S/output/tc/test-case.md"

# 5.6 悬空 TP 引用
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tc/test-case.md'
s=open(p,encoding='utf-8').read().replace('| TC-004 | 审核人非本项目测试管理人提交被拒 | TP-004 |','| TC-004 | 审核人非本项目测试管理人提交被拒 | TP-099 |',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VC" "$S/output/tc/test-case.md" --tp-file "$S/output/tp/test-point.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "悬空TP引用未被捕获" || ok "悬空 TP 引用被捕获"
cp /tmp/_tc.bak "$S/output/tc/test-case.md"

# 5.7 TP 未被覆盖
python3 - <<'PY'
p='workspace/runtime_demo/file/sess-demo-0001/output/tc/test-case.md'
s=open(p,encoding='utf-8').read().replace('| TP-003 |  | 可见范围差异由 TC 在 TP-001 下补充，不单列 |','| TP-003 |  |  |',1)
open(p,'w',encoding='utf-8').write(s)
PY
python3 "$VC" "$S/output/tc/test-case.md" --tp-file "$S/output/tp/test-point.md" --prd-dir "$PRD" --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ng "TP未覆盖未被捕获" || ok "TP 未覆盖且无原因被捕获"
cp /tmp/_tc.bak "$S/output/tc/test-case.md"

echo
echo "===== 5b. A1/A2/A3/A4 修复回归（--clarifications / SHA256 / docx）====="
TPFIX="$S/output/tp/test-point.md"
CLF="$S/state/clarifications.md"
cp "$TPFIX" /tmp/_tp.clear.bak

# 5b-1 悬空 CL-999 → 必须 FAIL（临时副本）
python3 - <<'PY'
s=open('workspace/runtime_demo/file/sess-demo-0001/output/tp/test-point.md',encoding='utf-8').read()
row='| TP-099 | 验证挂空澄清编号的场景被拒绝 | 异常 | 错误推测 | CL-999 用户澄清：不存在。 |'
s=s.replace('| TP-006 | 验证审核通过后风险状态变更为已审核 | 流程 | 状态迁移 | M1-S4-P8 审核通过后状态变更为已审核；审核不通过则退回，状态为已关闭。 |',
            '| TP-006 | 验证审核通过后风险状态变更为已审核 | 流程 | 状态迁移 | M1-S4-P8 审核通过后状态变更为已审核；审核不通过则退回，状态为已关闭。 |\n'+row)
open('/tmp/_tp.cl999.md','w',encoding='utf-8').write(s)
PY
python3 "$VP" /tmp/_tp.cl999.md --ledger "$S/scope/anchors.md" --scope-list "$S/state/scope-list.md" --clarifications "$CLF" >/dev/null 2>&1 && ng "悬空 CL-999 未被捕获" || ok "A2: 悬空澄清编号被捕获"
rm -f /tmp/_tp.cl999.md

# 5b-2 依据摘录改写 → 必须 FAIL
cp "$TPFIX" /tmp/_tp.rew.md
python3 - <<'PY'
s=open('/tmp/_tp.rew.md',encoding='utf-8').read()
s=s.replace('M1-S4-P1 风险名称必填，长度不超过 50 个字符。','M1-S4-P1 风险名称必须填写，且长度上限为 50 个字符。',1)
open('/tmp/_tp.rew.md','w',encoding='utf-8').write(s)
PY
python3 "$VP" /tmp/_tp.rew.md --ledger "$S/scope/anchors.md" --scope-list "$S/state/scope-list.md" --clarifications "$CLF" >/dev/null 2>&1 && ng "摘录改写未被捕获" || ok "A3: 依据摘录与底册不一致被捕获"
rm -f /tmp/_tp.rew.md

# 5b-3 正面回归带 --clarifications（退出码 0 且含 SHA256 行）
OUT=$(python3 "$VP" "$TPFIX" --ledger "$S/scope/anchors.md" --scope-list "$S/state/scope-list.md" --clarifications "$CLF" 2>&1)
if echo "$OUT" | grep -q '\[SHA256\]' && echo "$OUT" | tail -1 | grep -q 'FAIL=0'; then ok "A4: 脚本输出含 [SHA256] 且原清单全绿"; else ng "A4: SHA256 行缺失或校验非绿: $(echo "$OUT" | tail -2 | head -1)"; fi

# 5b-4 docx PRD → 摘录逐字命中 PASS
python3 - <<'PY'
import zipfile, os, shutil
d='/tmp/_selftest_docx'
shutil.rmtree(d, ignore_errors=True)
os.makedirs(d)
src=open('workspace/runtime_demo/file/project-docs/prd-demo.md',encoding='utf-8').read()
paras=[l.strip() for l in src.split(chr(10)) if l.strip()]
body=''.join('<w:p><w:r><w:t xml:space="preserve">'+t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')+'</w:t></w:r></w:p>' for t in paras)
doc='<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>'
ct='<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
with zipfile.ZipFile(d+'/prd.docx','w') as z:
    z.writestr('[Content_Types].xml',ct); z.writestr('_rels/.rels',rels); z.writestr('word/document.xml',doc)
PY
python3 "$VA" "$S/scope/anchors.md" --prd-dir /tmp/_selftest_docx --scope-list "$S/state/scope-list.md" >/dev/null 2>&1 && ok "PRD/docx: 摘录逐字命中 docx 通过" || ng "PRD/docx: docx 命中校验失败"
rm -rf /tmp/_selftest_docx /tmp/_tp.clear.bak

echo
echo "========== 6. 摘录提取脚本 =========="
OUT=$(python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py --prd-dir "$PRD" --locate "M1-S4-P6" 2>&1)
if [ $? -eq 0 ] && echo "$OUT" | grep -q "提交时校验审核人身份"; then ok "extract_excerpt 提取正确"; else ng "extract_excerpt 提取失败: $OUT"; fi
python3 .opencode/skills/prd-record-spec/scripts/extract_excerpt.py --prd-dir "$PRD" --locate "NOT-EXIST" >/dev/null 2>&1 && ng "不存在的定位未拒绝" || ok "不存在的定位被拒绝"

echo
echo "========== 7. 工作空间结构 =========="
for d in "$W/project-docs" "$S/user-input" "$S/output/tp" "$S/output/tc" "$S/output/reports" "$S/state" "$S/scope"; do
  [ -d "$d" ] && ok "目录 $d" || ng "目录缺失 $d"
done
[ -f "opencode.jsonc" ] && ok "opencode.jsonc" || ng "opencode.jsonc 缺失"
[ -f "README.md" ] && ok "README.md" || ng "README.md 缺失"
[ -f "工作空间目录结构.md" ] && ok "工作空间目录结构.md" || ng "工作空间目录结构.md 缺失"

echo
echo "=========================================="
echo "通过 $PASS 项，失败 $FAIL 项"
[ "$FAIL" -eq 0 ] || exit 1
