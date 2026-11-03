#!/usr/bin/env python3
"""extract_excerpt.py — 程序化提取 PRD 原文摘录（禁止模型手抄）

按锚点定位从 PRD 原文中提取连续原句，输出到 stdout 并报告字符数。
手抄摘录是摘录漂移的根因——所有写入底册/依据列的摘录必须经本脚本提取。

用法：
  # 按章节定位提取
  python3 extract_excerpt.py --prd-dir <PRD目录> --locate "4.3.1"

  # 按锚点定位（从底册中已登记的锚点读取其章节定位）
  python3 extract_excerpt.py --prd-dir <PRD目录> --ledger <底册路径> --anchor "4.3.1"

  # 指定最大字数与截断策略
  python3 extract_excerpt.py --prd-dir <PRD目录> --locate "4.3.1" --max-chars 40

退出码：0 = 提取成功；1 = 未找到或无法定位；2 = 用法错误
说明：只做定位与截取，不改写、不拼接、不跨段。
"""
import os
import re
import sys
import argparse


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


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


def iter_prd_files(prd_dir):
    for root, _d, files in os.walk(prd_dir):
        for fn in sorted(files):
            if fn.startswith(".") or not fn.lower().endswith(PRD_EXTS):
                continue
            yield os.path.join(root, fn)


def locate_in_text(text, locate):
    """在文本中定位章节，返回该章节的正文（不含标题行）。找不到返回 None。

    定位串可以是：章节编号(4.3.1)、标题文字、或二者组合(4.3.1 标题)。
    兼容两种 PRD 写法：
      A. 标题层级：### 4.3.1 提交时校验审核人身份
      B. 列表项编号：- 4.3.1 提交时校验审核人身份，...
    """
    lines = text.split("\n")
    # 收集标题行与其序号
    heads = []  # (index, num, title, level)
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s*(.*)$", ln)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            num = ""
            mnum = re.match(r"^([0-9]+(?:\.[0-9]+)*)\s*[、.．]?\s*(.*)$", title)
            if mnum:
                num = mnum.group(1)
                title = (mnum.group(2) or title).strip()
            heads.append((i, num, title, level))

    # 1) 精确匹配章节号
    target = None
    for i, num, title, _lv in heads:
        if num == locate:
            target = i
            break
    # 2) 匹配标题文字
    if target is None:
        for i, num, title, _lv in heads:
            if title and (title == locate or locate in title):
                target = i
                break
    # 3) 列表项编号写法：- 4.3.1 内容
    if target is None:
        for i, ln in enumerate(lines):
            m = re.match(r"^\s*[-*+]\s+([0-9]+(?:\.[0-9]+)*)\s*[、.．]?\s*(.*)$", ln)
            if m and m.group(1) == locate:
                body = "\n".join(lines[i:i + 12]).strip()
                return body or None
    # 4) 无编号 PRD 的锚点形式 M<模块>-S<章节>-P<段落>：定位到章节，取第 P 个段落
    if target is None:
        mseg = re.fullmatch(r"M(\d+)-S(\d+)-P(\d+)", locate)
        if mseg:
            sec = int(mseg.group(2))
            para = int(mseg.group(3))
            for i, num, title, _lv in heads:
                if num == str(sec):
                    lvl = next(l for (j, n, t, l) in heads if j == i)
                    end = len(lines)
                    for j, n2, t2, l2 in heads:
                        if j > i and l2 <= lvl:
                            end = j
                            break
                    # 段落计数只数内容行（排除子标题行），P 从 1 开始
                    paras = []
                    for ln in lines[i + 1:end]:
                        s = ln.strip()
                        if not s:
                            continue
                        if s.startswith("#"):
                            continue
                        paras.append(s)
                    if 0 < para <= len(paras):
                        return paras[para - 1]
                    break

    # 5) 纯文本回退（docx/doc/txt 无 markdown 标题）：行首编号且行长 ≤60 视为标题行
    #    已知限制：docx 标题为自动编号样式（提取后无编号文本）时可能无法定位，
    #    此时按 prd-record-spec 以「> 摘录机验：跳过（原因）」登记降级。
    if target is None:
        def _num_of(line):
            t = line.strip()
            if not t or len(t) > 60 or t.startswith(("-", "*", "+", "|")):
                return None
            m = re.match(r"^([0-9]+(?:\.[0-9]+)*)\s*[、.．]?\s*\S", t)
            return m.group(1) if m else None

        numbered = [(i, _num_of(ln)) for i, ln in enumerate(lines)]
        numbered = [(i, n) for i, n in numbered if n]
        hits = [(i, n) for i, n in numbered if n == locate]
        if hits:
            i0, n0 = hits[0]
            lvl = n0.count(".")
            end = len(lines)
            for j, nj in numbered:
                if j > i0 and nj.count(".") <= lvl:
                    end = j
                    break
            body = "\n".join(lines[i0 + 1:end]).strip()
            return body or None

    if target is None:
        return None

    # 章节正文 = 下一个同级或更高级标题之前的内容
    lvl = next(l for (i, n, t, l) in heads if i == target)
    end = len(lines)
    for i, num, title, l in heads:
        if i > target and l <= lvl:
            end = i
            break
    body = "\n".join(lines[target + 1:end]).strip()
    return body or None


def pick_sentence(body, max_chars):
    """从章节正文里取出最贴切的一句连续原句（≤max_chars）。

    策略：按中文句末标点切句，优先取包含业务动词、长度最接近上限的一句；
    绝不跨段拼接——只从单一段落内取。
    """
    paras = [p.strip() for p in body.split("\n") if p.strip()]
    best = None
    for para in paras:
        # 句末标点切分（保留标点）
        sents = re.findall(r"[^。；！？\n]*[。；！？]", para)
        if not sents:
            sents = [para]
        for s in sents:
            s = s.strip()
            if not s:
                continue
            if len(s) <= max_chars:
                if best is None or len(s) > len(best):
                    best = s
            else:
                # 超长句：在句内逗号处截断（仍在同一句内，不跨段）
                m = re.match(rf"^(.{{1,{max_chars}}})(?:，|、)(.*)$", s, re.S)
                if m:
                    cand = m.group(1)
                    if best is None or len(cand) > len(best):
                        best = cand
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prd-dir", required=True, help="PRD 文件目录")
    ap.add_argument("--locate", default="", help="章节定位串")
    ap.add_argument("--ledger", default="", help="锚点底册路径（配合 --anchor 使用）")
    ap.add_argument("--anchor", default="", help="锚点ID（从底册读取其章节定位）")
    ap.add_argument("--max-chars", type=int, default=40, help="最大字符数")
    args = ap.parse_args()

    if not os.path.isdir(args.prd_dir):
        print(f"用法错误: PRD 目录不存在 {args.prd_dir}", file=sys.stderr)
        return 2

    locate = args.locate
    if args.anchor:
        if not args.ledger or not os.path.isfile(args.ledger):
            print("用法错误: --anchor 需配合 --ledger", file=sys.stderr)
            return 2
        lt = read_text(args.ledger)
        # 底册列序: 锚点ID | 来源PRD文件 | 章节定位 | 原文摘录 | 关联功能编号
        in_sec = False
        for line in lt.split("\n"):
            if line.startswith("##"):
                in_sec = "锚点清单" in line
                continue
            if not in_sec:
                continue
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]*", c) for c in cells):
                continue
            if cells and cells[0] == args.anchor:
                locate = cells[2] if len(cells) > 2 else ""
                break
        if not locate:
            print(f"未找到锚点: {args.anchor}", file=sys.stderr)
            return 1

    if not locate:
        print("用法错误: 需 --locate 或 --anchor", file=sys.stderr)
        return 2

    for path in iter_prd_files(args.prd_dir):
        try:
            text = read_any_text(path)
        except Exception:
            continue
        body = locate_in_text(text, locate)
        if body is None:
            continue
        sent = pick_sentence(body, args.max_chars)
        if not sent:
            continue
        print(f"# 来源: {os.path.basename(path)}  定位: {locate}")
        print(f"# 字符数: {len(sent)}")
        print(sent)
        return 0

    print(f"未能在 PRD 目录中定位: {locate}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        print(f"提取失败: {e}", file=sys.stderr)
        sys.exit(1)
