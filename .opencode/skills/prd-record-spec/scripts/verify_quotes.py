#!/usr/bin/env python3
r"""verify_quotes.py — 引文逐字机验（溯源规范 V2：文件:行号 直引，见 SKILL.md）。

对引用表逐条验证：给定的「摘录原文 + 来源文件 + 行号」确实存在于原文件该行。
判定口径与 verify_requirement_baseline.py 一致（**误植即 FAIL**）：
  1. 比对双侧先经 test-script-lib/mdtable.py norm_quote 归一：空白单格化、Markdown 表格 `\|`
     转义还原、全/半角标点与引号形制折叠——表示法差异不算错；
  2. norm(quote) 命中行区间文本 → PASS；不命中 → FAIL，报告 failures 记录
     seq/file/lines/quote/error，交生成者按 extract_excerpt.py --by-line 输出重抄；
  3. 默认不回读原文、不回填、不回写、不计自愈，产物零改动。

--autofix 仅供维护者离线修复存量产物，机验管线 check.py 永不传该开关；
带开关时回填摘录会做 Markdown 表格转义，并由报告 artifact_changed 留痕。

这是机验引擎，必须保持零语义、确定性、可独立运行。

输入（二选一）：
  1. JSON 数组：[{"file": "...", "lines": "596", "quote": "..."}]
  2. Markdown 管道表：表头须含三列（列序即校验契约）：| 来源文件 | 行号 | 原话/摘录 |

行号写法：`596`（单行）或 `596-598`（行区间，摘录须在区间连接文本中命中）。

用法（<SKILLS_ROOT> 默认 ~/.config/opencode/skills，<WORKSPACE_ROOT> 由派发单注入；
      命令发出前占位符须替换为实际绝对路径）：
  python3 <SKILLS_ROOT>/prd-record-spec/scripts/verify_quotes.py \
    <WORKSPACE_ROOT>/file/session-XXXXXX/output/tp/test-point.md \
    --input-dir <WORKSPACE_ROOT>/file/project-docs
  加 --context 可在输出中打印每条引用的上下文行（供质检抽查断章风险）。
  加 --extract-from 可直接从 TP/TC 等清单文件抽取引用（语法 `文件名:L行号或区间「摘录」`），
  免于单独维护引用表——单一来源是清单文件本身。
  加 --autofix 且 --report 才允许离线回填并回写（回写前转义裸 |，禁用于机验管线）。

退出码：0 = 全部命中；1 = 存在未命中；2 = 用法错误
"""
import argparse
import hashlib
import json
import os
import re
import sys

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "test-script-lib", "scripts"))
from mdtable import norm_quote as norm  # noqa: E402  引文归一唯一实现（2026-11-05 收敛）

# 从任意 Markdown 清单抽取引用的语法：`<文件名>:L<行号或区间>「<摘录>」`
# 文件名字符类 = 中英数字 + 下划线/点/连字符（不含空格与全角标点；含空格的文件名不适用于本语法）
CITE_RE = re.compile(
    r"([A-Za-z0-9_\-./\u4e00-\u9fff]+?\.(?:md|markdown|txt|csv)):L(\d+(?:\s*[-~]\s*\d+)?)\s*「([^」]{1,300})」"
)


def _skeleton_index_map(text):
    """骨架 + 每个骨架字符在原文中的位置（用于自愈回读的原文区间定位）。"""
    kept, idx = [], []
    for i, ch in enumerate(text):
        if ch.isspace() or (not ch.isalnum() and not ("\u4e00" <= ch <= "\u9fff")):
            continue
        kept.append(ch)
        idx.append(i)
    return "".join(kept), idx


def recover_slice(region, needle):
    """按骨架在 region 中定位 needle 对应的原文片段（含原空白/标点）。命中失败返回 None。

    判定（零语义、确定性）：
    - needle 骨架须以**有序子序列**方式完整出现在 region 骨架中（允许书写时漏字符）；
    - 缺口上限 = max(3, needle 骨架长/4)——缺口过大视为"远距拼接"的假命中，拒绝；
    - 回读片段与 needle 归一后无实质差异时不返回（无须自愈）。
    """
    reg_skel, reg_idx = _skeleton_index_map(region)
    nee_skel, _ = _skeleton_index_map(needle)
    if len(nee_skel) < 3:
        return None
    pos = 0
    start = end = None
    for i, ch in enumerate(reg_skel):
        if pos < len(nee_skel) and ch == nee_skel[pos]:
            if pos == 0:
                start = i
            pos += 1
            end = i
    if pos != len(nee_skel) or start is None:
        return None
    gap = (end - start + 1) - len(nee_skel)
    if gap > max(3, len(nee_skel) // 4):
        return None
    recovered = region[reg_idx[start]:reg_idx[end] + 1]
    if norm(recovered) == norm(needle):
        return None
    return recovered


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
    """管道表；只解析表头符合列序契约（| 来源文件 | 行号 | 原话摘录 |）的表格。

    2026-11-04 修复：此前逐行扫描会把清单主表/覆盖表/语义表等所有管道表
    （含表头行）误当引用条目，导致混排报告无法直接机验。现按整表分块处理：
    表头首列须为 来源文件/文件/source 且第二列为 行号，不合契约的表整块跳过。
    """
    out = []
    seq = 0
    block = []

    def header_ok(cells):
        if len(cells) < 3:
            return False
        first = re.sub(r"[\s　]+", "", cells[0])
        second = re.sub(r"[\s　]+", "", cells[1])
        return first in ("来源文件", "文件", "source") and second == "行号"

    def flush():
        nonlocal seq
        if not block:
            return
        head = [c.strip() for c in block[0].strip().strip("|").split("|")]
        if header_ok(head):
            for line in block[1:]:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if all(re.fullmatch(r"[-: ]*", c) for c in cells):
                    continue  # 分隔行
                if len(cells) < 3:
                    continue
                seq += 1
                out.append({"seq": seq, "file": cells[0], "lines": cells[1], "quote": cells[2]})
        block.clear()

    for line in text.splitlines():
        if line.strip().startswith("|"):
            block.append(line)
        else:
            flush()
    flush()
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
    if stripped.startswith("{"):
        # 2026-11-08 fail-loud 补丁：对象 JSON（如需求基线整文件）此前会静默落到
        # parse_md_quotes 返回空列表 → 0 条假 PASS。显式报错并指引正确工具，
        # 杜绝"机验绿但什么都没验"。
        raise ValueError(
            "输入是 JSON 对象而非引用表：对需求基线请改用 verify_requirement_baseline.py "
            "（其 evidence 逐字裁决内嵌）；如确需对引用条目机验，请抽取为 JSON 数组 "
            '[{"file","lines","quote"}, …] 或引用语法的 Markdown 文件后再传入'
        )
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


def index_input_files(input_dirs):
    """资料目录下的实际文件清单——文件名消歧的候选集。

    input_dirs 可传多个（资料目录 + 会话内转换区），逐目录 walk 合并，
    返回 [(rel, 该目录)]；同一 rel 在多个目录重复时由 resolve_file 判歧义。
    """
    files = []
    for input_dir in input_dirs:
        for root, _dirs, names in os.walk(input_dir):
            for name in names:
                rel = os.path.relpath(os.path.join(root, name), input_dir)
                files.append((rel.replace(os.sep, "/"), input_dir))
    return files


def resolve_file(token, input_dirs, index):
    """把引用里的文件 token 解析为资料目录下的真实文件（多目录版）。

    解析顺序：① token 在任一目录下精确命中登记 rel（唯一 → 放行）；
    ② 散文前缀黏连按「token 以某登记文件名为后缀」消歧——取最长命中名，唯一才放行；
    ③ 同 rel 跨目录重复、或候选多条 → 歧义交人裁决；无命中 → 文件不存在。
    返回 (rel | None, 命中目录 | None, 说明)。
    """
    exact = [(rel, d) for rel, d in index if rel == token]
    if len(exact) == 1:
        return exact[0][0], exact[0][1], ""
    if len(exact) > 1:
        return None, None, f"登记 rel 跨目录同名歧义: {token} → {sorted(d for _r, d in exact)}"
    token_base = token.replace("\\", "/").rsplit("/", 1)[-1]
    by_base = {}
    for rel, d in index:
        base = rel.rsplit("/", 1)[-1]
        if base and token_base.endswith(base):
            by_base.setdefault((base, d), []).append((rel, d))
    if not by_base:
        return None, None, f"资料文件不存在: {token}"
    longest = max(len(base) for base, _d in by_base)
    candidates = [cand for (base, _d), rels in by_base.items()
                  if len(base) == longest for cand in rels]
    if len(candidates) > 1:
        return None, None, f"文件名消歧不唯一: {token} → {' / '.join(f'{d}/{r}' for r, d in sorted(candidates))}"
    rel, d = candidates[0]
    return rel, d, "散文前缀黏连，已按资料目录实际文件解析"


def locate(index, rel, input_dir):
    """按 resolve 出的 (rel, 目录) 取绝对路径（未命中目录时回落首个资料目录）。"""
    for registered, d in index:
        if registered == rel and (d == input_dir or input_dir is None):
            return os.path.join(d, registered)
    return os.path.join(input_dir, rel) if input_dir else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quotes", help="引用表（JSON 数组或 Markdown 管道表）或清单文件（配合 --extract-from）")
    parser.add_argument("--input-dir", required=True, nargs="+", help="资料目录（可传多个：文本资料目录 + 会话转换区，合并 解析/直引）")
    parser.add_argument("--context", action="store_true", help="输出每条引用的上下文行")
    parser.add_argument("--extract-from", action="store_true", help="从清单文件按 引用语法 直抽取引，不读表格/JSON")
    parser.add_argument("--autofix", action="store_true", help="离线修复专用：行号正确且骨架命中时回读原文回填并回写；须与 --report 同用，机验管线禁用")
    parser.add_argument("--report", default="", help="机验结果写 JSON 报告（含清单指纹），供质检按工件采信")
    args = parser.parse_args()

    if args.autofix and not args.report:
        print("用法错误: --autofix 为离线修复模式，必须同时提供 --report 留痕", file=sys.stderr)
        return 2
    if not os.path.isfile(args.quotes):
        print(f"用法错误: 引用表不存在 {args.quotes}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.input_dir[0]):
        print(f"用法错误: 资料目录不存在 {args.input_dir[0]}", file=sys.stderr)
        return 2
    source_digest = None
    try:
        source_digest = hashlib.sha256(open(args.quotes, "rb").read()).hexdigest()
    except OSError:
        pass

    try:
        quotes = load_quotes(args.quotes, args.extract_from)
    except ValueError as exc:
        print(f"[FAIL] 引用表格式错误: {exc}", file=sys.stderr)
        return 2
    if not quotes:
        print("引用表为空：无条目可验", file=sys.stderr)
        return 2

    cache = {}
    index = index_input_files(args.input_dir)
    passed = failed = auto_fixed = 0
    artifact_changed = False
    _report_failures = []
    _auto_fixes = []
    _resolved = []

    def escape_md_cell(text):
        """回填文本写入 Markdown 表格单元格前转义裸 | 并压平换行，避免切断表格行。"""
        return re.sub(r"(?<!\\)\|", r"\|", text.replace("\r", " ").replace("\n", " "))

    def try_writeback(path, old, new):
        """把回填后的摘录原位写回产物（仅离线修复；旧摘录唯一且产物不在任一资料目录下）。"""
        nonlocal artifact_changed
        note = ""
        try:
            path_a = os.path.abspath(path)
            if any(path_a.startswith(os.path.abspath(d) + os.sep) for d in args.input_dir):
                note = "skip: 源文件位于资料目录（原资料禁止修改）"
                return note
            with open(path_a, encoding="utf-8-sig") as stream:
                content = stream.read()
            count = content.count(old)
            if count != 1:
                note = f"skip: 旧摘录在源文件中出现 {count} 次，不唯一"
            else:
                escaped = escape_md_cell(new)
                replaced = content.replace(old, escaped)
                before_line = next((ln for ln in content.splitlines() if old in ln), "")
                after_line = next((ln for ln in replaced.splitlines() if escaped in ln), "")
                if before_line.startswith("|") and not (
                        after_line.startswith("|") and after_line.rstrip().endswith("|")):
                    note = "skip: 替换后表格行形态被破坏，拒绝回写"
                    return note
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(replaced)
                note = "written(escaped)" if escaped != new else "written"
                artifact_changed = True
        except OSError as exc:
            note = f"skip: 回写失败 ({exc})"
        return note

    for q in quotes:
        rel_raw = q["file"]
        rel, hit_dir, resolve_note = resolve_file(rel_raw, args.input_dir, index)
        if rel is None:
            print(f"FAIL 引用#{q['seq']} {rel_raw}:{q['lines']} — {resolve_note}")
            _report_failures.append({"seq": q["seq"], "file": rel_raw, "lines": q["lines"], "quote": q["quote"], "error": resolve_note})
            failed += 1
            continue
        if resolve_note:
            print(f"[RESOLVED] 引用#{q['seq']} {rel_raw} → {rel}（{resolve_note}）")
            _resolved.append({"seq": q["seq"], "raw": rel_raw, "resolved": rel})
        source_path = os.path.join(hit_dir, rel)
        try:
            line_no = int(re.sub(r"\D", "", q["lines"][:8]) or 0)
        except ValueError:
            line_no = 0
        context = ""
        if line_no:
            if os.path.isfile(source_path):
                lines = lookup(source_path, cache)
                lo, hi = max(1, line_no - 1), min(len(lines), line_no + 1)
                context = " ⏐ ".join(ln for ln in lines[lo - 1:hi])

        try:
            lines = lookup(source_path, cache)
            start, end = resolve_lines(q["lines"], len(lines))
            if start == end and args.context is not None and context:
                lo, hi = max(1, start - 1), min(len(lines), start + 1)
                context = " ⏐ ".join(lines[lo - 1:hi])
            elif args.context:
                context = " ⏐ ".join(lines[start - 1:end][:3])
            region = "\n".join(lines[start - 1:end])
            haystack = norm(region)
            needle = norm(q["quote"])
            ok = bool(needle) and needle in haystack
            if not ok and args.autofix:
                # 离线修复专用：行号正确 + 内容骨架命中 → 回读原文回填摘录并转义回写
                # 默认机验路径不进入本分支，误植一律由下方 FAIL 分支裁决。
                fixed = recover_slice(region, q["quote"])
                if fixed and norm(fixed) in haystack:
                    old_quote, tag_auto = q["quote"], fixed[:24] + ("…" if len(fixed) > 24 else "")
                    note = try_writeback(args.quotes, old_quote, fixed)
                    q["quote"] = fixed
                    auto_fixed += 1
                    _auto_fixes.append({
                        "seq": q["seq"], "file": rel, "lines": q["lines"],
                        "old_quote": old_quote, "quote": fixed,
                        "new_quote": fixed, "recovered_prefix": tag_auto,
                        "writeback": note,
                    })
                    print(f"[AUTOFIX] 引用#{q['seq']} {rel}:{q['lines']} 摘录按行号回填（离线模式，回写: {note}）")
                    ok = True
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"FAIL 引用#{q['seq']} {rel}:{q['lines']} — {exc}")
            _report_failures.append({"seq": q["seq"], "file": rel, "lines": q["lines"], "quote": q["quote"], "error": str(exc)})
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
            _report_failures.append({"seq": q["seq"], "file": rel, "lines": q["lines"], "quote": q["quote"], "error": "未在指定行命中"})
            failed += 1

    print(f"========== 结论: PASS={passed} FAIL={failed} 离线自愈={auto_fixed} 总={passed + failed} ==========")

    # 自愈回写会改动被检产物 → 指纹前后不一致，必须透明可见（否则报告指纹与磁盘对不上，
    # 下游会误判"机验后主件被改动"）。产物已变更时提示重跑全量。
    source_digest_after = source_digest
    if artifact_changed:
        try:
            source_digest_after = hashlib.sha256(open(args.quotes, "rb").read()).hexdigest()
        except OSError:
            source_digest_after = None
        print(
            f"[产物已变更] 自愈回写了 {os.path.abspath(args.quotes)}，"
            f"主件指纹已变化（{source_digest} → {source_digest_after}），需重跑全量机验"
        )

    if args.report:
        report = {
            "schema_version": 1,
            "kind": "quote-verification",
            "source": os.path.abspath(args.quotes),
            "source_sha256": source_digest,
            "source_sha256_after": source_digest_after,
            "artifact_changed": artifact_changed,
            "input_dir": os.path.abspath(args.input_dir[0]),
            "input_dirs": [os.path.abspath(d) for d in args.input_dir],
            "extract_from": bool(args.extract_from),
            "autofix": bool(args.autofix),
            "total": passed + failed,
            "passed": passed,
            "failed": failed,
            "auto_fixed": auto_fixed,
            "auto_fixes": _auto_fixes,
            "resolved_files": _resolved,
            "failures": _report_failures,
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"[REPORT] {args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
