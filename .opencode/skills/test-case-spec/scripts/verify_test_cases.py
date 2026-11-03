#!/usr/bin/env python3
"""verify_test_cases.py — 测试用例清单机械校验

校验项：
  1. 编号格式 TC-NNN、唯一、连续
  2. 必填字段非空（标题/关联TP/优先级/前置条件/测试数据/操作步骤/预期结果/用例类型/标签）
  3. 优先级取值 P0-P3
  4. 关联TP 引用完整性（必须存在于测试点清单）
  5. 覆盖对照表存在；已验收 TP 全覆盖，未覆盖须写明原因
  6. 标签列结构：至少含「所属业务功能」键；取值非空时须逐字命中 PRD
  7. 交付物中不得出现业务功能编号

用法：
  python3 verify_test_cases.py <测试用例清单> [--tp-file <测试点清单>] [--prd-dir <PRD目录>] [--scope-list <任务功能清单>]

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


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


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
def norm(s):
    """空白规范化（保留引号等字符——不做引号归一，引号漂移要能被抓到）。"""
    return re.sub(r"[\s　]+", "", s)


# ---- PRD 多格式读取：md/markdown/txt 直读；docx 用 stdlib 解包解析；doc 用 macOS textutil 转换 ----
PRD_EXTS = (".md", ".markdown", ".txt", ".docx", ".doc")


def read_any_text(path):
    p = path.lower()
    if p.endswith(".docx"):
        return _docx_text(path)
    if p.endswith(".doc"):
        return _doc_text(path)
    return read_text(path)


def _docx_text(path):
    """零依赖解析 docx：word/document.xml 段落 -> 行文本。"""
    import zipfile
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = xml.replace("</w:p>", "\n")
    xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    txt = (txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&apos;", "'"))
    return txt


def _doc_text(path):
    """doc(旧二进制) 经 macOS textutil 转换；写临时目录，不触碰输入。失败返回 None。"""
    import subprocess
    import tempfile
    import shutil
    tmpd = tempfile.mkdtemp(prefix="prdconv_")
    try:
        out = os.path.join(tmpd, "out.txt")
        r = subprocess.run(["textutil", "-convert", "txt", "-output", out, path],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.isfile(out):
            return read_text(out)
        return None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def load_prd_texts(prd_dir):
    """返回 (规范化拼接文本, 跳过文件列表)。只读，不做任何格式转换落盘。"""
    blob, skipped = [], []
    for root, _dirs, files in os.walk(prd_dir):
        for fn in sorted(files):
            if fn.startswith("."):
                continue
            if not fn.lower().endswith(PRD_EXTS):
                continue
            path = os.path.join(root, fn)
            try:
                t = read_any_text(path)
            except Exception:
                skipped.append(fn)
                continue
            if t is None:
                skipped.append(fn)
                continue
            blob.append(norm(t))
    return "".join(blob), skipped



def parse_first_table(text):
    """返回 (表头行, 数据行列表)——取文档中第一张表。

    兼容两种写法：
      A. 表在某个 ## 章节下 → 取该章节的第一张表
      B. 表直接跟在 H1 下（无 ## 章节）→ 取全文第一张表
    """
    rows_all = []
    header = None
    seen_section = False
    in_first_section = False
    first_section_done = False
    for line in text.split("\n"):
        if line.startswith("##"):
            if seen_section:
                break
            seen_section = True
            in_first_section = True
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tcfile", help="测试用例清单路径")
    ap.add_argument("--tp-file", default="", help="测试点清单路径")
    ap.add_argument("--prd-dir", default="", help="PRD 文件所在目录")
    ap.add_argument("--scope-list", default="", help="任务功能清单路径")
    args = ap.parse_args()

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
    nums = sorted(int(i.split("-")[1]) for i in ids if re.fullmatch(r"TC-\d{3}", i))
    if nums and nums != list(range(nums[0], nums[0] + len(nums))):
        fail(f"TC 编号不连续: {nums}")
    elif nums:
        ok("TC 编号连续性校验通过")

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

    # 4) 关联TP 引用完整性
    tps = set()
    if args.tp_file and os.path.isfile(args.tp_file):
        tt = read_text(args.tp_file)
        _h, trows = parse_first_table(tt)
        tps = {r[0] for r in trows if r and re.fullmatch(r"TP-\d{3}", r[0])}
    if tps:
        badref = []
        for r in main_rows:
            ref = r[2] if len(r) > 2 else ""
            if ref and ref not in tps:
                badref.append(f"{r[0]}→{ref}")
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
        for r in crows:
            if len(r) < 3:
                continue
            tp = r[0].strip()
            if not re.fullmatch(r"TP-\d{3}", tp):
                continue
            tcs = [x.strip() for x in re.split(r"[,，、]", r[1]) if x.strip()]
            all_tc_refs |= {x for x in tcs if re.fullmatch(r"TC-\d{3}", x)}
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

    # 6) 标签结构与取值
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
                fail(f"{r[0]} 标签「{k}」值为空(应留空则整项省略,不得写占位词)")
                if v in ("无", "待定", "N/A", "待补充", "-", "—"):
                    fail(f"{r[0]} 标签「{k}」使用了占位词: {v}")
    if not any("标签" in m for m in FAILS):
        ok("标签结构校验通过")

    # 6b) 标签取值须逐字命中 PRD
    if args.prd_dir and os.path.isdir(args.prd_dir):
        blob, skipped = load_prd_texts(args.prd_dir)
        for fn in skipped:
            warn(f"PRD 文件无法解析，标签命中未覆盖该文件: {fn}")
        if blob:
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
                ok("标签取值逐字命中 PRD 校验通过")
    else:
        print("[WARN] 未提供 --prd-dir，跳过标签取值命中校验")

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
