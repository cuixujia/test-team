#!/usr/bin/env python3
"""convert_office.py — Office 材料入库前转换（唯一口径，见 SKILL.md）。

将资料目录中的 .docx/.xlsx 转为同名 .md，落到 --output-dir（如
<WORKSPACE_ROOT>/file/session-XXXXXX/user-input-converted/）。转换是确定性映射，不做渲染猜测：

docx（zip 内 word/document.xml，OOXML）：
- 标题样式/大纲级别 → `#` 层级；普通段落 → 原样一段（文字逐字保留）
- 表格 w:tbl → md 表格；合并单元格只留左上值，占比格留痕注记
- 列表段落 → md 列表（统一 `- ` 前缀）
- 修订痕迹按"接受修订后"的定稿取字：w:ins 合并、w:del 剔除
- 批注剔除；图片/绘图/公式落留痕注记（不静默丢）

xlsx（zip 内 xl/worksheets/*.xml + xl/sharedStrings.xml）：
- 一工作簿一 md；Sheet 名 → `##` 标题；首行作表头，每行数据 = md 表格一行
- 公式取缓存计算值（`<v>`），公式本身进丢弃清单；日期/数字按显示值转文本
- 合并单元格只留左上值 + 留痕注记；空 Sheet 落"（无数据）"

质量自校验（不通过不产出 md）：
- 兼容性验收：产出的 md 表格必须能被同目录 mdtable.py 解析，否则不落盘

幂等：--output-dir 中同名 md 已存在 → 跳过（同一会话重复运行不重复转）。
md 文件头登记来源注记（原件相对路径 + sha256）与转换丢弃清单。

用法：
  python3 <SKILLS_ROOT>/test-script-lib/scripts/convert_office.py \
    --input-dir <资料目录绝对路径> --output-dir <WORKSPACE_ROOT>/file/session-XXXXXX/user-input-converted/

退出码：0 = 全部处理完毕（含幂等跳过）；1 = 用法错误；2 = 有文件转换失败。
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

W = lambda tag: "{%s}%s" % (W_NS, tag)
S = lambda tag: "{%s}%s" % (S_NS, tag)

HEADING_STYLE_RE = re.compile(r"Heading\s*([1-9])$", re.IGNORECASE)
OFFICE_EXTS = (".docx", ".xlsx")


class ConversionError(Exception):
    pass


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def sha256_file(path):
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def md_escape_cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------------------
# docx → md
# ---------------------------------------------------------------------------

def _load_styles(xml_bytes):
    """styles.xml → {style_id: 显示名}（pStyle 存的是 id，比对 Heading 需要显示名）。"""
    styles = {}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return styles
    for st in root.findall(W("style")):
        style_id = st.get(W("styleId"))
        name_el = st.find(W("name"))
        if style_id and name_el is not None:
            styles[style_id] = name_el.get(W("val"), style_id)
    return styles


def _pPr(p_el):
    pPr = p_el.find(W("pPr"))
    return pPr


def _heading_level(p_el, styles):
    """标题级别：pStyle（显示名匹配 HeadingN）优先，其次 outlineLvl。"""
    pPr = _pPr(p_el)
    if pPr is None:
        return None
    val_el = pPr.find(W("pStyle"))
    if val_el is not None:
        style_id = val_el.get(W("val"))
        display = styles.get(style_id, style_id) if style_id else None
        m = HEADING_STYLE_RE.match(display or "")
        if m:
            return int(m.group(1))
    lvl_el = pPr.find(W("outlineLvl"))
    if lvl_el is not None:
        val = lvl_el.get(W("val"))
        if val is not None and val.isdigit() and int(val) <= 8:
            return int(val) + 1
    return None


def _is_list(p_el):
    pPr = _pPr(p_el)
    return pPr is not None and pPr.find(W("numPr")) is not None


def _deleted_ids(root):
    """id 集合：w:del / moveFrom 容器内的全部节点（定稿口径下剔除）。"""
    ids = set()
    for node in root.iter():
        if local_name(node.tag) in ("del", "moveFrom"):
            for sub in node.iter():
                ids.add(id(sub))
    return ids


def _final_text(p_el, deleted_ids):
    """定稿取字：w:del/moveFrom 容器内全部剔除，其余 w:t 逐字拼接。"""
    chars = []
    for node in p_el.iter():
        if id(node) in deleted_ids:
            continue
        if local_name(node.tag) == "t" and node.text:
            chars.append(node.text)
    return "".join(chars)


def _drawing_note(p_el):
    """段落内图片/绘图/公式 → 留痕注记标签（计入丢弃清单）。"""
    found = []
    if p_el.find(f".//{W('oMath')}") is not None or \
       p_el.find(f".//{W('oMathPara')}") is not None:
        found.append("公式")
    for name in ("drawing", "pict", "object"):
        if p_el.find(f".//{W(name)}") is not None:
            found.append("图片")
            break
    return found


def _comment_ids(p_el):
    """段落内批注 id 集合（按 commentRangeStart 的 w:id 去重，一处批注计一次）。"""
    ids = set()
    for node in p_el.iter(W("commentRangeStart")):
        wid = node.get(W("id"))
        if wid:
            ids.add(wid)
    return ids


def _decode_table(tbl_el, deleted_ids):
    """w:tbl → (行文本列表, 合并留痕行)。合并单元格只留左上值。"""
    rows = []
    notes = []
    for r_idx, tr in enumerate(tbl_el.findall(W("tr")), start=1):
        row = []
        for c_idx, tc in enumerate(tr.findall(W("tc")), start=1):
            cell_text = " ".join(
                t for t in (_final_text(p, deleted_ids) for p in tc.findall(W("p"))) if t
            ).strip()
            tc_pr = tc.find(W("tcPr"))
            merged = False
            if tc_pr is not None:
                vm = tc_pr.find(W("vMerge"))
                if vm is not None and (vm.get(W("val")) or "continue") == "continue":
                    merged = True
            if merged:
                notes.append("表格 %d 行 %d 列：合并单元格占位，仅保留左上值" % (r_idx, c_idx))
                cell_text = "[留痕:合并单元格]"
            row.append(cell_text)
        rows.append(row)
    return rows, notes


def convert_docx(path):
    """docx → (md 行列表, 丢弃/留痕清单)。内容零丢失超出定稿口径时抛错。"""
    with zipfile.ZipFile(path) as zf:
        doc = zf.read("word/document.xml")
        names = zf.namelist()
        styles = _load_styles(zf.read("word/styles.xml")) if "word/styles.xml" in names else {}
    root = ET.fromstring(doc)
    deleted_ids = _deleted_ids(root)
    body = root.find(W("body"))
    if body is None:
        body = root

    lines = []
    drop_lines = []
    comment_ids = set()
    for child in body:
        name = local_name(child.tag)
        if name == "p":
            comment_ids |= _comment_ids(child)
            text = _final_text(child, deleted_ids)
            level = _heading_level(child, styles)
            if level:
                if text:
                    lines.append("#" * level + " " + text)
                else:
                    drop_lines.append("标题段落无文字，未产出")
            elif text:
                lines.append(("- " if _is_list(child) else "") + text)
            drawings = _drawing_note(child)
            for kind in drawings:
                lines.append("<!-- [转换留痕] 此处原文有%s（未转换） -->" % kind)
        elif name == "tbl":
            lines.append("")
            rows, notes = _decode_table(child, deleted_ids)
            drop_lines.extend(notes)
            if rows:
                width = max(len(r) for r in rows)
                norm = [r + [""] * (width - len(r)) for r in rows]
                lines.append("| " + " | ".join(md_escape_cell(c) for c in norm[0]) + " |")
                lines.append("|" + "---|" * width)
                for r in norm[1:]:
                    lines.append("| " + " | ".join(md_escape_cell(c) for c in r) + " |")
                lines.append("")
        elif name in ("sectPr", "bookmarkStart", "bookmarkEnd", "proofErr", "sdt"):
            if name == "sdt":
                # 结构化文档标签（内容控件）：展开其内部段落
                for inner in child.iter(W("p")):
                    t = _final_text(inner, deleted_ids)
                    if t:
                        lvl = _heading_level(inner, styles)
                        lines.append(("#" * lvl + " " + t) if lvl else t)
            continue
    if comment_ids:
        drop_lines.append("批注剔除 %d 处" % len(comment_ids))
    ins_nodes = len([n for n in root.iter(W("ins"))])
    del_nodes = len([n for n in root.iter() if local_name(n.tag) == "del"])
    if ins_nodes:
        drop_lines.append("修订合并（接受后文本）%s 处" % ins_nodes)
    if del_nodes:
        drop_lines.append("修订删除（已剔除文本）%s 处" % del_nodes)
    return lines, drop_lines


# ---------------------------------------------------------------------------
# xlsx → md
# ---------------------------------------------------------------------------

_COL_RE = re.compile(r"([A-Z]+)")


def _col_index(ref):
    letters = _COL_RE.match(ref).group(1)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _shared_strings(zf):
    try:
        sst_xml = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(sst_xml)
    return ["".join(t.text or "" for t in si.iter(S("t"))) for si in root.findall(S("si"))]


_DATE_FMT_IDS = {14, 15, 16, 17, 22, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 45, 46, 47,
                 50, 51, 52, 53, 55, 56, 57, 58}
_EPOCH = date(1899, 12, 30)


def _numfmt_map(zf):
    """styles.xml numFmt → {style_id: fmt_id}（只认内置日期/时间格式 id，最小实现）。"""
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except (KeyError, ET.ParseError):
        return {}
    custom_fmts = {}
    for nf in root.iter(S("numFmt")):
        try:
            code = nf.get("formatCode", "")
            custom_fmts[nf.get("numFmtId")] = code
        except (TypeError, ValueError):
            continue
    cell_fmts = {}
    for xfs in root.iter(S("cellXfs")):
        for idx, xf in enumerate(xfs.findall(S("xf"))):
            style_id = xf.get("numFmtId")
            if not style_id:
                continue
            code = custom_fmts.get(style_id, "")
            body = code.replace("\\", "").replace('"', "")
            try:
                builtin = int(style_id)
            except ValueError:
                builtin = None
            # 内置日期/时间 id 直接认；自定义格式码按字母特征认（最小实现）
            if (builtin is not None and builtin in _DATE_FMT_IDS) or \
               re.search(r"[ymdhs]", body, re.IGNORECASE):
                cell_fmts[idx] = ("B" if (builtin is not None and builtin in _DATE_FMT_IDS) else "C",
                                  builtin if builtin is not None else body)
    return cell_fmts


def _serial_to_display(v_text, want_time_only):
    """Excel 日期序列号 → 显示文本（1900 日期系；≤0 原样）。"""
    try:
        serial = float(v_text)
    except ValueError:
        return v_text
    if serial <= 0 or serial > 100000:
        return v_text
    days = int(serial)
    frac = serial - days
    base = _EPOCH + timedelta(days=days)
    seconds = round(frac * 86400)
    if seconds >= 86400:
        seconds = 0
        base = base + timedelta(days=1)
    hh, rem = divmod(seconds, 3600)
    mm, ss = divmod(rem, 60)
    if not want_time_only:
        # 纯日期格式：时间小数部分按显示格式丢弃（与 Excel 显示一致）
        return base.strftime("%Y-%m-%d")
    if days == 0:
        return "%02d:%02d:%02d" % (hh, mm, ss)
    return "%s %02d:%02d:%02d" % (base.strftime("%Y-%m-%d"), hh, mm, ss)


def _cell_display(c_el, shared, date_styles=None, style_idx=None):
    """单元格 → 显示文本。公式取缓存 v；字符串直取/取 shared；日期序列号转显示值。"""
    t = c_el.get("t")
    if t == "s":
        v = c_el.find(S("v"))
        if v is not None and v.text is not None:
            idx = int(v.text)
            if 0 <= idx < len(shared):
                return shared[idx]
        return ""
    if t == "inlineStr":
        is_el = c_el.find(S("is"))
        if is_el is not None:
            return "".join(x.text or "" for x in is_el.iter(S("t")))
        return ""
    v = c_el.find(S("v"))
    if v is None or v.text is None:
        return ""
    if t not in ("b", "e", "str") and date_styles is not None:
        fmt = date_styles.get(style_idx)
        if fmt is not None:
            kind, value = fmt
            if kind == "B":
                if value in (45, 46, 47, 32, 33):
                    return _serial_to_display(v.text, True)
                return _serial_to_display(v.text, False)
            # 自定义日期格式码：含 h/s 或纯时间 → 带时间；否则日期
            has_time = bool(re.search(r"[hs]", value, re.IGNORECASE))
            has_date = bool(re.search(r"[dy]", value, re.IGNORECASE))
            return _serial_to_display(v.text, has_time and not has_date)
    return v.text


def convert_xlsx(path):
    """xlsx → (md 行列表, 丢弃/留痕清单)。"""
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        date_styles = _numfmt_map(zf)
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_map = {}
        try:
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rels_root.findall("{%s}Relationship" % PKG_REL_NS):
                rels_map[rel.get("Id")] = rel.get("Target", "")
        except KeyError:
            pass
        lines = []
        drop_lines = []
        formula_total = 0
        merge_total = 0
        sheets = workbook.findall(f"{S('sheets')}/{S('sheet')}")
        if not sheets:
            raise ConversionError("xlsx 无可识别的工作表")
        for sheet in sheets:
            name = sheet.get("name", "Sheet")
            r_id = sheet.get("{%s}id" % REL_NS)
            target = (rels_map.get(r_id) or "").lstrip("/")
            rel_path = target if target.startswith("xl/") else "xl/" + target
            try:
                sheet_xml = zf.read(rel_path)
            except KeyError:
                raise ConversionError("无法定位工作表 %s 的 XML（%s）" % (name, rel_path))
            lines.append("## " + name)
            lines.append("")
            root = ET.fromstring(sheet_xml)
            merges_node = root.find(S("mergeCells"))
            merge_refs = [mc.get("ref", "") for mc in (merges_node or []) if mc.get("ref")]
            for ref in merge_refs:
                lines.append("<!-- [转换留痕] 合并单元格 %s：仅保留左上值 -->" % ref)
            merge_total += len(merge_refs)
            sheet_data = root.find(S("sheetData"))
            rows = []
            if sheet_data is not None:
                for row in sheet_data.findall(S("row")):
                    cells = {}
                    for c in row.findall(S("c")):
                        ref = c.get("r", "")
                        if not ref:
                            continue
                        if c.find(S("f")) is not None:
                            formula_total += 1
                        try:
                            style_idx = int(c.get("s", ""))
                        except ValueError:
                            style_idx = None
                        cells[_col_index(ref)] = _cell_display(
                            c, shared, date_styles, style_idx)
                    rows.append(cells)
            if not rows:
                lines.append("（无数据）")
                lines.append("")
                continue
            width = max(max(cells) + 1 for cells in rows if cells)
            header = [md_escape_cell(rows[0].get(i, "")) for i in range(width)]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "---|" * width)
            for cells in rows[1:]:
                lines.append("| " + " | ".join(
                    md_escape_cell(cells.get(i, "")) for i in range(width)) + " |")
            lines.append("")
        if formula_total:
            drop_lines.append("公式单元格取缓存计算值 %d 处" % formula_total)
        return lines, drop_lines


# ---------------------------------------------------------------------------
# md 产出包装（来源注记 + 丢弃清单 + 表格兼容自测）
# ---------------------------------------------------------------------------

def _mdtable_selfcheck(lines):
    """产出的第一张表必须能被 mdtable.py 解析（用下游真实消费者当验收标准）。"""
    text = "\n".join(lines)
    if "|" not in text:
        return
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import mdtable
    header, rows = mdtable.parse_first_table(text)
    if header is None:
        raise ConversionError("md 表格兼容性验收失败：mdtable 无法解析产出表格")


def render_md(rel_src, src_sha, lines, drop_lines):
    out = ["<!-- converted from: %s (sha256=%s) -->"
           % (rel_src.replace("\\", "/"), src_sha)]
    if drop_lines:
        out.append("<!-- 转换丢弃清单：")
        for d in drop_lines:
            out.append("     - %s" % d)
        out.append("-->")
    out.append("")
    out.extend(lines)
    return "\n".join(out) + "\n"


def convert_one(src_path, rel_src):
    """转换单个文件 → 完整 md 文本；失败抛 ConversionError（不产出）。"""
    ext = os.path.splitext(src_path)[1].lower()
    src_sha = sha256_file(src_path)
    if ext == ".docx":
        fn = convert_docx
    elif ext == ".xlsx":
        fn = convert_xlsx
    else:
        raise ConversionError("不支持的扩展名: %s" % ext)
    try:
        lines, drop_lines = fn(src_path)
    except ConversionError:
        raise
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError) as exc:
        raise ConversionError("源件非有效 %s（%s）" % (ext.lstrip("."), exc))
    _mdtable_selfcheck(lines + drop_lines)
    return render_md(rel_src, src_sha, lines, drop_lines)


def _output_rel(rel_src, input_dir):
    """同名 md，冠以来源目录名前缀：user-input/xxx.docx → user-input/xxx.md。

    前缀 = --input-dir 的目录名（跨多个被轻扫描的资料目录时，各来源的 rel 不可能
    互相重名，杜绝跨目录同名互踩）。来源内部子目录原样保留。
    """
    prefix = os.path.basename(os.path.normpath(input_dir))
    rel_dir, base = os.path.split(rel_src)
    md_name = os.path.splitext(base)[0] + ".md"
    parts = [p for p in (prefix, rel_dir, md_name) if p]
    return os.path.join(*parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="docx/xlsx → md 入库前转换")
    parser.add_argument("--input-dir", required=True, help="用户资料目录（只读）")
    parser.add_argument("--output-dir", required=True, help="转换产物目录（会话内）")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.input_dir):
        print("用法错误: 资料目录不存在 %s" % args.input_dir, file=sys.stderr)
        return 1
    os.makedirs(args.output_dir, exist_ok=True)
    targets = []
    for directory, _dirs, files in os.walk(args.input_dir):
        for name in sorted(files):
            if name.startswith(".") or name.startswith("~$"):
                continue
            if name.lower().endswith(OFFICE_EXTS):
                targets.append(os.path.join(directory, name))

    converted, skipped, failed = [], [], []
    for src in targets:
        rel = os.path.relpath(src, args.input_dir).replace(os.sep, "/")
        out_path = os.path.join(args.output_dir, _output_rel(rel, args.input_dir))
        src_sha = sha256_file(src)
        if os.path.exists(out_path):
            # 幂等跳过前防漂移：md 来源注记 sha 须与原件现 sha 一致，
            # 不一致说明原件已被替换，禁止静默沿用旧转换 → 拒绝并要求人工清档
            try:
                with open(out_path, encoding="utf-8") as stream:
                    head = stream.readline()
            except OSError as exc:
                failed.append(rel)
                print("FAIL %s: 转换区已有文件不可读（%s）" % (rel, exc), file=sys.stderr)
                continue
            m = re.search(r"sha256=([0-9a-fA-F]{64})", head)
            if m is None or m.group(1).lower() != src_sha.lower():
                failed.append(rel)
                print("FAIL %s: 转换区已存在同名 md 但来源指纹不符（原件已被替换），请人工清档后重跑"
                      % rel, file=sys.stderr)
                continue
            skipped.append(rel)
            continue
        try:
            text = convert_one(src, rel)
        except ConversionError as exc:
            failed.append(rel)
            print("FAIL %s: %s" % (rel, exc), file=sys.stderr)
            continue
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as stream:
            stream.write(text)
        converted.append(out_path)

    print("converted %d, skipped %d, failed %d"
          % (len(converted), len(skipped), len(failed)))
    for rel in converted:
        print("-> %s" % rel)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
