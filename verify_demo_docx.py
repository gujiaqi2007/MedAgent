from docx import Document

path = r"E:\MedAgent\docs\MedAgent_Demo_Script.docx"
d = Document(path)
paras = d.paragraphs
heads = [p.text for p in paras if p.style.name.startswith("Heading")]
text = "\n".join(p.text for p in paras)

print("paragraphs:", len(paras))
print("tables:", len(d.tables))
print("table_rows:", [len(t.rows) for t in d.tables])
print("headings:", len(heads))
for h in heads:
    print("  -", h)
print("first_para:", paras[0].text[:60])

checks = ["膝盖疼", "没有胸痛", "幺二零", "74 条", "退出登录", "SOS", "导出诊断凭据", "一句话卖点"]
for kw in checks:
    print("含", kw, ":", kw in text)
