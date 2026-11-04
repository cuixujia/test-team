#!/usr/bin/env python3
"""verify_quotes.py — 引文逐字机验（溯源规范 V2：文件:行号 直引，见 SKILL.md）。

对引用表逐条验证：给定的「摘录原文 + 来源文件 + 行号」确实存在于原文件该行（空白规范化后逐字一致）。
这是机验引擎，必须保持零语义、确定性、可独立运行。

输入（二选一）：
  1. JSON 数组：[{"file": "...", "lines": "596", "quote": "..."}]
  2. Markdown 管道表：表头须含三列（列序即校验契约）：| 来源文件 | 行号 | 原话/摘录 |

行号写法：`596`（单行）或 `596-598`（行区间，摘录须在区间连接文本中命中）。

用法：
  python3 .opencode/skills/prd-record-spec/scripts/verify_quotes.py <引用表> --input-dir <资料目录>
  加 --context 可在输出中打印每条引用的上下文行（供质检抽查断章风险）。
  加 --extract-from 可直接从 TP/TC 等清单文件抽取引用（语法 `文件名:L行号或区间「摘录」`），
  免于单独维护引用表——单一来源是清单文件本身。

退出码：0 = 全部命中；1 = 存在未命中；2 = 用法错误
"""
import argparse
import json
import os
import re
import sys

# 从任意 Markdown 清单抽取引用的语法：`<文件名>:L<行号或区间>「<摘录>」`
# 文件名字符类 = 中英数字 + 下划线/点/连字符（不含空格与全角标点；含空格的文件名不适用于本语法）
CITE_RE = re.compile(
    r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L(\d+(?:\s*[-~]\s*\d+)?)\s*「([^」]{1,300})」"
)

import argparse
import json
import os
import re
import sys


def norm(text):
    """规范化：统一空白为单空格（不规范化标点——标点差异即未命中）。"""
    return re.sub(r"\s+", " ", text.strip())


ENCODINGS = ("utf-8-sig", "utf-8", "gbk")


def read_file(path):
    last_err = None
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc) as stream:
                return stream.read().splitlines()
        except (UnicodeDecodeError, LookupError) as exc:
            last_err = exc
    raise RuntimeError(f"无法解码 {path}: {last_err}")


def parse_json_quotes(text):
    entries = json.loads(text)
    if not isinstance(entries, list):
        raise ValueError("JSON 引用表须为数组")
    out = []
    for i, item in enumerate(entries, 1):
        out.append({
            "seq": i,
            "file": str(item.get("file", "")),
            "lines": str(item.get("lines", "")),
            "quote": str(item.get("quote") or item.get("excerpt") or ""),
        })
    return out


def parse_md_quotes(text):
    """管道表；列序契约：| 来源文件 | 行号 | 原话摘录 |。"""
    out = []
    seq = 0
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]*", c) for c in cells):
            continue
        header_keys = {"来源文件", "文件", "source"}
        if cells and any(h in cells[0] for h in header_keys) and "行号" in " ".join(cells):
            continue  # 表头
        if len(cells) < 3:
            continue
        seq += 1
        out.append({"seq": seq, "file": cells[0], "lines": cells[1], "quote": cells[2]})
    return out


def load_quotes(path, extract_from=False):
    with open(path, encoding="utf-8-sig") as stream:
        text = stream.read()
    if extract_from:
        out = []
        for seq, m in enumerate(CITE_RE.finditer(text), 1):
            out.append({"seq": seq, "file": m.group(1).strip(), "lines": m.group(2).strip(), "quote": m.group(3).strip()})
        return out
    stripped = text.lstrip()
    if stripped.startswith("["):
        return parse_json_quotes(text)
    return parse_md_quotes(text)


def resolve_lines(spec, total):
    m = re.fullmatch(r"(\d+)(?:\s*[-~]\s*(\d+))?", spec.strip())
    if not m:
        raise ValueError(f"行号写法无法解析: {spec!r}")
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    if start < 1 or end < start or end > total:
        raise ValueError(f"行号越界或区间倒置: {spec!r}（文件共 {total} 行）")
    return start, end


def lookup(path, files_cache):
    if path not in files_cache:
        files_cache[path] = read_file(path)
    return files_cache[path]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quotes", help="引用表（JSON 数组或 Markdown 管道表）或清单文件（配合 --extract-from）")
    parser.add_argument("--input-dir", required=True, help="资料目录（引用表中的文件相对此目录）")
    parser.add_argument("--context", action="store_true", help="输出每条引用的上下文行")
    parser.add_argument("--extract-from", action="store_true", help="从清单文件按 引用语法 直抽取引，不读表格/JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.quotes):
        print(f"用法错误: 引用表不存在 {args.quotes}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.input_dir):
        print(f"用法错误: 资料目录不存在 {args.input_dir}", file=sys.stderr)
        return 2

    quotes = load_quotes(args.quotes, args.extract_from)
    if not quotes:
        print("引用表为空：无条目可验", file=sys.stderr)
        return 2

    cache = {}
    passed = failed = 0
    for q in quotes:
        rel = q["file"]
        try:
            line_no = int(re.sub(r"\D", "", q["lines"][:8]) or 0)
        except ValueError:
            line_no = 0
        context = ""
        if line_no:
            candidate = os.path.join(args.input_dir, rel)
            if os.path.isfile(candidate):
                lines = lookup(candidate, cache)
                lo, hi = max(1, line_no - 1), min(len(lines), line_no + 1)
                context = " ⏐ ".join(ln for ln in lines[lo - 1:hi])

        try:
            lines = lookup(os.path.join(args.input_dir, rel), cache)
            start, end = resolve_lines(q["lines"], len(lines))
            if start == end and args.context is not None and context:
                lo, hi = max(1, start - 1), min(len(lines), start + 1)
                context = " ⏐ ".join(lines[lo - 1:hi])
            elif args.context:
                context = " ⏐ ".join(lines[start - 1:end][:3])
            haystack = norm("\n".join(lines[start - 1:end]))
            needle = norm(q["quote"])
            ok = bool(needle) and needle in haystack
        except (RuntimeError, ValueError) as exc:
            print(f"FAIL 引用#{q['seq']} {rel}:{q['lines']} — {exc}")
            failed += 1
            continue

        tag = f"引用#{q['seq']}"
        snippet = q["quote"][:24] + ("…" if len(q["quote"]) > 24 else "")
        if ok:
            passed += 1
            if args.context and context:
                print(f"PASS {tag} {rel}:{q['lines']} 「{snippet}」 上下文: {context}")
            else:
                print(f"PASS {tag} {rel}:{q['lines']}")
        else:
            print(f"FAIL {tag} {rel}:{q['lines']} 「{snippet}」未在指定行命中")
            failed += 1

    print(f"========== 结论: PASS={passed} FAIL={failed} 总={passed + failed} ==========")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
