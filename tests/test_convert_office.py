#!/usr/bin/env python3
"""test_convert_office.py — convert_office.py 的金样本契约回归。

金样本在测试内用 stdlib zipfile 现场构建（最小 OOXML），锁定七件事：
① docx 标题/段落/列表逐字保真；② 修订按定稿取字（ins 保留、del 剔除）；
③ 批注剔除且留痕登记；④ 图片留痕注记原位插入；⑤ 合并单元格只留左上值+注记；
⑥ xlsx 多 sheet/公式缓存值/日期文本；⑦ 幂等跳过、失败不落盘、文件头来源注记。
"""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT, ".opencode", "skill", "test-script-lib", "scripts", "convert_office.py")

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def make_docx(path):
    """最小 docx：标题+段落+列表+修订+批注+图片引用。"""
    body = (
        '<w:document xmlns:w="%s" xmlns:r="%s">'
        "<w:body>"
        # H1 标题
        "<w:p><w:pPr><w:pStyle w:val=\"p1\"/></w:pPr>"
        "<w:r><w:t>用户管理需求</w:t></w:r></w:p>"
        # 普通段落（含全角标点）
        "<w:p><w:r><w:t>用户注册需要：手机号，验证码，密码。</w:t></w:r></w:p>"
        # 修订：删除"旧逻辑" + 插入"新逻辑" → 定稿只留"新逻辑"
        "<w:p><w:ins w:id=\"1\"><w:r><w:t>新逻辑</w:t></w:r></w:ins>"
        "<w:del w:id=\"2\"><w:r><w:delText>旧逻辑</w:delText></w:r></w:del></w:p>"
        # 批注段
        "<w:p><w:commentRangeStart w:id=\"9\"/><w:r><w:t>正式文字保留</w:t></w:r>"
        "<w:commentRangeEnd w:id=\"9\"/></w:p>"
        # 列表段
        "<w:p><w:pPr><w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"1\"/></w:numPr></w:pPr>"
        "<w:r><w:t>第一步</w:t></w:r></w:p>"
        # 图片段
        "<w:p><w:drawing><wp:inline xmlns:wp=\"urn:x-drawing\"/></w:drawing></w:p>"
        "</w:body></w:document>" % (W, REL_NS)
    )
    styles = (
        '<w:styles xmlns:w="%s">'
        "<w:style w:styleId=\"p1\"><w:name w:val=\"Heading 1\"/></w:style>"
        "</w:styles>" % W
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", body)
        zf.writestr("word/styles.xml", styles)


def make_xlsx(path, two_sheets=True):
    """最小 xlsx：共享字符串 + 公式缓存值 + 合并单元格，可有两个 sheet。"""
    shared = (
        '<sst xmlns="%s" count="3" uniqueCount="3">'
        '<si><t>登录方式</t></si><si><t>手机验证码</t></si><si><t>邮箱验证</t></si>'
        "</sst>" % S
    )
    sheet1 = (
        '<worksheet xmlns="%s">'
        '<sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
        '<c r="C1" t="s"><v>2</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><f>SUM(1,2)</f><v>3</v></c>'
        '<c r="C2" t="d"><v>2026-11-09</v></c></row>'
        '</sheetData>'
        '<mergeCells count="1"><mergeCell ref="A2:B2"/></mergeCells>'
        "</worksheet>" % S
    )
    sheet2 = (
        '<worksheet xmlns="%s"><sheetData><row r="1"><c r="A1" t="s"><v>2</v></c></row>'
        "</sheetData></worksheet>" % S
    )
    if two_sheets:
        wb = (
            '<workbook xmlns="%s" xmlns:r="%s">'
            '<sheets>'
            '<sheet name="字段定义" r:id="rId1"/>'
            '<sheet name="辅助表" r:id="rId2"/>'
            '</sheets></workbook>' % (S, REL_NS)
        )
        rels = (
            '<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
            "</Relationships>" % PKG_REL_NS
        )
    else:
        wb = (
            '<workbook xmlns="%s" xmlns:r="%s">'
            '<sheets><sheet name="字段定义" r:id="rId1"/></sheets></workbook>' % (S, REL_NS)
        )
        rels = (
            '<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>" % PKG_REL_NS
        )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet1)
        if two_sheets:
            zf.writestr("xl/worksheets/sheet2.xml", sheet2)


class TestConvertOffice(unittest.TestCase):
    def make_dirs(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return d.name

    def out_md(self, root, out_base, name):
        """转换产物路径：转换区/<来源目录名>/<原名>.md（防跨目录同名互踩）。"""
        return os.path.join(root, out_base, os.path.basename(root), name + ".md")

    # -- docx ----------------------------------------------------------------

    def test_docx_headings_and_text_literal(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "PRD.docx"))
        out = self.out_md(root, "converted", "PRD")
        result = run("--input-dir", root, "--output-dir", os.path.join(root, "converted"))
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("# 用户管理需求", md)
        self.assertIn("用户注册需要：手机号，验证码，密码。", md)

    def test_docx_revision_final_text(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "a"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("新逻辑", md)
        self.assertNotIn("旧逻辑", md)

    def test_docx_comment_dropped_but_text_kept(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "a"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("正式文字保留", md)
        self.assertIn("批注剔除", md)

    def test_docx_list_and_drawing_note(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "a"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("- 第一步", md)
        self.assertIn("[转换留痕] 此处原文有图片（未转换）", md)

    def test_docx_table_and_merge_note(self):
        root = self.make_dirs()
        path = os.path.join(root, "t.docx")
        grid = (
            '<w:tbl xmlns:w="%s"><w:tr><w:tc><w:p><w:r><w:t>字段</w:t></w:r></w:p></w:tc>'
            "<w:tc><w:p><w:r><w:t>规则</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:tcPr><w:vMerge w:val=\"continue\"/></w:tcPr>"
            "<w:p/></w:tc><w:tc><w:p><w:r><w:t>必填</w:t></w:r></w:p></w:tc></w:tr></w:tbl>" % W
        )
        doc = "<w:document xmlns:w=\"%s\"><w:body>%s</w:body></w:document>" % (W, grid)
        styles = '<w:styles xmlns:w="%s"/>' % W
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml", doc)
            zf.writestr("word/styles.xml", styles)
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "t"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| 字段 | 规则 |", md)
        self.assertIn("合并单元格占位，仅保留左上值", md)
        self.assertIn("| [留痕:合并单元格] | 必填 |", md)

    def test_docx_source_note_in_header(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "a"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("converted from: a.docx (sha256=", md)

    # -- xlsx ----------------------------------------------------------------

    def test_xlsx_two_sheets_and_values(self):
        root = self.make_dirs()
        make_xlsx(os.path.join(root, "字段表.xlsx"))
        out = self.out_md(root, "converted", "字段表")
        run("--input-dir", root, "--output-dir", os.path.join(root, "converted"))
        self.assertTrue(os.path.exists(out))
        with open(out, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("## 字段定义", md)
        self.assertIn("## 辅助表", md)
        self.assertIn("| 登录方式 | 手机验证码 | 邮箱验证 |", md)
        # 合并 A2:B2 → 只保留左上值（A2 的"手机验证码"），B2 缓存值照常渲染
        self.assertIn("| 手机验证码 | 3 | 2026-11-09 |", md)

    def test_xlsx_formula_cached_value_and_note(self):
        root = self.make_dirs()
        make_xlsx(os.path.join(root, "f.xlsx"), two_sheets=False)
        out = self.out_md(root, "c", "f")
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(out, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| 3 |", md)
        self.assertNotIn("SUM", md)
        with open(out, encoding="utf-8") as f:
            header = f.read()
        self.assertTrue(header.startswith("<!-- converted from: f.xlsx (sha256="))

    def test_xlsx_merge_note_for_mergecells(self):
        root = self.make_dirs()
        make_xlsx(os.path.join(root, "m.xlsx"), two_sheets=False)
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "m"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("合并单元格 A2:B2：仅保留左上值", md)

    # -- 通用行为 -------------------------------------------------------------

    def test_xlsx_builtin_date_serial_becomes_display_value(self):
        root = self.make_dirs()
        path = os.path.join(root, "d.xlsx")
        sheet = (
            '<worksheet xmlns="%s"><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
            '<row r="2"><c r="A2" s="0"><v>45678</v></c><c r="B2" s="0"><v>45678.75</v></c></row>'
            '</sheetData></worksheet>' % S
        )
        styles = (
            '<styleSheet xmlns="%s">'
            '<cellXfs count="1"><xf numFmtId="14"/></cellXfs>'
            "</styleSheet>" % S
        )
        wb = (
            '<workbook xmlns="%s" xmlns:r="%s">'
            '<sheets><sheet name="S1" r:id="rId1"/></sheets></workbook>' % (S, REL_NS)
        )
        rels = (
            '<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>" % PKG_REL_NS
        )
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("xl/worksheets/sheet1.xml", sheet)
            zf.writestr("xl/styles.xml", styles)
            zf.writestr("xl/workbook.xml", wb)
            zf.writestr("xl/_rels/workbook.xml.rels", rels)
            zf.writestr("xl/sharedStrings.xml", '<sst xmlns="%s"><si><t>日期</t></si></sst>' % S)
        run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        with open(self.out_md(root, "c", "d"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| 日期 |  |", md)
        # 内置 14 格式 → 日期序列号按显示值转换（时间小数不显示，与格式一致）
        self.assertIn("| 2025-01-21 | 2025-01-21 |", md)
        self.assertNotIn("| 45678 |", md)

    def test_staleness_guard_rejects_replaced_source(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        out_dir = os.path.join(root, "c")
        first = run("--input-dir", root, "--output-dir", out_dir)
        self.assertEqual(first.returncode, 0)
        # 原件内容被替换（同名新 docx）→ 重跑必须 FAIL 且不覆盖旧 md
        with zipfile.ZipFile(os.path.join(root, "a.docx"), "w") as zf:
            zf.writestr("word/document.xml",
                        '<w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>换了内容</w:t>'
                        "</w:r></w:p></w:body></w:document>" % W)
        with open(os.path.join(out_dir, os.path.basename(root), "a.md"), encoding="utf-8") as f:
            before = f.read()
        second = run("--input-dir", root, "--output-dir", out_dir)
        self.assertEqual(second.returncode, 2)
        self.assertIn("来源指纹不符", second.stderr)
        with open(os.path.join(out_dir, os.path.basename(root), "a.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def test_idempotent_skip(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        out_dir = os.path.join(root, "c")
        first = run("--input-dir", root, "--output-dir", out_dir)
        self.assertEqual(first.returncode, 0)
        out_path = self.out_md(root, out_dir, "a")
        with open(out_path, encoding="utf-8") as f:
            first_text = f.read()
        second = run("--input-dir", root, "--output-dir", out_dir)
        self.assertEqual(second.returncode, 0)
        self.assertIn("skipped 1", second.stdout)
        with open(out_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), first_text)

    def test_subdir_separated_same_name(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        sub = os.path.join(root, "project-docs")
        os.makedirs(sub)
        make_docx(os.path.join(sub, "a.docx"))
        result = run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(self.out_md(root, "c", "a")))
        self.assertTrue(os.path.exists(os.path.join(root, "c", os.path.basename(root), "project-docs", "a.md")))

    def test_failure_no_output_and_exit_code(self):
        root = self.make_dirs()
        bad = os.path.join(root, "bad.docx")
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("broken", "not xml")
        result = run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(root, "c", "bad.md")))

    def test_non_text_and_temp_files_ignored(self):
        root = self.make_dirs()
        make_docx(os.path.join(root, "a.docx"))
        with open(os.path.join(root, "~$a.docx"), "w", encoding="utf-8") as f:
            f.write("temp")
        result = run("--input-dir", root, "--output-dir", os.path.join(root, "c"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count("-> "), 1)

    def test_mdtable_parses_output_tables(self):
        root = self.make_dirs()
        make_xlsx(os.path.join(root, "字段表.xlsx"))
        out = self.out_md(root, "converted", "字段表")
        run("--input-dir", root, "--output-dir", os.path.join(root, "converted"))
        lib_dir = os.path.join(ROOT, ".opencode", "skill", "test-script-lib", "scripts")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import mdtable
        with open(out, encoding="utf-8") as f:
            text = f.read()
        header, rows = mdtable.parse_first_table(text)
        self.assertEqual(header, ["登录方式", "手机验证码", "邮箱验证"])
        self.assertEqual(rows[0], ["手机验证码", "3", "2026-11-09"])


if __name__ == "__main__":
    unittest.main()
