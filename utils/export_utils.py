"""
试卷导出工具：
- Markdown 解析（图片、表格、段落）
- Word 导出（python-docx，含中文字体、图片、表格）
- PDF 导出（fpdf2，含中文字体、图片、表格）

题目内容是 Markdown 格式，可能包含：
  - 图片：![alt](path)
  - 表格：| col | col | + | --- | --- |
  - 普通段落文本
不含 LaTeX / HTML 标签（已通过数据扫描确认）。
"""

import os
import re
import io
from typing import List, Tuple, Optional

from PIL import Image

# ============================================================
# Markdown 解析：把一段 Markdown 拆成有序的"块"序列
# 块类型：
#   ("text", str)           —— 普通文本段落（可能含多行）
#   ("image", path)         —— 图片（本地路径）
#   ("table", rows)         —— 表格，rows 是 list[list[str]]，第一行是表头
# ============================================================

IMAGE_PATTERN = re.compile(r"!\[.*?\]\((.*?)\)")


def _is_table_separator(line: str) -> bool:
    """判断是否是 Markdown 表格分隔行 | --- | --- |"""
    s = line.strip()
    if not s.startswith("|") or not s.endswith("|"):
        return False
    # 去掉首尾 |，按 | 分割，每段应只含 -、:、空格
    inner = s.strip("|")
    cells = inner.split("|")
    for c in cells:
        if not re.fullmatch(r"\s*:?-+:?\s*", c):
            return False
    return True


def _parse_table_row(line: str) -> List[str]:
    """解析一行表格 | a | b | c | → ['a', 'b', 'c']"""
    s = line.strip()
    # 去掉首尾 |
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_markdown_blocks(text: str) -> List[Tuple[str, object]]:
    """
    把 Markdown 文本解析成块序列。
    返回 [("text", str) | ("image", path) | ("table", rows), ...]
    """
    if not text:
        return []

    blocks: List[Tuple[str, object]] = []
    lines = text.split("\n")

    text_buffer: List[str] = []
    table_buffer: List[List[str]] = []
    in_table = False

    def flush_text():
        if text_buffer:
            # 合并连续非空行，保留空行作为段落分隔
            joined = "\n".join(text_buffer).strip()
            if joined:
                blocks.append(("text", joined))
            text_buffer.clear()

    def flush_table():
        nonlocal table_buffer, in_table
        if table_buffer:
            blocks.append(("table", table_buffer))
            table_buffer = []
        in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # 图片行（整行就是一张图片）
        m = IMAGE_PATTERN.search(line)
        if m and line.strip().startswith("!["):
            flush_text()
            img_path = m.group(1).strip()
            blocks.append(("image", img_path))
            i += 1
            continue

        # 表格起始：当前行以 | 开头，下一行是分隔行
        if line.strip().startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            flush_text()
            in_table = True
            table_buffer.append(_parse_table_row(line))
            i += 1  # 跳过表头行
            i += 1  # 跳过分隔行
            # 继续读表格数据行
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_buffer.append(_parse_table_row(lines[i]))
                i += 1
            flush_table()
            continue

        # 普通文本行
        text_buffer.append(line)
        i += 1

    flush_text()
    flush_table()
    return blocks


# ============================================================
# 图片处理：安全加载、缺失容错、获取尺寸
# ============================================================

def _resolve_image(path: str) -> Optional[str]:
    """把题目里的图片路径解析成绝对路径，不存在返回 None。"""
    if not path:
        return None
    if os.path.isabs(path) and os.path.exists(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    return None


# ============================================================
# Word 导出（python-docx）
# ============================================================

def _set_cell_text(cell, text: str):
    """设置 Word 表格单元格文本（清空原有内容）。"""
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)


def export_to_word(
    questions: List[dict],
    paper_title: str,
    include_answer: bool = True,
    include_analysis: bool = True,
    include_source: bool = True,
) -> bytes:
    """
    把一套试卷的题目导出为 Word 文档，返回二进制内容。
    questions: list[dict]，每个 dict 含 content/answer/analysis/source/analysis_source/question_no 等字段
    paper_title: 试卷标题，如 "2025 北京卷"
    """
    from docx import Document
    from docx.shared import Pt, Inches, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn

    doc = Document()

    # 设置默认中文字体（宋体）
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    # 设置中文字体需要操作 XML
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        from docx.oxml import OxmlElement
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), "宋体")

    # 标题
    title_p = doc.add_heading(paper_title, level=0)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info_p = doc.add_paragraph()
    info_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info_run = info_p.add_run(f"共 {len(questions)} 道题")
    info_run.font.size = Pt(10)

    doc.add_paragraph()  # 空行

    for idx, q in enumerate(questions, 1):
        qno = q.get("question_no") or str(idx)
        content = q.get("content") or ""
        answer = q.get("answer") or ""
        analysis = q.get("analysis") or ""
        source = q.get("source") or ""
        analysis_source = q.get("analysis_source") or ""

        # 题号标题
        h = doc.add_heading(f"第 {qno} 题", level=1)

        # 题目内容
        _render_blocks_to_word(doc, content)

        # 答案
        if include_answer and answer:
            doc.add_heading("【答案】", level=2)
            _render_blocks_to_word(doc, answer)

        # 解析
        if include_analysis and analysis:
            doc.add_heading("【解析】", level=2)
            _render_blocks_to_word(doc, analysis)

        # 来源
        if include_source:
            src_parts = []
            if source:
                src_parts.append(f"题目来源：{source}")
            if analysis_source and analysis_source != source:
                src_parts.append(f"解析来源：{analysis_source}")
            if src_parts:
                p = doc.add_paragraph()
                run = p.add_run("；".join(src_parts))
                run.font.size = Pt(9)
                run.italic = True

        # 题目间分隔
        if idx < len(questions):
            doc.add_paragraph()

    # 序列化成 bytes
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _render_blocks_to_word(doc, text: str):
    """把 Markdown 文本解析成块并写入 Word 文档。"""
    from docx.shared import Inches, Pt
    from docx.enum.table import WD_TABLE_ALIGNMENT

    blocks = parse_markdown_blocks(text)
    for kind, payload in blocks:
        if kind == "text":
            # 按空行分段
            for para in re.split(r"\n\s*\n", payload):
                para = para.strip()
                if para:
                    # 单行内的 \n 转成空格，避免 Word 里出现硬换行
                    para = para.replace("\n", " ")
                    p = doc.add_paragraph(para)

        elif kind == "image":
            abs_path = _resolve_image(payload)
            if abs_path:
                try:
                    # 限制图片宽度，避免超大图撑爆页面
                    doc.add_picture(abs_path, width=Inches(5.5))
                except Exception:
                    doc.add_paragraph(f"[图片加载失败：{payload}]")
            else:
                doc.add_paragraph(f"[图片缺失：{payload}]")

        elif kind == "table":
            rows = payload
            if not rows:
                continue
            n_cols = max(len(r) for r in rows)
            # 补齐每行列数
            rows = [r + [""] * (n_cols - len(r)) for r in rows]
            table = doc.add_table(rows=len(rows), cols=n_cols, style="Table Grid")
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for ri, row in enumerate(rows):
                for ci, cell_text in enumerate(row):
                    _set_cell_text(table.cell(ri, ci), cell_text)
            doc.add_paragraph()  # 表格后空行


# ============================================================
# PDF 导出（fpdf2）
# ============================================================

# fpdf2 中文字体：用 Unicode TrueType，需要系统字体文件。
# macOS 自带 PingFang / STHeiti；Linux 常见 Noto CJK。
# 我们按优先级查找一个可用的 CJK 字体。
_CJK_FONT_CANDIDATES = [
    # (字体显示名, 文件路径)
    # macOS
    ("PingFang", "/System/Library/Fonts/PingFang.ttc"),
    ("STHeiti", "/System/Library/Fonts/STHeiti Medium.ttc"),
    ("HiraginoSansGB", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
    # Linux Noto CJK（各发行版路径不同）
    ("NotoSansCJK", "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),  # RHEL/Alibaba Cloud Linux
    ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),    # Debian/Ubuntu
    ("NotoSansCJK", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),    # 其他
    # 文泉驿
    ("WenQuanYi", "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc"),
]


def _find_cjk_font() -> Tuple[str, str]:
    """返回 (字体名, 字体文件路径)，找不到抛异常。"""
    for name, path in _CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            return name, path
    raise RuntimeError(
        "未找到可用的中文字体。请安装 Noto CJK 或 PingFang 等中文字体。"
    )


def export_to_pdf(
    questions: List[dict],
    paper_title: str,
    include_answer: bool = True,
    include_analysis: bool = True,
    include_source: bool = True,
) -> bytes:
    """
    把一套试卷的题目导出为 PDF，返回二进制内容。
    """
    from fpdf import FPDF

    font_name, font_path = _find_cjk_font()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font(font_name, fname=font_path)
    pdf.set_font(font_name, size=11)

    # fpdf2 的 multi_cell 默认会把光标移到右侧，必须显式指定
    # new_x="LMARGIN", new_y="NEXT"，否则后续写入会报
    # "Not enough horizontal space to render a single character"
    MC_KW = dict(new_x="LMARGIN", new_y="NEXT")

    # 标题
    pdf.set_font_size(20)
    pdf.multi_cell(0, 12, paper_title, align="C", **MC_KW)
    pdf.ln(2)
    pdf.set_font_size(10)
    pdf.multi_cell(0, 8, f"共 {len(questions)} 道题", align="C", **MC_KW)
    pdf.ln(4)

    for idx, q in enumerate(questions, 1):
        qno = q.get("question_no") or str(idx)
        content = q.get("content") or ""
        answer = q.get("answer") or ""
        analysis = q.get("analysis") or ""
        source = q.get("source") or ""
        analysis_source = q.get("analysis_source") or ""

        # 题号
        pdf.set_font_size(14)
        pdf.multi_cell(0, 10, f"第 {qno} 题", **MC_KW)
        pdf.ln(1)
        pdf.set_font_size(11)

        # 题目内容
        _render_blocks_to_pdf(pdf, content, font_name)

        # 答案
        if include_answer and answer:
            pdf.ln(2)
            pdf.set_font_size(12)
            pdf.multi_cell(0, 9, "【答案】", **MC_KW)
            pdf.set_font_size(11)
            _render_blocks_to_pdf(pdf, answer, font_name)

        # 解析
        if include_analysis and analysis:
            pdf.ln(2)
            pdf.set_font_size(12)
            pdf.multi_cell(0, 9, "【解析】", **MC_KW)
            pdf.set_font_size(11)
            _render_blocks_to_pdf(pdf, analysis, font_name)

        # 来源
        if include_source:
            src_parts = []
            if source:
                src_parts.append(f"题目来源：{source}")
            if analysis_source and analysis_source != source:
                src_parts.append(f"解析来源：{analysis_source}")
            if src_parts:
                pdf.ln(1)
                pdf.set_font_size(9)
                pdf.multi_cell(0, 6, "；".join(src_parts), **MC_KW)
                pdf.set_font_size(11)

        # 题间空行
        pdf.ln(4)

    return pdf.output()


def _render_blocks_to_pdf(pdf, text: str, font_name: str):
    """把 Markdown 文本解析成块并写入 PDF。"""
    blocks = parse_markdown_blocks(text)
    page_width = pdf.w - 2 * pdf.l_margin  # 可用宽度
    MC_KW = dict(new_x="LMARGIN", new_y="NEXT")

    for kind, payload in blocks:
        if kind == "text":
            for para in re.split(r"\n\s*\n", payload):
                para = para.strip()
                if para:
                    para = para.replace("\n", " ")
                    pdf.multi_cell(0, 7, para, **MC_KW)

        elif kind == "image":
            abs_path = _resolve_image(payload)
            if abs_path:
                try:
                    # 计算合适的图片宽度（不超过页面可用宽度）
                    with Image.open(abs_path) as im:
                        w_px, h_px = im.size
                    # 转成 mm：假设 96 DPI
                    w_mm = w_px * 25.4 / 96.0
                    if w_mm > page_width:
                        w_mm = page_width
                    pdf.image(abs_path, w=w_mm)
                    pdf.ln(2)
                except Exception:
                    pdf.multi_cell(0, 7, f"[图片加载失败：{payload}]", **MC_KW)
            else:
                pdf.multi_cell(0, 7, f"[图片缺失：{payload}]", **MC_KW)

        elif kind == "table":
            rows = payload
            if not rows:
                continue
            n_cols = max(len(r) for r in rows)
            rows = [r + [""] * (n_cols - len(r)) for r in rows]
            # 用 fpdf2 2.8+ 内置的 table 上下文管理器
            try:
                with pdf.table() as table:
                    for row in rows:
                        row_obj = table.row()
                        for cell_text in row:
                            row_obj.cell(cell_text)
            except Exception:
                # 降级：逐行用 | 分隔的纯文本
                for row in rows:
                    pdf.multi_cell(0, 7, " | ".join(row), border=1, **MC_KW)
            pdf.ln(2)
