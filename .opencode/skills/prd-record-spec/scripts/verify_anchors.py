#!/usr/bin/env python3
"""verify_anchors.py — 溯源锚点底册机械校验

校验项：
  1. 底册存在，锚点清单表可解析
  2. 锚点ID 唯一
  3. 原文摘录 ≤40 字
  4. 原文摘录真实存在于「来源PRD文件」列指向的 PRD 文件（逐字命中，空白规范化后比对；
     该列无法对应具体文件时退回全目录拼接文本比对并输出 WARN）
  5. 摘录连续、不跨段拼接（摘录内不得含连续两个换行）
  6. 关联功能编号在任务功能清单内
  7. 底册锚点是否已全部出现在测试点覆盖对照表中（可选，传 --tp-file）
  8. 弱校验：底册含「## 段落账」章节（供阶段 3 漏锚抽查降耗，缺省仅 WARN 不拦截）

用法：
  python3 verify_anchors.py <底册路径> [--prd-dir <PRD目录>] [--scope-list <任务功能清单>] [--tp-file <测试点清单>]

退出码：0 = 通过；1 = 存在 FAIL；2 = 用法错误
降级：底册含「> 摘录机验：跳过」时，第 4 项输出 WARN 并跳过。
"""
import os
import re
import sys
import argparse

MAX_EXCERPT = 40
FAILS = []
WARNS = []
PASSES = []


def load_file_texts(prd_dir):
    """按文件名建立 {basename: 规范化文本} 映射（供摘录精确到来源文件比对）。"""
    files = {}
    for root, _dirs, fnames in os.walk(prd_dir):
        for fn in sorted(fnames):
            if fn.startswith(".") or not fn.lower().endswith(PRD_EXTS):
                continue
            path = os.path.join(root, fn)
            try:
                t = read_any_text(path)
            except Exception:
                continue
            if t is not None:
                files[fn] = norm(t)
    return files


def fail(msg):
    FAILS.append(msg)
    print(f"[FAIL] {msg}")


def warn(msg):
    WARNS.append(msg)
    print(f"[WARN] {msg}")


def ok(msg):
    PASSES.append(msg)
    print(f"[PASS] {msg}")


def norm(s: str) -> str:
    """空白规范化：折叠所有空白（含全角空格），用于摘录逐字比对。"""
    return re.sub(r"[\s　]+", "", s)


def parse_md_table(text: str, section_keyword: str):
    """从 markdown 中抽取指定章节下的表格，返回 list[list[str]]（已 strip）。

    兼容两种写法：
      A. 章节标题存在：只取该 ## 章节下的表
      B. 无 ## 章节（表直接跟在 H1 下）：取全文中第一张表
    注意：本函数返回章节内**全部**表的行（锚点清单 + 引用链），由调用方按列位区分。
    """
    rows = []
    in_sec = False
    seen_any_section = False
    for line in text.split("\n"):
        if line.startswith("##"):
            seen_any_section = True
            in_sec = section_keyword in line
            continue
        if seen_any_section and not in_sec:
            continue
        if not seen_any_section and line.startswith("#"):
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]*", c) for c in cells):
            continue  # 分隔行
        rows.append(cells)
    return rows


def parse_first_table(text):
    """返回 (表头行, 数据行列表)——取文档中第一张表。

    兼容两种写法：
      A. 表在某个 ## 章节下 → 取该章节的第一张表
      B. 表直接跟在 H1 下（无 ## 章节）→ 取全文第一张表
    """
    header = None
    rows = []
    seen_section = False
    for line in text.split("\n"):
        if line.startswith("##"):
            if seen_section:
                break
            seen_section = True
            continue
        if not seen_section and line.startswith("#"):
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]*", c) for c in cells):
            continue  # 分隔行
        if header is None:
            header = cells
            continue
        rows.append(cells)
    return header, rows


def read_text(path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码文件: {path}")


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
    """（兼容保留）返回 (规范化拼接文本, 跳过文件列表)。只读，不做任何格式转换落盘。"""
    files = load_file_texts(prd_dir)
    return "".join(files.values()), []



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", help="溯源锚点底册路径")
    ap.add_argument("--prd-dir", default="", help="PRD 文件所在目录")
    ap.add_argument("--scope-list", default="", help="任务功能清单路径")
    ap.add_argument("--tp-file", default="", help="测试点清单路径（校验锚点全覆盖）")
    args = ap.parse_args()

    if not os.path.isfile(args.ledger):
        print(f"[FAIL] 底册不存在: {args.ledger}")
        return 1

    text = read_text(args.ledger)
    degraded = any(
        line.strip().startswith("> 摘录机验：跳过") for line in text.split("\n")
    )

    rows = parse_md_table(text, "锚点清单")
    rows = [r for r in rows if r and r[0] != "锚点ID"]
    if not rows:
        print("[FAIL] 底册缺少「锚点清单」表或无有效数据行")
        return 1
    ok(f"底册锚点清单存在（{len(rows)} 条锚点）")

    # 列序契约：锚点ID | 来源PRD文件 | 章节定位 | 原文摘录 | 关联功能编号
    if len(rows[0]) < 5:
        print(f"[FAIL] 底册锚点清单列数不足（需 5 列：锚点ID/来源PRD文件/章节定位/原文摘录/关联功能编号），实为 {len(rows[0])} 列")
        return 1

    # 1) 锚点ID 唯一
    seen = set()
    for r in rows:
        aid = r[0]
        if aid in seen:
            fail(f"锚点ID 重复: {aid}")
        seen.add(aid)
    if len(seen) == len(rows):
        ok("锚点ID 唯一性校验通过")

    # 2) 摘录长度
    over = []
    for r in rows:
        excerpt = r[3]
        if len(excerpt) > MAX_EXCERPT:
            over.append(f"{r[0]}({len(excerpt)}字)")
    if over:
        fail(f"原文摘录超过 {MAX_EXCERPT} 字: {' '.join(over)}")
    else:
        ok(f"原文摘录长度校验通过（均 ≤{MAX_EXCERPT} 字）")

    # 3) 摘录非空 & 连续
    for r in rows:
        if not r[3]:
            fail(f"锚点 {r[0]} 原文摘录为空")
        elif "\n" in r[3]:
            fail(f"锚点 {r[0]} 摘录跨段拼接（摘录内含换行）")

    # 4) 摘录逐字命中 PRD —— 精确到锚点行「来源PRD文件」列的文件比对，
    #    防止摘录只出现在其他文档（如开发设计文档）里也被判命中
    if degraded:
        warn("底册已声明摘录机验跳过，逐字命中校验跳过")
    elif not args.prd_dir:
        warn("未提供 --prd-dir，逐字命中校验跳过")
    else:
        files = load_file_texts(args.prd_dir)
        if not files:
            fail("PRD 目录下无可解析的文本文件，无法机验摘录")
        else:
            miss = []
            fallback_rows = []
            for r in rows:
                if not r[3]:
                    continue
                fname = (r[1] or "").strip() if len(r) > 1 else ""
                target = files.get(fname)
                if target is None:
                    # 来源PRD文件无法对应到具体文件：退回全目录拼接文本，并提示
                    fallback_rows.append(r[0])
                    target = "".join(files.values())
                if norm(r[3]) not in target:
                    miss.append(r[0])
            if miss:
                fail(f"原文摘录未逐字命中 PRD 原文: {' '.join(miss)}")
            else:
                ok("原文摘录逐字命中 PRD 原文校验通过（按来源文件比对）")
            if fallback_rows:
                warn(f"摘录命中退回全目录比对（底册「来源PRD文件」列无法对应到具体文件）: "
                     f"{len(fallback_rows)} 条锚点 {sorted(set(fallback_rows))}")

    # 5) 关联功能编号在任务功能清单内（按任务功能清单第一张表解析，未再依赖章节标题关键字）
    if args.scope_list and os.path.isfile(args.scope_list):
        sl = read_text(args.scope_list)
        _fh, frows = parse_first_table(sl)
        codes = {r[0] for r in frows if r and r[0] != "业务功能编号" and r[0]}
        if not codes:
            warn("任务功能清单未解析出功能编号，关联校验按空清单跳过")
        else:
            bad = [f"{r[0]}→{r[4]}" for r in rows if len(r) > 4 and r[4] and r[4] not in codes]
            if bad:
                fail(f"关联功能编号不在任务功能清单内: {' '.join(bad)}")
            else:
                ok("关联功能编号在任务功能清单内校验通过")
    else:
        warn("未提供 --scope-list，功能编号关联校验跳过")

    # 5b) 段落账提示（弱校验：不拦截，仅供阶段 3 漏锚抽查降耗）
    if "## 段落账" not in text:
        warn("底册缺少「## 段落账」章节——建议随底册逐段登记处置（已建锚/范围外/待确认），"
             "阶段 3 漏锚扫描可据此抽查而不必全文重读")
    else:
        ok("底册含段落账章节，阶段 3 漏锚抽查可据此降耗")

    # 6) 底册锚点是否被测试点覆盖对照表全覆盖
    if args.tp_file and os.path.isfile(args.tp_file):
        tp = read_text(args.tp_file)
        crows = parse_md_table(tp, "覆盖对照表")
        covered = {r[0] for r in crows if r and r[0] not in ("锚点ID", "PRD 锚点", "锚点")}
        missing = sorted(seen - covered)
        if missing:
            fail(f"底册锚点未出现在测试点覆盖对照表: {' '.join(missing)}")
        else:
            ok("底册锚点在测试点覆盖对照表全覆盖校验通过")
    else:
        warn("未提供 --tp-file，锚点覆盖校验跳过")

    try:
        import hashlib
        _h = hashlib.sha256()
        with open(args.ledger, "rb") as f:
            for _c in iter(lambda: f.read(65536), b""):
                _h.update(_c)
        print(f"\n[SHA256] {args.ledger}: {_h.hexdigest()}")
    except Exception as e:  # noqa
        warn(f"SHA256 计算失败: {e}")

    print(f"\n========== 校验汇总: PASS={len(PASSES)} WARN={len(WARNS)} FAIL={len(FAILS)} ==========")
    return 1 if FAILS else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        print(f"[FAIL] 校验脚本异常: {e}")
        sys.exit(1)
