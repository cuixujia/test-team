#!/usr/bin/env python3
"""verify_test_points.py — 测试点清单机械校验（纯文本直引，V2 唯一流程）

校验项：
  1. 编号格式 TP-NNN、唯一、连续
  2. 验证意图以「验证」开头
  3. 必填字段非空（验证意图/类型/分析方法/依据）
  4. 依据证据项校验（每项必须是行首证据 token）：
     - 直引证据：`文件名:L行号或区间「原话」` → **格式/定位校验**（摘录正文保真由
       check.py 的 quote-tp 步统一逐字裁决——2026-11-05 收敛，本关不再双重比字）
     - 澄清证据：CL-xxx → 必须存在于澄清记录（--clarifications，未提供而引用即 FAIL）
     - 其余写法（含旧锚点 ID）一律 FAIL，杜绝幻觉锚点
  5. 覆盖对照表（证据→测试点）可省略（2026-11-05 收敛：由机验管线自动推导，
     check.py 的 derive-coverage-table 步骤输出数据视图）；手工提供时仍按契约校验：
     已引用的 直引证据 必须上表；未覆盖须写明原因；CL 行可选、不参与覆盖核算
  6. 交付物中不得出现业务功能编号
  7. 输出 [SHA256] 行（交稿自证/收回核验共用同一指纹来源）

用法：
  python3 verify_test_points.py <测试点清单> --input-dir <资料目录> [--scope-list <任务功能清单>] [--clarifications <澄清记录>]

退出码：0 = 通过；1 = 存在 FAIL；2 = 用法错误
"""
import os
import re
import sys
import argparse

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "_lib"))
from mdtable import parse_first_table, parse_md_table, read_text, sha256_file as sha256_of  # noqa: E402

FAILS = []
PASSES = []


def fail(m):
    FAILS.append(m)
    print(f"[FAIL] {m}")


def ok(m):
    PASSES.append(m)
    print(f"[PASS] {m}")


def warn(m):
    print(f"[WARN] {m}")


# 逐字比对已收敛至 check.py 的 quote-tp 步（verify_quotes.py，归一比对 + --autofix 自愈），
# 本脚本不再对摘录做原文比对（2026-11-05 收敛 A1：消除双重机验与口径分歧）；
# 引文裁决口径以 check.py 报告工件为准。


# parse_md_table / parse_first_table / norm / read_text / sha256_of 已收敛至
# .opencode/skills/_lib/mdtable.py（唯一实现，禁止本地副本——2026-11-05 收敛）


# 直引证据（文件:行号+原话，唯一 PRD 证据格式，见 prd-record-spec/SKILL.md）
V2_CITE_RE = re.compile(
    r"^\s*([A-Za-z0-9_\-./\u4e00-\u9fff]+\.(?:md|markdown|txt|csv)):"
    r"L(\d+(?:\s*[-~]\s*\d+)?)\s*「([^」]{1,300})」"
)


def evidence_anchor(segment):
    """识别依据证据项的行首证据 token：
    - 直引：返回 `文件:L行号`（并返回原始引用元组供逐字比对）
    - 澄清：返回 CL-xxx
    - 其余：None（含 TP/TC 编号与旧式锚点，均不允许）
    """
    m = V2_CITE_RE.match(segment)
    if m:
        return f"{m.group(1)}:L{m.group(2)}", (m.group(1), m.group(2), m.group(3))
    m = re.match(r"^\s*(CL-\d+)\b", segment)
    if m:
        return m.group(1), None
    return None, None


def evidence_segments(cell):
    """多条证据以保留分隔符 ⟂ 分隔。"""
    return [part.strip() for part in re.split(r"\s*⟂\s*", cell) if part.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tpfile", help="测试点清单路径")
    ap.add_argument("--input-dir", required=True, help="资料目录（直引证据就地逐字校验）")
    ap.add_argument("--scope-list", default="", help="任务功能清单路径")
    ap.add_argument("--clarifications", default="", help="澄清记录路径")
    args = ap.parse_args()

    if not os.path.isfile(args.tpfile):
        print(f"[FAIL] 文件不存在: {args.tpfile}")
        return 1
    text = read_text(args.tpfile)

    # 主表 = 第一个 ## 章节之前的表格
    header, main_rows = parse_md_table(text, "")

    if not main_rows:
        print("[FAIL] 测试点清单无有效数据行")
        return 1

    # 列序契约: 编号 | 验证意图 | 类型 | 分析方法 | 依据
    if header != ["编号", "验证意图", "类型", "分析方法", "依据（文件:行号+原话）"]:
        print(f"[FAIL] 测试点清单列序不符合契约: {header}")

    # 1) 编号格式 / 唯一 / 连续
    ids = [r[0] for r in main_rows]
    bad_fmt = [i for i in ids if not re.fullmatch(r"TP-\d{3}", i)]
    if bad_fmt:
        fail(f"TP 编号格式非法(须 TP-NNN): {' '.join(bad_fmt)}")
    else:
        ok("TP 编号格式校验通过")
    if len(set(ids)) != len(ids):
        dup = {i for i in ids if ids.count(i) > 1}
        fail(f"TP 编号重复: {' '.join(sorted(dup))}")
    else:
        ok("TP 编号唯一性校验通过")
    nums = sorted(int(i.split("-")[1]) for i in ids if re.fullmatch(r"TP-\d{3}", i))
    if nums and nums != list(range(nums[0], nums[0] + len(nums))):
        fail(f"TP 编号不连续: {nums}")
    elif nums:
        ok("TP 编号连续性校验通过")

    # 2) 验证意图以「验证」开头
    bad = [f"{r[0]}:{r[1]}" for r in main_rows if r[1] and not r[1].startswith("验证")]
    if bad:
        fail(f"验证意图未以「验证」开头: {' | '.join(bad)}")
    else:
        ok("验证意图以「验证」开头校验通过")

    # 3) 必填字段
    fields = [(2, "类型"), (3, "分析方法"), (4, "依据")]
    empties = []
    for r in main_rows:
        if not r[1]:
            empties.append(f"{r[0]}:验证意图")
        for idx, name in fields:
            if idx < len(r) and not r[idx]:
                empties.append(f"{r[0]}:{name}")
    if empties:
        fail(f"必填字段为空: {' '.join(empties)}")
    else:
        ok("必填字段非空校验通过")

    # 4) 依据证据项校验
    #    - 直引证据 `文件:L行「原话」` → 对原文件指定行逐一比对
    #    - 澄清证据 CL-xxx → 须存在于澄清记录（未提供文件即 FAIL）
    cl_ids = set()
    if args.clarifications:
        if os.path.isfile(args.clarifications):
            ct = read_text(args.clarifications)
            _ch, crows = parse_first_table(ct)
            cl_ids = {r[0] for r in crows if r and re.fullmatch(r"CL-\d+", r[0])}

    cited = set()           # 被引用的 直引 token：file:Llines（保真裁决由 quote-tp 步负责，本关只做 token 定位校验）
    used_cl = set()
    for r in main_rows:
        cell = r[4] if len(r) > 4 else ""
        if not cell:
            continue
        segments = evidence_segments(cell)
        if not segments:
            fail(f"依据证据项缺失或格式非法: {r[0]}")
            continue
        for segment in segments:
            tok, cite = evidence_anchor(segment)
            if tok is None:
                fail(f"依据证据项未以 直引(文件:L行「原话」) 或 CL-xxx 开头: {r[0]} ({segment[:30]})")
                continue
            if tok.startswith("CL-"):
                used_cl.add(tok)
                if not args.clarifications:
                    fail(f"依据引用澄清编号但未提供 --clarifications: {r[0]} ({tok})")
                elif tok not in cl_ids:
                    fail(f"澄清编号不在澄清记录中: {r[0]} ({tok})")
                continue
            # 2026-11-05 收敛（A1）：不再在此对原文件逐字比对——保真与自愈统一由 quote-tp 步裁决；
            # 本关校验 token 结构（文件与行号写法可解析，防幻觉锚点）。
            rel, spec, quote = cite
            if not re.fullmatch(r"[A-Za-z0-9_\-./\u4e00-\u9fff]+\.(?:md|markdown|txt|csv)", rel) \
                    or not re.fullmatch(r"\d+(?:\s*[-~]\s*\d+)?", spec):
                fail(f"直引证据定位写法非法（文件名/行号）: {r[0]} ({rel}:L{spec})")
                continue
            cited.add(tok)

    if cited and not any("直引证据定位写法非法" in m for m in FAILS):
        ok("直引证据定位格式校验通过（逐字保真由 quote-tp 步裁决）")
    if used_cl and not any("澄清编号" in m for m in FAILS):
        ok("澄清编号存在性校验通过")

    # 5) 覆盖对照表（证据→测试点）：**可省略**（2026-11-05 收敛——该表可由机验管线从主表
    #    自动推导，check.py 会生成 derived 数据视图；手工维护是表格式错误的主要来源）。
    #    提供时仍按既有契约校验，防止"另写一份与主表矛盾的手工表"。
    ch, crows = parse_md_table(text, "证据→测试点")
    if not crows:
        ok("覆盖对照表未手工提供（由机验管线自动推导，check.py derive-coverage-table 输出）")
    else:
        covered = set()
        bad_rows = []
        for r in crows:
            if len(r) < 3 or not r[0]:
                continue
            ev = r[0].strip()
            m = re.fullmatch(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+\.(?:md|markdown|txt|csv)):L(\d+(?:\s*[-~]\s*\d+)?)", ev)
            if m:
                covered.add(f"{m.group(1)}:L{m.group(2)}")
                continue
            if re.fullmatch(r"CL-\d+", ev) or ev in ("证据（文件:行号）", "文件:行号", "直引证据"):
                continue
            bad_rows.append(ev)
        if bad_rows:
            fail(f"覆盖对照表首列含非法证据标识(须 文件:L行 或 CL-xxx): {' | '.join(bad_rows[:5])}")
        missing = sorted(cited - covered)
        if missing:
            fail(f"被引用的证据未出现在覆盖对照表: {' '.join(missing)}")
        else:
            ok("被引用证据在覆盖对照表全覆盖校验通过")
        extra = sorted(covered - cited)
        if extra:
            fail(f"覆盖对照表登记了未被任何 TP 引用的证据(疑似幻覺证据): {' '.join(extra)}")
        # 未覆盖项（无 TP 的证据行）须写明原因；已覆盖项原因列应留空
        noreason, hasreason = [], []
        for r in crows:
            if len(r) < 3:
                continue
            ev = r[0].strip()
            if not re.fullmatch(r"([A-Za-z0-9_\-./\u4e00-\u9fff]+\.(?:md|markdown|txt|csv)):L\d+", ev):
                continue
            tps = [x.strip() for x in re.split(r"[,，、]", r[1]) if x.strip()]
            bad_tps = [tp for tp in tps if not re.fullmatch(r"TP-\d{3}", tp)]
            if bad_tps:
                fail(f"覆盖对照表含非法测试点编号: {ev} ({' '.join(bad_tps)})")
            reason = r[2].strip()
            if not tps and not reason:
                noreason.append(ev)
            if tps and reason:
                hasreason.append(ev)
        if noreason:
            fail(f"覆盖对照表中未覆盖的证据未填写原因: {' '.join(noreason)}")
        else:
            ok("覆盖对照表未覆盖项原因声明校验通过")
        if hasreason:
            warn(f"覆盖对照表中已覆盖的证据填写了未覆盖原因: {' '.join(hasreason)}")

    # 6) 交付物不得出现业务功能编号
    if args.scope_list and os.path.isfile(args.scope_list):
        st = read_text(args.scope_list)
        sh, srows = parse_first_table(st)
        codes = {r[0] for r in srows if r and r[0] != "业务功能编号" and r[0]}
        if codes:
            hit = []
            for c in sorted(codes):
                if re.search(rf"\b{re.escape(c)}\b", text):
                    hit.append(c)
            if hit:
                fail(f"交付物中出现业务功能编号(仅限过程使用): {' '.join(hit)}")
            else:
                ok("交付物未出现业务功能编号校验通过")
        else:
            warn("任务功能清单中无功能编号，跳过泄漏检查")
    else:
        warn("未提供 --scope-list，跳过业务功能编号泄漏检查")

    # 7) 交稿指纹（交稿自证与收回核验取同一来源）
    try:
        print(f"\n[SHA256] {args.tpfile}: {sha256_of(args.tpfile)}")
    except Exception as e:  # noqa
        warn(f"SHA256 计算失败: {e}")

    print(f"\n========== 校验汇总: PASS={len(PASSES)} FAIL={len(FAILS)} ==========")
    return 1 if FAILS else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        print(f"[FAIL] 校验脚本异常: {e}")
        sys.exit(1)
