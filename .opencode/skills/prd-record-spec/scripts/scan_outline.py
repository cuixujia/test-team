#!/usr/bin/env python3
"""scan_outline.py — 资料轻扫描（溯源规范 V2：文本格式直引，见 SKILL.md）。

对资料目录中的文本文件（.md/.markdown/.txt/.csv）输出：
  1. 标题树（含行号，定位引用用）；
  2. 规则编号索引（BR/GOAL/EXCL/NFR/FUNC/MOD/REQ/VER 等带编号 token → 首个行号）。

轻扫描只做机械定位，不做深度质检；输出行数受控，供经理在选定范围前使用。
二进制格式（.docx/.pdf/图片等）不在本脚本处理范围——按 SKILL.md 入库约定，
非文本件提示用户替换为文本格式后方可入库，流程自动 fail-fast，无遗留分支。

用法（仓库根目录起，相对路径单命令）：
  python3 .opencode/skills/prd-record-spec/scripts/scan_outline.py --input-dir <资料目录>
  可加 --output <路径> 落盘；--ids-only 仅输出规则编号索引（最小量输出）。

退出码：0 = 扫描成功；1 = 扫描部分失败（无法解析的文件）；2 = 用法错误
"""
import argparse
import hashlib
import os
import re
import sys


TEXT_EXTS = (".md", ".markdown", ".txt", ".csv")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
NUMBERED_RE = re.compile(r"^(\d+(?:\.\d+)*)(?:[、.． ]+)(.{1,80})$")
ID_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:FUNC|BR|GOAL|EXCL|NFR|MOD|REQ|VER|SRS|BF|CL)[-\d][0-9A-Za-z\-]*|(?:F|E-EX)\d{1,3}\b"
)


def read_lines(path):
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, encoding=enc) as stream:
                return stream.read().splitlines()
        except (UnicodeDecodeError, LookupError) as exc:
            last_err = exc
    raise RuntimeError(f"无法解码: {last_err}")


def scan_file(path, rel):
    lines = read_lines(path)
    headings = []  # (line, depth, title)
    id_map = {}    # token -> first line
    for no, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        m = HEADING_RE.match(line)
        if m:
            headings.append((no, len(m.group(1)), m.group(2).strip()))
        else:
            m2 = NUMBERED_RE.match(line)
            # 阈值 ≤60 字：长编号句多为正文列表项，避免污染标题树
            # （extract_excerpt.py 定位逻辑不受此影响）。
            if m2 and len(line) <= 60:
                depth = m2.group(1).count(".") + 1
                headings.append((no, depth, line))
        for token in ID_TOKEN_RE.findall(line):
            if token not in id_map:
                id_map[token] = no
    with open(path, "rb") as stream:  # 指纹按 python 侧字节为准（与机验管线同侧）
        digest = hashlib.sha256(stream.read()).hexdigest()
    return {"rel": rel, "lines_total": len(lines), "headings": headings, "id_map": id_map, "sha256": digest}


def render(sources, ids_only):
    out = []
    for s in sources:
        out.append(f"# {s['rel']}（{s['lines_total']} 行）")
        if not ids_only:
            for no, depth, title in s["headings"]:
                out.append(f"  {no}: {'  ' * (depth - 1)}{title}")
        out.append("## 规则编号索引")
        for token in sorted(s["id_map"]):
            out.append(f"  {token} @ L{s['id_map'][token]}")
        out.append("")
    return "\n".join(out)


def render_manifest(sources):
    """指纹清单（python 侧 sha256，与机验管线同口径）。
    产物同时供人工检查与需求基线 input_files 字段复制。"""
    out = ["# files-manifest（V2 指纹清单）", "", "| 文件 | sha256 |", "|---|---|"]
    for s in sources:
        out.append(f"| {s['rel']} | {s['sha256']} |")
    out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, help="资料目录")
    parser.add_argument("--output", default="", help="结果落盘路径（默认 stdout）")
    parser.add_argument("--ids-only", action="store_true", help="仅输出规则编号索引")
    parser.add_argument("--manifest", default="", help="指纹清单落盘路径（python 侧 sha256；与机验同口径）")
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"用法错误: 资料目录不存在 {args.input_dir}", file=sys.stderr)
        return 2

    sources, errors = [], []
    for directory, dirs, files in os.walk(args.input_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or not name.lower().endswith(TEXT_EXTS):
                continue
            path = os.path.join(directory, name)
            rel = os.path.relpath(path, args.input_dir).replace(os.sep, "/")
            try:
                sources.append(scan_file(path, rel))
            except RuntimeError as exc:
                errors.append(f"[WARN] 无法解析 {rel}: {exc}")

    sources.sort(key=lambda s: s["rel"])
    text = render(sources, args.ids_only)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
    if args.manifest:
        os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)
        with open(args.manifest, "w", encoding="utf-8") as stream:
            stream.write(render_manifest(sources) + "\n")
    print(text)
    for err in errors:
        print(err, file=sys.stderr)
    print(f"[SCAN] 文件数: {len(sources)}  规则编号数: {sum(len(s['id_map']) for s in sources)}")
    if args.manifest:
        print(f"[MANIFEST] {args.manifest}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
