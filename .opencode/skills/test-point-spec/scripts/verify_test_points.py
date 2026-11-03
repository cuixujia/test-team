#!/usr/bin/env python3
"""verify_test_points.py — 测试点清单机械校验

校验项：
  1. 编号格式 TP-NNN、唯一、连续
  2. 验证意图以「验证」开头
  3. 必填字段非空（验证意图/类型/分析方法/依据）
  4. 依据锚点分类校验：
     - 澄清锚点（CL-xxx）→ 必须存在于澄清记录（--clarifications，未提供而引用即 FAIL，杜绝悬空与静默跳过）
     - PRD 锚点 → 必须存在于锚点底册（--ledger）
  5. PRD 锚点的摘录必须与底册登记摘录逐字一致（空白规范化后包含比对，防改写/漂移）
  6. 覆盖对照表存在；底册锚点全覆盖；未覆盖须写明原因；CL 行可选、不参与底册覆盖核算
  7. 交付物中不得出现业务功能编号
  8. 输出 [SHA256] 行（交稿自证/收回核验共用同一指纹来源）

用法：
  python3 verify_test_points.py <测试点清单> [--ledger <锚点底册>] [--scope-list <任务功能清单>] [--clarifications <澄清记录>]

退出码：0 = 通过；1 = 存在 FAIL；2 = 用法错误
"""
import os
import re
import sys
import argparse

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


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


def sha256_of(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(s):
    """空白规范化（保留引号等字符——引号漂移必须被抓到，不做引号归一）。"""
    return re.sub(r"\s+", "", s)


def parse_md_table(text, keyword):
    """返回 (表头行, 数据行列表)。

    - keyword 非空：只取标题含 keyword 的 ## 章节下的第一张表。
    - keyword 为空：取全文中**第一个 ## 章节之前**的主表（若无 ##，则取第一张表）。
    """
    header, rows = None, []
    if keyword:
        in_sec = False
        for line in text.split("\n"):
            if line.startswith("##"):
                in_sec = keyword in line
                header, rows = None, []
                continue
            if not in_sec:
                continue
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]*", c) for c in cells):
                continue
            if header is None:
                header = cells
                continue
            rows.append(cells)
        return header, rows

    # 主表：第一个 ## 之前
    for line in text.split("\n"):
        if line.startswith("##"):
            break
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]*", c) for c in cells):
            continue
        if header is None:
            header = cells
            continue
        rows.append(cells)
    return header, rows


def parse_first_table(text):
    """返回 (表头行, 数据行列表)——取文档中第一张表。

    兼容两种写法：
      A. 表在某个 ## 章节下 → 取该章节的第一张表
      B. 表直接跟在 H1 下（无 ## 章节）→ 取全文第一张表
    """
    rows_all = []
    header = None
    seen_section = False
    for line in text.split("\n"):
        if line.startswith("##"):
            if seen_section:
                break
            seen_section = True
            continue
        if not seen_section and line.startswith("#"):
            continue
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]*", c) for c in cells):
            continue
        if header is None:
            header = cells
            continue
        rows_all.append(cells)
    return header, rows_all


# 依据列锚点识别：CL- 前缀优先（避免被通用编号规则吞掉）
ANCHOR_RE = re.compile(r"(CL-\d+|M\d+-S\d+-P\d+|[A-Z]{2,5}(?:-[A-Z]{2,5})?-\d{1,5}|\d+(?:\.\d+)+)")


def first_anchor(cell):
    """取依据列第一个合法锚点 token；TP/TC 编号不算锚点。"""
    for m in ANCHOR_RE.finditer(cell):
        t = m.group(1)
        if re.fullmatch(r"(TP|TC)-\d{3}", t):
            continue
        return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tpfile", help="测试点清单路径")
    ap.add_argument("--ledger", default="", help="溯源锚点底册路径")
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
    if header != ["编号", "验证意图", "类型", "分析方法", "依据（锚点+原文摘录）"]:
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

    # 4) 依据锚点分类校验
    #    - 澄清锚点 CL-xxx → 须存在于澄清记录（未提供文件即 FAIL，防悬空/静默跳过）
    #    - PRD 锚点 → 须存在于底册，且摘录与底册登记逐字一致（空白规范化比对）
    anchors = set()
    excerpt_map = {}
    if args.ledger:
        if os.path.isfile(args.ledger):
            lt = read_text(args.ledger)
            _lh, lrows = parse_first_table(lt)
            for row in lrows:
                if not row:
                    continue
                aid = row[0]
                if re.fullmatch(r"(M\d+-S\d+-P\d+|[A-Za-z]{2,5}(?:-[A-Za-z]{2,5})?-\d{1,5}|\d+(?:\.\d+)+)", aid):
                    anchors.add(aid)
                    excerpt_map[aid] = row[3] if len(row) > 3 else ""
        else:
            fail(f"底册不存在: {args.ledger}")

    cl_ids = set()
    if args.clarifications:
        if os.path.isfile(args.clarifications):
            ct = read_text(args.clarifications)
            _ch, crows = parse_first_table(ct)
            cl_ids = {r[0] for r in crows if r and re.fullmatch(r"CL-\d+", r[0])}

    used_prd, used_cl = set(), set()
    missing_exitcode = False
    for r in main_rows:
        cell = r[4] if len(r) > 4 else ""
        if not cell:
            continue
        tok = first_anchor(cell)
        if tok is None:
            fail(f"依据缺锚点ID: {r[0]}")
            continue
        if tok.startswith("CL-"):
            used_cl.add(tok)
            if not args.clarifications:
                fail(f"依据引用澄清锚点但未提供 --clarifications: {r[0]} ({tok})")
                missing_exitcode = True
            elif tok not in cl_ids:
                fail(f"澄清锚点不在澄清记录中: {r[0]} ({tok})")
        else:
            used_prd.add(tok)
            if not args.ledger:
                fail(f"依据引用 PRD 锚点但未提供或无法读取 --ledger: {r[0]} ({tok})")
                missing_exitcode = True
            elif tok not in anchors:
                fail(f"依据锚点不在底册内: {r[0]} ({tok})")
            elif not excerpt_map.get(tok):
                fail(f"底册该锚点无原文摘录: {r[0]} ({tok})")
            elif norm(excerpt_map[tok]) not in norm(cell):
                fail(f"依据摘录与底册登记不一致(须逐字引用): {r[0]} ({tok})")
    if used_prd and anchors:
        ok("依据锚点在底册内且摘录逐字一致校验通过")
    if used_cl and args.clarifications and not missing_exitcode:
        unkn = sorted(used_cl - cl_ids)
        if not unkn:
            ok("澄清锚点在澄清记录中存在性校验通过")

    # 5) 覆盖对照表存在 + 底册锚点全覆盖
    ch, crows = parse_md_table(text, "覆盖对照表")
    if not crows:
        fail("缺少覆盖对照表章节或表内无有效行")
    else:
        covered = {
            r[0] for r in crows
            if r and r[0] not in ("锚点ID", "PRD 锚点", "锚点") and not re.fullmatch(r"CL-\d+", r[0])
        }
        if anchors:
            missing = sorted(anchors - covered)
            if missing:
                fail(f"底册锚点未出现在覆盖对照表: {' '.join(missing)}")
            else:
                ok("底册锚点在覆盖对照表全覆盖校验通过")
        extra = sorted(covered - anchors) if anchors else []
        if extra:
            fail(f"覆盖对照表锚点不在底册内(疑似幻觉锚点): {' '.join(extra)}")
        # 未覆盖项（即无 TP 的底册锚点）须写明原因；已覆盖项原因列应留空
        noreason, hasreason = [], []
        for r in crows:
            if len(r) < 3 or r[0] not in anchors:
                continue
            tps = [x.strip() for x in re.split(r"[,，、]", r[1]) if x.strip()]
            reason = r[2].strip()
            if not tps and not reason:
                noreason.append(r[0])
            if tps and reason:
                hasreason.append(r[0])
        if noreason:
            fail(f"覆盖对照表中未覆盖的锚点未填写原因: {' '.join(noreason)}")
        else:
            ok("覆盖对照表未覆盖项原因声明校验通过")
        if hasreason:
            warn(f"覆盖对照表中已覆盖的锚点填写了未覆盖原因: {' '.join(hasreason)}")

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
