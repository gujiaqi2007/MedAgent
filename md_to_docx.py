"""把 Markdown 转成排版好的 Word 文档。

用法：python md_to_docx.py [输入.md] [输出.docx]
"""
import re
import sys

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.oxml.ns import qn

FONT = "微软雅黑"
SRC = sys.argv[1] if len(sys.argv) > 1 else r"E:\MedAgent\docs\DEMO_SCRIPT.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"E:\MedAgent\docs\MedAgent_Demo_Script.docx"
BLUE = (0x1A, 0x73, 0xE8)
DARK = (0x1F, 0x2D, 0x3D)
GRAY = (0x6B, 0x7A, 0x8D)


def cjk(run, size=10.5, bold=False, color=None):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)


def add_inline(p, text, size=10.5, color=None):
    for part in re.split(r"(\*\*.+?\*\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            cjk(p.add_run(part[2:-2]), size=size, bold=True, color=color)
        else:
            cjk(p.add_run(part), size=size, color=color)


doc = Document()
st = doc.styles["Normal"]
st.font.name = FONT
st.font.size = Pt(10.5)
st.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)

lines = open(SRC, encoding="utf-8").read().splitlines()
i = 0
first_quote = True

while i < len(lines):
    s = lines[i].strip()
    if not s:
        i += 1
        continue

    if s.startswith("```"):
        i += 1
        code_lines = []
        while i < len(lines) and not lines[i].strip().startswith("```"):
            code_lines.append(lines[i])
            i += 1
        i += 1
        for cl in code_lines:
            cp = doc.add_paragraph()
            run = cp.add_run(cl)
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
            cp.paragraph_format.left_indent = Cm(0.4)
            cp.paragraph_format.space_after = Pt(0)
        continue
    if s.startswith("# "):
        p = doc.add_paragraph()
        p.alignment = 1
        cjk(p.add_run(s[2:]), size=22, bold=True, color=DARK)
        p.paragraph_format.space_after = Pt(2)
    elif s.startswith("### "):
        h = doc.add_heading(level=2)
        cjk(h.add_run(s[4:]), size=13, bold=True, color=DARK)
        h.paragraph_format.space_before = Pt(10)
        h.paragraph_format.space_after = Pt(4)
    elif s.startswith("## "):
        h = doc.add_heading(level=1)
        cjk(h.add_run(s[3:]), size=16, bold=True, color=DARK)
        h.paragraph_format.space_before = Pt(14)
        h.paragraph_format.space_after = Pt(6)
    elif s.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(lines[i].strip())
            i += 1
        data = []
        for r in rows:
            cells = [c.strip() for c in r.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            data.append(cells)
        if data:
            t = doc.add_table(rows=0, cols=len(data[0]))
            t.style = "Table Grid"
            for ri, row in enumerate(data):
                cells = t.add_row().cells
                for ci, val in enumerate(row):
                    cells[ci].text = ""
                    add_inline(cells[ci].paragraphs[0], val, size=10)
                    if ri == 0:
                        for run in cells[ci].paragraphs[0].runs:
                            run.bold = True
        continue
    elif s.startswith("> "):
        p = doc.add_paragraph()
        if first_quote:
            p.alignment = 1
            cjk(p.add_run(s[2:]), size=10, color=GRAY)
            first_quote = False
        else:
            add_inline(p, s[2:], size=10.5)
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_after = Pt(6)
    elif s.startswith("- [ ] "):
        p = doc.add_paragraph()
        cjk(p.add_run("☐ " + s[6:]), size=10.5)
        p.paragraph_format.space_after = Pt(3)
    elif s.startswith("- "):
        p = doc.add_paragraph(style="List Bullet")
        add_inline(p, s[2:], size=10.5)
        p.paragraph_format.space_after = Pt(2)
    elif re.match(r"^\d+\.\s", s):
        p = doc.add_paragraph()
        add_inline(p, s, size=10.5)
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_after = Pt(2)
    elif s.startswith("**【"):
        m = re.match(r"^(\*\*.+?\*\*)\s*(.*)$", s)
        p = doc.add_paragraph()
        cjk(p.add_run(m.group(1)[2:-2]), size=10.5, bold=True, color=BLUE)
        if m.group(2):
            p.add_run(" ")
            add_inline(p, m.group(2), size=10.5)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
    else:
        p = doc.add_paragraph()
        add_inline(p, s, size=10.5)
        p.paragraph_format.space_after = Pt(6)
    i += 1

doc.save(OUT)
print("saved", OUT)
