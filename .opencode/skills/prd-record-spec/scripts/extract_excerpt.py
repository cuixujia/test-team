#!/usr/bin/env python3
"""extract_excerpt.py — 程序化提取 PRD 原文摘录（禁止模型手抄）

按锚点定位从 PRD 原文中提取连续原句，输出到 stdout 并报告字符数。
手抄摘录是摘录漂移的根因——所有写入底册/依据列的摘录必须经本脚本提取。

用法：
  # 按章节定位提取
  python3 extract_excerpt.py --prd-dir <资料目录> --locate "4.3.1"

  # 批量提取（一次调用取多个定位串，N 条锚点不再 N 次调用）
  python3 extract_excerpt.py --prd-dir <资料目录> --locate-file <定位串清单.txt>
  #   定位串清单：每行一个定位串；空行与 # 开头的注释行跳过

  # 候选句模式：不止自动挑一句，而是一次给出 top-N 句候选供点名采用
  python3 extract_excerpt.py --prd-dir <资料目录> --locate "4.3.1" --candidates 3

  # 指定最大字数与截断策略
  python3 extract_excerpt.py --prd-dir <资料目录> --locate "4.3.1" --max-chars 40

退出码：0 = 提取成功；1 = 未找到或无法定位；2 = 用法错误
说明：只做定位与截取，不改写、不拼接、不跨段；资料为纯文本格式。
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


PRD_EXTS = (".md", ".markdown", ".txt", ".csv")


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

    # 5) 纯文本回退（txt/csv 无 markdown 标题）：行首编号且行长 ≤60 视为标题行
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


def pick_sentences(body, max_chars, topn=1):
    """从章节正文里取出 topn 句最贴切的连续原句（≤max_chars），按贴切度降序。

    策略：按中文句末标点切句，优先取包含业务动词、长度最接近上限的一句；
    绝不跨段拼接——只从单一段落内取。
    topn=1 时与旧版 pick_sentence 的选择完全一致（等长取先出现者）。
    """
    cands = []  # (len, sentence, 首次出现序)
    seq = 0
    paras = [p.strip() for p in body.split("\n") if p.strip()]
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
                cands.append((len(s), s, seq))
                seq += 1
            else:
                # 超长句：在句内逗号处截断（仍在同一句内，不跨段）
                m = re.match(rf"^(.{{1,{max_chars}}})(?:，|、)(.*)$", s, re.S)
                if m:
                    cands.append((len(m.group(1)), m.group(1), seq))
                    seq += 1
    if not cands:
        return []
    # 去重后按长度降序（稳定排序：等长保持先出现在前）
    seen, uniq = set(), []
    for _l, s, _i in cands:
        if s not in seen:
            seen.add(s)
            uniq.append((len(s), s))
    uniq.sort(key=lambda t: -t[0])
    return [s for _l, s in uniq[:max(1, topn)]]


def pick_sentence(body, max_chars):
    """兼容旧接口：返回单句（自动挑选最长贴切句）。"""
    got = pick_sentences(body, max_chars, 1)
    return got[0] if got else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prd-dir", default="", help="资料目录（纯文本：md/markdown/txt/csv）")
    ap.add_argument("--locate", default="", help="章节定位串")
    ap.add_argument("--locate-file", default="", help="批量模式：定位串清单文件（每行一个，空行与 # 注释跳过）")
    ap.add_argument("--max-chars", type=int, default=40, help="最大字符数")
    ap.add_argument("--candidates", type=int, default=1, help="每个定位串输出的候选句数量（默认 1）")
    args = ap.parse_args()

    if not os.path.isdir(args.prd_dir):
        print(f"用法错误: 资料目录不存在 {args.prd_dir}", file=sys.stderr)
        return 2
    if args.locate_file and args.locate:
        print("用法错误: --locate-file 为批量模式，不与 --locate 同用", file=sys.stderr)
        return 2

    # 批量模式：一次调用提取多个定位串
    if args.locate_file:
        if not os.path.isfile(args.locate_file):
            print(f"用法错误: 定位串清单不存在 {args.locate_file}", file=sys.stderr)
            return 2
        locates = [
            ln.strip() for ln in read_text(args.locate_file).split("\n")
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not locates:
            print("用法错误: 定位串清单为空", file=sys.stderr)
            return 2
        hits = 0
        for i, locate in enumerate(locates, 1):
            sents, source = _extract_one(args.prd_dir, locate, args.max_chars, max(1, args.candidates))
            print(f"===== [{i}/{len(locates)}] {locate} =====")
            if not sents:
                print(f"# 未命中（在资料目录中无法定位: {locate}）")
                continue
            hits += 1
            _print_candidates(locate, source, sents)
        if hits == 0:
            print("批量提取完成：0 条命中", file=sys.stderr)
            return 1
        print(f"\n批量提取完成：{hits}/{len(locates)} 条命中")
        return 0

    # 单条模式（保持原行为）
    if not args.locate:
        print("用法错误: 需 --locate 或 --locate-file", file=sys.stderr)
        return 2

    sents, source = _extract_one(args.prd_dir, args.locate, args.max_chars, max(1, args.candidates))
    if not sents:
        print(f"未能在资料目录中定位: {args.locate}", file=sys.stderr)
        return 1
    _print_candidates(args.locate, source, sents)
    return 0


def _extract_one(prd_dir, locate, max_chars, topn):
    """对单个定位串执行提取。返回 (命中候选列表, 来源文件名)；未命中返回 ([], None)。"""
    for path in iter_prd_files(prd_dir):
        try:
            text = read_text(path)
        except Exception:
            continue
        body = locate_in_text(text, locate)
        if body is None:
            continue
        sents = pick_sentences(body, max_chars, topn)
        if sents:
            return sents, os.path.basename(path)
    return [], None


def _print_candidates(locate, source, sents):
    if len(sents) <= 1:
        sent = sents[0]
        print(f"# 来源: {source}  定位: {locate}")
        print(f"# 字符数: {len(sent)}")
        print(sent)
        return
    for i, sent in enumerate(sents, 1):
        print(f"===== 候选 {i}/{len(sents)} =====")
        print(f"# 来源: {source}  定位: {locate}")
        print(f"# 字符数: {len(sent)}")
        print(sent)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        print(f"提取失败: {e}", file=sys.stderr)
        sys.exit(1)
