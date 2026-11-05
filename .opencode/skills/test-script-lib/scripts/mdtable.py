"""test-script-lib/scripts/mdtable.py — 清单脚本共享的 Markdown 表格解析与基础工具（单一实现，2026-11-05 收敛；2026-11-05 迁入 test-script-lib skill）。

背景（复盘 2026-11-04/05）：verify_test_points.py、verify_test_cases.py、export_tables.py、
verify_traceability.py 各自维护一份语义相近但不完全相同的表格解析副本，是"契约散落、
漂移不可见"的主要来源。本模块为唯一实现，各脚本从 `../../test-script-lib/scripts` 导入，禁止再写本地副本。

注意：`norm_space_all`（TP/TC 清单校验口径：删除全部空白）与 `norm_ws_single`
（引文机验口径：空白规范化为单空格）是**两个既有口径**，不得混用，也不得互相"统一"。
2026-11-05 复盘收敛：引文机验统一升格为 `norm_quote`（空白单格化 + Markdown 表格
`\|` 转义还原 + 全/半角标点折叠）——表示法差异不再 FAIL；行号才是定位锚点，
摘录字符由 `verify_quotes.py --autofix` 按行号自愈回填。
"""
import hashlib
import re

TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gbk")

# 引文归一映射：两侧同时映射（原文件与摘录），字符内容差异不受影响，
# 仅"标点全/半角、引号形制、破折号形制"等表示法差异被折叠。
_QUOTE_CHAR_MAP = {
    "，": ",", "、": ",", "；": ";", "：": ":", "。": ".",
    "！": "!", "？": "?", "（": "(", "）": ")",
    "「": '"', "」": '"', "『": '"', "』": '"',
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "｜": "|", "—": "-", "–": "-", "～": "~",
}


def norm_quote(text):
    """引文机验归一口径（2026-11-05 起全线统一）：
    1) Markdown 表格内管道转义 `\\|` 还原为 `|`；
    2) 全/半角标点与引号形制折叠（双侧同射，不改变字符内容本身）；
    3) 空白统一为单空格。
    逗号点差、引号形制差、转义符差不再导致 FAIL；摘录正文（汉字/英文/数字）差异仍 FAIL，
    由 verify_quotes --autofix 按行号回读原文自愈。
    """
    s = (text or "").replace("\\|", "|")
    for src, dst in _QUOTE_CHAR_MAP.items():
        s = s.replace(src, dst)
    return re.sub(r"\s+", " ", s.strip())


def read_text(path):
    for enc in TEXT_ENCODINGS:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码: {path}")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_space_all(s):
    """TP/TC 清单校验口径：删除全部空白（含全角空格）。引号漂移必须能被抓到，不做引号归一。"""
    return re.sub(r"[\s　]+", "", s or "")


def norm_ws_single(text):
    """引文机验口径：统一空白为单空格（不规范化标点——标点差异即未命中）。"""
    return re.sub(r"\s+", " ", (text or "").strip())


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells):
    return all(re.fullmatch(r"[-: ]*", c) for c in cells)


def parse_md_table(text, keyword):
    """返回 (表头行, 数据行列表)。

    - keyword 非空：只取标题含 keyword 的 ## 章节下的第一张表（进入下一章节即结束，
      避免"命中章节必须位于文件末尾才生效"的 2026-11-04 缺陷回归）。
    - keyword 为空：取全文中**第一个 ## 章节之前**的主表（主表定位的唯一主契约）。
    """
    header, rows = None, []
    if keyword:
        in_sec = False
        for line in text.split("\n"):
            if line.startswith("##"):
                if in_sec:
                    break
                in_sec = keyword in line
                if in_sec:
                    header, rows = None, []
                continue
            if not in_sec:
                continue
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = _cells(s)
            if _is_separator(cells):
                continue
            if header is None:
                header = cells
                continue
            rows.append(cells)
        return header, rows

    # 主表：第一个 ## 之前（这与 # 一级标题行无关，跳过所有 # 行直到第一个 ##）
    for line in text.split("\n"):
        if line.startswith("##"):
            break
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = _cells(s)
        if _is_separator(cells):
            continue
        if header is None:
            header = cells
            continue
        rows.append(cells)
    return header, rows


def parse_first_table(text):
    """返回 (表头行, 数据行列表)——取文档中第一张表。

    兼容两种写法：
      A. 表在某个 ## 章节下 → 取该章节的第一张表（不会跟进后续章节）
      B. 表直接跟在 # 一级标题下（无 ## 章节）→ 取全文第一张表
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
        cells = _cells(s)
        if _is_separator(cells):
            continue
        if header is None:
            header = cells
            continue
        rows_all.append(cells)
    return header, rows_all
