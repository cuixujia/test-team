#!/usr/bin/env python3
"""verify_test_cases.py — 测试用例清单机械校验

校验项：
  1. 编号格式 TC-NNN、唯一（允许空号）
  2. 必填字段非空（标题/关联TP/优先级/前置条件/测试数据/操作步骤/预期结果/用例类型/标签）
  3. 优先级取值 P0-P3
  4. 关联TP 单值（一 TC = 一 TP，裁例通告裁决二；多值/分隔符一律 FAIL，不依赖 --tp-file）
  4b. 关联TP 引用完整性（唯一 TP 必须存在于测试点清单）
  5. 覆盖对照表存在；已验收 TP 全覆盖，未覆盖须写明原因
  5b. 每 TP 直属 TC ≥ 2（裁例通告裁决一；覆盖对照表已登记例外说明的 TP 交质检语义裁决）
  6. 标签列结构：含「所属业务功能」键；取值非空时须逐字命中 PRD；仅该键允许按规范留空（PRD 无功能矩阵项时）
  6b. 标签取值逐字命中 PRD
  7. 交付物中不得出现业务功能编号

用法：
  python3 <SKILLS_ROOT>/test-case-spec/scripts/verify_test_cases.py <TC主件绝对路径> \
    --tp-file <TP主件绝对路径> --prd-dir <资料目录绝对路径> --scope-list <scope-list绝对路径>

退出码：0 = 通过；1 = 存在 FAIL；2 = 用法错误
"""
import os
import re
import sys
import argparse

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "test-script-lib", "scripts"))
from mdtable import parse_first_table, parse_md_table, norm_space_all as norm, read_text  # noqa: E402

FAILS = []
PASSES = []


def fail(m):
    FAILS.append(m)
    print(f"[FAIL] {m}")


def ok(m):
    PASSES.append(m)
    print(f"[PASS] {m}")


def warn(m):
    # 降级提示（跳过校验/范围收窄等），不计入 FAIL——2026-11-04 修复：此前未定义导致 NameError 崩溃
    print(f"[WARN] {m}")


def split_tp_refs(value):
    """拆出 关联TP 列的所有 TP 项——仅用于单值违规诊断。

    裁例通告裁决二（一 TC = 一 TP）后，本函数不再产出「主要 TP / 相关 TP」层级：
    合法值只能拆出 1 项，多项即由校验 4 判 FAIL。分隔符放宽到空白与分号，
    防止用空格或分号绕过单值约束。
    """
    return [item.strip() for item in re.split(r"[,，、;；\s]+", value or "") if item.strip()]


def scope_list_prd_files(scope_text):
    """从任务功能清单提取「来源 PRD 文件」集合（2026-11-05 契约修复）。

    契约（见 prd-record-spec SKILL「scope-list 机器契约」）：scope-list 的
    「资料角色登记」表首列名为「文件」，登记各资料文件；本函数在该表中取
    所有 .md/.markdown/.txt/.csv 结尾的文件名。
    按具名列解析，不再按"第一张表第 3 列"猜测旧结构。
    """
    found = set()
    import re as _re
    cur_cols, cur_rows = None, []
    blocks = []

    rows_acc = []
    header_acc = None
    for line in scope_text.split("\n"):
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(_re.fullmatch(r"[-: ]*", c) for c in cells):
                continue
            if header_acc is None:
                header_acc = cells
                continue
            rows_acc.append(cells)
        else:
            if header_acc is not None:
                blocks.append((header_acc, rows_acc))
            header_acc, rows_acc = None, []
    if header_acc is not None:
        blocks.append((header_acc, rows_acc))

    def normc(x):
        return norm(x.strip("` *"))

    for header, rows in blocks:
        if not header:
            continue
        first = normc(header[0]) if header else ""
        if first == "文件":  # 资料角色登记表契约列
            for r in rows:
                if r and r[0].lower().endswith(_PRD_EXTS):
                    found.add(os.path.basename(r[0].strip()))
    return found


# ---- 资料读取：纯文本（md/markdown/txt/csv），docx/图片等非文本件在入库仪式即拦截 ----
_PRD_EXTS = (".md", ".markdown", ".txt", ".csv")
PRD_EXTS = _PRD_EXTS


# parse_md_table / parse_first_table / norm / read_text 的唯一实现在
# <SKILLS_ROOT>/test-script-lib/scripts/mdtable.py（2026-11-05 收敛，禁止本地副本）；
# split_tp_refs 是本文件本地的单值违规诊断工具（裁决二后不再解析「相关 TP」）。


def load_prd_texts(prd_dirs):
    """返回 (全部文件规范化拼接文本, 跳过文件列表)。只读，不做任何格式转换落盘。

    prd_dirs 可传多个（资料目录列表），逐目录 walk 合并。"""
    blob, skipped = [], []
    for prd_dir in prd_dirs:
        for root, _dirs, files in os.walk(prd_dir):
            for fn in sorted(files):
                if fn.startswith("."):
                    continue
                if not fn.lower().endswith(PRD_EXTS):
                    skipped.append(fn)
                    continue
                path = os.path.join(root, fn)
                try:
                    t = read_text(path)
                except Exception:
                    skipped.append(fn)
                    continue
                blob.append(norm(t))
    return "".join(blob), skipped


def load_file_texts(prd_dirs):
    """按文件名建立 {basename: 规范化文本} 映射（供标签命中精确到指定 PRD 文件）。"""
    files = {}
    for prd_dir in prd_dirs:
        for root, _dirs, fnames in os.walk(prd_dir):
            for fn in sorted(fnames):
                if fn.startswith("."):
                    continue
                if not fn.lower().endswith(PRD_EXTS):
                    continue
                path = os.path.join(root, fn)
                try:
                    t = read_text(path)
                except Exception:
                    continue
                files[fn] = norm(t)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tcfile", help="测试用例清单路径")
    ap.add_argument("--tp-file", default="", help="测试点清单路径")
    ap.add_argument("--prd-dir", default="", nargs="+", help="资料目录（可传多个：文本资料目录 + 会话转换区）")
    ap.add_argument("--scope-list", default="", help="任务功能清单路径")
    args = ap.parse_args()

    for name in ("tcfile", "tp_file", "scope_list"):
        value = getattr(args, name)
        if value and not os.path.isabs(value):
            print(f"用法错误: --{name.replace('_', '-')} 必须为绝对路径: {value}", file=sys.stderr)
            return 2
    if args.prd_dir:
        for d in args.prd_dir:
            if not os.path.isabs(d):
                print(f"用法错误: --prd-dir 必须为绝对路径: {d}", file=sys.stderr)
                return 2
        missing = [d for d in args.prd_dir if not os.path.isdir(d)]
        if missing:
            print(f"用法错误: --prd-dir 目录不存在或非目录: {' '.join(missing)}", file=sys.stderr)
            return 2

    if not os.path.isfile(args.tcfile):
        print(f"[FAIL] 文件不存在: {args.tcfile}")
        return 1
    text = read_text(args.tcfile)

    # 主表 = 第一个 ## 章节之前的表格
    header, main_rows = parse_md_table(text, "")

    if not main_rows:
        print("[FAIL] 测试用例清单无有效数据行")
        return 1

    expected = ["编号", "标题", "关联TP", "优先级", "前置条件", "测试数据",
                "操作步骤", "预期结果", "用例类型", "标签"]
    if header != expected:
        print(f"[FAIL] 测试用例清单列序不符合契约，期望 {expected}，实为 {header}")

    # 1) 编号
    ids = [r[0] for r in main_rows]
    bad = [i for i in ids if not re.fullmatch(r"TC-\d{3}", i)]
    if bad:
        fail(f"TC 编号格式非法(须 TC-NNN): {' '.join(bad)}")
    else:
        ok("TC 编号格式校验通过")
    if len(set(ids)) != len(ids):
        dup = {i for i in ids if ids.count(i) > 1}
        fail(f"TC 编号重复: {' '.join(sorted(dup))}")
    else:
        ok("TC 编号唯一性校验通过")

    # 2) 必填字段
    labels = [(1, "标题"), (2, "关联TP"), (3, "优先级"), (4, "前置条件"),
              (5, "测试数据"), (6, "操作步骤"), (7, "预期结果"), (8, "用例类型"), (9, "标签")]
    empties = []
    for r in main_rows:
        for idx, name in labels:
            if idx >= len(r) or not r[idx]:
                empties.append(f"{r[0]}:{name}")
    if empties:
        fail(f"必填字段为空: {' '.join(empties)}")
    else:
        ok("必填字段非空校验通过（含标签列）")

    # 3) 优先级
    badp = [f"{r[0]}:{r[3]}" for r in main_rows if len(r) > 3 and r[3] and not re.fullmatch(r"P[0-3]", r[3])]
    if badp:
        fail(f"优先级非法(须 P0-P3): {' '.join(badp)}")
    else:
        ok("优先级取值校验通过")

    # 4) 关联TP 单值（一 TC = 一 TP，裁例通告裁决二）
    #    与 --tp-file 无关：即使未给测试点清单，单值约束也必须生效。
    tps = set()
    if args.tp_file and os.path.isfile(args.tp_file):
        tt = read_text(args.tp_file)
        _h, trows = parse_first_table(tt)
        tps = {r[0] for r in trows if r and re.fullmatch(r"TP-\d{3}", r[0])}
    tc_tp_map = {}
    multi_ref = []
    for r in main_rows:
        ref = r[2] if len(r) > 2 else ""
        refs = split_tp_refs(ref)
        tc_tp_map[r[0]] = set(refs)
        if len(refs) != 1 or not re.fullmatch(r"TP-\d{3}", refs[0]):
            multi_ref.append(f"{r[0]}→({ref.strip() or '空'})")
    if multi_ref:
        fail("关联TP 必须为单一 TP 编号（一 TC = 一 TP，禁止多挂靠）: "
             + " ".join(multi_ref))
    else:
        ok("关联TP 单值校验通过（一 TC = 一 TP）")

    # 4b) 关联TP 引用完整性（唯一 TP 必须存在于测试点清单）
    if tps:
        badref = [
            f"{r[0]}→{tp}"
            for r in main_rows
            for tp in tc_tp_map.get(r[0], ())
            if tp not in tps
        ]
        if badref:
            fail(f"关联TP 不存在于测试点清单: {' '.join(badref)}")
        else:
            ok("关联TP 引用完整性校验通过")
    else:
        print("[WARN] 未提供 --tp-file 或测试点清单为空，跳过引用完整性校验")

    # 5) 覆盖对照表 + TP 全覆盖
    # 覆盖对照表列序: TP编号 | 覆盖的 TC 编号 | 未覆盖原因
    ch, crows = parse_md_table(text, "覆盖对照表")
    if not crows:
        fail("缺少覆盖对照表章节或表内无有效行")
    else:
        covered_tp = set()      # 被 TC 覆盖的 TP
        declared_exempt = set() # 声明了未覆盖原因的 TP
        all_tc_refs = set()     # 覆盖对照表中引用的 TC 编号
        matrix_pairs = set()    # (TP, TC) 覆盖关系
        for r in crows:
            if len(r) < 3:
                continue
            tp = r[0].strip()
            if not re.fullmatch(r"TP-\d{3}", tp):
                continue
            tcs = [x.strip() for x in re.split(r"[,，、]", r[1]) if x.strip()]
            all_tc_refs |= {x for x in tcs if re.fullmatch(r"TC-\d{3}", x)}
            matrix_pairs |= {(tp, tc) for tc in tcs if re.fullmatch(r"TC-\d{3}", tc)}
            if tcs:
                covered_tp.add(tp)
            if r[2].strip() and r[2].strip() not in ("—", "-"):
                declared_exempt.add(tp)
        if tps:
            uncovered = sorted(tps - covered_tp - declared_exempt)
            if uncovered:
                fail(f"以下 TP 未被任何 TC 覆盖且未声明未覆盖原因: {' '.join(uncovered)}")
            else:
                ok("TP 全覆盖校验通过")
        # 覆盖对照表引用的 TC 必须真实存在于用例清单
        tc_ids = {r[0] for r in main_rows if r and re.fullmatch(r"TC-\d{3}", r[0])}
        badtc = sorted(all_tc_refs - tc_ids)
        if badtc:
            fail(f"覆盖对照表引用的 TC 不存在于测试用例清单: {' '.join(badtc)}")
        # 反向：每条 TC 都应在覆盖对照表中登记
        unregistered = sorted(tc_ids - all_tc_refs)
        if unregistered:
            fail(f"以下 TC 未在覆盖对照表中登记: {' '.join(unregistered)}")
        expected_pairs = {
            (tp, tc)
            for tc, refs in tc_tp_map.items()
            for tp in refs
        }
        missing_pairs = sorted(expected_pairs - matrix_pairs)
        extra_pairs = sorted(matrix_pairs - expected_pairs)
        if missing_pairs:
            fail("测试点→用例对照表漏登记关联: " + " ".join(f"{tp}→{tc}" for tp, tc in missing_pairs))
        if extra_pairs:
            fail("测试点→用例对照表登记了用例中未声明的关联: " + " ".join(f"{tp}→{tc}" for tp, tc in extra_pairs))
        if not missing_pairs and not extra_pairs:
            ok("用例关联与测试点→用例对照表一致")

        # 5b) 每 TP 直属 TC ≥ 2（裁例通告裁决一）
        #     单值归属后，tc_tp_map 中每个 TP 的计数即其直属 TC 数；
        #     覆盖对照表「未覆盖原因」列非空 = 已登记例外说明，交质检按维度数语义裁决。
        if tps:
            tc_per_tp = {}
            for refs in tc_tp_map.values():
                for tp in refs:
                    tc_per_tp[tp] = tc_per_tp.get(tp, 0) + 1
            thin = [
                f"{tp}({tc_per_tp.get(tp, 0)}条)"
                for tp in sorted(covered_tp & tps)
                if tc_per_tp.get(tp, 0) < 2 and tp not in declared_exempt
            ]
            if thin:
                fail("以下 TP 直属 TC 不足 2 条（每 TP ≥2）: " + " ".join(thin)
                     + "；确属单维度承载的须在覆盖对照表「未覆盖原因」列登记例外说明交质检裁决")
            else:
                ok("每 TP 直属 TC ≥ 2 校验通过")

    # 6) 标签结构与取值
    #   规范（test-case-spec「标签规范」）：所属业务功能在 PRD 无对应功能矩阵项（如非功能约束）时允许留空；
    #   其余键值不得为空；非空值不得使用占位词（无/待定/N/A 等）。
    for r in main_rows:
        lab = r[9] if len(r) > 9 else ""
        if not lab:
            continue
        if "所属业务功能" not in lab:
            fail(f"{r[0]} 标签缺少「所属业务功能」键")
        for pair in [p.strip() for p in lab.split("；") if p.strip()]:
            if "：" not in pair:
                fail(f"{r[0]} 标签格式非法(须 键：值): {pair}")
                continue
            k, v = pair.split("：", 1)
            k, v = k.strip(), v.strip()
            if k not in ("所属系统", "所属业务活动", "所属业务功能"):
                fail(f"{r[0]} 标签键非法: {k}")
            if not v:
                if k != "所属业务功能":
                    fail(f"{r[0]} 标签「{k}」值为空(仅「所属业务功能」允许按规范留空)")
            elif v in ("无", "待定", "N/A", "待补充", "-", "—"):
                fail(f"{r[0]} 标签「{k}」使用了占位词: {v}")
    if not any("标签" in m for m in FAILS):
        ok("标签结构校验通过")

    # 6b) 标签取值须逐字命中 PRD —— 命中范围限定为任务功能清单「来源PRD文件」列锁定的 PRD，
    #     防止标签值只出现在开发设计文档等其他文件中也被判命中
    if args.prd_dir and all(os.path.isdir(d) for d in args.prd_dir):
        files_map = load_file_texts(args.prd_dir)
        prd_files = set()
        if args.scope_list and os.path.isfile(args.scope_list):
            st0 = read_text(args.scope_list)
            # 2026-11-05 契约修复：按「资料角色登记」表首列（列名「文件」）取资料文件，
            # 不再按旧结构"第一张表第 3 列"猜测；不匹配时回退全目录比对并 WARN。
            prd_files = scope_list_prd_files(st0)
            if not prd_files:
                warn("任务功能清单「资料角色登记」表未解析到资料文件，退回全目录比对")
        scoped_note = ""
        if prd_files:
            whitelist = [files_map[f] for f in sorted(prd_files) if f in files_map]
            if whitelist:
                blob = "".join(whitelist)
                scoped_note = "（按任务功能清单锁定的 PRD 文件比对）"
            else:
                blob, _sk = load_prd_texts(args.prd_dir)
                warn("标签命中范围收窄失败：任务功能清单指向的 PRD 文件均无法解析，退回全目录比对")
            for fn in sorted(prd_files - set(files_map)):
                warn(f"任务功能清单设定的 PRD 文件「{fn}」无法解析，标签命中未纳入该文件")
        else:
            blob, _sk = load_prd_texts(args.prd_dir)
            for fn in _sk:
                warn(f"PRD 文件无法解析，标签命中未覆盖该文件: {fn}")
        if not blob:
            warn("PRD 目录下无可解析文本，标签取值命中校验跳过")
        else:
            nothit = []
            for r in main_rows:
                lab = r[9] if len(r) > 9 else ""
                for pair in [p.strip() for p in lab.split("；") if p.strip()]:
                    if "：" not in pair:
                        continue
                    k, v = pair.split("：", 1)
                    v = v.strip()
                    if v and re.sub(r"[\s　]+", "", v) not in blob:
                        nothit.append(f"{r[0]}:{k}={v}")
            if nothit:
                fail(f"标签取值未逐字命中 PRD 原文: {' '.join(nothit)}")
            else:
                ok("标签取值逐字命中 PRD 校验通过" + scoped_note)
    else:
        fail("未提供 --prd-dir，标签取值命中校验（6b）未执行；机验管线必须传入资料目录绝对路径")

    # 7) 交付物不得出现业务功能编号
    if args.scope_list and os.path.isfile(args.scope_list):
        st = read_text(args.scope_list)
        sh, srows = parse_first_table(st)
        codes = {r[0] for r in srows if r and r[0] != "业务功能编号" and r[0]}
        if codes:
            hit = [c for c in sorted(codes) if re.search(rf"\b{re.escape(c)}\b", text)]
            if hit:
                fail(f"交付物中出现业务功能编号(仅限过程使用): {' '.join(hit)}")
            else:
                ok("交付物未出现业务功能编号校验通过")
    else:
        print("[WARN] 未提供 --scope-list，跳过业务功能编号泄漏检查")

    try:
        import hashlib
        _h = hashlib.sha256()
        with open(args.tcfile, "rb") as f:
            for _c in iter(lambda: f.read(65536), b""):
                _h.update(_c)
        print(f"\n[SHA256] {args.tcfile}: {_h.hexdigest()}")
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
